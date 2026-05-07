# app/services/owner_entity_writer.py
# Branch: v5-whatsapp
# Iteration: v6.3.17 (WhatsApp Natural-Language Entity Edits)
#
# FILE PURPOSE
# Owner-bypass direct-write path for WhatsApp entity creation. When a
# top-tier role (proprietor / owner / factory_manager / co_owner) sends
# a message containing an explicit creation verb plus an entity name,
# this module parses the intent heuristically, fuzzy-matches against
# existing entities to skip duplicates, and writes the new row with
# source='whatsapp_owner' — bypassing the v6.3.14 extractor confidence
# threshold and the v6.3.15 nightly confirmation cycle. Manager and
# operator messages, plus any phrasing without an explicit creation
# verb, fall through to the existing extractor path unchanged.
#
# WHO CALLS THIS FILE
# - app/routers/whatsapp.py — `_process_inbound_message` calls
#   `evaluate_and_write` after the role-blocked early-return and
#   before the existing `if action_type is not None` confirmation
#   loop. A non-None return short-circuits the rest of the pipeline
#   (no AI, no extractor schedule).
# - tests/services/test_owner_entity_writer.py — exercises the
#   detector, the four writers, the role gate, and the audit event.
#
# WHAT THIS FILE CALLS
# - app/services/promotion/fuzzy_match.fuzzy_best_match — idempotency
#   check before every insert.
# - app/models.{employee.Employee, employee.EmployeeSkill,
#   machine.Machine, skill.Skill, event.Event} — ORM writes.
# - app/services/whatsapp_responses (no — replies composed inline).
# - sqlalchemy ORM read queries; one row insert per write call.
#
# KEY DESIGN DECISIONS
# - Heuristic-only intent detection (Q1 approval). Tight verb-required
#   regex: a message must contain BOTH a creation verb AND an entity
#   name to trigger. The detector errs toward false negatives — a
#   missed create falls through to the v6.3.14 extractor and surfaces
#   later via the v6.3.15 confirmation cycle, which is fine. False
#   positives (accidental writes) are not.
# - source='whatsapp_owner' (Q2 approval) distinguishes these writes
#   from manager-typed ('whatsapp') and bot-promoted ('whatsapp_
#   inferred') rows. Added to VALID_SOURCE_VALUES in v6.3.17.
# - Skill rows now carry the same source column (Q3, migration 032).
# - EmployeeSkill (join) does NOT carry provenance (Q4); the audit
#   event is the audit trail.
# - One audit event type — entity.owner_added (Q5) — covers all four
#   write paths. parse_strategy='heuristic' so v6.4.x can introduce
#   a hybrid LLM-assisted path without breaking the payload schema.
# - Idempotency via app.services.promotion.fuzzy_match.fuzzy_best_match
#   with the same PROMOTION_FUZZY_MATCH_THRESHOLD (85) the v6.3.15
#   promoter uses. A match short-circuits with an "already exists"
#   reply — no insert, no audit event, only a debug log.
# - The role gate is enforced strictly here (NOT relying on the
#   existing detect_write_intent role gate). NULL phone_role and
#   unknown phone_role values default to DENY — they fall through
#   to the existing extractor path. Only the four explicit top-tier
#   strings trigger the bypass.
# - Reply text is romanised Hindi/Hinglish by default, matching the
#   existing dispatcher convention (see briefings/templates.py and
#   the existing whatsapp_responses module).
#
# FORWARD-COMPAT
# - v6.3.18 message formatter pass will standardise the reply tone.
#   Until then, the replies here use the same plain-text Hinglish
#   style as the rest of the WhatsApp surface.
# - v6.4.x may evolve the heuristic to a hybrid (heuristic + LLM
#   fallback for ambiguous messages). The OwnerCreateIntent dataclass
#   shape and the entity.owner_added event payload (with
#   parse_strategy='heuristic') are designed to absorb that change
#   without breaking consumers.
# - DELETE / UPDATE / bulk-add paths are intentionally NOT in this
#   module — they have stronger audit / confirmation requirements
#   and live in a future version.

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import TOP_TIER_ROLES
from app.models.employee import Employee, EmployeeSkill, VALID_SOURCE_VALUES
from app.models.event import Event
from app.models.machine import Machine
from app.models.skill import Skill
from app.services.promotion.fuzzy_match import fuzzy_best_match

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

# The source value written into the entity tables when this module
# performs a direct write. Distinguishes owner-asserted rows from
# manager-typed ('whatsapp') and bot-promoted ('whatsapp_inferred')
# rows. Added to VALID_SOURCE_VALUES in v6.3.17.
SOURCE_VALUE: str = "whatsapp_owner"
assert SOURCE_VALUE in VALID_SOURCE_VALUES, (
    "SOURCE_VALUE must be in VALID_SOURCE_VALUES — see app/models/employee.py"
)

# Audit event type for every successful write. Namespace 'entity.*' is
# new in v6.3.17 and reserved for owner-asserted entity provenance.
EVENT_OWNER_ADDED: str = "entity.owner_added"

# Strategy identifier for the audit event payload. v6.4.x may add
# 'heuristic+llm' or 'llm' values without payload schema break.
PARSE_STRATEGY_HEURISTIC: str = "heuristic"

# Top-tier set as a frozenset for fast membership testing. Mirrors
# whatsapp_intent.PHONE_TOP_TIER_ROLES — both reference the canonical
# TOP_TIER_ROLES tuple from app.models.auth so a role rename flows
# through every gate automatically.
PHONE_TOP_TIER_ROLES: frozenset[str] = frozenset(TOP_TIER_ROLES)


# ---------------------------------------------------------------------------
# Heuristic vocabulary — TIGHT
# ---------------------------------------------------------------------------
# CREATION_VERBS: imperative forms only. A message MUST contain at
# least one of these phrases (matched as a word-boundary substring on
# the lowercased message) to qualify as a create intent. Pure
# entity-noun mentions or implicit references must NOT trigger.
#
# False-positive risk audit:
#   - "add karo / add kar do / add kardo / add kar" — clear imperative.
#   - "banao / bana do / banaado" — "make/create" imperative. The
#     past-tense "banaya" / "ban gaya" is NOT here so descriptions
#     ("Mukesh ne banaya hai") cannot trigger.
#   - "jodo / jod do" — "join/connect" imperative. Used in
#     "Mukesh ko team mein jodo".
#   - "daalo / daal do" — "put in" imperative.
#   - "register karo / register kar do" — explicit register verb.
#   - "create" — English imperative. Bare. Past tense "created" is
#     NOT here.
#   - "add" alone is NOT a creation verb — it must combine with
#     "kar/karo/kar do" or be followed by a name+role. Ambiguity
#     between "Mukesh ko add kar do" (create) and "Mukesh ko file
#     add kar do" (assign file) is resolved by the entity-noun
#     requirement: only when an employee/machine/skill clue word is
#     present do we proceed.
#
# All phrases are lowercase. Detector lowercases the message before
# scanning. Word boundaries handled by the regex pattern below.
CREATION_VERB_PHRASES: tuple[str, ...] = (
    "add karo", "add kar do", "add kardo", "add kar",
    "banao", "bana do", "banaado",
    "jodo", "jod do",
    "daalo", "daal do",
    "register karo", "register kar do",
    "create",
)

# Compiled once at import. Word-boundary anchored on both sides so
# "addressing" doesn't match "add" and "creature" doesn't match
# "create".
_CREATION_VERB_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in CREATION_VERB_PHRASES) + r")\b",
    flags=re.IGNORECASE,
)

# Entity-noun clues. Presence of one (or more) is REQUIRED in addition
# to a creation verb. Categories shown for human readers; the matcher
# treats them as a single set.
EMPLOYEE_CLUES: frozenset[str] = frozenset([
    # Role nouns (commonly used as skill names too).
    "welder", "operator", "fitter", "technician", "helper", "labour",
    "labor", "worker", "employee", "karigar", "mistri", "mason",
    "machinist", "electrician", "painter", "carpenter",
    # The literal word "person" / "aadmi" used by some owners.
    "aadmi", "person",
])
MACHINE_CLUES: frozenset[str] = frozenset([
    "machine", "press", "reactor", "asset", "equipment", "tool",
])
SKILL_CLUES: frozenset[str] = frozenset([
    "skill", "skills",
])
LINK_CLUES: frozenset[str] = frozenset([
    # Phrases that suggest "give X this skill" rather than "create X".
    "skills mein", "skills me", "skill mein", "skill me",
])

# Stop words filtered from name candidates.
NAME_STOPWORDS: frozenset[str] = frozenset([
    "naya", "nayi", "naye", "ek", "aur", "hai", "hain", "ka", "ki",
    "ke", "ko", "se", "mein", "me", "ho", "gaya", "gayi", "yeh", "ye",
    "wo", "woh", "the", "that", "this", "and", "or", "is", "are",
    "with", "for", "to", "in", "on", "of", "a", "an", "an",
    "add", "addo", "kar", "karo", "kardo", "do", "kardiya", "kardiyo",
    "banao", "banaado", "bana", "register", "create", "jodo", "jod",
    "daalo", "daal",
    # Entity-type words must not be picked as names.
    "employee", "machine", "skill", "skills", "welder", "operator",
    "fitter", "technician", "helper", "labour", "labor", "worker",
    "press", "reactor", "asset", "equipment", "tool", "karigar",
    "mistri", "mason", "machinist", "electrician", "painter",
    "carpenter", "aadmi", "person", "naam", "name",
])


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class OwnerCreateIntent:
    """Parsed intent from an owner-create message.

    Used by:
        Detector returns this to the dispatcher. The dispatcher then
        invokes the appropriate writer based on `kind`.

    Fields:
        kind:           One of 'employee' | 'machine' | 'skill' |
                        'link_employee_skill'. Drives the writer choice.
        name:           Primary entity name (the thing being created).
                        For link_employee_skill this is the skill name.
        skill_hint:     Only set when kind='employee' and the message
                        also names a skill ("naya welder hai - Mukesh");
                        the writer attempts to link the new employee
                        to that skill after the insert.
        employee_name:  Only set when kind='link_employee_skill'.
        raw_message:    Verbatim original message text. Goes into the
                        audit event payload so post-hoc review can see
                        exactly what the owner typed.
    """
    kind:          str
    name:          str
    skill_hint:    Optional[str] = None
    employee_name: Optional[str] = None
    raw_message:   str = ""


@dataclass
class WriteOutcome:
    """Outcome of one write attempt.

    Used by:
        Each writer returns this; evaluate_and_write turns the result
        into a reply string. Tests assert on .kind to verify behaviour.

    Fields:
        kind:           'created' | 'already_exists' | 'missing_data' |
                        'dependency_missing'. Drives the reply text and
                        whether an audit event was written.
        reply:          The localised reply text to send back.
        entity_id:      DB id of the new (or matched) row. None when
                        no entity was touched.
        fuzzy_skipped:  True iff a fuzzy match short-circuited the
                        write. Recorded in the audit event payload.
    """
    kind:          str
    reply:         str
    entity_id:     Optional[int] = None
    fuzzy_skipped: bool = False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def evaluate_and_write(
    *,
    message: str,
    tenant_id: int,
    phone_role: Optional[str],
    actor_user_id: Optional[int],
    db: Session,
) -> Optional[str]:
    """Top-level entry. Detect intent, run the role gate, write, reply.

    Called by:
        app/routers/whatsapp.py:_process_inbound_message — between the
        role-blocked early-return and the existing action_type
        confirmation loop. (Added in this commit, see whatsapp.py
        Step 6 region.)

    Calls into:
        - _is_top_tier_role (this file) — strict role gate.
        - detect_owner_create_intent (this file).
        - write_employee / write_machine / write_skill /
          link_employee_skill (this file).

    Side effects:
        - At most one ORM insert (Employee / Machine / Skill /
          EmployeeSkill).
        - At most one audit Event row (entity.owner_added).
        - Caller commits.

    Args:
        message:       Raw inbound text (original case). The detector
                       lowercases internally.
        tenant_id:     Tenant scope. All reads + writes filter by it.
        phone_role:    Sender's phone_role from PhoneTenantMap. The
                       v6.3.17 role gate denies NULL and any role
                       outside TOP_TIER_ROLES — those fall through to
                       the existing extractor path.
        actor_user_id: User id resolved from PhoneTenantMap (the
                       sender). Goes into audit Event.actor_user_id.
                       May be None if the phone is unmapped (the
                       outer dispatcher already filters those, but we
                       defend anyway).
        db:            Sync SQLAlchemy session. Caller commits.

    Returns:
        - str: the reply text to send back to the owner. The
          dispatcher returns this directly; downstream pipeline
          (extractor schedule, AI call) is skipped.
        - None: no owner-bypass action — let the existing pipeline
          run unchanged.
    """
    # Strict role gate — runs FIRST. NULL / unknown / mid-tier /
    # operator all fall through (return None) without parsing.
    if not _is_top_tier_role(phone_role):
        return None

    intent = detect_owner_create_intent(message)
    if intent is None:
        return None

    # Dispatch to the appropriate writer.
    if intent.kind == "employee":
        outcome = write_employee(intent, tenant_id, actor_user_id, db)
    elif intent.kind == "machine":
        outcome = write_machine(intent, tenant_id, actor_user_id, db)
    elif intent.kind == "skill":
        outcome = write_skill(intent, tenant_id, actor_user_id, db)
    elif intent.kind == "link_employee_skill":
        outcome = link_employee_skill(intent, tenant_id, actor_user_id, db)
    else:
        # Detector returned an unknown kind — log loudly, return None
        # so the pipeline continues. This branch should be unreachable
        # given the detector's own kind set.
        logger.warning(
            "owner_entity_writer: unknown intent kind=%r tenant=%s",
            intent.kind, tenant_id,
        )
        return None

    return outcome.reply


# ---------------------------------------------------------------------------
# Role gate
# ---------------------------------------------------------------------------

def _is_top_tier_role(phone_role: Optional[str]) -> bool:
    """Strict membership check against TOP_TIER_ROLES.

    Called by:    evaluate_and_write (this file).
    Calls into:   nothing — pure set membership.
    Side effects: none.

    NULL and any role string not exactly in TOP_TIER_ROLES return
    False. The owner-bypass is a privileged write path; ambiguity
    defaults to deny per the v6.3.17 spec.
    """
    if phone_role is None:
        return False
    return phone_role in PHONE_TOP_TIER_ROLES


# ---------------------------------------------------------------------------
# Heuristic detector
# ---------------------------------------------------------------------------

def detect_owner_create_intent(message: str) -> Optional[OwnerCreateIntent]:
    """Parse an inbound message for a tight create-intent signal.

    Called by:    evaluate_and_write (this file).
    Calls into:   _CREATION_VERB_RE (compiled regex), _extract_name
                  (this file), _extract_skill_phrase (this file).
    Side effects: none — pure string analysis.

    Returns:
        OwnerCreateIntent when ALL three are present:
          1. an explicit creation verb (CREATION_VERB_PHRASES)
          2. at least one entity-clue word (employee role, machine,
             skill, etc.)
          3. an extractable name candidate
        None otherwise. The detector errs toward false negatives —
        when in doubt, return None and let the existing extractor
        path handle the message.

    Decision order (highest specificity first):
      1. LINK_EMPLOYEE_SKILL — message contains an "X ko ... skills
         mein Y" pattern OR "X ko Y banao" with X capitalised and Y a
         known role-noun. Both employee + skill names extracted.
      2. CREATE_SKILL — "skill" / "skills" clue + creation verb +
         name candidate (often unquoted phrase after "-" or "naam").
      3. CREATE_MACHINE — machine clue + creation verb + name.
      4. CREATE_EMPLOYEE — employee role clue + creation verb +
         capitalised name. The role-noun becomes skill_hint.
      5. None.
    """
    if not message:
        return None
    raw = message.strip()
    lower = raw.lower()

    if not _CREATION_VERB_RE.search(lower):
        return None

    tokens_lower = re.findall(r"[a-z][a-z0-9]*", lower)
    has_employee_clue = bool(set(tokens_lower) & EMPLOYEE_CLUES)
    has_machine_clue = bool(set(tokens_lower) & MACHINE_CLUES)
    has_skill_clue = bool(set(tokens_lower) & SKILL_CLUES)
    has_link_clue = any(phrase in lower for phrase in LINK_CLUES)

    # 1. LINK_EMPLOYEE_SKILL — strongest specificity.
    #    Pattern A: "Ravi ko skills mein paint spray bhi add kar do".
    #    Detected by LINK_CLUES match. Employee name is the
    #    capitalised token; skill name is the free-text after
    #    "skills mein".
    if has_link_clue:
        link = _parse_link_intent(raw, lower)
        if link is not None:
            return link

    # 2. CREATE_SKILL — owner explicitly says "skill banao".
    if has_skill_clue and not has_link_clue:
        skill_name = _extract_skill_phrase(raw, lower)
        if skill_name:
            return OwnerCreateIntent(
                kind="skill",
                name=skill_name,
                raw_message=raw,
            )

    # 3. CREATE_MACHINE.
    if has_machine_clue:
        name = _extract_machine_name(raw, lower)
        if name:
            return OwnerCreateIntent(
                kind="machine",
                name=name,
                raw_message=raw,
            )

    # 4. CREATE_EMPLOYEE — capitalised name + employee role-noun.
    #    Also handles "Mukesh ko welder banao" (the spec edge case)
    #    by treating the role-noun as a skill_hint and letting the
    #    writer decide whether to create+link or only link.
    if has_employee_clue:
        name = _extract_employee_name(raw, lower)
        if name:
            skill_hint = _first_employee_clue(tokens_lower)
            return OwnerCreateIntent(
                kind="employee",
                name=name,
                skill_hint=skill_hint,
                raw_message=raw,
            )

    return None


# ---------------------------------------------------------------------------
# Detector helpers
# ---------------------------------------------------------------------------

def _parse_link_intent(raw: str, lower: str) -> Optional[OwnerCreateIntent]:
    """Parse 'X ko skills mein Y' / 'X ko Y bhi add kar do' patterns.

    Called by:    detect_owner_create_intent (this file).
    Calls into:   regex search; _extract_capitalised_name (this file).
    Side effects: none.

    Returns OwnerCreateIntent(kind='link_employee_skill', ...) when
    both an employee name and a skill name can be located, else None.
    The detector falls back to None on ambiguity rather than guessing.
    """
    # Find the marker phrase position so we can split before/after.
    marker_pos = -1
    for phrase in LINK_CLUES:
        idx = lower.find(phrase)
        if idx >= 0:
            marker_pos = idx
            marker_phrase = phrase
            break
    if marker_pos < 0:
        return None

    # Employee name comes before the marker — first capitalised token
    # in that prefix.
    prefix = raw[:marker_pos]
    employee_name = _extract_capitalised_name(prefix)
    if not employee_name:
        return None

    # Skill name comes after the marker. Strip leading punctuation
    # and trailing creation-verb phrases.
    suffix = raw[marker_pos + len(marker_phrase):].strip(" -:,.")
    skill_name = _strip_trailing_verbs(suffix)
    skill_name = re.sub(r"\s+bhi\s*", " ", skill_name, flags=re.IGNORECASE)
    skill_name = skill_name.strip(" -:,.").strip()
    if not skill_name:
        return None

    return OwnerCreateIntent(
        kind="link_employee_skill",
        name=skill_name,
        employee_name=employee_name,
        raw_message=raw,
    )


def _extract_skill_phrase(raw: str, lower: str) -> Optional[str]:
    """Pull the skill name from a 'naya skill banao - powder coating' shape.

    Called by:    detect_owner_create_intent (this file).
    Calls into:   regex search.
    Side effects: none.

    Heuristics, in order:
      1. After a dash, colon, or "naam" / "name" keyword, take the
         remaining text up to the creation-verb phrase.
      2. After "skill banao" / "skill add karo" without a separator,
         take the trailing run of non-verb tokens.
      3. Return None when no extractable phrase remains.
    """
    # Pattern (1): explicit separator.
    sep_match = re.search(
        r"(?:[-:]|\bnaam\b|\bname\b)\s*(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if sep_match:
        candidate = sep_match.group(1).strip()
        candidate = _strip_trailing_verbs(candidate)
        if candidate and not _is_only_stopwords(candidate):
            return candidate

    # Pattern (2): fall back to "skill <X> banao/add karo".
    fallback = re.search(
        r"\bskills?\b\s+(?:banao|add\s+karo|add\s+kar\s+do|create)\s+(.+)$",
        lower,
    )
    if fallback:
        # Map back to original case using the position.
        start = fallback.start(1)
        candidate = raw[start:].strip()
        candidate = _strip_trailing_verbs(candidate)
        if candidate and not _is_only_stopwords(candidate):
            return candidate

    # Pattern (3): "naya skill banao X" — take X.
    naya = re.search(
        r"\bnaya\s+skills?\b.+?\b(?:banao|add\s+karo|create)\b\s+(.+)$",
        lower,
    )
    if naya:
        start = naya.start(1)
        candidate = raw[start:].strip()
        candidate = _strip_trailing_verbs(candidate)
        if candidate and not _is_only_stopwords(candidate):
            return candidate

    return None


def _extract_machine_name(raw: str, lower: str) -> Optional[str]:
    """Pull the machine name from a 'machine ... naam Cutter 4' shape.

    Called by:    detect_owner_create_intent (this file).
    Calls into:   regex search.
    Side effects: none.
    """
    # "naam Cutter 4" / "name Cutter 4".
    naam_match = re.search(
        r"(?:\bnaam\b|\bname\b)\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if naam_match:
        candidate = naam_match.group(1).strip()
        candidate = _strip_trailing_verbs(candidate)
        if candidate and not _is_only_stopwords(candidate):
            return candidate

    # "Cutter 4 add kar do" — capitalised token sequence before verb.
    # Take the run of tokens (capitalised or numeric) immediately
    # preceding the creation verb.
    verb_match = _CREATION_VERB_RE.search(lower)
    if verb_match:
        prefix = raw[:verb_match.start()].strip()
        candidate = _extract_trailing_titlecase(prefix)
        if candidate:
            return candidate

    return None


def _extract_employee_name(raw: str, lower: str) -> Optional[str]:
    """Pull the employee name when the message names an employee role-noun.

    Called by:    detect_owner_create_intent (this file).
    Calls into:   _extract_capitalised_name (this file).
    Side effects: none.

    Pattern: any capitalised token that is not a stopword. We don't
    require the name to be adjacent to the role-noun — owner phrasings
    are loose ("naya welder hai - Mukesh add kar do" puts the name at
    the end; "Mukesh ko welder banao" puts it at the start).
    """
    return _extract_capitalised_name(raw)


def _extract_capitalised_name(text: str) -> Optional[str]:
    """First capitalised token in `text` that is not a NAME_STOPWORDS member.

    Called by:    _parse_link_intent, _extract_employee_name (this file).
    Calls into:   regex.
    Side effects: none.

    Allows two-token names ("Patel Kumar") when both tokens are
    capitalised and consecutive. Stops at the first non-capitalised
    token to avoid swallowing trailing verbs.
    """
    tokens = text.split()
    out: list[str] = []
    for token in tokens:
        clean = re.sub(r"[^\w]", "", token)
        if not clean:
            if out:
                break  # punctuation breaks a multi-word name run
            continue
        if not clean[0].isupper():
            if out:
                break
            continue
        if clean.lower() in NAME_STOPWORDS:
            if out:
                break
            continue
        out.append(clean)
        if len(out) >= 2:
            break  # cap at two tokens — three-word names rare in practice
    if not out:
        return None
    return " ".join(out)


def _extract_trailing_titlecase(text: str) -> Optional[str]:
    """Trailing run of TitleCase / numeric tokens at the end of `text`.

    Called by:    _extract_machine_name (this file).
    Calls into:   nothing.
    Side effects: none.

    Used for "Cutter 4 add kar do" — we want "Cutter 4", not "naya".
    """
    tokens = text.split()
    out: list[str] = []
    for token in reversed(tokens):
        clean = re.sub(r"[^\w]", "", token)
        if not clean:
            if out:
                break
            continue
        # Allow alphanumeric ("4", "Cutter", "SM52") if the FIRST char
        # is uppercase or it's a digit.
        if clean[0].isupper() or clean[0].isdigit():
            if clean.lower() in NAME_STOPWORDS:
                break
            out.append(clean)
            continue
        break
    if not out:
        return None
    return " ".join(reversed(out))


def _strip_trailing_verbs(text: str) -> str:
    """Drop any trailing creation-verb phrase from `text`.

    Called by:    skill / machine name extractors (this file).
    Calls into:   _CREATION_VERB_RE.
    Side effects: none.
    """
    match = _CREATION_VERB_RE.search(text.lower())
    if match is None:
        return text
    return text[:match.start()].rstrip(" -:,.")


def _is_only_stopwords(text: str) -> bool:
    """True when every word in `text` is in NAME_STOPWORDS.

    Called by:    skill / machine name extractors (this file).
    Calls into:   nothing.
    Side effects: none.
    """
    tokens = re.findall(r"[a-z][a-z0-9]*", text.lower())
    if not tokens:
        return True
    return all(t in NAME_STOPWORDS for t in tokens)


def _first_employee_clue(tokens_lower: list[str]) -> Optional[str]:
    """First token that matches EMPLOYEE_CLUES, or None.

    Called by:    detect_owner_create_intent (this file).
    Calls into:   nothing.
    Side effects: none.

    Used as the skill_hint when creating an employee — "naya welder
    hai - Mukesh add kar do" yields skill_hint='welder'.
    """
    for tok in tokens_lower:
        if tok in EMPLOYEE_CLUES:
            return tok
    return None


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_employee(
    intent: OwnerCreateIntent,
    tenant_id: int,
    actor_user_id: Optional[int],
    db: Session,
) -> WriteOutcome:
    """Insert one Employee, optionally linking a hinted skill.

    Called by:    evaluate_and_write (this file).
    Calls into:   fuzzy_best_match (idempotency), Skill query for
                  skill_hint resolution, _emit_owner_added_event.
    Side effects: at most one Employee insert, at most one EmployeeSkill
                  insert, one Event row. Caller commits.

    Idempotency: fuzzy_best_match against existing Employee rows. On
    match → no insert, no event, debug log, "already exists" reply.

    skill_hint handling: when present, the writer attempts to find a
    Skill with a matching (case-insensitive) name. Found → also insert
    an EmployeeSkill link. Not found → reply offers to create the
    skill ("'Welder' skill nahi mila — skill banana hai? Reply YES to
    create"). The link, if created, gets no source column (Q4); the
    audit event records the action.
    """
    name = intent.name.strip()
    if not name:
        return WriteOutcome(
            kind="missing_data",
            reply="Naam parse nahi hua. Phir se bhejein: 'Mukesh add kar do'.",
        )

    # Idempotency check.
    existing = list(db.execute(
        select(Employee.id, Employee.full_name).where(
            Employee.tenant_id == tenant_id,
        )
    ).all())
    match = fuzzy_best_match(name, existing)
    if match is not None:
        logger.debug(
            "owner_entity_writer: employee fuzzy hit tenant=%s name=%r "
            "matched_id=%s score=%.1f",
            tenant_id, name, match.matched_id, match.score,
        )
        return WriteOutcome(
            kind="already_exists",
            reply=f"{match.matched_value.title()} pehle se team mein hai.",
            entity_id=match.matched_id,
            fuzzy_skipped=True,
        )

    new_emp = Employee(
        tenant_id=tenant_id,
        full_name=name,
        source=SOURCE_VALUE,
        worker_type="permanent",  # default; matches v6.3.15 promoter behaviour
    )
    db.add(new_emp)
    db.flush()

    # Optional skill_hint link.
    skill_link_msg = ""
    if intent.skill_hint:
        skill_row = db.execute(
            select(Skill).where(
                Skill.tenant_id == tenant_id,
                Skill.name.ilike(intent.skill_hint),
            )
        ).scalars().first()
        if skill_row is not None:
            db.add(EmployeeSkill(
                tenant_id=tenant_id,
                employee_id=new_emp.id,
                skill_id=skill_row.id,
                skill_level="Generic",
            ))
            skill_link_msg = f" as {skill_row.name}"
        else:
            skill_link_msg = (
                f". '{intent.skill_hint.title()}' skill nahi mila "
                f"— skill banana hai? Reply YES to create"
            )

    _emit_owner_added_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="employee",
        entity_id=new_emp.id,
        raw_message=intent.raw_message,
        fuzzy_skipped=False,
        extra={
            "name":       name,
            "skill_hint": intent.skill_hint,
        },
    )

    return WriteOutcome(
        kind="created",
        reply=f"{name} added{skill_link_msg}.",
        entity_id=new_emp.id,
    )


def write_machine(
    intent: OwnerCreateIntent,
    tenant_id: int,
    actor_user_id: Optional[int],
    db: Session,
) -> WriteOutcome:
    """Insert one Machine row.

    Called by:    evaluate_and_write (this file).
    Calls into:   fuzzy_best_match (idempotency), _emit_owner_added_event.
    Side effects: at most one Machine insert, one Event row. Caller commits.

    machine_type stays NULL — the owner can correct it later via the
    desktop UI or a future v6.4.x edit message.
    """
    name = intent.name.strip()
    if not name:
        return WriteOutcome(
            kind="missing_data",
            reply="Machine ka naam parse nahi hua.",
        )

    existing = list(db.execute(
        select(Machine.id, Machine.name).where(
            Machine.tenant_id == tenant_id,
        )
    ).all())
    match = fuzzy_best_match(name, existing)
    if match is not None:
        logger.debug(
            "owner_entity_writer: machine fuzzy hit tenant=%s name=%r "
            "matched_id=%s score=%.1f",
            tenant_id, name, match.matched_id, match.score,
        )
        return WriteOutcome(
            kind="already_exists",
            reply=f"{match.matched_value.title()} pehle se machines mein hai.",
            entity_id=match.matched_id,
            fuzzy_skipped=True,
        )

    new_mach = Machine(
        tenant_id=tenant_id,
        name=name,
        source=SOURCE_VALUE,
        # machine_type left None for owner correction later.
    )
    db.add(new_mach)
    db.flush()

    _emit_owner_added_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="machine",
        entity_id=new_mach.id,
        raw_message=intent.raw_message,
        fuzzy_skipped=False,
        extra={"name": name},
    )

    return WriteOutcome(
        kind="created",
        reply=f"{name} added as machine. Machine type set karna ho to bolein.",
        entity_id=new_mach.id,
    )


def write_skill(
    intent: OwnerCreateIntent,
    tenant_id: int,
    actor_user_id: Optional[int],
    db: Session,
) -> WriteOutcome:
    """Insert one Skill row.

    Called by:    evaluate_and_write (this file).
    Calls into:   fuzzy_best_match (idempotency), _emit_owner_added_event.
    Side effects: at most one Skill insert, one Event row. Caller commits.

    Skills carry a `source` column as of v6.3.17 (migration 032). The
    `category` column is required by the schema — defaults to 'Generic'
    when not specified by the owner. Owners can refine via desktop.
    """
    name = intent.name.strip()
    if not name:
        return WriteOutcome(
            kind="missing_data",
            reply="Skill ka naam parse nahi hua.",
        )

    existing = list(db.execute(
        select(Skill.id, Skill.name).where(
            Skill.tenant_id == tenant_id,
        )
    ).all())
    match = fuzzy_best_match(name, existing)
    if match is not None:
        logger.debug(
            "owner_entity_writer: skill fuzzy hit tenant=%s name=%r "
            "matched_id=%s score=%.1f",
            tenant_id, name, match.matched_id, match.score,
        )
        return WriteOutcome(
            kind="already_exists",
            reply=f"'{match.matched_value.title()}' skill pehle se hai.",
            entity_id=match.matched_id,
            fuzzy_skipped=True,
        )

    new_skill = Skill(
        tenant_id=tenant_id,
        name=name,
        category="Generic",
        is_active=True,
        source=SOURCE_VALUE,
    )
    db.add(new_skill)
    db.flush()

    _emit_owner_added_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="skill",
        entity_id=new_skill.id,
        raw_message=intent.raw_message,
        fuzzy_skipped=False,
        extra={"name": name},
    )

    return WriteOutcome(
        kind="created",
        reply=(
            f"Skill '{name.title()}' created. Kisi employee ko assign "
            f"karna hai? Reply with name."
        ),
        entity_id=new_skill.id,
    )


def link_employee_skill(
    intent: OwnerCreateIntent,
    tenant_id: int,
    actor_user_id: Optional[int],
    db: Session,
) -> WriteOutcome:
    """Insert one EmployeeSkill row linking an existing employee + skill.

    Called by:    evaluate_and_write (this file).
    Calls into:   fuzzy_best_match (employee + skill resolution),
                  _emit_owner_added_event.
    Side effects: at most one EmployeeSkill insert, one Event row.
                  Caller commits.

    Resolution rules:
      - employee_name must fuzzy-match an existing Employee row above
        the threshold. Miss → reply prompts owner to add the employee
        first; no insert, no event.
      - skill name must match an existing Skill row OR fuzzy-match.
        Miss → reply prompts owner to create the skill first.
      - existing EmployeeSkill row for the (employee, skill) pair → no
        duplicate insert, "already linked" reply.
    """
    if not intent.employee_name or not intent.name:
        return WriteOutcome(
            kind="missing_data",
            reply="Employee aur skill ke naam parse nahi hue.",
        )

    employees = list(db.execute(
        select(Employee.id, Employee.full_name).where(
            Employee.tenant_id == tenant_id,
        )
    ).all())
    emp_match = fuzzy_best_match(intent.employee_name, employees)
    if emp_match is None:
        return WriteOutcome(
            kind="dependency_missing",
            reply=(
                f"{intent.employee_name} team mein nahi hai. Pehle add "
                f"karein, phir skill jodein."
            ),
        )

    skills = list(db.execute(
        select(Skill.id, Skill.name).where(
            Skill.tenant_id == tenant_id,
        )
    ).all())
    skill_match = fuzzy_best_match(intent.name, skills)
    if skill_match is None:
        return WriteOutcome(
            kind="dependency_missing",
            reply=(
                f"'{intent.name.title()}' skill nahi hai. Pehle banana "
                f"hai? YES to create."
            ),
        )

    # Already linked?
    existing_link = db.execute(
        select(EmployeeSkill).where(
            EmployeeSkill.tenant_id == tenant_id,
            EmployeeSkill.employee_id == emp_match.matched_id,
            EmployeeSkill.skill_id == skill_match.matched_id,
        )
    ).scalars().first()
    if existing_link is not None:
        logger.debug(
            "owner_entity_writer: employee_skill link already exists "
            "tenant=%s emp=%s skill=%s",
            tenant_id, emp_match.matched_id, skill_match.matched_id,
        )
        return WriteOutcome(
            kind="already_exists",
            reply=(
                f"{emp_match.matched_value.title()} ke skills mein "
                f"'{skill_match.matched_value.title()}' pehle se hai."
            ),
            entity_id=existing_link.id,
            fuzzy_skipped=True,
        )

    new_link = EmployeeSkill(
        tenant_id=tenant_id,
        employee_id=emp_match.matched_id,
        skill_id=skill_match.matched_id,
        skill_level="Generic",
    )
    db.add(new_link)
    db.flush()

    _emit_owner_added_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="employee_skill",
        entity_id=new_link.id,
        raw_message=intent.raw_message,
        fuzzy_skipped=False,
        extra={
            "employee_id": emp_match.matched_id,
            "skill_id":    skill_match.matched_id,
        },
    )

    return WriteOutcome(
        kind="created",
        reply=(
            f"{emp_match.matched_value.title()} ke skills mein "
            f"'{skill_match.matched_value.title()}' add ho gaya."
        ),
        entity_id=new_link.id,
    )


# ---------------------------------------------------------------------------
# Audit event
# ---------------------------------------------------------------------------

def _emit_owner_added_event(
    db: Session,
    *,
    tenant_id: int,
    actor_user_id: Optional[int],
    entity_type: str,
    entity_id: int,
    raw_message: str,
    fuzzy_skipped: bool,
    extra: Optional[dict] = None,
) -> None:
    """Stage one entity.owner_added Event row on the caller's session.

    Called by:    write_employee, write_machine, write_skill,
                  link_employee_skill (this file).
    Calls into:   db.add (no flush, no commit).
    Side effects: stages an INSERT on events.

    Payload schema (Q5 approval):
        {
          "entity_type":     "employee" | "machine" | "skill" | "employee_skill",
          "entity_id":       int,
          "raw_message":     str (capped at 500 chars),
          "source":          "whatsapp_owner",
          "actor_user_id":   int | None,
          "parse_strategy":  "heuristic"
        }
        Plus any writer-specific keys merged from `extra`.
    """
    payload: dict = {
        "entity_type":    entity_type,
        "entity_id":      entity_id,
        "raw_message":    (raw_message or "")[:500],
        "source":         SOURCE_VALUE,
        "actor_user_id":  actor_user_id,
        "parse_strategy": PARSE_STRATEGY_HEURISTIC,
        "fuzzy_skipped":  fuzzy_skipped,
    }
    if extra:
        payload.update(extra)
    db.add(Event(
        tenant_id=tenant_id,
        event_type=EVENT_OWNER_ADDED,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        source="whatsapp",
        payload=payload,
    ))
