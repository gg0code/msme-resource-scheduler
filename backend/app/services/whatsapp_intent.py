"""
```python
"""
FILE PURPOSE
This file implements intent detection for the WhatsApp Copilot feature (v5-whatsapp branch).
It analyzes incoming user messages to identify when users want to perform write operations
(like marking employees absent or updating job statuses) and extracts the necessary parameters
for those actions. This serves as the critical bridge between AI conversation and the confirmation
state machine, ensuring all database modifications go through proper owner approval before execution.

WHAT THIS FILE DOES — step by step
1. Defines keyword lists for different intent types (absent, maintenance, job status updates)
2. Provides helper functions to extract employee names and resolve relative dates from messages
3. Performs database lookups to convert extracted names into employee IDs
4. Scans user messages against keyword patterns to detect write intents
5. Returns structured action data (ActionType + parameters) for the confirmation workflow
6. Falls back gracefully when names don't match database records or parameters are incomplete

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _resolve_date
Type         : function (private helper)
Purpose      : Converts relative date references like "aaj" (today) or "kal" (tomorrow) into 
               YYYY-MM-DD format strings. Defaults to today's date if no date keywords found.
Parameters   : user_message (str) - the raw user message text, converted to lowercase
Returns      : str - date in YYYY-MM-DD format for database storage
Calls        : datetime.date.today(), timedelta() from Python standard library
DB/API       : None - pure function with no external calls
Side effects : None - reads system date but doesn't modify anything

Name         : _extract_employee_name
Type         : function (private helper)  
Purpose      : Attempts to identify employee names in user messages by looking for capitalized
               words that aren't common Hindi/English keywords. Uses best-effort heuristics
               since the confirmation prompt will show the extracted name for owner verification.
Parameters   : user_message (str) - raw user message text with original capitalization preserved
Returns      : str|None - extracted employee name or None if no likely name found
Calls        : re.sub() for punctuation cleaning, string methods for capitalization checks
DB/API       : None - pure text processing function
Side effects : None - only analyzes text without external modifications

Name         : _find_employee_id
Type         : function (private helper)
Purpose      : Performs database lookup to find employee ID and full name using case-insensitive
               partial name matching. Scoped to tenant for security and filters out inactive employees.
               Returns first match if multiple employees share similar names.
Parameters   : name (str) - partial or full employee name to search for
               tenant_id (int) - tenant scope for the database query  
               db (Session) - sync SQLAlchemy session for database access
Returns      : tuple[int|None, str|None] - (employee_id, full_name) if found, (None, None) if not
Calls        : app.models.employee.Employee ORM model for database queries
DB/API       : SELECT query on employees table with tenant_id filter and ILIKE name matching
Side effects : Database read operation - no writes or modifications

Name         : detect_write_intent
Type         : function (main entry point)
Purpose      : Main intent detection engine that scans user messages for write operations requiring
               confirmation. Currently handles absent marking, maintenance requests, and job status
               updates. Called before AI response generation to catch actionable user requests.
Parameters   : user_message (str) - raw user message text with original case
               tenant_id (int) - tenant scope for database lookups
               db (Session) - sync SQLAlchemy session for employee/machine/job queries
Returns      : tuple[ActionType|None, dict|None] - (action_type, parameters) if intent detected, 
               (None, None) for read-only conversations requiring no confirmation
Calls        : _extract_employee_name(), _find_employee_id(), _resolve_date() helper functions
DB/API       : Indirect database queries through helper functions for employee lookups
Side effects : Database read operations for ID resolution - no writes during detection phase

WHO CALLS THIS FILE
- backend/app/routers/whatsapp_router.py imports detect_write_intent for message processing
- backend/app/services/whatsapp_bridge.py may call this during message flow orchestration
- backend/app/services/whatsapp_actions.py works with ActionType enum defined here

IMPORTS EXPLAINED
- logging: Provides module-level logger for debugging intent detection and name matching results
- re: Regular expressions for cleaning punctuation from extracted employee names during processing  
- datetime.date, timedelta: Date arithmetic for resolving "aaj"/"kal" to actual YYYY-MM-DD dates
- sqlalchemy.orm.Session: Database session type annotation for tenant-scoped employee lookups
- app.services.whatsapp_actions.ActionType: Enum defining available action types for confirmation workflow

INTERN NOTES
- Easiest thing to break: Adding new keywords without testing against actual user messages - Hindi/English mixing creates edge cases that simple string matching misses
- Non-obvious design decision: Uses keyword matching instead of AI tool calling to avoid double AI calls per message (latency + cost), plus user intent is clearer in their original words than AI summaries
- Most common mistake: Forgetting tenant_id filtering in database lookups when adding new intent types - this creates security vulnerabilities across tenant boundaries  
- Implements design principle #2: All database queries include tenant scoping through _find_employee_id helper function
- If this file behaves unexpectedly: Check keyword lists for missing phrases, verify database has active employees with matching names, and ensure ActionType enum matches expected return values
- v5-whatsapp merge consideration: This entire file is WhatsApp-specific and should not be merged to v4-dev - it depends on v5-only models like PhoneTenantMap and WhatsAppConversation
"""
```
"""

import logging
import re
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.services.whatsapp_actions import ActionType

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# INTENT KEYWORDS — edit these to add new trigger phrases
# ---------------------------------------------------------------------------

# Phrases in the USER message that signal "mark employee absent"
# All lowercase — we match against lowercased user message.
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
# HELPER — resolve relative date to YYYY-MM-DD string
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

    # Default to today — covers "aaj" and no date specified
    return str(today)


# ---------------------------------------------------------------------------
# HELPER — extract employee name from user message
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
    # Common non-name words to skip — these appear frequently near absent keywords
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

    # Fallback — take first word that looks like a name (not a keyword)
    for word in words:
        clean = re.sub(r'[^\w]', '', word).lower()
        if clean and clean not in SKIP_WORDS and len(clean) > 2:
            return word.capitalize()

    return None


# ---------------------------------------------------------------------------
# HELPER — look up employee id by name in DB
# ---------------------------------------------------------------------------

def _find_employee_id(name: str, tenant_id: int, db: Session) -> tuple[int | None, str | None]:
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
# MAIN INTENT DETECTOR
# ---------------------------------------------------------------------------

def detect_write_intent(
    user_message: str,
    tenant_id: int,
    db: Session,
) -> tuple[ActionType | None, dict | None]:
    """
    Scan the USER message for write intents that need confirmation.

    Called BEFORE the AI response is sent — we check the user's words
    directly because intent is clearest in what they said, not what
    the AI summarised.

    Currently detects:
      - MARK_ABSENT:      "Rajan aaj nahi aaya", "mark Sunita absent"
      - MARK_MAINTENANCE: "Heidelberg kharab ho gayi", "machine maintenance pe"
      - UPDATE_JOB_STATUS: "Wedding Card job complete ho gaya"

    Adding a new intent type:
      1. Add keywords to the relevant keyword list above
      2. Add a detection block in this function following the same pattern
      3. Add the action to ActionType enum in whatsapp_actions.py
      4. Add the executor in whatsapp_actions.py _execute_* functions
      5. Add the confirmation prompt in build_confirmation_prompt()

    Args:
        user_message: The raw user message text (original case).
        tenant_id:    For DB lookups scoped to this tenant.
        db:           Sync SQLAlchemy session for employee/job lookups.

    Returns:
        (ActionType, params_dict) if a write intent is detected.
        (None, None) if this is a read/query message — no action needed.

    Side effects:
        Reads from employees/machines/jobs tables for ID lookups.
        No writes — this is detection only.
    """
    message_lower = user_message.lower()

    # ── 1. Check for ABSENT intent ──────────────────────────────────────────
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
                # We have enough to propose a confirmed action
                logger.info(
                    f"Absent intent detected: employee='{full_name}' "
                    f"(id={employee_id}), date={target_date}, tenant={tenant_id}"
                )
                return ActionType.MARK_ABSENT, {
                    "employee_id":   employee_id,
                    "employee_name": full_name,
                    "date":          target_date,
                }
            else:
                # Name found but no DB match — still flag intent but without ID.
                # build_confirmation_prompt will show name and ask owner to confirm.
                # execute_action will fail gracefully if employee_id is missing.
                logger.info(
                    f"Absent intent detected but employee '{employee_name_raw}' "
                    f"not found in DB for tenant={tenant_id}. "
                    f"Will ask for confirmation without ID."
                )
                return ActionType.MARK_ABSENT, {
                    "employee_id":   None,
                    "employee_name": employee_name_raw,
                    "date":          target_date,
                }

    # ── 2. Check for MAINTENANCE intent ─────────────────────────────────────
    maintenance_detected = any(
        keyword in message_lower for keyword in MAINTENANCE_KEYWORDS
    )

    if maintenance_detected:
        # For now, return intent without machine ID — confirmation prompt
        # will ask owner to confirm which machine before we look up the ID.
        # This is safer than guessing which machine they mean.
        logger.info(
            f"Maintenance intent detected in message: '{user_message[:50]}'"
        )
        return ActionType.MARK_MAINTENANCE, {
            "machine_id":   None,
            "machine_name": "the machine",  # Will be clarified in confirmation
        }

    # ── 3. Check for JOB STATUS UPDATE intent ───────────────────────────────
    job_status_detected = any(
        keyword in message_lower for keyword in JOB_STATUS_KEYWORDS
    )

    if job_status_detected:
        logger.info(
            f"Job status update intent detected in message: '{user_message[:50]}'"
        )
        return ActionType.UPDATE_JOB_STATUS, {
            "job_id":     None,
            "new_status": "completed",
            "job_name":   "the job",  # Will be clarified in confirmation
        }

    # No write intent detected — normal read/query message
    return None, None
