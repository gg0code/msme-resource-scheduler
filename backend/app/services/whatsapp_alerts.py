# app/services/whatsapp_alerts.py — Version 2.0
# Branch: v5-whatsapp
#
# ─────────────────────────────────────────────────────────────────────────────
# FILE PURPOSE
# ─────────────────────────────────────────────────────────────────────────────
# Proactive WhatsApp alert system for ZetaOps factory owners.
#
# Runs three scheduled background jobs using APScheduler:
#   1. Morning briefing   — 7:00 AM IST daily
#   2. Job delay check    — every 2 hours during working hours (8am–8pm IST)
#   3. Conflict check     — every 4 hours
#
# Also handles one on-demand alert:
#   4. Machine down alert — triggered immediately when a machine goes offline
#
# In WHATSAPP_MOCK_MODE=True (development): all alerts are logged to console
# as [MOCK ALERT] lines instead of sending real WhatsApp messages.
# In production: sends via Interakt API.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHO CALLS THIS FILE
# ─────────────────────────────────────────────────────────────────────────────
# app/main.py
#   — calls start_scheduler() on FastAPI startup event
#   — calls stop_scheduler() on FastAPI shutdown event
#
# app/routers/whatsapp.py
#   — POST /api/v1/whatsapp/trigger-dev-alerts
#     calls send_morning_briefings(), check_delayed_jobs(),
#     check_scheduling_conflicts() directly for dev testing
#
# app/routers/machines.py (planned)
#   — calls send_machine_down_alert() when machine status → maintenance/breakdown
#
# ─────────────────────────────────────────────────────────────────────────────
# WHAT THIS FILE CALLS
# ─────────────────────────────────────────────────────────────────────────────
# app/config.py                          — settings.WHATSAPP_MOCK_MODE,
#                                          settings.INTERAKT_API_KEY
# app/database.py                        — SessionLocal (sync DB sessions)
# app/models/whatsapp.py                 — PhoneTenantMap (phone → tenant lookup)
# app/models/job.py                      — Job (job data for alerts)
# app/models/employee.py                 — Employee (headcount for briefing)
# app/routers/scheduler_router.py        — ScheduleEntryModel (conflict detection)
# app/services/whatsapp_formatter.py     — format_for_whatsapp() (strip markdown)
# httpx (production only)               — POST to Interakt API
#
# ─────────────────────────────────────────────────────────────────────────────
# ARCHITECTURE NOTES
# ─────────────────────────────────────────────────────────────────────────────
# - Uses sync SQLAlchemy (SessionLocal, not AsyncSession) for all DB reads.
#   The async alert functions are async only because APScheduler AsyncIOScheduler
#   requires it — the DB calls inside are sync.
# - Conflict detection uses schedule_entries GROUP BY count (same as dashboard.py).
#   The old has_conflict column does NOT exist on Job — do not use it.
# - _get_active_phone_mappings() respects per-phone alert_preferences JSONB —
#   defaults all alert types ON if preference key is absent.
# ─────────────────────────────────────────────────────────────────────────────

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

# Timezone for all scheduled jobs - IST (Indian Standard Time)
# All pilot factories are in India so we use IST for scheduling.
SCHEDULER_TIMEZONE = "Asia/Kolkata"

# Morning briefing time - 7:00 AM IST every day
MORNING_BRIEFING_HOUR   = 7
MORNING_BRIEFING_MINUTE = 0

# Job delay check - runs every 2 hours during working hours (8am to 8pm IST)
JOB_DELAY_CHECK_HOURS = "8-20"   # Only during working hours
JOB_DELAY_CHECK_EVERY = 2        # Every 2 hours

# Conflict check - runs every 4 hours
CONFLICT_CHECK_EVERY = 4

# Alert type identifiers - must match keys in alert_preferences JSON column
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
# SCHEDULER LIFECYCLE - start and stop
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    """
    Start the APScheduler and register all three scheduled alert jobs.

    Called by: app/main.py — FastAPI startup event
    Calls:     Registers send_morning_briefings, check_delayed_jobs,
               check_scheduling_conflicts as APScheduler cron jobs.

    Schedule registered:
        morning_briefing — 7:00 AM IST daily
        job_delay_check  — every 2 hours, 8am-8pm IST only
        conflict_check   — every 4 hours

    In WHATSAPP_MOCK_MODE=True: jobs run on schedule but log [MOCK ALERT]
    instead of sending real messages. Safe for development.
    Guards against double-start — second call is skipped silently.

    Side effects:
        Starts APScheduler background thread.
        Registers three cron jobs.
    """
    if scheduler.running:
        # Guard against double-start if startup event fires twice
        logger.warning("Scheduler already running — skipping start.")
        return

    # Register morning briefing - 7am IST daily
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

    # Register job delay check - every 2 hours during working hours
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

    # Register conflict check - every 4 hours
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

    Called by: app/main.py — FastAPI shutdown event
    Calls:     scheduler.shutdown()

    Waits for any currently running alert jobs to finish before stopping
    (wait=True). Safe to call even if scheduler was never started.

    Side effects:
        Stops the APScheduler background thread.
    """
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("WhatsApp alert scheduler stopped.")
    else:
        logger.info("Scheduler was not running — nothing to stop.")


# ---------------------------------------------------------------------------
# DEV HELPER - override schedule for testing
# ---------------------------------------------------------------------------

def set_dev_schedule() -> None:
    """
    Override all alert schedules to fire every 2 minutes for dev testing.

    Called by: developer manually, or can replace start_scheduler() in main.py
               temporarily during development.
    Calls:     Replaces all registered cron jobs with 2-minute interval jobs.

    Use this when you want to verify alert content without waiting for
    the real cron times (7am briefing, 2-hour delay check, 4-hour conflict).

    NEVER use in production — will spam factory owners every 2 minutes.

    Side effects:
        Removes all existing scheduler jobs.
        Re-registers all three jobs with 2-minute interval trigger.
        Starts scheduler if not already running.
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
# ALERT JOB 1 - Morning briefing
# ---------------------------------------------------------------------------

async def send_morning_briefings() -> None:
    """
    Send daily morning briefing to all active factory owners.

    Called by: APScheduler at 7:00 AM IST daily (registered in start_scheduler)
               POST /api/v1/whatsapp/trigger-dev-alerts?alert_type=briefing
    Calls:     _get_active_phone_mappings(), _build_morning_briefing(), _send_alert()

    For each active phone number opted into morning_briefing alerts:
        1. Builds a briefing with active job count, total jobs,
           delayed job count, and active employee count.
        2. Sends (or mock-logs) the briefing via _send_alert().

    Skips phones that have morning_briefing disabled in alert_preferences.
    Errors on individual phones are caught and logged — one failure does
    not stop other phones from receiving their briefing.

    Side effects:
        Reads jobs and employees tables for each active tenant.
        Sends WhatsApp message or logs [MOCK ALERT] per phone.
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
# ALERT JOB 2 - Job delay check
# ---------------------------------------------------------------------------

async def check_delayed_jobs() -> None:
    """
    Check for delayed jobs and alert factory owners.

    Called by: APScheduler every 2 hours during 8am-8pm IST (registered in start_scheduler)
               POST /api/v1/whatsapp/trigger-dev-alerts?alert_type=delays
    Calls:     _get_active_phone_mappings(), _get_delayed_jobs(),
               _build_delay_alert(), _send_alert()

    A job is delayed if end_date < today and status is not Completed/Cancelled.
    For each active phone opted into job_delay alerts:
        1. Fetches delayed jobs for the tenant.
        2. If any found, builds and sends a delay alert listing up to 3 jobs.

    Errors on individual tenants are caught and logged — one failure does
    not stop checks for other tenants.

    Side effects:
        Reads jobs table for each active tenant.
        Sends WhatsApp alert or logs [MOCK ALERT] if delayed jobs found.
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
# ALERT JOB 3 - Conflict check
# ---------------------------------------------------------------------------

async def check_scheduling_conflicts() -> None:
    """
    Check for scheduling conflicts and alert factory owners.

    Called by: APScheduler every 4 hours (registered in start_scheduler)
               POST /api/v1/whatsapp/trigger-dev-alerts?alert_type=conflicts
    Calls:     _get_active_phone_mappings(), _get_conflicts(),
               _build_conflict_alert(), _send_alert()

    A conflict means the scheduler could not fill all expected daily slots
    for a job (schedule_entries count < expected days). Uses the same
    logic as dashboard.py — NOT the old has_conflict column which does not exist.

    For each active phone opted into conflict alerts:
        1. Fetches conflicted jobs for the tenant.
        2. If any found, builds and sends a conflict alert listing up to 3 jobs.

    Side effects:
        Reads jobs and schedule_entries tables for each active tenant.
        Sends WhatsApp alert or logs [MOCK ALERT] if conflicts found.
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
# MACHINE DOWN ALERT - triggered on demand, not on schedule
# ---------------------------------------------------------------------------

async def send_machine_down_alert(
    tenant_id: int,
    machine_name: str,
    machine_id: int
) -> None:
    """
    Send an immediate alert when a machine goes into maintenance/breakdown.

    Called by: app/routers/machines.py — PATCH /api/machines/{id} when
               machine status changes to 'maintenance' or 'breakdown'.
               This is NOT a scheduled job — fires immediately on demand.
    Calls:     _get_active_phone_mappings(tenant_id_filter=tenant_id), _send_alert()

    Only alerts phones belonging to the affected tenant (not all tenants).
    If no active phones are found for the tenant, logs and returns silently.

    Args:
        tenant_id:    The tenant whose machine went down.
        machine_name: Display name e.g. "Heidelberg SM 52"
        machine_id:   DB ID of the machine (used in the alert message for follow-up queries)

    Side effects:
        Reads phone_tenant_map for the specific tenant only.
        Sends immediate WhatsApp alert or logs [MOCK ALERT].
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
    Get all active phone numbers opted into a specific alert type.

    Called by: send_morning_briefings, check_delayed_jobs,
               check_scheduling_conflicts, send_machine_down_alert
    Calls:     SessionLocal(), PhoneTenantMap query

    Queries phone_tenant_map for is_active=True rows. Checks each row's
    alert_preferences JSONB — if the key for alert_type is absent, defaults
    to True (all alerts ON by default). Only returns phones where the
    specific alert type is enabled.

    Args:
        alert_type:        One of ALERT_TYPE_BRIEFING, ALERT_TYPE_JOB_DELAY,
                           ALERT_TYPE_MACHINE_DOWN, ALERT_TYPE_CONFLICT.
        tenant_id_filter:  If set, restricts results to one tenant only.
                           Used by send_machine_down_alert to target one factory.

    Returns:
        List of dicts: [{phone_number, tenant_id, industry_type}, ...]
        Empty list if no active opted-in phones found.

    Side effects:
        Opens and closes a sync DB session.
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
            # alert_preferences is JSONB - default all ON if not set
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
    Build the morning briefing message text for one tenant.

    Called by: send_morning_briefings()
    Calls:     SessionLocal(), Job and Employee queries, format_for_whatsapp()

    Runs 4 COUNT queries against the DB:
        - Active jobs (In Progress / Pending)
        - Total jobs
        - Delayed jobs (end_date < today, not Completed/Cancelled)
        - Active employees

    Builds a plain-text briefing e.g.:
        "Good morning! ZetaOps daily briefing — 07 April 2026
         Jobs: 3 active, 12 total
         DELAYED: 1 jobs need attention
         Team: 6 employees
         Details ke liye poochein: 'aaj ka schedule dikhao'"

    Args:
        tenant_id:     Tenant to build briefing for.
        industry_type: Reserved for future factory-type customisation.

    Returns:
        Formatted string ready to send, or None if DB query failed.

    Side effects:
        Opens and closes a sync DB session.
    """
    from sqlalchemy import select, func
    from app.database import SessionLocal
    from app.models.job import Job
    from app.models.employee import Employee
    from app.services.whatsapp_formatter import format_for_whatsapp

    db = SessionLocal()

    try:
        today = date.today()

        # Active jobs - in_progress or pending
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

        # Delayed jobs - end_date passed, not finished
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

    Called by: check_delayed_jobs()
    Calls:     SessionLocal(), Job query

    A job is delayed if end_date < today AND status is not
    Completed or Cancelled. Checks both lowercase and title-case
    status values for safety.

    Args:
        tenant_id: The tenant to check.

    Returns:
        List of dicts: [{job_id, job_name, end_date, status}, ...]
        Empty list if no delayed jobs.

    Side effects:
        Opens and closes a sync DB session.
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

    A conflict means the scheduler could not fill all expected daily slots
    for a job — i.e. schedule_entries count < expected days in date range.
    Uses the same logic as dashboard.py _has_scheduling_conflict().

    NOTE: The old has_conflict column does not exist on Job. Conflict
    detection was refactored in v4.0.11 to use schedule_entries count.

    Args:
        tenant_id: The tenant to check.

    Returns:
        List of dicts with job_id, job_name, status.
        Empty list if no conflicts found.

    Side effects:
        Reads from PostgreSQL jobs and schedule_entries tables.
    """
    from sqlalchemy import select, func
    from app.database import SessionLocal
    from app.models.job import Job
    from app.routers.scheduler_router import ScheduleEntryModel

    db = SessionLocal()

    try:
        # Load all active jobs with dates set
        jobs = db.execute(
            select(Job).where(
                Job.tenant_id == tenant_id,
                Job.status.notin_([
                    "Completed", "Cancelled", "completed", "cancelled"
                ]),
                Job.start_date.isnot(None),
                Job.end_date.isnot(None)
            )
        ).scalars().all()

        if not jobs:
            return []

        # Build entry count map in one GROUP BY query — O(1) not O(N)
        rows = db.execute(
            select(
                ScheduleEntryModel.job_id,
                func.count().label("cnt")
            ).where(
                ScheduleEntryModel.tenant_id == tenant_id
            ).group_by(
                ScheduleEntryModel.job_id
            )
        ).all()
        entry_count_map = {row[0]: row[1] for row in rows}

        conflicts = []
        for job in jobs:
            count = entry_count_map.get(job.id, 0)

            # Jobs with no schedule entries at all are not conflicts —
            # they just haven't been scheduled yet.
            if count == 0:
                continue

            # Use original dates if available (set by scheduler when it
            # moved the job) so expected days reflect the user's request.
            ref_start = job.original_start_date or job.start_date
            ref_end   = job.original_end_date   or job.end_date
            expected  = max(1, (ref_end - ref_start).days + 1)

            if count < expected:
                conflicts.append({
                    "job_id":   job.id,
                    "job_name": job.name or f"Job #{job.id}",
                    "status":   job.status
                })

        return conflicts

    except Exception as e:
        logger.error(f"Failed to get conflicts for tenant {tenant_id}: {e}")
        return []

    finally:
        db.close()


def _build_delay_alert(delayed_jobs: list[dict], industry_type: str) -> str:
    """
    Build the delay alert message text.

    Called by: check_delayed_jobs()
    Calls:     format_for_whatsapp()

    Lists up to 3 delayed jobs by name and due date. If more than 3,
    appends "...aur N aur jobs". Pure function — no DB calls.

    Args:
        delayed_jobs:  Output of _get_delayed_jobs().
        industry_type: Reserved for future factory-type customisation.

    Returns:
        Plain text alert message, WhatsApp-formatted (no markdown).

    Side effects:
        None — pure function.
    """
    from app.services.whatsapp_formatter import format_for_whatsapp

    job_count = len(delayed_jobs)
    alert = f"ALERT: {job_count} delayed job{'s' if job_count > 1 else ''}\n\n"

    # List first 3 delayed jobs - avoid very long messages on mobile
    for job in delayed_jobs[:3]:
        alert += f"- {job['job_name']} (due: {job['end_date']})\n"

    if job_count > 3:
        alert += f"...aur {job_count - 3} aur jobs\n"

    alert += "\nDetails ke liye poochein: 'delayed jobs dikhao'"

    return format_for_whatsapp(alert)


def _build_conflict_alert(conflicts: list, industry_type: str) -> str:
    """
    Build the conflict alert message text.

    Called by: check_scheduling_conflicts()
    Calls:     format_for_whatsapp()

    Lists up to 3 conflicted jobs by name. If more than 3,
    appends "...aur N aur". Pure function — no DB calls.

    Args:
        conflicts:     Output of _get_conflicts().
        industry_type: Reserved for future factory-type customisation.

    Returns:
        Plain text alert message, WhatsApp-formatted (no markdown).

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
    Send a WhatsApp message to one phone number.

    Called by: send_morning_briefings, check_delayed_jobs,
               check_scheduling_conflicts, send_machine_down_alert
    Calls:     httpx.AsyncClient POST to Interakt API (production only)

    Behaviour:
        WHATSAPP_MOCK_MODE=True  → logs [MOCK ALERT] to console, returns.
        WHATSAPP_MOCK_MODE=False → POSTs to https://api.interakt.ai/v1/public/message/
                                   using INTERAKT_API_KEY from settings.
        WHATSAPP_MOCK_MODE=False + no INTERAKT_API_KEY → logs error, returns.

    Interakt expects phone number WITHOUT leading '+'. This function
    strips it automatically.

    Args:
        phone_number: E.164 format e.g. +919876543210
        message:      Plain text, already formatted by whatsapp_formatter.
        alert_type:   One of ALERT_TYPE_* constants — used only for logging.

    Side effects:
        Mock mode: writes one INFO log line.
        Production: makes one HTTP POST to Interakt API.
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
