import json
import logging
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy.orm import Session

# Reuse the Redis connection pool from whatsapp_session.py
from app.services.whatsapp_session import (
    redis_client,
    sync_redis_client,
    _mock_sessions,
)

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

# How long a pending action waits for confirmation before auto-cancelling.
# 300 seconds = 5 minutes. After this, the owner must ask again.
CONFIRMATION_TIMEOUT_SECONDS = 300

# Redis key prefix for pending actions - separate from session keys.
# Full key format: whatsapp:pending_action:+919876543210
PENDING_ACTION_KEY_PREFIX = "whatsapp:pending_action"


# ---------------------------------------------------------------------------
# ACTION TYPES - all supported write actions
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    """
    All write actions that require confirmation before DB execution.

    Each action type maps to a specific DB operation in execute_action().
    Using an Enum prevents typos and makes the code self-documenting.
    """
    MARK_ABSENT          = "mark_absent"          # Mark an employee absent for a date
    CREATE_JOB           = "create_job"           # Create a new job
    UPDATE_JOB_STATUS    = "update_job_status"    # Change a job's status
    RESCHEDULE_JOB       = "reschedule_job"       # Change a job's start/end date
    MARK_MAINTENANCE     = "mark_maintenance"     # Mark a machine under maintenance
    UPDATE_PUSH_SETTING  = "update_push_setting"  # v6.3.20 — change a tenant/user push-briefing setting
    PAUSE_PUSH           = "pause_push"           # v6.3.20 — temporarily suppress push briefings


# ---------------------------------------------------------------------------
# CONFIRMATION AND CANCELLATION WORD LISTS
# ---------------------------------------------------------------------------

# Words the owner can type to CONFIRM a pending action.
# Covers Hindi, Hinglish, and English variations.
# All lowercase - we compare against lowercased input.
CONFIRMATION_WORDS = {
    "haan", "haa", "han",           # Hindi yes
    "yes", "y", "yeah", "yep",      # English yes
    "ok", "okay", "theek", "thik",  # Agreement
    "kar do", "karo", "kardo",      # "do it" in Hindi
    "confirm", "confirmed",          # Explicit confirmation
    "bilkul", "zaroor",             # "absolutely", "definitely" in Hindi
}

# Words the owner can type to CANCEL a pending action.
CANCELLATION_WORDS = {
    "nahi", "nahin", "naa", "na",   # Hindi no
    "no", "n", "nope",              # English no
    "cancel", "cancelled", "ruko",  # Cancel / "wait" in Hindi
    "mat karo", "mat kar",          # "don't do it" in Hindi
    "band karo", "rehne do",        # "stop it", "leave it" in Hindi
}


# ---------------------------------------------------------------------------
# REDIS HELPERS FOR PENDING ACTIONS
# ---------------------------------------------------------------------------

def _build_pending_action_key(phone_number: str) -> str:
    """
    Build the Redis key for storing a pending action for a phone number.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210

    Returns:
        Redis key string e.g. "whatsapp:pending_action:+919876543210"
    """
    return f"{PENDING_ACTION_KEY_PREFIX}:{phone_number}"


async def store_pending_action(
    phone_number: str,
    action_type: ActionType,
    action_params: dict
) -> bool:
    """
    Store a pending action in Redis waiting for owner confirmation.

    Called when write intent is detected. The action is stored with a
    5-minute TTL. If the owner does not confirm within 5 minutes,
    Redis auto-deletes it and the action is cancelled.

    Args:
        phone_number:  E.164 format phone number e.g. +919876543210
        action_type:   The type of action e.g. ActionType.MARK_ABSENT
        action_params: Parameters e.g. {"employee_name": "Rajan",
                       "date": "2026-03-29", "employee_id": 5}

    Returns:
        True if stored successfully, False if storage failed.

    Side effects:
        Writes to Redis or _mock_sessions with CONFIRMATION_TIMEOUT_SECONDS TTL.
    """
    pending_key = _build_pending_action_key(phone_number)

    pending_action = {
        "action_type":   action_type.value,  # Store string not Enum object
        "action_params": action_params,
        "proposed_at":   datetime.now(timezone.utc).isoformat(),
        "phone_number":  phone_number
    }

    action_json = json.dumps(pending_action, ensure_ascii=False)

    # Mock mode - store in memory dict (no Redis)
    if redis_client is None:
        _mock_sessions[pending_key] = action_json
        logger.info(
            f"Mock: Pending action stored for ****{phone_number[-4:]} — "
            f"action={action_type.value}, params={action_params}"
        )
        return True

    # Real Redis mode - store with TTL so it auto-expires after 5 minutes
    try:
        await redis_client.set(
            pending_key,
            action_json,
            ex=CONFIRMATION_TIMEOUT_SECONDS
        )
        logger.info(
            f"Pending action stored for ****{phone_number[-4:]} — "
            f"action={action_type.value}, TTL={CONFIRMATION_TIMEOUT_SECONDS}s"
        )
        return True

    except Exception as e:
        logger.error(
            f"Failed to store pending action for ****{phone_number[-4:]}. "
            f"Action will not be executed. Error: {e}"
        )
        return False


async def get_pending_action(phone_number: str) -> dict | None:
    """
    Retrieve the pending action for a phone number from Redis.

    Called on every inbound message — we check if there is a pending
    action waiting for confirmation before processing normally.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210

    Returns:
        Dict with action_type, action_params, proposed_at, phone_number.
        None if no pending action exists or TTL has expired.

    Side effects:
        None — read only.
    """
    pending_key = _build_pending_action_key(phone_number)

    # Mock mode - read from memory dict
    if redis_client is None:
        raw_data = _mock_sessions.get(pending_key)
        if raw_data is None:
            return None
        return json.loads(raw_data)

    # Real Redis mode
    try:
        raw_data = await redis_client.get(pending_key)
        if raw_data is None:
            return None
        return json.loads(raw_data)

    except Exception as e:
        logger.error(
            f"Failed to retrieve pending action for ****{phone_number[-4:]}. "
            f"Error: {e}"
        )
        return None


async def clear_pending_action(phone_number: str) -> bool:
    """
    Delete the pending action for a phone number.

    Called after the action is confirmed and executed, or when
    the owner cancels.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210

    Returns:
        True if cleared successfully or no action existed.
        False if deletion failed.

    Side effects:
        Removes the pending action key from Redis or _mock_sessions.
    """
    pending_key = _build_pending_action_key(phone_number)

    # Mock mode
    if redis_client is None:
        _mock_sessions.pop(pending_key, None)
        return True

    try:
        await redis_client.delete(pending_key)
        logger.info(f"Pending action cleared for ****{phone_number[-4:]}")
        return True

    except Exception as e:
        logger.error(
            f"Failed to clear pending action for ****{phone_number[-4:]}. "
            f"Error: {e}"
        )
        return False


# ---------------------------------------------------------------------------
# SYNC STAGING (v6.3.20)
# ---------------------------------------------------------------------------
# ai_service.execute_tool runs sync (called from sync run_ai_chat). The async
# Redis client cannot be awaited from sync code. This sync companion uses
# whatsapp_session.sync_redis_client + the same _mock_sessions dict so the
# async router-side reads still see the writes. Used by the v6.3.20
# update_push_setting / pause_push tool handlers.

def store_pending_action_sync(
    phone_number: str,
    action_type: ActionType,
    action_params: dict,
) -> bool:
    """Sync companion to store_pending_action.

    Same key namespace, same JSON shape, same TTL — only the transport
    differs. Returns True on success, False on Redis failure (mock mode
    cannot fail since it's a dict assignment).
    """
    pending_key = _build_pending_action_key(phone_number)
    pending_action = {
        "action_type":   action_type.value,
        "action_params": action_params,
        "proposed_at":   datetime.now(timezone.utc).isoformat(),
        "phone_number":  phone_number,
    }
    action_json = json.dumps(pending_action, ensure_ascii=False)

    if sync_redis_client is None:
        _mock_sessions[pending_key] = action_json
        logger.info(
            f"Mock (sync): Pending action stored for ****{phone_number[-4:]} — "
            f"action={action_type.value}, params={action_params}"
        )
        return True

    try:
        sync_redis_client.set(
            pending_key,
            action_json,
            ex=CONFIRMATION_TIMEOUT_SECONDS,
        )
        logger.info(
            f"Pending action stored (sync) for ****{phone_number[-4:]} — "
            f"action={action_type.value}, TTL={CONFIRMATION_TIMEOUT_SECONDS}s"
        )
        return True
    except Exception as e:
        logger.error(
            f"Failed to store pending action (sync) for ****{phone_number[-4:]}. "
            f"Error: {e}"
        )
        return False


# ---------------------------------------------------------------------------
# MESSAGE INTENT DETECTION
# ---------------------------------------------------------------------------

def is_confirmation(message: str) -> bool:
    """
    Check if a message is a confirmation of a pending action.

    Args:
        message: Raw message text from the factory owner.

    Returns:
        True if the message clearly confirms a pending action.
        False otherwise — when in doubt, do not confirm.

    Side effects:
        None — pure function.
    """
    normalised = message.lower().strip()

    if normalised in CONFIRMATION_WORDS:
        return True

    # Also match if message starts with a confirmation word and has more text
    # e.g. "haan kar do" or "yes please"
    for word in CONFIRMATION_WORDS:
        if normalised.startswith(word + " "):
            return True

    return False


def is_cancellation(message: str) -> bool:
    """
    Check if a message is a cancellation of a pending action.

    Args:
        message: Raw message text from the factory owner.

    Returns:
        True if the message clearly cancels a pending action.
        False otherwise.

    Side effects:
        None — pure function.
    """
    normalised = message.lower().strip()

    if normalised in CANCELLATION_WORDS:
        return True

    for word in CANCELLATION_WORDS:
        if normalised.startswith(word + " "):
            return True

    return False


# ---------------------------------------------------------------------------
# CONFIRMATION PROMPT BUILDER
# ---------------------------------------------------------------------------

def build_confirmation_prompt(
    action_type: ActionType,
    action_params: dict
) -> str:
    """
    Build a human-readable confirmation message to send to the factory owner.

    Written in Hinglish — works for Hindi, Hinglish, and English speakers.
    The owner must reply with a confirmation word before anything is written.

    Args:
        action_type:   The type of action being proposed.
        action_params: Parameters for the action — used to fill in specifics.

    Returns:
        Plain text confirmation message ready to send via WhatsApp.

    Side effects:
        None — pure function.
    """

    if action_type == ActionType.MARK_ABSENT:
        employee_name = action_params.get("employee_name", "employee")
        target_date   = action_params.get("date", "aaj")
        description   = f"{employee_name} ko {target_date} ke liye absent mark karna"

    elif action_type == ActionType.CREATE_JOB:
        job_name    = action_params.get("job_name", "naya job")
        description = f"'{job_name}' naam ka naya job banana"

    elif action_type == ActionType.UPDATE_JOB_STATUS:
        job_name   = action_params.get("job_name", "job")
        new_status = action_params.get("new_status", "update")
        description = f"'{job_name}' ka status '{new_status}' karna"

    elif action_type == ActionType.RESCHEDULE_JOB:
        job_name  = action_params.get("job_name", "job")
        new_date  = action_params.get("new_start_date", "nayi date")
        description = f"'{job_name}' ko {new_date} tak reschedule karna"

    elif action_type == ActionType.MARK_MAINTENANCE:
        machine_name = action_params.get("machine_name", "machine")
        description  = f"'{machine_name}' ko maintenance mode mein daalna"

    elif action_type == ActionType.UPDATE_PUSH_SETTING:
        # v6.3.20 — staged by ai_service.execute_tool after server-side
        # validation, so action_params already carries a 'snippet_en'
        # string that describes the proposed change in plain English.
        # Fall back to the field/value if snippet was missing.
        snippet = action_params.get("snippet_en")
        if not snippet:
            field = action_params.get("field", "setting")
            value = action_params.get("new_value", "?")
            snippet = f"{field} ko {value} karna"
        description = snippet

    elif action_type == ActionType.PAUSE_PUSH:
        # v6.3.20 — pause_range_human is the "Tue Sep 30 through Sat Oct 4,
        # resume Sun Oct 5" string that pause_push() built. Restating the
        # date range in the confirmation prompt is load-bearing — it
        # catches today + (days - 1) inference errors before they commit.
        range_human = action_params.get("pause_range_human") or "the requested range"
        description = f"Push briefings {range_human} ke liye band karna"

    else:
        description = f"'{action_type.value}' action execute karna"

    return (
        f"Kya main ye karna chahta hoon:\n"
        f"{description}\n\n"
        f"Confirm karne ke liye: HAAN\n"
        f"Cancel karne ke liye: NAHI\n"
        f"(5 minute mein reply nahi kiya toh automatically cancel ho jayega)"
    )


# ---------------------------------------------------------------------------
# ACTION EXECUTOR
# ---------------------------------------------------------------------------

async def execute_action(
    pending_action: dict,
    db: Session,
    tenant_id: int
) -> tuple[bool, str]:
    """
    Execute a confirmed write action against the database.

    Called only AFTER the owner has confirmed with a confirmation word.
    Uses sync SQLAlchemy Session — no await on db.execute() or db.commit().

    Args:
        pending_action: The action dict from get_pending_action().
                        Contains action_type, action_params, phone_number.
        db:             Sync SQLAlchemy Session — NOT AsyncSession.
        tenant_id:      For DB row isolation — never touch other tenants' data.

    Returns:
        (True, success_message) if DB write succeeded.
        (False, error_message) if write failed.

    Side effects:
        Writes to PostgreSQL. The ONLY place in the WhatsApp codebase
        that writes to the main application database.
    """

    action_type   = pending_action.get("action_type")
    action_params = pending_action.get("action_params", {})

    logger.info(
        f"Executing confirmed action: {action_type} "
        f"for tenant_id={tenant_id}, params={action_params}"
    )

    try:
        if action_type == ActionType.MARK_ABSENT.value:
            return _execute_mark_absent(action_params, db, tenant_id)

        elif action_type == ActionType.UPDATE_JOB_STATUS.value:
            return _execute_update_job_status(action_params, db, tenant_id)

        elif action_type == ActionType.RESCHEDULE_JOB.value:
            return _execute_reschedule_job(action_params, db, tenant_id)

        elif action_type == ActionType.MARK_MAINTENANCE.value:
            return _execute_mark_maintenance(action_params, db, tenant_id)

        elif action_type == ActionType.UPDATE_PUSH_SETTING.value:
            return _execute_update_push_setting(action_params, db, tenant_id)

        elif action_type == ActionType.PAUSE_PUSH.value:
            return _execute_pause_push(action_params, db, tenant_id)

        else:
            logger.error(
                f"Unknown action type '{action_type}' — cannot execute. "
                f"Add this action type to execute_action() in whatsapp_actions.py."
            )
            return False, "Ye action abhi supported nahi hai. Admin se contact karein."

    except Exception as e:
        logger.error(
            f"Action execution failed for {action_type}: {e}. "
            f"DB write was NOT completed. Owner should try again."
        )
        return False, "Kuch gadbad ho gayi. Action complete nahi hua. Dobara try karein."


# ---------------------------------------------------------------------------
# PRIVATE ACTION EXECUTORS - one function per action type
# ---------------------------------------------------------------------------
# All functions use sync SQLAlchemy Session - no async, no await.
# Adding a new action type:
#   1. Add to ActionType enum above
#   2. Add a _execute_* function here following the same pattern
#   3. Add to build_confirmation_prompt() above
#   4. Add to execute_action() dispatcher above
#   5. Add detection keywords to whatsapp_intent.py

def _execute_mark_absent(
    params: dict,
    db: Session,
    tenant_id: int
) -> tuple[bool, str]:
    """
    Mark an employee as absent for a specific date.

    Args:
        params:    Must contain 'employee_id' (int) and 'date' (YYYY-MM-DD).
                   Optional: 'employee_name' for the success message.
        db:        Sync SQLAlchemy Session.
        tenant_id: For row-level isolation — only updates this tenant's employees.

    Returns:
        (True, success_message) if marked successfully.
        (False, error_message) if employee not found or write failed.

    Side effects:
        Updates employees.status = 'absent' for the matched employee.
    """
    from sqlalchemy import update
    from app.models.employee import Employee

    employee_id   = params.get("employee_id")
    date_str      = params.get("date")
    employee_name = params.get("employee_name", "Employee")

    # Validate required params - fail fast with a helpful message
    if not employee_id or not date_str:
        return False, (
            "Employee ID ya date missing hai. "
            "Dobara poochein: 'Rajan ko aaj absent mark karo'"
        )

    # Sync execute - no await
    result = db.execute(
        update(Employee)
        .where(
            Employee.id        == employee_id,
            Employee.tenant_id == tenant_id   # Row-level isolation
        )
        .values(status="absent")
    )
    db.commit()

    if result.rowcount == 0:
        return False, (
            f"Employee ID {employee_id} nahi mila. "
            f"Shayad already absent hai ya account mein nahi hai."
        )

    logger.info(
        f"Employee id={employee_id} ({employee_name}) marked absent "
        f"for tenant_id={tenant_id} on date={date_str}"
    )

    return True, f"Done. {employee_name} ko {date_str} ke liye absent mark kar diya gaya."


def _execute_update_job_status(
    params: dict,
    db: Session,
    tenant_id: int
) -> tuple[bool, str]:
    """
    Update the status of a job.

    Args:
        params:    Must contain 'job_id' (int) and 'new_status' (string).
                   Optional: 'job_name' for the success message.
        db:        Sync SQLAlchemy Session.
        tenant_id: For row-level isolation.

    Returns:
        (True, success_message) or (False, error_message).

    Side effects:
        Updates jobs.status for the matched job.
    """
    from sqlalchemy import update
    from app.models.job import Job

    job_id     = params.get("job_id")
    new_status = params.get("new_status")
    job_name   = params.get("job_name", f"Job #{job_id}")

    if not job_id or not new_status:
        return False, (
            "Job ID ya status missing hai. "
            "Dobara poochein: 'Job #5 ka status complete karo'"
        )

    result = db.execute(
        update(Job)
        .where(
            Job.id        == job_id,
            Job.tenant_id == tenant_id
        )
        .values(status=new_status)
    )
    db.commit()

    if result.rowcount == 0:
        return False, f"Job ID {job_id} nahi mila ya aapke account mein nahi hai."

    return True, f"Done. '{job_name}' ka status '{new_status}' kar diya gaya."


def _execute_reschedule_job(
    params: dict,
    db: Session,
    tenant_id: int
) -> tuple[bool, str]:
    """
    Reschedule a job to a new start date.

    Args:
        params:    Must contain 'job_id' (int) and 'new_start_date' (YYYY-MM-DD).
                   Optional: 'job_name', 'new_end_date'.
        db:        Sync SQLAlchemy Session.
        tenant_id: For row-level isolation.

    Returns:
        (True, success_message) or (False, error_message).

    Side effects:
        Updates jobs.start_date (and optionally end_date) for the matched job.
    """
    from sqlalchemy import update
    from app.models.job import Job

    job_id          = params.get("job_id")
    new_start_date  = params.get("new_start_date")
    new_end_date    = params.get("new_end_date")
    job_name        = params.get("job_name", f"Job #{job_id}")

    if not job_id or not new_start_date:
        return False, (
            "Job ID ya nayi date missing hai. "
            "Dobara poochein: 'Job #5 ko 5 April tak reschedule karo'"
        )

    update_values = {"start_date": new_start_date}
    if new_end_date:
        update_values["end_date"] = new_end_date

    result = db.execute(
        update(Job)
        .where(
            Job.id        == job_id,
            Job.tenant_id == tenant_id
        )
        .values(**update_values)
    )
    db.commit()

    if result.rowcount == 0:
        return False, f"Job ID {job_id} nahi mila ya aapke account mein nahi hai."

    return True, f"Done. '{job_name}' ab {new_start_date} se shuru hoga."


def _execute_mark_maintenance(
    params: dict,
    db: Session,
    tenant_id: int
) -> tuple[bool, str]:
    """
    Mark a machine as under maintenance.

    Args:
        params:    Must contain 'machine_id' (int).
                   Optional: 'machine_name'.
        db:        Sync SQLAlchemy Session.
        tenant_id: For row-level isolation.

    Returns:
        (True, success_message) or (False, error_message).

    Side effects:
        Updates machines.status = 'maintenance' for the matched machine.
    """
    from sqlalchemy import update
    from app.models.machine import Machine

    machine_id   = params.get("machine_id")
    machine_name = params.get("machine_name", f"Machine #{machine_id}")

    if not machine_id:
        return False, (
            "Machine ID missing hai. "
            "Dobara poochein: 'Heidelberg machine ko maintenance mein daalo'"
        )

    result = db.execute(
        update(Machine)
        .where(
            Machine.id        == machine_id,
            Machine.tenant_id == tenant_id
        )
        .values(status="maintenance")
    )
    db.commit()

    if result.rowcount == 0:
        return False, f"Machine ID {machine_id} nahi mila ya aapke account mein nahi hai."

    return True, (
        f"Done. '{machine_name}' ko maintenance mode mein dal diya gaya. "
        f"Is machine par scheduled jobs affected ho sakte hain."
    )


# ---------------------------------------------------------------------------
# v6.3.20 — push-setting executors
# ---------------------------------------------------------------------------
# These are thin wrappers over push_settings_service. The whitelist,
# validators, top-tier check, audit row, and tenant-isolation guarantees
# all live in that service module — these executors only re-call the
# service with the params that were validated and staged in Redis at
# tool-call time. Re-validation at execute time is intentional: the
# Redis payload could in principle have been tampered with, and re-
# running the validator costs microseconds.

def _execute_update_push_setting(
    params: dict,
    db: "Session",  # type: ignore[name-defined]
    tenant_id: int,
) -> tuple[bool, str]:
    """Apply a confirmed push-setting change.

    params keys (set by ai_service.execute_tool when the LLM called the
    tool):
      field          — the EDITABLE_FIELDS key (str)
      raw_value      — the value the LLM passed (already validated once
                       at stage time; re-validated by the service)
      user_id        — None for tenant-scoped fields, int for user-scoped
      actor_user_id  — int, the user behind the calling phone
      source_phrase  — verbatim user message that produced the change
      snippet_en     — confirmation snippet built at stage time (kept in
                       payload for the post-execute reply)
    """
    from app.services import push_settings_service as pss

    field = params.get("field")
    raw_value = params.get("raw_value")
    user_id = params.get("user_id")
    actor_user_id = params.get("actor_user_id")
    source_phrase = params.get("source_phrase", "")

    if not field or actor_user_id is None:
        return False, "Setting change parameters missing. Please ask again."

    try:
        result = pss.update_push_setting(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            field=field,
            raw_value=raw_value,
            source_phrase=source_phrase,
            actor_user_id=actor_user_id,
        )
        db.commit()
    except pss.PushSettingValidationError as e:
        db.rollback()
        return False, e.messages.get("hi_en") or e.messages.get("en", str(e))
    except pss.PushSettingForbidden as e:
        db.rollback()
        return False, e.messages.get("hi_en") or e.messages.get("en", str(e))
    except Exception as e:
        db.rollback()
        logger.error(
            f"update_push_setting execute failed tenant={tenant_id} "
            f"field={field}: {e}"
        )
        return False, "Setting update fail ho gaya. Phir se try karein."

    return True, result.snippet.get("hi_en") or result.snippet.get("en", "Done.")


def _execute_pause_push(
    params: dict,
    db: "Session",  # type: ignore[name-defined]
    tenant_id: int,
) -> tuple[bool, str]:
    """Apply a confirmed push pause.

    params keys (set by ai_service.execute_tool):
      days           — int in [1, 30] (re-validated by the service)
      actor_user_id  — int, the user behind the calling phone
      source_phrase  — verbatim user message
      pause_range_human — human range string built at stage time, used
                          here only as a fallback in the success reply
    """
    from app.services import push_settings_service as pss

    days = params.get("days")
    actor_user_id = params.get("actor_user_id")
    source_phrase = params.get("source_phrase", "")

    if days is None or actor_user_id is None:
        return False, "Pause parameters missing. Please ask again."

    try:
        result = pss.pause_push(
            db=db,
            tenant_id=tenant_id,
            days=days,
            source_phrase=source_phrase,
            actor_user_id=actor_user_id,
        )
        db.commit()
    except pss.PushSettingValidationError as e:
        db.rollback()
        return False, e.messages.get("hi_en") or e.messages.get("en", str(e))
    except pss.PushSettingForbidden as e:
        db.rollback()
        return False, e.messages.get("hi_en") or e.messages.get("en", str(e))
    except Exception as e:
        db.rollback()
        logger.error(
            f"pause_push execute failed tenant={tenant_id} days={days}: {e}"
        )
        return False, "Pause fail ho gaya. Phir se try karein."

    return True, result.snippet.get("hi_en") or result.snippet.get("en", "Done.")
