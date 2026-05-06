# app/services/promotion/reply_parser.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.15 (revised) reply-parsing service. Takes the owner's free-text
# WhatsApp reply to a confirmation message + the candidates that were
# in that batch, and returns a per-candidate decision dict
# {candidate_id: 'confirmed'|'rejected'|'deferred'} plus the strategy
# that produced the verdict ('heuristic'|'llm'|'fallback').
#
# Per Q4 the strategy is hybrid:
#   1. Heuristic prong - covers the obvious all-yes / all-no / skip
#      cases plus simple "1, 2 haan, 3 nahi" and "Suresh haan,
#      Mukesh nahi" partials. Uses the SAME confirmation/cancellation
#      vocabulary as whatsapp_actions.is_confirmation /
#      is_cancellation so the owner's understanding of "yes/no" is
#      coherent across surfaces (per Stage-1 finding A.6).
#   2. LLM prong - only fires when the heuristic returns 'unparseable'.
#      Sends the original numbered proposal + the reply to Groq with
#      response_format=json_object and parses the dict it returns.
#   3. Fallback - if the LLM call also fails, every candidate is
#      marked 'deferred' so the owner sees "samajh nahi aaya - dobara
#      bolein" and the candidates stay 'pending' for the timeout
#      handler to re-ask later.
#
# WHO CALLS THIS FILE
# - app/routers/whatsapp.py - the new Step 2.5 confirmation-reply
#   branch. Resolves the in-flight batch via DB lookup, then calls
#   parse_reply with the inbound text + the batch's candidates.
# - app/services/promotion/__init__.py - re-exports parse_reply.
# - backend/tests/services/test_reply_parser.py.
#
# WHAT THIS FILE CALLS
# - app.services.whatsapp_actions.is_confirmation / is_cancellation -
#   the existing heuristic detectors used by the v5.12 confirmation
#   state machine. Reusing them keeps the bot's "yes/no" vocabulary
#   in one place across all surfaces (per Stage-1 A.6).
# - app.services.ai_service.{get_groq_client, MODEL} - test seam
#   pattern lifted from entity_extractor.py. Production injects None
#   and we fetch the singleton; tests inject a stub object whose
#   chat.completions.create returns a canned response.
#
# DESIGN NOTES (Q4)
# - Reply parsing must be deterministic for the heuristic prong so
#   tests can assert exact decision dicts. The LLM prong is non-
#   deterministic but tests stub the client to return a fixed
#   response. Fallback is also deterministic ('all deferred').
# - The heuristic prong matches against candidate.raw_value AND
#   candidate.normalized_value (case-insensitive substring) so
#   owners can write either "Suresh" or "suresh" or "Suresh Kumar"
#   and have their intent resolved. Tied matches go to the first
#   candidate in iteration order.
# - Per Q4 footnote: name corrections ("Suresh ka spelling Suresh
#   Kumar hai") are deferred to v6.3.17. The LLM prompt explicitly
#   instructs the model NOT to attempt correction; replies that
#   look like corrections come back as 'deferred' for that candidate.
# - The parser is sync and pure-ish (the LLM call hits the network,
#   but no DB writes). The caller commits state changes after using
#   the returned dict.
#
# FAILURE SEMANTICS
# - Heuristic prong: cannot fail. Returns either decisions or signals
#   'unparseable' for the LLM prong.
# - LLM prong: catches every exception (timeout, malformed JSON,
#   missing keys, network error). On any failure, returns 'all
#   deferred' with strategy='fallback' and logs the failure with
#   tenant_id + candidate_ids context.
# - Empty reply: returns 'all deferred' with strategy='heuristic'
#   (the heuristic recognises this as "no decision possible").

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Iterable, Literal, Optional

from app.models.extraction_candidate import ExtractionCandidate
from app.services.whatsapp_actions import is_cancellation, is_confirmation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

Decision = Literal["confirmed", "rejected", "deferred"]
Strategy = Literal["heuristic", "llm", "fallback"]

# Words that indicate "skip / let me think later" rather than yes or no.
# Distinct from cancellation (which means rejection) - 'skip' means
# 'leave them all pending'.
SKIP_WORDS: frozenset[str] = frozenset({
    "skip", "kuch nahi", "baad mein", "later", "abhi nahi",
    "rehne do",   # also cancellation; here it doubles as 'leave pending'.
})

# LLM tunables. Kept conservative because reply parsing is a single-shot
# JSON task with a small input + small output - no need for high
# temperature or large max_tokens.
_LLM_MAX_TOKENS: int = 256
_LLM_TEMPERATURE: float = 0.0
_LLM_TIMEOUT_S: float = 10.0


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedReply:
    """Outcome of reply parsing.

    Used by:    routers/whatsapp.py confirmation reply branch + tests.
    Fields:
        decisions:      candidate_id -> 'confirmed'|'rejected'|'deferred'.
                        Always has one entry per input candidate; the
                        parser never silently drops candidates.
        strategy:       Which prong produced the result.
                        'heuristic' - resolved from keyword/name match.
                        'llm'       - resolved from LLM JSON.
                        'fallback'  - everything deferred (LLM failed
                                      or both prongs gave up).
        raw_reply:      The original owner reply, lowercased + stripped.
                        Useful for the audit event payload.
        unparsed_text:  Raw reply when strategy=='fallback', empty
                        otherwise. Lets the audit event preserve the
                        owner's exact words so a human can review later.
    """
    decisions: dict[int, Decision]
    strategy: Strategy
    raw_reply: str
    unparsed_text: str = ""


def parse_reply(
    reply_text: str,
    candidates: Iterable[ExtractionCandidate],
    *,
    tenant_id: int,
    groq_client=None,
) -> ParsedReply:
    """Resolve an owner's free-text reply into per-candidate decisions.

    Called by:    routers/whatsapp.py confirmation reply branch +
                  unit tests.
    Calls into:   _parse_heuristic, _parse_llm (only when heuristic
                  returns unparseable).
    Side effects: At most one outbound LLM call. No DB writes.
                  Logs at INFO level with the chosen strategy + reply
                  excerpt; logs at WARNING when the LLM prong falls
                  back.

    Args:
        reply_text:   Raw inbound message text from the owner.
        candidates:   Iterable of ExtractionCandidate rows that were
                      in the batch the owner is replying to. The
                      caller resolves these via the in-flight pending
                      batch lookup (state='pending', asked_at within
                      the routing-precedence window).
        tenant_id:    For log context.
        groq_client:  Test seam. None in production -> we fetch from
                      ai_service.get_groq_client(). Tests inject a
                      stub.

    Returns:
        ParsedReply with one entry per input candidate. Never raises.
    """
    candidates_list = list(candidates)
    candidate_ids = [int(c.id) for c in candidates_list]
    if not candidate_ids:
        # Defensive - caller should not invoke us with no candidates.
        return ParsedReply(
            decisions={}, strategy="fallback",
            raw_reply=reply_text or "", unparsed_text="",
        )

    norm = (reply_text or "").strip().lower()

    # Empty reply -> defer everything. Heuristic strategy (we are
    # confident the answer is "nothing decisive said").
    if not norm:
        return ParsedReply(
            decisions={cid: "deferred" for cid in candidate_ids},
            strategy="heuristic",
            raw_reply="",
        )

    # Prong 1: heuristic.
    heuristic_result = _parse_heuristic(norm, candidates_list)
    if heuristic_result is not None:
        logger.info(
            "reply_parsed_heuristic tenant=%s candidates=%s reply=%r",
            tenant_id, candidate_ids, norm[:120],
        )
        return ParsedReply(
            decisions=heuristic_result,
            strategy="heuristic",
            raw_reply=norm,
        )

    # Prong 2: LLM.
    llm_result = _parse_llm(
        norm, candidates_list, tenant_id=tenant_id, groq_client=groq_client,
    )
    if llm_result is not None:
        logger.info(
            "reply_parsed_llm tenant=%s candidates=%s reply=%r",
            tenant_id, candidate_ids, norm[:120],
        )
        return ParsedReply(
            decisions=llm_result,
            strategy="llm",
            raw_reply=norm,
        )

    # Fallback: defer everything, log the unparsed text for human review.
    logger.warning(
        "reply_parser_fallback tenant=%s candidates=%s reply=%r - "
        "neither heuristic nor LLM could decide; deferring all.",
        tenant_id, candidate_ids, norm[:200],
    )
    return ParsedReply(
        decisions={cid: "deferred" for cid in candidate_ids},
        strategy="fallback",
        raw_reply=norm,
        unparsed_text=reply_text or "",
    )


# ---------------------------------------------------------------------------
# Prong 1 - heuristic
# ---------------------------------------------------------------------------

def _parse_heuristic(
    norm_reply: str,
    candidates: list[ExtractionCandidate],
) -> Optional[dict[int, Decision]]:
    """Try to decide every candidate via keyword + name matching.

    Called by:    parse_reply.
    Calls into:   is_confirmation, is_cancellation, _split_pairs,
                  _resolve_token_to_candidate.
    Side effects: none.

    Returns:
        Decision dict if the heuristic is confident, or None to signal
        "give up - try the LLM". Confidence rules:
          - Whole-message keyword match (haan, nahi, skip, etc.)
            -> apply uniformly to every candidate.
          - Numbered pairs ("1 haan, 2 nahi, 3 skip") -> apply per
            candidate by 1-based index.
          - Name + verdict pairs ("suresh haan, mukesh nahi") -> apply
            per candidate by raw_value / normalized_value substring
            match.
          - Anything else -> None.

        For mixed strategies (e.g. number + name) the parser also
        gives up and lets the LLM handle it. The point is to be
        conservative - the LLM prong is cheap enough that being
        wrong here is worse than passing the buck.
    """
    candidate_ids = [int(c.id) for c in candidates]

    # Whole-message uniform decisions.
    # is_confirmation also accepts "ok", "yes please" etc. - same
    # vocabulary the v5.12 pending-action machine uses.
    if is_confirmation(norm_reply) and not _looks_like_partial(norm_reply):
        return {cid: "confirmed" for cid in candidate_ids}
    if is_cancellation(norm_reply) and not _looks_like_partial(norm_reply):
        return {cid: "rejected" for cid in candidate_ids}
    if _is_skip(norm_reply):
        return {cid: "deferred" for cid in candidate_ids}

    # Numbered partial: split on commas / 'and' / 'aur' and look for
    # "<digit><space><verdict>" pairs. Owners often write "1 haan, 2
    # nahi" or "1, 2 haan, 3 nahi" - both shapes parse here.
    numbered = _try_numbered_partial(norm_reply, candidates)
    if numbered is not None:
        return numbered

    # Name partial: "<name> <verdict>" pairs.
    named = _try_named_partial(norm_reply, candidates)
    if named is not None:
        return named

    return None


def _looks_like_partial(norm: str) -> bool:
    """True if the reply contains a digit or comma suggesting list-form.

    Called by:    _parse_heuristic.
    Side effects: none.

    Why: "haan" alone is a clear all-yes; "haan 1 nahi" is a partial
    that happens to start with "haan". We don't want is_confirmation()
    to swallow the latter as all-yes.
    """
    if "," in norm:
        return True
    if any(ch.isdigit() for ch in norm):
        return True
    return False


def _is_skip(norm: str) -> bool:
    """True if the reply matches one of the SKIP_WORDS."""
    if norm in SKIP_WORDS:
        return True
    for w in SKIP_WORDS:
        if norm.startswith(w + " ") or norm.endswith(" " + w):
            return True
    return False


# Verdict tokens used by the partial parsers. Order matters - we check
# the longer phrase first so "kuch nahi" is recognised as 'deferred',
# not as 'rejected' on the trailing 'nahi'.
_VERDICT_TOKENS: tuple[tuple[str, Decision], ...] = (
    ("kuch nahi",  "deferred"),
    ("mat karo",   "rejected"),
    ("mat kar",    "rejected"),
    ("haan",       "confirmed"),
    ("haa",        "confirmed"),
    ("han",        "confirmed"),
    ("yes",        "confirmed"),
    ("ok",         "confirmed"),
    ("kar do",     "confirmed"),
    ("karo",       "confirmed"),
    ("nahi",       "rejected"),
    ("nahin",      "rejected"),
    ("naa",        "rejected"),
    ("no",         "rejected"),
    ("skip",       "deferred"),
)


def _verdict_for_token(text: str) -> Optional[Decision]:
    """Return the verdict carried by `text`, or None if no verdict found."""
    text = text.strip().lower()
    for token, verdict in _VERDICT_TOKENS:
        # Substring match - allows "haan kar do" to resolve as confirmed
        # because "haan" is a substring. Order in _VERDICT_TOKENS makes
        # multi-word tokens win over single-word ones.
        if token in text:
            return verdict
    return None


def _try_numbered_partial(
    norm: str, candidates: list[ExtractionCandidate],
) -> Optional[dict[int, Decision]]:
    """Parse '1 haan, 2 nahi, 3 skip' style replies.

    Returns a decision dict only when EVERY candidate gets a verdict
    (either explicitly or via a clear default). Partial coverage
    (some candidates not mentioned and no global default) -> None,
    falls through to LLM.
    """
    # Match groups of digits followed by a verdict. Tolerates commas,
    # 'and', 'aur', and missing whitespace. Examples:
    #   "1 haan, 2 nahi"
    #   "1,2 haan, 3 nahi"
    #   "1 aur 2 haan, 3 nahi"
    pairs = re.findall(
        r"((?:\d+\s*[, ]+\s*)*\d+)\s*([a-z][a-z\s]*)",
        norm,
    )
    if not pairs:
        return None

    # Build {idx -> decision} from pairs.
    by_idx: dict[int, Decision] = {}
    for digits_blob, verdict_text in pairs:
        verdict = _verdict_for_token(verdict_text)
        if verdict is None:
            continue
        # Extract every integer in the digits blob.
        for idx_str in re.findall(r"\d+", digits_blob):
            try:
                idx = int(idx_str)
            except ValueError:
                continue
            if 1 <= idx <= len(candidates):
                by_idx[idx] = verdict

    if not by_idx:
        return None

    # Any candidate not explicitly mentioned -> deferred.
    decisions: dict[int, Decision] = {}
    for one_based_idx, cand in enumerate(candidates, start=1):
        decisions[int(cand.id)] = by_idx.get(one_based_idx, "deferred")

    # Sanity: at least one candidate should have a non-deferred verdict.
    # Otherwise the heuristic was probably wrong (the digits matched
    # something else, like "5 baar" in a quoted line) - bail out.
    if all(v == "deferred" for v in decisions.values()):
        return None

    return decisions


def _try_named_partial(
    norm: str, candidates: list[ExtractionCandidate],
) -> Optional[dict[int, Decision]]:
    """Parse 'suresh haan, mukesh nahi' style replies."""
    # Split on commas / 'and' / 'aur' to get clauses.
    clauses = re.split(r"\s*(?:,|\band\b|\baur\b)\s*", norm)
    clauses = [c.strip() for c in clauses if c.strip()]
    if not clauses:
        return None

    by_id: dict[int, Decision] = {}
    for clause in clauses:
        verdict = _verdict_for_token(clause)
        if verdict is None:
            continue
        # Find which candidate this clause refers to. Match on
        # raw_value / normalized_value substring.
        matched = _resolve_clause_to_candidate(clause, candidates)
        if matched is None:
            continue
        by_id[int(matched.id)] = verdict

    if not by_id:
        return None

    # Pad missing candidates with deferred.
    decisions: dict[int, Decision] = {}
    for cand in candidates:
        decisions[int(cand.id)] = by_id.get(int(cand.id), "deferred")

    if all(v == "deferred" for v in decisions.values()):
        return None
    return decisions


def _resolve_clause_to_candidate(
    clause: str, candidates: list[ExtractionCandidate],
) -> Optional[ExtractionCandidate]:
    """Find the candidate whose name appears in `clause`.

    Returns the longest-matching candidate to avoid 'Suresh' beating
    'Suresh Kumar' when both exist. Ties go to the first encountered.
    """
    clause_lower = clause.lower()
    best: Optional[ExtractionCandidate] = None
    best_len = 0
    for cand in candidates:
        for needle in (cand.raw_value, cand.normalized_value):
            if not needle:
                continue
            n = needle.strip().lower()
            if not n:
                continue
            if n in clause_lower and len(n) > best_len:
                best = cand
                best_len = len(n)
    return best


# ---------------------------------------------------------------------------
# Prong 2 - LLM
# ---------------------------------------------------------------------------

def _build_llm_prompt(
    norm_reply: str, candidates: list[ExtractionCandidate],
) -> list[dict]:
    """Build the chat prompt the Groq client receives."""
    listing_lines = []
    for one_based_idx, cand in enumerate(candidates, start=1):
        listing_lines.append(
            f"{one_based_idx}. id={cand.id} name={cand.raw_value!r} "
            f"type={cand.entity_type}"
        )
    listing = "\n".join(listing_lines)

    system = (
        "You translate a factory owner's free-text WhatsApp reply into "
        "per-candidate decisions. The bot proposed these candidates:\n"
        f"{listing}\n\n"
        "Return STRICT JSON of the form "
        "{\"decisions\": {\"<candidate_id>\": \"confirmed\"|\"rejected\"|\"deferred\"}}\n"
        "Rules:\n"
        "- 'confirmed' means the owner accepts adding this entity.\n"
        "- 'rejected' means the owner explicitly does NOT want it added.\n"
        "- 'deferred' means the owner is unsure / wants to think / "
        "is asking for a name correction. (Name corrections are NOT "
        "applied at this stage - mark as deferred.)\n"
        "- Every candidate id from the listing MUST appear as a key.\n"
        "- Respond with JSON only - no explanation, no markdown."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": norm_reply},
    ]


def _parse_llm(
    norm_reply: str,
    candidates: list[ExtractionCandidate],
    *,
    tenant_id: int,
    groq_client,
) -> Optional[dict[int, Decision]]:
    """Send the reply to Groq, parse JSON, return decisions or None.

    Called by:    parse_reply when the heuristic gives up.
    Calls into:   ai_service.get_groq_client (when groq_client is None),
                  groq_client.chat.completions.create.
    Side effects: one network call. No DB writes.

    Returns:
        Decision dict on success, None on any failure (parse_reply
        then falls back to 'all deferred').
    """
    try:
        if groq_client is None:
            from app.services.ai_service import get_groq_client
            groq_client = get_groq_client()
        from app.services.ai_service import MODEL

        messages = _build_llm_prompt(norm_reply, candidates)
        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=_LLM_MAX_TOKENS,
            temperature=_LLM_TEMPERATURE,
            response_format={"type": "json_object"},
            timeout=_LLM_TIMEOUT_S,
        )
        content = response.choices[0].message.content or ""
        if not content.strip():
            logger.warning(
                "reply_parser_llm_empty tenant=%s reply=%r",
                tenant_id, norm_reply[:200],
            )
            return None

        parsed = json.loads(content)
        decisions_raw = parsed.get("decisions", {})
        if not isinstance(decisions_raw, dict):
            logger.warning(
                "reply_parser_llm_bad_shape tenant=%s parsed=%r",
                tenant_id, str(parsed)[:200],
            )
            return None

        valid_ids = {int(c.id) for c in candidates}
        out: dict[int, Decision] = {}
        for k, v in decisions_raw.items():
            try:
                cid = int(k)
            except (ValueError, TypeError):
                continue
            if cid not in valid_ids:
                continue
            if v not in ("confirmed", "rejected", "deferred"):
                continue
            out[cid] = v   # type: ignore[assignment]

        if not out:
            return None

        # Pad missing candidate ids with 'deferred' so every candidate
        # has a verdict the caller can act on.
        for cid in valid_ids:
            out.setdefault(cid, "deferred")
        return out

    except Exception as exc:  # noqa: BLE001 - blanket catch by design
        logger.warning(
            "reply_parser_llm_failed tenant=%s err=%r reply=%r",
            tenant_id, exc, norm_reply[:200],
        )
        return None
