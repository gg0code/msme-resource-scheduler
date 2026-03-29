"""
FILE:    whatsapp_actions.py
PATH:    backend/app/services/whatsapp_actions.py
PURPOSE: Confirmation state machine for WhatsApp write actions.

         When the AI detects that a factory owner wants to make a change
         (mark someone absent, create a job, update a status), we do NOT
         execute it immediately. Instead we:
           1. Show the owner what we are about to do
           2. Wait for them to confirm (HAAN/yes/ok) or cancel (NAHI/no)
           3. Only then write to the database

         This prevents accidental changes — a factory owner might say
         "Ravi absent hai" as a statement, not necessarily as a command.
         The confirmation step makes the intent explicit.

         State machine states:
           IDLE                — no pending action, normal conversation
           PENDING_CONFIRMATION — action proposed, waiting for owner reply
           CONFIRMED           — owner confirmed, executing DB write
           CANCELLED           — owner cancelled or timeout occurred

         Pending actions are stored in Redis alongside the session history.
         They expire after CONFIRMATION_TIMEOUT_SECONDS (5 minutes).
         If the owner does not reply within 5 minutes, the action is
         auto-cancelled and they must ask again.

BRANCH:  v5-whatsapp
VERSION: v5.3
CREATED: 2026-03

DEPENDENCIES:
  app/models/whatsapp.py     — WhatsAppConversation for logging
  app/services/whatsapp_session.py — Redis client for storing pending actions
  app/database.py            — AsyncSession for DB writes
  redis (pip package)        — already installed for whatsapp_session.py

USAGE:
  from app.services.whatsapp_actions import (
      store_pending_action, get_pending_action,
      clear_pending_action, is_confirmation, is_cancellation,
      build_confirmation_prompt
  )

  # When AI returns a write intent — store it and ask for confirmation
  await store_pending_action(phone_number, action_type, action_params)
  confirmation_text = build_confirmation_prompt(action_type, action_params)

  # When next message arrives — check if it is a confirmation or cancellation
  if is_confirmation(message):
      pending = await get_pending_action(phone_number)
      if pending:
          await execute_action(pending, db)
          await clear_pending_action(phone_number)
  elif is_cancellation(message):
      await clear_pending_action(phone_number)
"""

import json
import logging
from datetime import datetime
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

# Import the Redis client from whatsapp_session.py — we reuse the same
# connection pool rather than creating a second Redis connection.
from app.services.whatsapp_session import redis_client, _mock_sessions

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

# Redis key prefix for pending actions — separate from session keys.
# Full key format: whatsapp:pending_action:+919876543210
PENDING_ACTION_KEY_PREFIX = "whatsapp:pending_action"


# ---------------------------------------------------------------------------
# ACTION TYPES — all supported write actions
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    """
    All write actions that require confirmation before DB execution.

    Each action type maps to a specific DB operation in execute_action().
    Using an Enum prevents typos and makes the code self-documenting.
    """
    MARK_ABSENT      = "mark_absent"       # Mark an employee absent for a date
    CREATE_JOB       = "create_job"        # Create a new job
    UPDATE_JOB_STATUS = "update_job_status" # Change a job's status
    RESCHEDULE_JOB   = "reschedule_job"    # Change a job's start/end date
    MARK_MAINTENANCE = "mark_maintenance"  # Mark a machine under maintenance


# ---------------------------------------------------------------------------
# CONFIRMATION AND CANCELLATION WORD LISTS
# ---------------------------------------------------------------------------

# Words the owner can type to CONFIRM a pending action.
# Covers Hindi, Hinglish, and English variations.
# All lowercase — we compare against lowercased input.
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

    Called when the AI detects a write intent. The action is stored
    with a 5-minute TTL. If the owner does not confirm within 5 minutes,
    Redis auto-deletes it and the action is cancelled.

    Args:
        phone_number:  E.164 format phone number e.g. +919876543210
        action_type:   The type of action to perform e.g. ActionType.MARK_ABSENT
        action_params: Parameters for the action e.g. {"employee_name": "Ravi",
                       "date": "2026-03-29", "employee_id": 5}

    Returns:
        True if stored successfully, False if storage failed.

    Side effects:
        Writes to Redis or _mock_sessions with CONFIRMATION_TIMEOUT_SECONDS TTL.
    """
    pending_key = _build_pending_action_key(phone_number)

    # Build the pending action record with all data needed to execute it later
    pending_action = {
        "action_type":   action_type.value,  # Store string value not Enum object
        "action_params": action_params,
        "proposed_at":   datetime.utcnow().isoformat(),  # When action was proposed
        "phone_number":  phone_number
    }

    # Serialise to JSON for Redis storage
    action_json = json.dumps(pending_action, ensure_ascii=False)

    # Mock mode — store in memory dict
    if redis_client is None:
        _mock_sessions[pending_key] = action_json
        logger.info(
            f"Mock: Pending action stored for ****{phone_number[-4:]} — "
            f"action={action_type.value}, params={action_params}"
        )
        return True

    # Real Redis mode — store with TTL so it auto-expires
    try:
        await redis_client.set(
            pending_key,
            action_json,
            ex=CONFIRMATION_TIMEOUT_SECONDS  # Auto-cancel after 5 minutes
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

    Called when an owner sends a message — we check if there is a
    pending action waiting for their confirmation.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210

    Returns:
        Dict with action_type, action_params, proposed_at, phone_number.
        None if no pending action exists or TTL has expired.

    Side effects:
        None — read only.
    """
    pending_key = _build_pending_action_key(phone_number)

    # Mock mode — read from memory dict
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
    the owner cancels, or when a new unrelated message arrives.

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

    # Real Redis mode
    try:
        await redis_client.delete(pending_key)
        logger.info(
            f"Pending action cleared for ****{phone_number[-4:]}"
        )
        return True

    except Exception as e:
        logger.error(
            f"Failed to clear pending action for ****{phone_number[-4:]}. "
            f"Error: {e}"
        )
        return False


# ---------------------------------------------------------------------------
# MESSAGE INTENT DETECTION
# ---------------------------------------------------------------------------

def is_confirmation(message: str) -> bool:
    """
    Check if a message is a confirmation of a pending action.

    Matches against CONFIRMATION_WORDS list — covers Hindi, Hinglish,
    and English confirmation phrases.

    Args:
        message: Raw message text from the factory owner.

    Returns:
        True if the message clearly confirms a pending action.
        False otherwise — when in doubt, do not confirm.

    Side effects:
        None — pure function.
    """
    # Normalise: lowercase and strip whitespace for comparison
    normalised = message.lower().strip()

    # Check exact match first — most common case (single word like "haan")
    if normalised in CONFIRMATION_WORDS:
        return True

    # Check if message starts with a confirmation word followed by more text
    # e.g. "haan kar do" or "yes please"
    for word in CONFIRMATION_WORDS:
        if normalised.startswith(word + " "):
            return True

    return False


def is_cancellation(message: str) -> bool:
    """
    Check if a message is a cancellation of a pending action.

    Matches against CANCELLATION_WORDS list — covers Hindi, Hinglish,
    and English cancellation phrases.

    Args:
        message: Raw message text from the factory owner.

    Returns:
        True if the message clearly cancels a pending action.
        False otherwise.

    Side effects:
        None — pure function.
    """
    normalised = message.lower().strip()

    # Check exact match
    if normalised in CANCELLATION_WORDS:
        return True

    # Check if message starts with a cancellation word
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

    This message is sent BEFORE executing any write action. The owner
    must reply with a confirmation word before anything is written to the DB.

    The message is written in Hinglish — works for Hindi, Hinglish,
    and English speakers. Factory owners understand it regardless of
    their preferred language.

    Args:
        action_type:   The type of action being proposed.
        action_params: Parameters for the action — used to fill in specifics.

    Returns:
        Plain text confirmation message ready to send via WhatsApp.
        Always ends with the confirmation/cancellation options.

    Side effects:
        None — pure function.
    """

    # Build action-specific description
    if action_type == ActionType.MARK_ABSENT:
        employee_name = action_params.get("employee_name", "employee")
        date = action_params.get("date", "aaj")
        description = f"{employee_name} ko {date} ke liye absent mark karna"

    elif action_type == ActionType.CREATE_JOB:
        job_name = action_params.get("job_name", "naya job")
        description = f"'{job_name}' naam ka naya job banana"

    elif action_type == ActionType.UPDATE_JOB_STATUS:
        job_name = action_params.get("job_name", "job")
        new_status = action_params.get("new_status", "update")
        description = f"'{job_name}' ka status '{new_status}' karna"

    elif action_type == ActionType.RESCHEDULE_JOB:
        job_name = action_params.get("job_name", "job")
        new_date = action_params.get("new_date", "nayi date")
        description = f"'{job_name}' ko {new_date} tak reschedule karna"

    elif action_type == ActionType.MARK_MAINTENANCE:
        machine_name = action_params.get("machine_name", "machine")
        description = f"'{machine_name}' ko maintenance mode mein daalna"

    else:
        # Fallback for any action type not explicitly handled above
        description = f"'{action_type.value}' action execute karna"

    # Build the full confirmation message
    # Format is consistent across all action types so owners learn the pattern
    confirmation_message = (
        f"Kya main ye karna chahta hoon:\n"
        f"{description}\n\n"
        f"Confirm karne ke liye: HAAN\n"
        f"Cancel karne ke liye: NAHI\n"
        f"(5 minute mein reply nahi kiya toh automatically cancel ho jayega)"
    )

    return confirmation_message


# ---------------------------------------------------------------------------
# ACTION EXECUTOR
# ---------------------------------------------------------------------------

async def execute_action(
    pending_action: dict,
    db: AsyncSession,
    tenant_id: int
) -> tuple[bool, str]:
    """
    Execute a confirmed write action against the database.

    Called only AFTER the owner has confirmed with a confirmation word.
    Never called directly — always called via the confirmation flow
    in routers/whatsapp.py.

    Args:
        pending_action: The action dict retrieved from get_pending_action().
                        Contains action_type, action_params, phone_number.
        db:             AsyncSession from FastAPI dependency injection.
        tenant_id:      The tenant making the request — for DB isolation.

    Returns:
        Tuple of (success: bool, message: str).
        success = True if DB write succeeded.
        message = Human-readable result to send back to the owner.

    Side effects:
        Writes to PostgreSQL. This is the ONLY place in the WhatsApp
        codebase that writes to the main application database.
    """

    action_type = pending_action.get("action_type")
    action_params = pending_action.get("action_params", {})

    logger.info(
        f"Executing confirmed action: {action_type} "
        f"for tenant_id={tenant_id}, params={action_params}"
    )

    try:
        if action_type == ActionType.MARK_ABSENT.value:
            return await _execute_mark_absent(action_params, db, tenant_id)

        elif action_type == ActionType.UPDATE_JOB_STATUS.value:
            return await _execute_update_job_status(action_params, db, tenant_id)

        elif action_type == ActionType.RESCHEDULE_JOB.value:
            return await _execute_reschedule_job(action_params, db, tenant_id)

        elif action_type == ActionType.MARK_MAINTENANCE.value:
            return await _execute_mark_maintenance(action_params, db, tenant_id)

        else:
            # Unknown action type — should never happen but handle gracefully
            logger.error(
                f"Unknown action type '{action_type}' — cannot execute. "
                f"This action type is not implemented in execute_action()."
            )
            return False, "Ye action abhi supported nahi hai. Admin se contact karein."

    except Exception as e:
        logger.error(
            f"Action execution failed for {action_type}: {e}. "
            f"DB write was NOT completed. Owner should try again."
        )
        return False, "Kuch gadbad ho gayi. Action complete nahi hua. Dobara try karein."


# ---------------------------------------------------------------------------
# PRIVATE ACTION EXECUTORS — one function per action type
# ---------------------------------------------------------------------------
# Each function handles exactly one DB write operation.
# Adding a new action type = add a new function here + add to ActionType enum
# + add to build_confirmation_prompt() + add to execute_action() dispatcher.

async def _execute_mark_absent(
    params: dict,
    db: AsyncSession,
    tenant_id: int
) -> tuple[bool, str]:
    """
    Mark an employee as absent for a specific date.

    Args:
        params:    Must contain 'employee_id' (int) and 'date' (YYYY-MM-DD string).
                   Optional: 'employee_name' for the confirmation message.
        db:        AsyncSession for DB write.
        tenant_id: For row-level isolation — ensures we only update
                   employees belonging to this tenant.

    Returns:
        (True, success_message) if marked successfully.
        (False, error_message) if employee not found or DB write failed.
    """
    from sqlalchemy import update
    from app.models.employee import Employee

    employee_id = params.get("employee_id")
    date_str = params.get("date")
    employee_name = params.get("employee_name", "Employee")

    # Validate required parameters are present
    if not employee_id or not date_str:
        return False, (
            "Employee ID ya date missing hai. "
            "Dobara poochein: 'Ravi ko aaj absent mark karo'"
        )

    # Update employee status — filter by both employee_id AND tenant_id
    # The tenant_id filter is critical — prevents one factory from
    # modifying another factory's employee data.
    result = await db.execute(
        update(Employee)
        .where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id  # Row-level isolation
        )
        .values(status="absent")
    )
    await db.commit()

    # rows_matched tells us if the employee was found and updated
    if result.rowcount == 0:
        return False, (
            f"Employee ID {employee_id} nahi mila. "
            f"Shayad already absent hai ya account mein nahi hai."
        )

    logger.info(
        f"Employee {employee_id} marked absent for tenant {tenant_id} "
        f"on date {date_str}"
    )

    return True, (
        f"Done. {employee_name} ko {date_str} ke liye absent mark kar diya gaya."
    )


async def _execute_update_job_status(
    params: dict,
    db: AsyncSession,
    tenant_id: int
) -> tuple[bool, str]:
    """
    Update the status of a job.

    Args:
        params:    Must contain 'job_id' (int) and 'new_status' (string).
                   Optional: 'job_name' for the confirmation message.
        db:        AsyncSession for DB write.
        tenant_id: For row-level isolation.

    Returns:
        (True, success_message) or (False, error_message).
    """
    from sqlalchemy import update
    from app.models.job import Job

    job_id = params.get("job_id")
    new_status = params.get("new_status")
    job_name = params.get("job_name", f"Job #{job_id}")

    if not job_id or not new_status:
        return False, (
            "Job ID ya status missing hai. "
            "Dobara poochein: 'Job #5 ka status complete karo'"
        )

    result = await db.execute(
        update(Job)
        .where(
            Job.id == job_id,
            Job.tenant_id == tenant_id  # Row-level isolation
        )
        .values(status=new_status)
    )
    await db.commit()

    if result.rowcount == 0:
        return False, (
            f"Job ID {job_id} nahi mila ya aapke account mein nahi hai."
        )

    return True, f"Done. '{job_name}' ka status '{new_status}' kar diya gaya."


async def _execute_reschedule_job(
    params: dict,
    db: AsyncSession,
    tenant_id: int
) -> tuple[bool, str]:
    """
    Reschedule a job to a new start date.

    Args:
        params:    Must contain 'job_id' (int) and 'new_start_date' (YYYY-MM-DD).
                   Optional: 'job_name', 'new_end_date'.
        db:        AsyncSession for DB write.
        tenant_id: For row-level isolation.

    Returns:
        (True, success_message) or (False, error_message).
    """
    from sqlalchemy import update
    from datetime import date
    from app.models.job import Job

    job_id = params.get("job_id")
    new_start_date = params.get("new_start_date")
    new_end_date = params.get("new_end_date")
    job_name = params.get("job_name", f"Job #{job_id}")

    if not job_id or not new_start_date:
        return False, (
            "Job ID ya nayi date missing hai. "
            "Dobara poochein: 'Job #5 ko 5 April tak reschedule karo'"
        )

    # Build update values — end date is optional
    update_values = {"start_date": new_start_date}
    if new_end_date:
        update_values["end_date"] = new_end_date

    result = await db.execute(
        update(Job)
        .where(
            Job.id == job_id,
            Job.tenant_id == tenant_id
        )
        .values(**update_values)
    )
    await db.commit()

    if result.rowcount == 0:
        return False, f"Job ID {job_id} nahi mila ya aapke account mein nahi hai."

    return True, (
        f"Done. '{job_name}' ab {new_start_date} se shuru hoga."
    )


async def _execute_mark_maintenance(
    params: dict,
    db: AsyncSession,
    tenant_id: int
) -> tuple[bool, str]:
    """
    Mark a machine as under maintenance.

    Args:
        params:    Must contain 'machine_id' (int).
                   Optional: 'machine_name'.
        db:        AsyncSession for DB write.
        tenant_id: For row-level isolation.

    Returns:
        (True, success_message) or (False, error_message).
    """
    from sqlalchemy import update
    from app.models.machine import Machine

    machine_id = params.get("machine_id")
    machine_name = params.get("machine_name", f"Machine #{machine_id}")

    if not machine_id:
        return False, (
            "Machine ID missing hai. "
            "Dobara poochein: 'Machine #3 ko maintenance mein daalo'"
        )

    result = await db.execute(
        update(Machine)
        .where(
            Machine.id == machine_id,
            Machine.tenant_id == tenant_id
        )
        .values(status="maintenance")
    )
    await db.commit()

    if result.rowcount == 0:
        return False, f"Machine ID {machine_id} nahi mila ya aapke account mein nahi hai."

    return True, (
        f"Done. '{machine_name}' ko maintenance mode mein dal diya gaya. "
        f"Is machine par scheduled jobs affected ho sakte hain."
    )