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
                # Name found but no DB match - still flag intent but without ID.
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

    # -- 2. Check for MAINTENANCE intent -------------------------------------
    maintenance_detected = any(
        keyword in message_lower for keyword in MAINTENANCE_KEYWORDS
    )

    if maintenance_detected:
        # For now, return intent without machine ID - confirmation prompt
        # will ask owner to confirm which machine before we look up the ID.
        # This is safer than guessing which machine they mean.
        logger.info(
            f"Maintenance intent detected in message: '{user_message[:50]}'"
        )
        return ActionType.MARK_MAINTENANCE, {
            "machine_id":   None,
            "machine_name": "the machine",  # Will be clarified in confirmation
        }

    # -- 3. Check for JOB STATUS UPDATE intent -------------------------------
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

    # No write intent detected - normal read/query message
    return None, None
