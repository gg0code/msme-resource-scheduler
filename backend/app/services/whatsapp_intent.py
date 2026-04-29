# whatsapp_intent.py - Version 1.2
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Three responsibilities:
#   1. Role gate (v5.12): checks phone_role before any action detection.
#      Blocked roles receive a localised reply and never reach the AI layer.
#   2. Write intent detection: scans user message for write actions
#      (mark absent, maintenance, job status) that need confirmation.
#   3. Briefing request detection (v6.3.4): scans for "morning briefing",
#      "today's plan", etc. The router uses the result to fan out to
#      app.services.briefings.dispatcher.manual_trigger_briefing for
#      top-tier requesters and to a polite refusal for everyone else.
#
# WHO CALLS THIS FILE
#   app/routers/whatsapp.py - calls detect_write_intent() and
#                             detect_briefing_request_intent() on every
#                             inbound message that has passed consent check.
#
# WHAT THIS FILE CALLS
#   app/services/whatsapp_actions.py    - ActionType enum
#   app/services/whatsapp_responses.py  - get_response() for role_blocked
#                                         and briefing_refused replies
#   app/models/employee.py              - Employee (name lookup for absent intent)
#
# KEY DESIGN DECISIONS (v5.12 additions)
#   - Role gate runs at the TOP of detect_write_intent(), before any keyword
#     matching. Blocked actions never reach AI. Never move this check lower.
#   - phone_role and language are new required parameters added in v5.12.
#     Callers must pass identity.phone_role and the detected language.
#   - Return signature extended to 4-tuple:
#       (blocked: bool, block_reply: str | None, action_type, action_params)
#     Callers MUST check blocked first before reading action_type/action_params.
#   - Owner always passes role gate unconditionally.
#   - Manager blocked from: financial queries, job create, job delete.
#     Allowed: attendance marking, machine status, schedule viewing.
#   - Operator blocked from all write/financial keywords. Own-assignment
#     queries with no blocked keywords pass through to AI read-only.
#   - Unknown phone_role defaults to 'operator' (most restrictive) safely.
#   - All keyword sets are lowercase frozensets. Input is lowercased before
#     matching. Do not rely on callers to normalise case.

import logging
import re
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.auth import TOP_TIER_ROLES
from app.services.whatsapp_actions import ActionType
from app.services.whatsapp_responses import Language, get_response

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ROLE CONSTANTS
# Match PhoneTenantMap.phone_role column values exactly.
#
# v5.12: Three-role taxonomy (owner / manager / operator).
# v6.3.3: Extended to honour the v6.4 SRS Section 6.28.6 role taxonomy.
#         Top-tier roles (owner, proprietor=legacy synonym, factory_manager,
#         co_owner) all pass the role gate unconditionally — same treatment
#         as 'owner' in v5.12. Mid-tier roles (manager, scheduler=legacy
#         synonym for manager) get manager-level gating. Anything else
#         (operator, viewer, unknown) is treated as operator (most
#         restrictive) for safety.
# ---------------------------------------------------------------------------
ROLE_OWNER:    str = "owner"
ROLE_MANAGER:  str = "manager"
ROLE_OPERATOR: str = "operator"

# Phone-side top-tier set. Imports TOP_TIER_ROLES from app.models.auth so
# the user-side and phone-side gates share one canonical role list (Lesson
# 22: single source of truth). Adding a new top-tier role anywhere flows
# through both gates automatically.
PHONE_TOP_TIER_ROLES: frozenset = frozenset(TOP_TIER_ROLES)

# Phone-side mid-tier set. 'manager' is the v6.4 spelling, 'scheduler' is
# the legacy spelling kept here as a synonym (same pattern as TOP_TIER's
# proprietor/owner). Both receive manager-level gating: blocked on
# financial / create / delete keywords, allowed on read + attendance.
PHONE_MID_TIER_ROLES: frozenset = frozenset(("manager", "scheduler"))

# ---------------------------------------------------------------------------
# ROLE GATE KEYWORD SETS (v5.12)
# Used to classify message intent for role-based blocking.
# All lowercase - matched against lowercased user message tokens.
#
# FINANCIAL_KEYWORDS   - queries that expose cost, revenue, salary, or wage data.
#                        Manager and operator are both blocked from these.
# MANAGER_CREATE_KEYWORDS - intent to create a new job or order.
#                           Manager blocked. Operator blocked via OPERATOR set.
# MANAGER_DELETE_KEYWORDS - intent to delete or cancel a job.
#                           Manager blocked. Operator blocked via OPERATOR set.
# OPERATOR_BLOCKED_KEYWORDS - union of all write/financial keywords plus
#                             any query that spans beyond own assignments.
#                             Operator sees only their own work.
# ---------------------------------------------------------------------------
FINANCIAL_KEYWORDS: frozenset[str] = frozenset([
    "cost", "price", "salary", "wage", "wages", "rate", "payment",
    "invoice", "revenue", "profit", "expense", "expenses", "paisa",
    "rupee", "rupees", "paise", "kitna", "lagat", "daam",
])

MANAGER_CREATE_KEYWORDS: frozenset[str] = frozenset([
    "create", "add", "new", "banao", "daalo", "shuru",
    "naya", "nayi",
])

MANAGER_DELETE_KEYWORDS: frozenset[str] = frozenset([
    "delete", "remove", "cancel", "hatao", "band", "khatam",
    "mitao", "rok", "roko",
])

# Operator blocked from all write/financial actions and non-self queries
OPERATOR_BLOCKED_KEYWORDS: frozenset[str] = (
    FINANCIAL_KEYWORDS
    | MANAGER_CREATE_KEYWORDS
    | MANAGER_DELETE_KEYWORDS
    | frozenset([
        "schedule", "assign", "reassign", "all", "sabka", "sab",
        "team", "machine", "machines",
    ])
)


# ---------------------------------------------------------------------------
# INTENT KEYWORDS - edit these to add new trigger phrases
# ---------------------------------------------------------------------------

# Phrases in the USER message that signal "mark employee absent"
# All lowercase - we match against lowercased user message.
ABSENT_KEYWORDS = [
    "nahi aaya", "nahi aayi", "absent", "nahi aayega", "nahi aayegi",
    "absent mark", "mark absent", "chutti", "leave pe", "nahi hai aaj",
    "aaj nahi", "nahi ayega", "not coming", "won't come", "on leave",
]

# Phrases that signal "mark machine under maintenance"
MAINTENANCE_KEYWORDS = [
    "maintenance", "kharab", "band karo machine", "machine down",
    "repair", "service pe", "not working", "kaam nahi kar rahi",
]

# Phrases that signal "update job status"
JOB_STATUS_KEYWORDS = [
    "complete kar", "complete ho gaya", "khatam ho gaya", "done ho gaya",
    "mark complete", "job complete", "finish kar", "band karo job",
    "status update", "complete karo",
]

# Date keywords for resolving relative dates
TODAY_KEYWORDS    = ["aaj", "today", "abhi", "is waqt"]
TOMORROW_KEYWORDS = ["kal", "tomorrow", "agle din"]


# ---------------------------------------------------------------------------
# BRIEFING REQUEST KEYWORDS (v6.3.4)
# ---------------------------------------------------------------------------
# The phrases below are matched as substrings (lowercased) against the
# inbound message. Order matters only inasmuch as the kind returned is
# the kind whose keyword appeared first in the message - "morning"
# wins over "evening" when both appear, since the prompt wording
# typically opens with the desired direction.
#
# All keywords are also tested in test_briefings.py so a typo here
# fails loudly at CI time, not silently in production.

BRIEFING_MORNING_KEYWORDS = [
    "morning briefing",
    "today's plan",
    "todays plan",
    "aaj ka plan",
    "aaj ka schedule",
]

BRIEFING_EVENING_KEYWORDS = [
    "evening briefing",
    "today's summary",
    "todays summary",
    "aaj ka summary",
    "din ka summary",
    "end of day",
]


# ---------------------------------------------------------------------------
# HELPER - resolve relative date to YYYY-MM-DD string
# ---------------------------------------------------------------------------

def _resolve_date(user_message: str) -> str:
    """
    Resolve relative date references in a user message to YYYY-MM-DD.

    Checks for 'aaj'/'today' → today's date.
    Checks for 'kal'/'tomorrow' → tomorrow's date.
    Defaults to today if no date keyword found.

    Args:
        user_message: The raw user message text (lowercased).

    Returns:
        Date string in YYYY-MM-DD format.

    Side effects:
        None — pure function.
    """
    today = date.today()
    message_lower = user_message.lower()

    for keyword in TOMORROW_KEYWORDS:
        if keyword in message_lower:
            return str(today + timedelta(days=1))

    # Default to today - covers "aaj" and no date specified
    return str(today)


# ---------------------------------------------------------------------------
# HELPER - extract employee name from user message
# ---------------------------------------------------------------------------

def _extract_employee_name(user_message: str) -> str | None:
    """
    Extract a likely employee name from the user message.

    Strategy: The first capitalised word that is NOT a known keyword
    is likely the employee name. We also look for common Hindi name
    patterns at the start of the sentence.

    This is a best-effort extraction — the confirmation prompt will
    show the extracted name so the owner can correct it if wrong.

    Args:
        user_message: Raw user message text (original case preserved).

    Returns:
        Extracted name string, or None if no name found.

    Side effects:
        None — pure function.
    """
    # Common non-name words to skip - these appear frequently near absent keywords
    SKIP_WORDS = {
        "aaj", "kal", "nahi", "absent", "hai", "hain", "ka", "ki",
        "ko", "ne", "se", "the", "is", "are", "was", "will", "not",
        "coming", "aaya", "aayi", "aayega", "mark", "please", "aur",
    }

    # Try to find capitalised words first (proper names)
    words = user_message.split()
    for word in words:
        clean = re.sub(r'[^\w]', '', word)  # Strip punctuation
        if (
            clean
            and clean[0].isupper()
            and clean.lower() not in SKIP_WORDS
            and len(clean) > 2  # Skip short words like "I", "A"
        ):
            return clean

    # Fallback - take first word that looks like a name (not a keyword)
    for word in words:
        clean = re.sub(r'[^\w]', '', word).lower()
        if clean and clean not in SKIP_WORDS and len(clean) > 2:
            return word.capitalize()

    return None


# ---------------------------------------------------------------------------
# HELPER - look up employee id by name in DB
# ---------------------------------------------------------------------------

def _find_employee_id(name: str, tenant_id: int, db: Session) -> int | None:
    """
    Look up an employee's ID by partial name match within a tenant.

    Uses case-insensitive LIKE match so "Rajan" matches "Rajan Mehta".
    Returns the first match — if multiple employees share a name, the
    confirmation prompt will show the full name so owner can verify.

    Args:
        name:      Partial or full employee name to search for.
        tenant_id: Tenant scope — never returns employees from other tenants.
        db:        Sync SQLAlchemy session for the DB query.

    Returns:
        Employee ID (int) if found, None if not found.

    Side effects:
        Reads from employees table — no writes.
    """
    from app.models.employee import Employee

    employee = (
        db.query(Employee)
        .filter(
            Employee.tenant_id == tenant_id,
            Employee.full_name.ilike(f"%{name}%"),  # Case-insensitive partial match
            Employee.status != "inactive"            # Skip terminated employees
        )
        .first()
    )

    if employee:
        logger.debug(
            f"Employee name match: '{name}' → id={employee.id}, "
            f"full_name='{employee.full_name}'"
        )
        return employee.id, employee.full_name

    logger.debug(f"No employee found for name='{name}' in tenant_id={tenant_id}")
    return None, None


# ---------------------------------------------------------------------------
# BRIEFING REQUEST DETECTOR (v6.3.4)
# ---------------------------------------------------------------------------

def detect_briefing_request_intent(user_message: str) -> str | None:
    """
    Pure-function classifier: does this message ask for a briefing?

    Called by:    app/routers/whatsapp.py - before detect_write_intent
                  so a request like "morning briefing" is routed to the
                  briefing dispatcher instead of falling through to AI.
    Calls into:   nothing - lowercase substring match on the keyword
                  lists above.
    Args:
        user_message: Raw inbound text. Original case is preserved by
                      the caller; this function lowercases internally.
    Returns:
        'morning' | 'evening' | None.
        Tie-break when both kinds appear: the kind whose first keyword
        appears earliest in the message wins. None when no briefing
        keyword matches.
    Side effects:
        None - pure function. Authorisation, dispatch, and event
        emission live in the dispatcher / router layers.
    """
    if not user_message:
        return None
    lower = user_message.lower()

    morning_pos = _earliest_match(lower, BRIEFING_MORNING_KEYWORDS)
    evening_pos = _earliest_match(lower, BRIEFING_EVENING_KEYWORDS)

    if morning_pos is None and evening_pos is None:
        return None
    if morning_pos is None:
        return "evening"
    if evening_pos is None:
        return "morning"
    return "morning" if morning_pos <= evening_pos else "evening"


def _earliest_match(haystack: str, needles: list[str]) -> int | None:
    """
    Return the smallest index at which any of `needles` first appears
    in `haystack`, or None when no needle is present.

    Called by:    detect_briefing_request_intent.
    Calls into:   str.find (cheaper than re for plain substring sets).
    Side effects: none.
    """
    earliest: int | None = None
    for needle in needles:
        pos = haystack.find(needle)
        if pos < 0:
            continue
        if earliest is None or pos < earliest:
            earliest = pos
    return earliest


# ---------------------------------------------------------------------------
# MAIN INTENT DETECTOR
# ---------------------------------------------------------------------------

def detect_write_intent(
    user_message: str,
    tenant_id: int,
    db: Session,
    phone_role: str = ROLE_OWNER,
    language: Language = "english",
) -> tuple[bool, str | None, ActionType | None, dict | None]:
    """
    Role gate + write intent detector. Called on every inbound message
    that has passed consent check, before any AI interaction.

    v5.12: Added phone_role and language parameters. Return signature
    extended to 4-tuple. Role gate runs first — blocked actions never
    reach AI. Callers MUST check blocked (index 0) before reading
    action_type (index 2) and action_params (index 3).

    Called by:   app/routers/whatsapp.py — on every message after consent.
    Calls:       get_response() for blocked reply string.
                 _extract_employee_name(), _find_employee_id(),
                 _resolve_date() for action param extraction.
    Args:
        user_message: The raw user message text (original case).
        tenant_id:    For DB lookups scoped to this tenant.
        db:           Sync SQLAlchemy session for employee/job lookups.
        phone_role:   Role from PhoneTenantMap.phone_role.
                      Valid: 'owner', 'manager', 'operator'.
                      Defaults to 'owner' for backwards compatibility
                      with any callers that have not yet been updated.
        language:     Detected language for localising the blocked reply.
                      Must match detect_language() output values:
                      'english', 'hinglish', 'hindi'.
    Returns:
        4-tuple: (blocked, block_reply, action_type, action_params)
        - blocked=True, block_reply=str:  role blocked — send reply, stop.
        - blocked=False, block_reply=None, action_type=ActionType, params=dict:
                                          write action detected — confirm.
        - blocked=False, block_reply=None, action_type=None, params=None:
                                          read/query — pass to AI.
    Side effects:
        Reads from employees/machines/jobs tables for ID lookups.
        No writes.
    """
    message_lower = user_message.lower()
    tokens: frozenset[str] = frozenset(message_lower.split())

    # ------------------------------------------------------------------
    # ROLE GATE (v5.12, extended v6.3.3) — runs before ALL other checks.
    # Blocked actions never reach AI. Never move this below intent checks.
    #
    # Tier classification (single dispatch on phone_role):
    #   top-tier (owner / proprietor / factory_manager / co_owner)
    #     — passes everything, no blocking applied.
    #   mid-tier (manager / scheduler)
    #     — blocked on financial / create / delete keywords.
    #   anything else (operator / viewer / unknown)
    #     — treated as operator: blocked on the broad write+financial set.
    # ------------------------------------------------------------------
    if phone_role in PHONE_TOP_TIER_ROLES:
        pass  # no blocking — owner-equivalent

    elif phone_role in PHONE_MID_TIER_ROLES:
        if tokens & FINANCIAL_KEYWORDS:
            block_reply = get_response("role_blocked", language)
            logger.info(
                "Role gate blocked %s (financial): tenant=%s",
                phone_role, tenant_id,
            )
            return True, block_reply, None, None
        if tokens & MANAGER_CREATE_KEYWORDS:
            block_reply = get_response("role_blocked", language)
            logger.info(
                "Role gate blocked %s (create): tenant=%s",
                phone_role, tenant_id,
            )
            return True, block_reply, None, None
        if tokens & MANAGER_DELETE_KEYWORDS:
            block_reply = get_response("role_blocked", language)
            logger.info(
                "Role gate blocked %s (delete): tenant=%s",
                phone_role, tenant_id,
            )
            return True, block_reply, None, None

    else:
        # Operator, viewer, or unknown — apply most restrictive gating.
        # Logged at warning when truly unknown (not 'operator') so misconfig
        # surfaces in logs without breaking the request.
        if phone_role != ROLE_OPERATOR:
            logger.warning(
                "Role gate: unknown phone_role '%s' treated as operator: tenant=%s",
                phone_role, tenant_id,
            )
        if tokens & OPERATOR_BLOCKED_KEYWORDS:
            block_reply = get_response("role_blocked", language)
            logger.info(
                "Role gate blocked %s: tenant=%s tokens_matched=%s",
                phone_role, tenant_id,
                tokens & OPERATOR_BLOCKED_KEYWORDS,
            )
            return True, block_reply, None, None

    # ------------------------------------------------------------------
    # END ROLE GATE — existing intent detection continues below unchanged
    # ------------------------------------------------------------------

    # -- 1. Check for ABSENT intent ------------------------------------------
    absent_detected = any(keyword in message_lower for keyword in ABSENT_KEYWORDS)

    if absent_detected:
        # Extract employee name from message
        employee_name_raw = _extract_employee_name(user_message)

        if employee_name_raw:
            # Look up employee in DB for their ID
            employee_id, full_name = _find_employee_id(
                name=employee_name_raw,
                tenant_id=tenant_id,
                db=db
            )
            target_date = _resolve_date(user_message)

            if employee_id:
                logger.info(
                    "Absent intent detected: employee='%s' (id=%s), date=%s, tenant=%s",
                    full_name,
                    employee_id,
                    target_date,
                    tenant_id,
                )
                return False, None, ActionType.MARK_ABSENT, {
                    "employee_id":   employee_id,
                    "employee_name": full_name,
                    "date":          target_date,
                }
            else:
                logger.info(
                    "Absent intent detected but employee '%s' not found in DB "
                    "for tenant=%s. Will ask for confirmation without ID.",
                    employee_name_raw,
                    tenant_id,
                )
                return False, None, ActionType.MARK_ABSENT, {
                    "employee_id":   None,
                    "employee_name": employee_name_raw,
                    "date":          target_date,
                }

    # -- 2. Check for MAINTENANCE intent -------------------------------------
    maintenance_detected = any(
        keyword in message_lower for keyword in MAINTENANCE_KEYWORDS
    )

    if maintenance_detected:
        logger.info(
            "Maintenance intent detected in message: '%s'",
            user_message[:50],
        )
        return False, None, ActionType.MARK_MAINTENANCE, {
            "machine_id":   None,
            "machine_name": "the machine",
        }

    # -- 3. Check for JOB STATUS UPDATE intent -------------------------------
    job_status_detected = any(
        keyword in message_lower for keyword in JOB_STATUS_KEYWORDS
    )

    if job_status_detected:
        logger.info(
            "Job status update intent detected in message: '%s'",
            user_message[:50],
        )
        return False, None, ActionType.UPDATE_JOB_STATUS, {
            "job_id":     None,
            "new_status": "completed",
            "job_name":   "the job",
        }

    # No write intent detected - normal read/query message
    return False, None, None, None
