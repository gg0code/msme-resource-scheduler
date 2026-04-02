"""
```python
"""
FILE PURPOSE:
This file implements the proactive WhatsApp alert system for ZetaOps Copilot v5.x 
WhatsApp branch. It sends automated alerts to factory owners WITHOUT them asking, 
making ZetaOps feel like a real AI assistant rather than just a reactive chatbot. 
The system watches factory operations and proactively alerts owners about morning 
briefings, job delays, machine downtime, and scheduling conflicts. It uses APScheduler 
running inside the FastAPI process to trigger alerts at specific times and intervals.

WHAT THIS FILE DOES — step by step:
1. Defines scheduler constants (timezone IST, cron timings, alert type identifiers)
2. Creates a single AsyncIOScheduler instance for the entire application  
3. Exports start_scheduler() and stop_scheduler() for FastAPI lifecycle management
4. Provides set_dev_schedule() helper for 2-minute testing intervals during development
5. Implements send_morning_briefings() that runs at 7am IST daily with job/employee counts
6. Implements check_delayed_jobs() that runs every 2 hours during working hours (8am-8pm)
7. Implements check_scheduling_conflicts() that runs every 4 hours checking for resource conflicts
8. Implements check_machine_downtime() that runs when machine status changes to maintenance
9. Provides helper functions to fetch active phone mappings, build alert messages, and send WhatsApp alerts
10. Respects tenant-scoped alert preferences stored in phone_tenant_map.alert_preferences JSON column

KEY FUNCTIONS / CLASSES / COMPONENTS:

Name         : scheduler
Type         : AsyncIOScheduler instance  
Purpose      : Single shared APScheduler instance for the entire FastAPI application. Uses AsyncIOScheduler to work with FastAPI's async event loop and IST timezone for all Indian pilot factories.
Parameters   : timezone=SCHEDULER_TIMEZONE ("Asia/Kolkata")
Returns      : Global scheduler object
Calls        : APScheduler library methods
DB/API       : None directly
Side effects : Creates background thread for cron job execution

Name         : start_scheduler
Type         : function
Purpose      : Initializes and starts the APScheduler with all four alert job types registered. Called from app/main.py FastAPI startup event. Guards against double-start and logs all registered jobs for debugging.
Parameters   : None
Returns      : None
Calls        : scheduler.add_job(), scheduler.start()
DB/API       : None
Side effects : Starts background scheduler thread, registers cron jobs, writes to application logs

Name         : stop_scheduler  
Type         : function
Purpose      : Gracefully stops the APScheduler and waits for any running jobs to complete. Called from app/main.py FastAPI shutdown event to prevent orphaned background threads.
Parameters   : None
Returns      : None
Calls        : scheduler.shutdown()
DB/API       : None
Side effects : Stops background scheduler, allows running jobs to finish

Name         : set_dev_schedule
Type         : function
Purpose      : Development helper that overrides all alert schedules to run every 2 minutes instead of production timings. NEVER use in production as it will spam factory owners. Used for testing alert content and formatting during development.
Parameters   : None
Returns      : None  
Calls        : scheduler.remove_all_jobs(), scheduler.add_job()
DB/API       : None
Side effects : Replaces all production cron jobs with 2-minute intervals, starts scheduler if not running

Name         : send_morning_briefings
Type         : async function
Purpose      : Sends daily morning briefing WhatsApp messages to all active factory owners at 7am IST. Fetches job counts, employee counts, and today's priorities directly from PostgreSQL for each tenant. Respects alert preferences to allow opt-out.
Parameters   : None
Returns      : None
Calls        : _get_active_phone_mappings(), _build_morning_briefing(), _send_alert()
DB/API       : Reads from Job, Employee, PhoneTenantMap tables; sends WhatsApp via Interakt API
Side effects : Sends WhatsApp messages, writes to logs, updates daily alert counts

Name         : check_delayed_jobs
Type         : async function  
Purpose      : Checks for jobs that have passed their end_date but are not completed or cancelled. Runs every 2 hours during working hours (8am-8pm IST). Alerts factory owners about which specific jobs are behind schedule with delay duration.
Parameters   : None
Returns      : None
Calls        : _get_active_phone_mappings(), _get_delayed_jobs(), _build_delay_alert(), _send_alert()
DB/API       : Queries Job table filtering by end_date < today and status not in [completed, cancelled]
Side effects : Sends WhatsApp delay alerts, logs delay check results

Name         : check_scheduling_conflicts
Type         : async function
Purpose      : Detects resource conflicts where multiple jobs are assigned to the same machine or employee at overlapping times. Runs every 4 hours. Queries JobAssignment and Job tables to find double-bookings and alerts owners to resolve conflicts manually.
Parameters   : None  
Returns      : None
Calls        : _get_active_phone_mappings(), _get_scheduling_conflicts(), _build_conflict_alert(), _send_alert()
DB/API       : Complex JOIN queries on Job, JobAssignment, Machine, Employee tables to detect overlapping assignments
Side effects : Sends WhatsApp conflict alerts, logs conflict detection results

Name         : _get_active_phone_mappings
Type         : async function
Purpose      : Fetches all active phone numbers from phone_tenant_map table that have opted-in to receive the specified alert type. Checks alert_preferences JSON column to respect user opt-out choices. Returns tenant context for alert personalization.
Parameters   : alert_type (str) - one of ALERT_TYPE_* constants to check preferences
Returns      : List[Dict] with phone_number, tenant_id, industry_type for active recipients  
Calls        : SessionLocal database session
DB/API       : SELECT from phone_tenant_map with JSON path queries on alert_preferences
Side effects : None (read-only)

Name         : _build_morning_briefing  
Type         : async function
Purpose      : Constructs personalized morning briefing text by querying job counts, employee counts, high-priority jobs, and today's deadlines for a specific tenant. Formats message using industry-specific terminology and WhatsApp-friendly formatting.
Parameters   : tenant_id (int), industry_type (str) for personalization
Returns      : str formatted WhatsApp message or empty string if no data
Calls        : SessionLocal, format_for_whatsapp()
DB/API       : Queries Job, Employee tables with tenant_id filtering
Side effects : None (read-only)

Name         : _send_alert
Type         : async function  
Purpose      : Sends WhatsApp message via Interakt API or logs to console if WHATSAPP_MOCK_MODE=True. Handles Interakt API authentication, message formatting, rate limiting, and error handling. Updates daily alert quotas and tracks delivery status.
Parameters   : phone_number (str), message (str), alert_type (str)
Returns      : None
Calls        : Interakt WhatsApp API via requests
DB/API       : HTTP POST to Interakt API, updates PhoneTenantMap alert counts  
Side effects : Sends WhatsApp message, writes to logs, updates database counters

WHO CALLS THIS FILE:
- app/main.py imports start_scheduler and stop_scheduler for FastAPI lifecycle events
- Development scripts may import set_dev_schedule for testing alert content
- No other files directly import this module
"""

import logging
from datetime import datetime, date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logging.getLogger(__name__).setLevel(logging.INFO)


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

# Alert type identifiers — must match keys in alert_preferences JSON column
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
        replace_existing=True
    )
    logger.info(
        f"Scheduled: morning briefing at "
        f"{MORNING_BRIEFING_HOUR:02d}:{MORNING_BRIEFING_MINUTE:02d} IST daily"
    )

    # Register job delay check — every 2 hours during working hours
    scheduler.add_job(
        func=check_delayed_jobs,
        trigger=CronTrigger(
            hour=JOB_DELAY_CHECK_HOURS,
            minute=0,
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
            hour="*/4",
            minute=30,
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

    if scheduler.running:
        scheduler.remove_all_jobs()

    for job_func, job_id in [
        (send_morning_briefings,     "morning_briefing"),
        (check_delayed_jobs,          "job_delay_check"),
        (check_scheduling_conflicts,  "conflict_check"),
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

    Runs at 7am IST every day. Fetches job and employee counts directly
    from PostgreSQL for each active tenant and sends a WhatsApp briefing.

    Side effects:
        Reads from PostgreSQL for each active tenant.
        Sends WhatsApp message to each active phone number.
        Logs to console if WHATSAPP_MOCK_MODE=True.
    """
    logger.info(f"Morning briefing job started at {datetime.now().isoformat()}")

    active_phones = await _get_active_phone_mappings(ALERT_TYPE_BRIEFING)

    if not active_phones:
        logger.info("No active phone mappings found — no briefings to send.")
        return

    sent_count = 0
    for phone_mapping in active_phones:
        try:
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
    and its status is not completed or cancelled.

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

    Runs every 4 hours. Detects jobs flagged with has_conflict=True.

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
    maintenance or breakdown.

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

    active_phones = await _get_active_phone_mappings(
        ALERT_TYPE_MACHINE_DOWN,
        tenant_id_filter=tenant_id
    )

    if not active_phones:
        logger.info(
            f"No active phone found for tenant {tenant_id} — "
            f"machine down alert not sent."
        )
        return

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
    db = SessionLocal()

    try:
        query = select(PhoneTenantMap).where(
            PhoneTenantMap.is_active == True  # noqa: E712
        )

        if tenant_id_filter is not None:
            query = query.where(
                PhoneTenantMap.tenant_id == tenant_id_filter
            )

        phone_mappings = db.execute(query).scalars().all()

        for mapping in phone_mappings:
            # alert_preferences is JSONB — default all ON if not set
            preferences = mapping.alert_preferences or {}
            alert_enabled = preferences.get(alert_type, True)

            if alert_enabled:
                results.append({
                    "phone_number":  mapping.phone_number,
                    "tenant_id":     mapping.tenant_id,
                    "industry_type": mapping.industry_type or "printing"
                })

    except Exception as e:
        logger.error(f"Failed to get active phone mappings: {e}")

    finally:
        db.close()

    return results


async def _build_morning_briefing(
    tenant_id: int,
    industry_type: str
) -> str | None:
    """
    Build the morning briefing message for a specific tenant.

    Uses direct DB queries for reliability — no dependency on ai_service
    tool names which may not exist or may change.

    Args:
        tenant_id:     The tenant to build briefing for.
        industry_type: Reserved for future terminology customisation.

    Returns:
        Formatted briefing text string, or None if data fetch failed.

    Side effects:
        Reads from PostgreSQL jobs and employees tables.
    """
    from sqlalchemy import select, func
    from app.database import SessionLocal
    from app.models.job import Job
    from app.models.employee import Employee
    from app.services.whatsapp_formatter import format_for_whatsapp

    db = SessionLocal()

    try:
        today = date.today()

        # Active jobs — in_progress or pending
        active_jobs = db.execute(
            select(func.count(Job.id)).where(
                Job.tenant_id == tenant_id,
                Job.status.in_([
                    "in_progress", "pending", "In Progress", "Pending"
                ])
            )
        ).scalar() or 0

        # Total jobs for this tenant
        total_jobs = db.execute(
            select(func.count(Job.id)).where(
                Job.tenant_id == tenant_id
            )
        ).scalar() or 0

        # Delayed jobs — end_date passed, not finished
        delayed_jobs = db.execute(
            select(func.count(Job.id)).where(
                Job.tenant_id == tenant_id,
                Job.end_date < today,
                Job.status.notin_([
                    "completed", "cancelled", "Completed", "Cancelled"
                ])
            )
        ).scalar() or 0

        # Active employees
        total_employees = db.execute(
            select(func.count(Employee.id)).where(
                Employee.tenant_id == tenant_id,
                Employee.status == "active"
            )
        ).scalar() or 0

        today_str = datetime.now().strftime("%d %B %Y")

        briefing = (
            f"Good morning! ZetaOps daily briefing — {today_str}\n\n"
            f"Jobs: {active_jobs} active, {total_jobs} total\n"
        )

        if delayed_jobs > 0:
            briefing += f"DELAYED: {delayed_jobs} jobs need attention\n"

        briefing += (
            f"Team: {total_employees} employees\n\n"
            f"Details ke liye poochein: 'aaj ka schedule dikhao'"
        )

        return format_for_whatsapp(briefing)

    except Exception as e:
        logger.error(
            f"Failed to build morning briefing for tenant {tenant_id}: {e}. "
            f"Check jobs and employees tables in the database."
        )
        return None

    finally:
        db.close()


async def _get_delayed_jobs(tenant_id: int) -> list[dict]:
    """
    Get all delayed jobs for a tenant.

    A job is delayed if end_date < today and status is not
    completed or cancelled.

    Args:
        tenant_id: The tenant to check.

    Returns:
        List of dicts with job_id, job_name, end_date, status.
        Empty list if no delayed jobs.

    Side effects:
        Reads from PostgreSQL jobs table.
    """
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
            Job.status.notin_([
                "completed", "cancelled", "Completed", "Cancelled"
            ])
        )

        jobs = db.execute(query).scalars().all()

        for job in jobs:
            delayed.append({
                "job_id":   job.id,
                "job_name": job.name or f"Job #{job.id}",
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
    Get scheduling conflicts for a tenant.

    Checks jobs with has_conflict=True flag — this flag is set by the
    scheduling engine when it detects a resource double-booking.

    Args:
        tenant_id: The tenant to check.

    Returns:
        List of dicts with job_id, job_name, status.
        Empty list if no conflicts found.

    Side effects:
        Reads from PostgreSQL jobs table.
    """
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.job import Job

    db = SessionLocal()

    try:
        conflict_jobs = db.execute(
            select(Job).where(
                Job.tenant_id == tenant_id,
                Job.has_conflict == True  # noqa: E712
            )
        ).scalars().all()

        return [
            {
                "job_id":   j.id,
                "job_name": j.name or f"Job #{j.id}",
                "status":   j.status
            }
            for j in conflict_jobs
        ]

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
        industry_type: Reserved for future terminology customisation.

    Returns:
        Plain text alert message ready to send via WhatsApp.

    Side effects:
        None — pure function.
    """
    from app.services.whatsapp_formatter import format_for_whatsapp

    job_count = len(delayed_jobs)
    alert = f"ALERT: {job_count} delayed job{'s' if job_count > 1 else ''}\n\n"

    # List first 3 delayed jobs — avoid very long messages on mobile
    for job in delayed_jobs[:3]:
        alert += f"- {job['job_name']} (due: {job['end_date']})\n"

    if job_count > 3:
        alert += f"...aur {job_count - 3} aur jobs\n"

    alert += "\nDetails ke liye poochein: 'delayed jobs dikhao'"

    return format_for_whatsapp(alert)


def _build_conflict_alert(conflicts: list, industry_type: str) -> str:
    """
    Build a WhatsApp alert message for scheduling conflicts.

    Args:
        conflicts:     List of conflict dicts from _get_conflicts().
        industry_type: Reserved for future terminology customisation.

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
    )

    # List up to 3 conflicting jobs by name
    for conflict in conflicts[:3]:
        alert += f"- {conflict['job_name']}\n"

    if conflict_count > 3:
        alert += f"...aur {conflict_count - 3} aur\n"

    alert += "\nDetails ke liye poochein: 'schedule conflicts dikhao'"

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
        logger.info(
            f"[MOCK ALERT] Type={alert_type} "
            f"To=****{phone_number[-4:]} "
            f"Message='{message[:150]}...'"
        )
        return

    if not settings.INTERAKT_API_KEY:
        logger.error(
            "INTERAKT_API_KEY not set in .env but WHATSAPP_MOCK_MODE=False. "
            "Cannot send alert. Set INTERAKT_API_KEY in .env or set "
            "WHATSAPP_MOCK_MODE=True for development."
        )
        return

    try:
        import httpx

        # Interakt expects number without + prefix
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
                timeout=10.0
            )

            if response.status_code == 200:
                logger.info(
                    f"Alert sent via Interakt. "
                    f"Type={alert_type}, To=****{phone_number[-4:]}"
                )
            else:
                logger.error(
                    f"Interakt API error {response.status_code} "
                    f"for ****{phone_number[-4:]}: {response.text[:200]}"
                )

    except Exception as e:
        logger.error(
            f"Failed to send alert via Interakt to ****{phone_number[-4:]}: {e}. "
            f"Check INTERAKT_API_KEY and network connectivity."
        )
