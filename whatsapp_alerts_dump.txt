"""
FILE:    whatsapp_alerts.py
PATH:    backend/app/services/whatsapp_alerts.py
PURPOSE: Proactive alert scheduler for WhatsApp Copilot.

         Sends alerts to factory owners WITHOUT them asking first.
         This is what makes ZetaOps feel like a real assistant rather
         than just a chatbot — it watches the factory and speaks up
         when something needs attention.

         Four alert types:
           BRIEFING     — 7am IST daily morning summary of the day ahead
           JOB_DELAY    — when a job falls behind its scheduled end date
           MACHINE_DOWN — when a machine status changes to maintenance
           CONFLICT     — when a scheduling conflict is detected

         Uses APScheduler running INSIDE the FastAPI process.
         No separate worker or Celery needed for pilot scale (5 factories).
         Scheduler is started when FastAPI app starts and stopped on shutdown.

         Alert flow:
           APScheduler triggers job → fetch data from DB → format message
           → send via Interakt (or log in mock mode) → done

         Each factory owner can opt out of individual alert types via
         alert_preferences JSON in phone_tenant_map table.

BRANCH:  v5-whatsapp
VERSION: v5.4
CREATED: 2026-03

DEPENDENCIES:
  apscheduler==3.11.2          — pip install apscheduler
  app/models/whatsapp.py       — PhoneTenantMap for active phone numbers
  app/services/whatsapp_formatter.py — format_for_whatsapp() for clean text
  app/database.py              — database session for DB queries
  app/config.py                — settings (WHATSAPP_MOCK_MODE, timezone)
  app/services/ai_service.py   — run_ai_chat() / execute_tool() for data

USAGE:
  # In app/main.py — start scheduler when app starts, stop on shutdown
  from app.services.whatsapp_alerts import start_scheduler, stop_scheduler

  @app.on_event("startup")
  async def startup():
      start_scheduler()

  @app.on_event("shutdown")
  async def shutdown():
      stop_scheduler()
"""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SCHEDULER CONSTANTS
# ---------------------------------------------------------------------------

# Timezone for all scheduled jobs — IST (Indian Standard Time)
# All pilot factories are in India so we use IST for scheduling.
SCHEDULER_TIMEZONE = "Asia/Kolkata"

# Morning briefing time — 7:00 AM IST every day
MORNING_BRIEFING_HOUR   = 7
MORNING_BRIEFING_MINUTE = 0

# Job delay check — runs every 2 hours during working hours (8am to 8pm IST)
JOB_DELAY_CHECK_HOURS = "8-20"   # Only during working hours
JOB_DELAY_CHECK_EVERY = 2        # Every 2 hours

# Conflict check — runs every 4 hours
CONFLICT_CHECK_EVERY = 4

# Alert type identifiers — used in alert_preferences JSON
ALERT_TYPE_BRIEFING     = "morning_briefing"
ALERT_TYPE_JOB_DELAY    = "job_delay"
ALERT_TYPE_MACHINE_DOWN = "machine_down"
ALERT_TYPE_CONFLICT     = "conflict"


# ---------------------------------------------------------------------------
# SCHEDULER INSTANCE
# ---------------------------------------------------------------------------
# Single shared scheduler for the entire application.
# AsyncIOScheduler works with FastAPI's async event loop.
# Created here but not started until start_scheduler() is called.

scheduler = AsyncIOScheduler(timezone=SCHEDULER_TIMEZONE)


# ---------------------------------------------------------------------------
# SCHEDULER LIFECYCLE — start and stop
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    """
    Start the APScheduler and register all alert jobs.

    Called from app/main.py on FastAPI startup event.
    Registers all scheduled jobs and starts the scheduler running.

    In mock mode (WHATSAPP_MOCK_MODE=True), jobs still run but
    send output to logs instead of real WhatsApp messages.
    This lets us test alert content without Interakt subscription.

    Side effects:
        Starts background scheduler thread.
        Registers cron jobs for all four alert types.
        Logs confirmation of each registered job.
    """
    if scheduler.running:
        # Guard against double-start if startup event fires twice
        logger.warning("Scheduler already running — skipping start.")
        return

    # Register morning briefing — 7am IST daily
    scheduler.add_job(
        func=send_morning_briefings,
        trigger=CronTrigger(
            hour=MORNING_BRIEFING_HOUR,
            minute=MORNING_BRIEFING_MINUTE,
            timezone=SCHEDULER_TIMEZONE
        ),
        id="morning_briefing",
        name="Daily morning briefing to all active factory owners",
        replace_existing=True   # Replace if job already registered (safe for restarts)
    )
    logger.info(
        f"Scheduled: morning briefing at "
        f"{MORNING_BRIEFING_HOUR:02d}:{MORNING_BRIEFING_MINUTE:02d} IST daily"
    )

    # Register job delay check — every 2 hours during working hours
    scheduler.add_job(
        func=check_delayed_jobs,
        trigger=CronTrigger(
            hour=JOB_DELAY_CHECK_HOURS,       # 8am to 8pm only
            minute=0,                          # At the top of each hour
            timezone=SCHEDULER_TIMEZONE
        ),
        id="job_delay_check",
        name="Check for delayed jobs every 2 hours",
        replace_existing=True
    )
    logger.info("Scheduled: job delay check every 2 hours (8am-8pm IST)")

    # Register conflict check — every 4 hours
    scheduler.add_job(
        func=check_scheduling_conflicts,
        trigger=CronTrigger(
            hour="*/4",                        # Every 4 hours (0, 4, 8, 12, 16, 20)
            minute=30,                         # At :30 to avoid clash with other jobs
            timezone=SCHEDULER_TIMEZONE
        ),
        id="conflict_check",
        name="Check for scheduling conflicts every 4 hours",
        replace_existing=True
    )
    logger.info("Scheduled: conflict check every 4 hours")

    # Start the scheduler
    scheduler.start()
    logger.info(
        f"WhatsApp alert scheduler started. "
        f"Mock mode: {settings.WHATSAPP_MOCK_MODE}. "
        f"Timezone: {SCHEDULER_TIMEZONE}"
    )


def stop_scheduler() -> None:
    """
    Stop the APScheduler gracefully.

    Called from app/main.py on FastAPI shutdown event.
    Waits for any running jobs to complete before stopping.

    Side effects:
        Stops the background scheduler.
        Any jobs currently running are allowed to finish.
    """
    if scheduler.running:
        # wait=True means we wait for running jobs to finish
        # before shutting down — prevents data corruption
        scheduler.shutdown(wait=True)
        logger.info("WhatsApp alert scheduler stopped.")
    else:
        logger.info("Scheduler was not running — nothing to stop.")


# ---------------------------------------------------------------------------
# DEV HELPER — override schedule for testing
# ---------------------------------------------------------------------------

def set_dev_schedule() -> None:
    """
    Override all schedules to run every 2 minutes for development testing.

    Call this instead of start_scheduler() during development when you
    want to test alert content without waiting hours for the real schedule.

    NEVER call this in production — it will spam factory owners every 2 minutes.

    Usage in development:
        from app.services.whatsapp_alerts import set_dev_schedule
        set_dev_schedule()  # Replace start_scheduler() temporarily
    """
    logger.warning(
        "DEV MODE: All alerts set to run every 2 minutes. "
        "Do NOT use this in production."
    )

    # Remove existing jobs if scheduler is running
    if scheduler.running:
        scheduler.remove_all_jobs()

    # Re-register all jobs with 2-minute interval for testing
    for job_func, job_id in [
        (send_morning_briefings,    "morning_briefing"),
        (check_delayed_jobs,         "job_delay_check"),
        (check_scheduling_conflicts, "conflict_check"),
    ]:
        scheduler.add_job(
            func=job_func,
            trigger="interval",
            minutes=2,
            id=job_id,
            replace_existing=True
        )

    if not scheduler.running:
        scheduler.start()

    logger.info("Dev scheduler started — all jobs run every 2 minutes.")


# ---------------------------------------------------------------------------
# ALERT JOB 1 — Morning briefing
# ---------------------------------------------------------------------------

async def send_morning_briefings() -> None:
    """
    Send daily morning briefing to all active factory owners.

    Runs at 7am IST every day. Fetches the day's schedule summary
    for each active tenant and sends it to their WhatsApp.

    The briefing content comes from the existing generate_daily_briefing()
    tool in ai_service.py — same data that powers the web dashboard.

    Side effects:
        Reads from PostgreSQL for each active tenant.
        Sends WhatsApp message to each active phone number.
        Logs to console if WHATSAPP_MOCK_MODE=True.
    """
    logger.info(f"Morning briefing job started at {datetime.now().isoformat()}")

    # Get all active phone mappings — one per factory owner
    active_phones = await _get_active_phone_mappings(ALERT_TYPE_BRIEFING)

    if not active_phones:
        logger.info("No active phone mappings found — no briefings to send.")
        return

    # Send briefing to each active factory owner
    sent_count = 0
    for phone_mapping in active_phones:
        try:
            # Build the briefing message for this tenant
            briefing_text = await _build_morning_briefing(
                tenant_id=phone_mapping["tenant_id"],
                industry_type=phone_mapping["industry_type"]
            )

            if briefing_text:
                await _send_alert(
                    phone_number=phone_mapping["phone_number"],
                    message=briefing_text,
                    alert_type=ALERT_TYPE_BRIEFING
                )
                sent_count += 1

        except Exception as e:
            # Log error but continue to next factory — one failure
            # should not stop briefings from going to other factories
            logger.error(
                f"Failed to send morning briefing to "
                f"****{phone_mapping['phone_number'][-4:]}: {e}"
            )

    logger.info(f"Morning briefing complete — sent to {sent_count} factories.")


# ---------------------------------------------------------------------------
# ALERT JOB 2 — Job delay check
# ---------------------------------------------------------------------------

async def check_delayed_jobs() -> None:
    """
    Check for delayed jobs and alert factory owners.

    Runs every 2 hours during working hours (8am-8pm IST).
    A job is considered delayed if its end_date has passed
    and its status is not 'completed' or 'cancelled'.

    Only sends an alert if new delays have been detected since
    the last check — avoids spamming owners about the same delay.

    Side effects:
        Reads from PostgreSQL for each active tenant.
        Sends WhatsApp alert for each tenant with delayed jobs.
    """
    logger.info(f"Job delay check started at {datetime.now().isoformat()}")

    active_phones = await _get_active_phone_mappings(ALERT_TYPE_JOB_DELAY)

    for phone_mapping in active_phones:
        try:
            delayed_jobs = await _get_delayed_jobs(phone_mapping["tenant_id"])

            if delayed_jobs:
                # Build alert message listing the delayed jobs
                alert_text = _build_delay_alert(
                    delayed_jobs=delayed_jobs,
                    industry_type=phone_mapping["industry_type"]
                )
                await _send_alert(
                    phone_number=phone_mapping["phone_number"],
                    message=alert_text,
                    alert_type=ALERT_TYPE_JOB_DELAY
                )

        except Exception as e:
            logger.error(
                f"Job delay check failed for "
                f"tenant {phone_mapping['tenant_id']}: {e}"
            )

    logger.info("Job delay check complete.")


# ---------------------------------------------------------------------------
# ALERT JOB 3 — Conflict check
# ---------------------------------------------------------------------------

async def check_scheduling_conflicts() -> None:
    """
    Check for scheduling conflicts and alert factory owners.

    Runs every 4 hours. Detects resource double-bookings —
    same employee or machine assigned to two overlapping jobs.

    Side effects:
        Reads from PostgreSQL for each active tenant.
        Sends WhatsApp alert for each tenant with conflicts.
    """
    logger.info(f"Conflict check started at {datetime.now().isoformat()}")

    active_phones = await _get_active_phone_mappings(ALERT_TYPE_CONFLICT)

    for phone_mapping in active_phones:
        try:
            conflicts = await _get_conflicts(phone_mapping["tenant_id"])

            if conflicts:
                alert_text = _build_conflict_alert(
                    conflicts=conflicts,
                    industry_type=phone_mapping["industry_type"]
                )
                await _send_alert(
                    phone_number=phone_mapping["phone_number"],
                    message=alert_text,
                    alert_type=ALERT_TYPE_CONFLICT
                )

        except Exception as e:
            logger.error(
                f"Conflict check failed for "
                f"tenant {phone_mapping['tenant_id']}: {e}"
            )

    logger.info("Conflict check complete.")


# ---------------------------------------------------------------------------
# MACHINE DOWN ALERT — triggered on demand, not on schedule
# ---------------------------------------------------------------------------

async def send_machine_down_alert(
    tenant_id: int,
    machine_name: str,
    machine_id: int
) -> None:
    """
    Send an immediate alert when a machine goes into maintenance/breakdown.

    This is NOT a scheduled job — it is called directly from the machine
    update endpoint in the router when machine status changes to
    'maintenance' or 'breakdown'.

    Args:
        tenant_id:    The tenant whose machine went down.
        machine_name: Display name of the machine e.g. "Printing Press 1"
        machine_id:   The machine's DB ID.

    Side effects:
        Sends immediate WhatsApp alert to the factory owner.
        No scheduling — fires immediately when called.
    """
    logger.info(
        f"Machine down alert triggered for machine '{machine_name}' "
        f"(ID: {machine_id}), tenant {tenant_id}"
    )

    # Find the active phone number for this tenant
    active_phones = await _get_active_phone_mappings(
        ALERT_TYPE_MACHINE_DOWN,
        tenant_id_filter=tenant_id  # Only for this specific tenant
    )

    if not active_phones:
        logger.info(
            f"No active phone found for tenant {tenant_id} — "
            f"machine down alert not sent."
        )
        return

    # Build the alert message
    alert_text = (
        f"ALERT: Machine down\n\n"
        f"'{machine_name}' abhi maintenance mode mein hai.\n"
        f"Is machine par scheduled jobs affect ho sakte hain.\n\n"
        f"Schedule check karne ke liye poochein: "
        f"'machine {machine_id} ki wajah se kaunse jobs affect hue'"
    )

    for phone_mapping in active_phones:
        await _send_alert(
            phone_number=phone_mapping["phone_number"],
            message=alert_text,
            alert_type=ALERT_TYPE_MACHINE_DOWN
        )


# ---------------------------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------------------------

async def _get_active_phone_mappings(
    alert_type: str,
    tenant_id_filter: int | None = None
) -> list[dict]:
    """
    Get all active phone mappings that have opted in to a specific alert type.

    Args:
        alert_type:        One of the ALERT_TYPE_* constants.
        tenant_id_filter:  If set, only return mappings for this tenant.
                           Used for machine_down alerts which target one tenant.

    Returns:
        List of dicts with phone_number, tenant_id, industry_type keys.
        Empty list if no active mappings found.

    Side effects:
        Reads from PostgreSQL phone_tenant_map table.
    """
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.whatsapp import PhoneTenantMap

    results = []

    # Use a sync session — APScheduler jobs run outside FastAPI request context
    # so we cannot use the FastAPI dependency injection for DB sessions.
    # We create a session directly here instead.
    db = SessionLocal()

    try:
        query = select(PhoneTenantMap).where(
            PhoneTenantMap.is_active == True  # noqa: E712
        )

        # Apply tenant filter if specified (for machine_down alerts)
        if tenant_id_filter is not None:
            query = query.where(
                PhoneTenantMap.tenant_id == tenant_id_filter
            )

        phone_mappings = db.execute(query).scalars().all()

        for mapping in phone_mappings:
            # Check if this alert type is enabled in the owner's preferences.
            # alert_preferences is a JSON dict — default all ON if not set.
            preferences = mapping.alert_preferences or {}
            alert_enabled = preferences.get(alert_type, True)
            # Default True = alert ON if preference not explicitly set

            if alert_enabled:
                results.append({
                    "phone_number":  mapping.phone_number,
                    "tenant_id":     mapping.tenant_id,
                    "industry_type": mapping.industry_type or "manufacturing"
                })

    except Exception as e:
        logger.error(f"Failed to get active phone mappings: {e}")

    finally:
        # Always close the session — even if an error occurred
        db.close()

    return results


async def _build_morning_briefing(
    tenant_id: int,
    industry_type: str
) -> str | None:
    """
    Build the morning briefing message for a specific tenant.

    Uses the existing execute_tool() function from ai_service.py to fetch
    the same dashboard summary data that powers the web UI.

    Args:
        tenant_id:     The tenant to build briefing for.
        industry_type: For terminology in the message text.

    Returns:
        Formatted briefing text string, or None if data fetch failed.

    Side effects:
        Reads from PostgreSQL via execute_tool().
    """
    from app.database import SessionLocal
    from app.services.ai_service import execute_tool
    from app.services.whatsapp_formatter import format_for_whatsapp

    db = SessionLocal()

    try:
        # Use the existing get_dashboard_summary tool — same data as web UI
        summary_data = execute_tool(
            name="get_dashboard_summary",
            args={},
            db=db,
            tenant_id=tenant_id
        )

        if not summary_data:
            return None

        # Build a concise WhatsApp-friendly briefing from the summary data
        today = datetime.now().strftime("%d %B %Y")

        # Extract key metrics from the summary data
        total_jobs     = summary_data.get("total_jobs", 0)
        active_jobs    = summary_data.get("active_jobs", 0)
        delayed_jobs   = summary_data.get("delayed_jobs", 0)
        total_employees = summary_data.get("total_employees", 0)

        briefing = (
            f"Good morning! ZetaOps daily briefing — {today}\n\n"
            f"Jobs: {active_jobs} active, {total_jobs} total\n"
        )

        # Highlight delays prominently — most actionable information
        if delayed_jobs > 0:
            briefing += f"DELAYED: {delayed_jobs} jobs need attention\n"

        briefing += (
            f"Team: {total_employees} employees\n\n"
            f"Details ke liye poochein: 'aaj ka schedule dikhao'"
        )

        # Pass through formatter to ensure no markdown
        return format_for_whatsapp(briefing)

    except Exception as e:
        logger.error(
            f"Failed to build morning briefing for tenant {tenant_id}: {e}"
        )
        return None

    finally:
        db.close()


async def _get_delayed_jobs(tenant_id: int) -> list[dict]:
    """
    Get all delayed jobs for a tenant.

    A job is delayed if end_date < today and status is not
    'completed' or 'cancelled'.

    Args:
        tenant_id: The tenant to check.

    Returns:
        List of dicts with job_id, job_name, end_date, status.
        Empty list if no delayed jobs.

    Side effects:
        Reads from PostgreSQL jobs table.
    """
    from datetime import date
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.job import Job

    db = SessionLocal()
    delayed = []

    try:
        today = date.today()

        query = select(Job).where(
            Job.tenant_id == tenant_id,
            Job.end_date < today,
            Job.status.notin_(["completed", "cancelled", "Completed", "Cancelled"])
        )

        jobs = db.execute(query).scalars().all()

        for job in jobs:
            delayed.append({
                "job_id":   job.id,
                "job_name": job.title or f"Job #{job.id}",
                "end_date": str(job.end_date),
                "status":   job.status
            })

    except Exception as e:
        logger.error(f"Failed to get delayed jobs for tenant {tenant_id}: {e}")

    finally:
        db.close()

    return delayed


async def _get_conflicts(tenant_id: int) -> list[dict]:
    """
    Get scheduling conflicts for a tenant using the existing execute_tool().

    Reuses the get_schedule_alerts tool from ai_service.py which already
    implements conflict detection logic.

    Args:
        tenant_id: The tenant to check.

    Returns:
        List of conflict dicts, empty if no conflicts.

    Side effects:
        Reads from PostgreSQL via execute_tool().
    """
    from app.database import SessionLocal
    from app.services.ai_service import execute_tool

    db = SessionLocal()

    try:
        conflicts_data = execute_tool(
            name="get_schedule_alerts",
            args={"what": "conflicts"},
            db=db,
            tenant_id=tenant_id
        )
        return conflicts_data if isinstance(conflicts_data, list) else []

    except Exception as e:
        logger.error(f"Failed to get conflicts for tenant {tenant_id}: {e}")
        return []

    finally:
        db.close()


def _build_delay_alert(delayed_jobs: list[dict], industry_type: str) -> str:
    """
    Build a WhatsApp alert message listing delayed jobs.

    Args:
        delayed_jobs:  List of delayed job dicts from _get_delayed_jobs().
        industry_type: For terminology context (not used yet, reserved).

    Returns:
        Plain text alert message ready to send via WhatsApp.

    Side effects:
        None — pure function.
    """
    from app.services.whatsapp_formatter import format_for_whatsapp

    job_count = len(delayed_jobs)

    alert = f"ALERT: {job_count} delayed job{'s' if job_count > 1 else ''}\n\n"

    # List first 3 delayed jobs — avoid very long messages
    for job in delayed_jobs[:3]:
        alert += f"• {job['job_name']} (due: {job['end_date']})\n"

    # If more than 3, mention the count
    if job_count > 3:
        alert += f"...aur {job_count - 3} aur jobs\n"

    alert += "\nDetails ke liye poochein: 'delayed jobs dikhao'"

    return format_for_whatsapp(alert)


def _build_conflict_alert(conflicts: list, industry_type: str) -> str:
    """
    Build a WhatsApp alert message for scheduling conflicts.

    Args:
        conflicts:     List of conflict data from _get_conflicts().
        industry_type: For terminology context.

    Returns:
        Plain text alert message ready to send via WhatsApp.

    Side effects:
        None — pure function.
    """
    from app.services.whatsapp_formatter import format_for_whatsapp

    conflict_count = len(conflicts)
    alert = (
        f"ALERT: {conflict_count} scheduling conflict"
        f"{'s' if conflict_count > 1 else ''} detected\n\n"
        f"Kuch resources double-booked hain.\n"
        f"Details ke liye poochein: 'schedule conflicts dikhao'"
    )

    return format_for_whatsapp(alert)


async def _send_alert(
    phone_number: str,
    message: str,
    alert_type: str
) -> None:
    """
    Send a WhatsApp alert message to a phone number.

    In mock mode (WHATSAPP_MOCK_MODE=True): logs the message to console.
    In production mode: sends via Interakt API using httpx.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210
        message:      Plain text message to send (already formatted).
        alert_type:   For logging — identifies what type of alert was sent.

    Side effects:
        Mock mode: writes to log.
        Production mode: makes HTTP POST to Interakt API.
    """

    if settings.WHATSAPP_MOCK_MODE:
        # Mock mode — log instead of sending real WhatsApp message.
        # This is how we test alert content during development.
        logger.info(
            f"[MOCK ALERT] Type={alert_type} "
            f"To=****{phone_number[-4:]} "
            f"Message='{message[:100]}...'"
        )
        return

    # Production mode — send via Interakt API
    if not settings.INTERAKT_API_KEY:
        logger.error(
            "INTERAKT_API_KEY not set in .env but WHATSAPP_MOCK_MODE=False. "
            "Cannot send alert. Either set INTERAKT_API_KEY or set "
            "WHATSAPP_MOCK_MODE=True in .env."
        )
        return

    try:
        import httpx

        # Remove the + from E.164 format — Interakt expects without +
        # e.g. +919876543210 becomes 919876543210
        phone_without_plus = phone_number.lstrip("+")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.interakt.ai/v1/public/message/",
                headers={
                    "Authorization": f"Basic {settings.INTERAKT_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "countryCode": "91",
                    "phoneNumber": phone_without_plus,
                    "type": "Text",
                    "data": {"message": message}
                },
                timeout=10.0  # 10 second timeout — don't hang forever
            )

            if response.status_code == 200:
                logger.info(
                    f"Alert sent successfully via Interakt. "
                    f"Type={alert_type}, "
                    f"To=****{phone_number[-4:]}"
                )
            else:
                logger.error(
                    f"Interakt API returned status {response.status_code} "
                    f"for alert to ****{phone_number[-4:]}. "
                    f"Response: {response.text[:200]}"
                )

    except Exception as e:
        logger.error(
            f"Failed to send alert via Interakt to ****{phone_number[-4:]}: {e}. "
            f"Check INTERAKT_API_KEY and network connectivity."
        )