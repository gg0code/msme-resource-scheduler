# whatsapp_alerts.py - Version 2.2
# Branch: v5-whatsapp
#
# FILE PURPOSE
# All scheduled and on-demand WhatsApp alert jobs for ZetaOps Copilot.
# Owns the APScheduler lifecycle and every outbound proactive message:
#   Job 1 - Morning briefing to owner (7:00am IST, scheduled data)
#   Job 2 - Delayed job check (every 2 hours, 8am-8pm IST)
#   Job 3 - Conflict check (every 4 hours)
#   Job 4 - Manager check-in prompt (7:00am IST) [v5.15]
#   Job 5 - Owner briefing from checkin (7:15am IST) [v5.15]
#   Job 6 - Daily push briefing dispatcher (every 5 minutes) [v6.3.4]
#   Job 7 - Candidate evaluation (02:00 IST nightly) [v6.3.15 revised]
#   Job 8 - Confirmation send (19:00 IST nightly)    [v6.3.15 revised]
#   On-demand - Machine down alert (triggered from machine router)
#
# WHO CALLS THIS FILE
#   app/main.py                      - start_scheduler() on FastAPI startup
#   app/main.py                      - stop_scheduler() on FastAPI shutdown
#   app/routers/whatsapp.py          - CHECKIN_WINDOW_START/END_HOUR constants
#   app/routers/whatsapp.py          - send_machine_down_alert() on machine status change
#   POST /api/v1/whatsapp/trigger-dev-alerts - dev endpoint fires all jobs immediately
#
# WHAT THIS FILE CALLS
#   app/database.py                  - SessionLocal (sync session per job)
#   app/config.py                    - settings (WHATSAPP_MOCK_MODE)
#   app/models/job.py                - Job (delayed/conflict queries)
#   app/models/employee.py           - Employee (headcount for briefing)
#   app/models/whatsapp.py           - PhoneTenantMap (active phone lookups)
#   app/services/whatsapp_checkin.py - build_checkin_prompt(), build_owner_briefing_from_checkin()
#   app/services/whatsapp_formatter.py - format_for_whatsapp()
#   app/services/whatsapp_send.py    - _send_whatsapp_message (mock>meta>error)
#
# KEY DESIGN DECISIONS
#   1. All DB access uses sync SessionLocal — never AsyncSession. APScheduler
#      jobs run in a thread pool executor; async DB sessions are not safe there.
#   2. WHATSAPP_MOCK_MODE=True in dev — all sends log [MOCK ALERT] to console.
#      Jobs still run on schedule so timing and logic can be verified.
#   3. set_dev_schedule() overrides all jobs to 2-minute intervals for testing.
#      NEVER call this in production — it will spam factory owners.
#   4. Conflict detection uses schedule_entries GROUP BY count — NOT Job.has_conflict.
#      That column does not exist. See _get_conflicts() for the correct pattern.
#   5. CHECKIN_WINDOW_START/END_HOUR constants exported for use in whatsapp router
#      to route manager messages to checkin handler vs normal AI pipeline.
import logging
from datetime import datetime, date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services.whatsapp_send import _send_whatsapp_message

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

# v6.3.4 - Daily push briefing dispatcher cadence. The dispatcher itself
# decides which tenants are due inside the 5-minute window per their
# briefing_morning_time / briefing_evening_time config; APScheduler just
# needs to fire often enough that no configured time falls between ticks.
BRIEFING_DISPATCH_INTERVAL_MINUTES = 5

# v6.3.15 (revised) - Candidate evaluation job. Runs nightly at
# 02:00 IST — low activity, before the 07:30 morning briefings. The
# evaluator iterates tenants opted into ENTITY_EXTRACTION_TENANT_IDS
# and: (a) fuzzy-matches qualifying candidates against existing
# employees/machines (silent confirm); (b) leaves non-matching
# qualifying candidates in state='none' for the 19:00 IST cron to
# ask the owner about. NO direct insertions on this tick.
# See app/services/promotion/promoter.py for the full design.
PROMOTION_JOB_HOUR   = 2
PROMOTION_JOB_MINUTE = 0

# v6.3.15 (revised) - Confirmation-send job. Runs at the time
# configured in settings (PROMOTION_CONFIRMATION_HOUR_IST,
# PROMOTION_CONFIRMATION_MINUTE_IST — default 19:00 IST). For each
# enabled tenant: sweeps timeouts, composes one batch (top-N
# candidates), sends a single WhatsApp confirmation message to the
# most-recently-active top-tier phone, and records the wamid + emits
# extraction.confirmation_requested. Owner replies HAAN/NAHI/partial
# overnight; the inbound webhook applies the decisions before the
# next morning's briefing.
CONFIRMATION_SEND_JOB_HOUR   = settings.PROMOTION_CONFIRMATION_HOUR_IST
CONFIRMATION_SEND_JOB_MINUTE = settings.PROMOTION_CONFIRMATION_MINUTE_IST


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
    Start the APScheduler and register all alert jobs.

    Called from app/main.py on FastAPI startup event.
    Registers all scheduled jobs and starts the scheduler running.

    In mock mode (WHATSAPP_MOCK_MODE=True), jobs still run but
    send output to logs instead of real WhatsApp messages.
    This lets us test alert content without a live WhatsApp provider.

    Side effects:
        Starts background scheduler thread.
        Registers cron jobs for all four alert types.
        Logs confirmation of each registered job.
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

    # Register manager check-in prompt - 7:00am IST daily (v5.15)
    scheduler.add_job(
        func=send_manager_checkin,
        trigger=CronTrigger(
            hour=MORNING_BRIEFING_HOUR,
            minute=MORNING_BRIEFING_MINUTE,
            timezone=SCHEDULER_TIMEZONE,
        ),
        id="manager_checkin",
        name="Daily manager check-in prompt at 7:00am IST",
        replace_existing=True,
    )
    logger.info("Scheduled: manager check-in prompt at 07:00 IST daily")

    # Register owner briefing from checkin - 7:15am IST daily (v5.15)
    scheduler.add_job(
        func=send_owner_briefing_from_checkin,
        trigger=CronTrigger(
            hour=OWNER_BRIEFING_FROM_CHECKIN_HOUR,
            minute=OWNER_BRIEFING_FROM_CHECKIN_MINUTE,
            timezone=SCHEDULER_TIMEZONE,
        ),
        id="owner_briefing_checkin",
        name="Owner briefing from manager checkin at 7:15am IST",
        replace_existing=True,
    )
    logger.info("Scheduled: owner briefing from checkin at 07:15 IST daily")

    # Register daily push briefing dispatcher - every 5 minutes (v6.3.4).
    # The dispatcher iterates tenants and sends briefings whose configured
    # morning_time / evening_time falls in the current 5-minute window.
    # Coexists with the v5.15 manager_checkin (07:00 IST) and
    # owner_briefing_checkin (07:15 IST) jobs - those are tied to a
    # specific clock time; this one is a recurring sweep.
    scheduler.add_job(
        func=run_briefing_dispatch_tick,
        trigger="interval",
        minutes=BRIEFING_DISPATCH_INTERVAL_MINUTES,
        id="briefing_dispatch_job",
        name="Daily push briefing dispatcher (every 5 minutes)",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info(
        "Scheduled: daily push briefing dispatcher every %d minutes",
        BRIEFING_DISPATCH_INTERVAL_MINUTES,
    )

    # Register candidate-evaluation job - 02:00 IST nightly (v6.3.15
    # revised). Late-imported to avoid pulling app.services.promotion
    # (which imports app.models) at module load — start_scheduler() is
    # called from app.main lifespan after model registration is complete.
    from app.services.promotion import (
        evaluate_for_all_tenants,
        send_confirmations_for_all_tenants,
    )
    scheduler.add_job(
        func=evaluate_for_all_tenants,
        trigger=CronTrigger(
            hour=PROMOTION_JOB_HOUR,
            minute=PROMOTION_JOB_MINUTE,
            timezone=SCHEDULER_TIMEZONE,
        ),
        id="candidate_evaluation_job",
        name="Candidate evaluation job (nightly 02:00 IST)",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info(
        "Scheduled: candidate-evaluation job at %02d:%02d IST nightly",
        PROMOTION_JOB_HOUR, PROMOTION_JOB_MINUTE,
    )

    # Register confirmation-send job - configurable evening time
    # (v6.3.15 revised). Coalesce + max_instances=1 prevent overlap;
    # the state-flip in compose_confirmation_for_tenant is the
    # second-line defence against double-asking.
    scheduler.add_job(
        func=send_confirmations_for_all_tenants,
        trigger=CronTrigger(
            hour=CONFIRMATION_SEND_JOB_HOUR,
            minute=CONFIRMATION_SEND_JOB_MINUTE,
            timezone=SCHEDULER_TIMEZONE,
        ),
        id="confirmation_send_job",
        name="Candidate confirmation send (nightly evening IST)",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info(
        "Scheduled: confirmation-send job at %02d:%02d IST nightly",
        CONFIRMATION_SEND_JOB_HOUR, CONFIRMATION_SEND_JOB_MINUTE,
    )

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
# DEV HELPER - override schedule for testing
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

    # Late-import the v6.3.15 (revised) cron entry points — avoids
    # dragging the promotion package into module load if dev never
    # calls set_dev_schedule().
    from app.services.promotion import (
        evaluate_for_all_tenants,
        send_confirmations_for_all_tenants,
    )

    for job_func, job_id in [
        (send_morning_briefings,            "morning_briefing"),
        (check_delayed_jobs,                "job_delay_check"),
        (check_scheduling_conflicts,        "conflict_check"),
        (send_manager_checkin,              "manager_checkin"),
        (send_owner_briefing_from_checkin,  "owner_briefing_checkin"),
        (run_briefing_dispatch_tick,        "briefing_dispatch_job"),
        (evaluate_for_all_tenants,          "candidate_evaluation_job"),
        (send_confirmations_for_all_tenants, "confirmation_send_job"),
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
# ALERT JOB 2 - Job delay check
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
# ALERT JOB 3 - Conflict check
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
# MACHINE DOWN ALERT - triggered on demand, not on schedule
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

    from app.services.message_templates import (
        MACHINE_DOWN_ALERT,
        DEFAULT_LOCALE,
        pick,
    )

    alert_text = pick(MACHINE_DOWN_ALERT, DEFAULT_LOCALE).format(
        machine_name=machine_name,
        machine_id=machine_id,
    )

    for phone_mapping in active_phones:
        await _send_alert(
            phone_number=phone_mapping["phone_number"],
            message=alert_text,
            alert_type=ALERT_TYPE_MACHINE_DOWN
        )


# ---------------------------------------------------------------------------
# ALERT JOB 4 - Manager check-in prompt (v5.15)
# ---------------------------------------------------------------------------

# Check-in window: messages from managers in this hour range are routed to
# handle_manager_checkin_reply() in whatsapp_checkin.py instead of AI pipeline.
# Defined here so whatsapp router can import without circular dependency.
CHECKIN_WINDOW_START_HOUR = 7   # 7:00am IST
CHECKIN_WINDOW_END_HOUR   = 9   # 9:00am IST — after this, normal AI pipeline

# Owner briefing from checkin fires 15 minutes after manager prompt
OWNER_BRIEFING_FROM_CHECKIN_HOUR   = 7
OWNER_BRIEFING_FROM_CHECKIN_MINUTE = 15


async def send_manager_checkin() -> None:
    """
    Send the 7:00am check-in prompt to all manager phones.

    Fires at 7:00am IST daily. Queries PhoneTenantMap for all active
    phone numbers with phone_role='manager'. Sends the three-question
    check-in prompt in the manager's detected language.

    Language: defaults to 'hinglish' for manager phones — most factory
    floor managers in Indian MSMEs communicate in Hinglish. Language will
    be updated to detected value after first reply in v5.15+.

    Called by:   APScheduler at 7:00am IST (registered in start_scheduler)
    Calls:       _get_manager_phone_mappings(), build_checkin_prompt(),
                 _send_alert()
    Args:        None
    Returns:     None
    Side effects:
        Sends WhatsApp message to every active manager phone per tenant.
        Logs [MOCK ALERT] if WHATSAPP_MOCK_MODE=True.
    """
    logger.info(f"Manager check-in prompt job started at {datetime.now().isoformat()}")

    manager_phones = await _get_manager_phone_mappings()

    if not manager_phones:
        logger.info("No active manager phones found — check-in prompt skipped.")
        return

    from app.services.whatsapp_checkin import build_checkin_prompt

    sent_count = 0
    for phone_mapping in manager_phones:
        try:
            # Default to hinglish for manager phones — most Indian factory
            # floor managers communicate in Hinglish. Per-phone language
            # detection will be added when session history is available.
            prompt = build_checkin_prompt(lang="hinglish")
            await _send_alert(
                phone_number=phone_mapping["phone_number"],
                message=prompt,
                alert_type="manager_checkin",
            )
            sent_count += 1
        except Exception as exc:
            logger.error(
                "Failed to send check-in prompt to ****%s: %s",
                phone_mapping["phone_number"][-4:], exc,
            )

    logger.info("Manager check-in prompts sent to %d phones.", sent_count)


# ---------------------------------------------------------------------------
# ALERT JOB 5 - Owner briefing from checkin (v5.15)
# ---------------------------------------------------------------------------

async def send_owner_briefing_from_checkin() -> None:
    """
    Send the 7:15am owner briefing built from today's manager check-in.

    Fires at 7:15am IST daily — 15 minutes after the manager check-in
    prompt. Reads checkin state from Redis for each tenant. If a manager
    has already replied, the briefing is built from real attendance data.
    If no checkin state exists yet, falls back to the existing scheduled
    data briefing (_build_morning_briefing).

    This is the OWNER output channel — signal only, no questions asked.
    Owner reads, acts, moves on.

    Called by:   APScheduler at 7:15am IST (registered in start_scheduler)
    Calls:       _get_active_phone_mappings(), build_owner_briefing_from_checkin(),
                 _build_morning_briefing(), _send_alert()
    Args:        None
    Returns:     None
    Side effects:
        Reads Redis checkin state per tenant.
        Reads PostgreSQL for employee/machine/job data.
        Sends WhatsApp briefing to every active owner phone per tenant.
        Logs [MOCK ALERT] if WHATSAPP_MOCK_MODE=True.
    """
    logger.info(
        f"Owner briefing from checkin started at {datetime.now().isoformat()}"
    )

    # Owner phones only — phone_role='owner'
    owner_phones = await _get_active_phone_mappings(ALERT_TYPE_BRIEFING)

    if not owner_phones:
        logger.info("No active owner phones found — owner briefing skipped.")
        return

    from app.database import SessionLocal
    from app.services.whatsapp_checkin import build_owner_briefing_from_checkin

    sent_count = 0
    for phone_mapping in owner_phones:
        try:
            db = SessionLocal()
            try:
                briefing_text = build_owner_briefing_from_checkin(
                    tenant_id=phone_mapping["tenant_id"],
                    db=db,
                    lang="hinglish",
                )
            finally:
                db.close()

            # Fall back to scheduled data briefing if no checkin state exists
            if briefing_text is None:
                logger.info(
                    "No checkin state for tenant %s — falling back to "
                    "scheduled data briefing.",
                    phone_mapping["tenant_id"],
                )
                briefing_text = await _build_morning_briefing(
                    tenant_id=phone_mapping["tenant_id"],
                    industry_type=phone_mapping["industry_type"],
                )

            if briefing_text:
                await _send_alert(
                    phone_number=phone_mapping["phone_number"],
                    message=briefing_text,
                    alert_type=ALERT_TYPE_BRIEFING,
                )
                sent_count += 1

        except Exception as exc:
            logger.error(
                "Failed to send owner briefing to ****%s: %s",
                phone_mapping["phone_number"][-4:], exc,
            )

    logger.info("Owner briefings from checkin sent to %d phones.", sent_count)


# ---------------------------------------------------------------------------
# ALERT JOB 6 - Daily push briefing dispatcher (v6.3.4)
# ---------------------------------------------------------------------------

async def run_briefing_dispatch_tick() -> None:
    """
    APScheduler entry point for the v6.3.4 daily push briefings.

    Fires every BRIEFING_DISPATCH_INTERVAL_MINUTES (5). Delegates to
    app.services.briefings.dispatcher.dispatch_due_briefings which:
      - Iterates every tenant.
      - Computes whether morning_time / evening_time falls in the
        current 5-minute window in the tenant's timezone.
      - Resolves top-tier subscribed recipients.
      - Builds industry-aware content (morning forward-looking,
        evening backward-looking).
      - Sends via the existing _send_alert wiring (mock-mode aware).
      - Writes briefing.* events for every send / skip / failure.

    Called by:   APScheduler 'briefing_dispatch_job' interval trigger.
    Calls into:  app.services.briefings.dispatcher.dispatch_due_briefings.
    Args:        none - APScheduler invokes with no positional args.
    Returns:     None (the dispatcher's DispatchSummary is logged here).
    Side effects:
        DB reads for every tenant. DB writes (Event rows) for sends,
        skips, and failures. WhatsApp sends per recipient (logged in
        mock mode, real Meta Cloud API POST in production).

    Why this thin wrapper instead of registering dispatch_due_briefings
    directly: APScheduler captures exceptions silently in some
    versions; centralising the try/except here ensures any unexpected
    crash inside the dispatcher surfaces as a logged error rather than
    a silently swallowed schedule run.
    """
    # Late import keeps the module's import graph free of v6.3.4 deps
    # so v5-only callers can still load whatsapp_alerts without a
    # zoneinfo / briefing-package penalty.
    from app.services.briefings.dispatcher import dispatch_due_briefings

    try:
        summary = await dispatch_due_briefings()
        logger.info(
            "briefing_dispatch_job tick: tenants=%d sent=%d skipped=%d",
            summary.tenants_processed,
            summary.briefings_sent,
            summary.briefings_skipped,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("briefing_dispatch_job crashed: %s", exc)


# ---------------------------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------------------------

async def _get_manager_phone_mappings() -> list[dict]:
    """
    Get all active phone mappings with phone_role='manager'.

    Called by:   send_manager_checkin()
    Calls:       SessionLocal, PhoneTenantMap
    Args:        None
    Returns:
        List of dicts with phone_number, tenant_id, industry_type keys.
        Empty list if no active manager phones found.
    Side effects:
        Reads from PostgreSQL phone_tenant_map table.
    """
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models.whatsapp import PhoneTenantMap

    results = []
    db = SessionLocal()

    try:
        mappings = db.execute(
            select(PhoneTenantMap).where(
                PhoneTenantMap.is_active == True,       # noqa: E712
                PhoneTenantMap.phone_role == "manager",
            )
        ).scalars().all()

        for mapping in mappings:
            results.append({
                "phone_number":  mapping.phone_number,
                "tenant_id":     mapping.tenant_id,
                "industry_type": mapping.industry_type or "printing",
            })

    except Exception as exc:
        logger.error("Failed to get manager phone mappings: %s", exc)

    finally:
        db.close()

    return results


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
    Build the morning briefing message for a specific tenant.

    Uses direct DB queries for reliability — no dependency on ai_service
    tool names which may not exist or may change.

    v6.3.18: renders via message_templates.MORNING_BRIEFING (Hinglish-first
    locale dict) instead of the previous inline f-string. Visual
    hierarchy + emoji + length cap are now centralised; the wire content
    is the same active/total/delayed/team counts.

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
    from app.services.message_formatters import format_for_whatsapp
    from app.services.message_templates import (
        MORNING_BRIEFING,
        MORNING_BRIEFING_DELAYED_LINE,
        DEFAULT_LOCALE,
        pick,
    )

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

        delayed_line = (
            pick(MORNING_BRIEFING_DELAYED_LINE, DEFAULT_LOCALE).format(
                delayed_count=delayed_jobs,
            )
            if delayed_jobs > 0
            else ""
        )

        briefing = pick(MORNING_BRIEFING, DEFAULT_LOCALE).format(
            date=today_str,
            active_jobs=active_jobs,
            total_jobs=total_jobs,
            delayed_line=delayed_line,
            total_employees=total_employees,
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

    A conflict exists when a job has fewer schedule_entries rows than the
    number of working days between its start_date and end_date. This means
    the scheduler could not fully allocate the job — a resource gap exists.

    Called by:   check_scheduling_conflicts()
    Calls:       SessionLocal, Job, ScheduleEntry
    Args:
        tenant_id: The tenant to check.
    Returns:
        List of dicts with job_id, job_name, status.
        Empty list if no conflicts found.
    Side effects:
        Reads from PostgreSQL jobs and schedule_entries tables.

    NOTE: Job.has_conflict column does NOT exist. Conflict detection uses
    schedule_entries GROUP BY count per dev prompt architecture rule 5.
    Never revert this to Job.has_conflict — that column was never created.
    """
    from sqlalchemy import select, func, text
    from app.database import SessionLocal
    from app.models.job import Job

    db = SessionLocal()

    try:
        # Load active jobs for this tenant in one query — no N+1
        active_jobs = db.execute(
            select(Job).where(
                Job.tenant_id == tenant_id,
                Job.status.notin_([
                    "completed", "cancelled", "Completed", "Cancelled"
                ]),
                Job.start_date.isnot(None),
                Job.end_date.isnot(None),
            )
        ).scalars().all()

        if not active_jobs:
            return []

        job_ids = [j.id for j in active_jobs]

        # Count schedule_entries per job in one query — prevents N+1
        entry_counts_raw = db.execute(
            text(
                "SELECT job_id, COUNT(*) AS entry_count "
                "FROM schedule_entries "
                "WHERE job_id = ANY(:job_ids) "
                "GROUP BY job_id"
            ),
            {"job_ids": job_ids},
        ).all()

        entry_count_map: dict[int, int] = {
            row.job_id: row.entry_count for row in entry_counts_raw
        }

        today = date.today()
        conflicts: list[dict] = []

        for job in active_jobs:
            if job.start_date is None or job.end_date is None:
                continue
            # Expected days = calendar days in job range (simple heuristic —
            # not working-days-only, keeps it dependency-free)
            expected_days = max(1, (job.end_date - job.start_date).days + 1)
            actual_entries = entry_count_map.get(job.id, 0)

            if actual_entries < expected_days:
                conflicts.append({
                    "job_id":   job.id,
                    "job_name": job.name or f"Job #{job.id}",
                    "status":   job.status,
                })

        return conflicts

    except Exception as e:
        logger.error(f"Failed to get conflicts for tenant {tenant_id}: {e}")
        return []

    finally:
        db.close()


def _build_delay_alert(delayed_jobs: list[dict], industry_type: str) -> str:
    """
    Build a WhatsApp alert message listing delayed jobs.

    v6.3.18: renders via message_templates.DELAY_ALERT (single English
    string per Q3 — Meta has approved en_US only for zetaops_job_ending_soon).
    Job list is shaped via message_formatters.format_jobs_list which
    enforces the 5-item cap + "+N more" tail.

    Args:
        delayed_jobs:  List of delayed job dicts from _get_delayed_jobs().
                       Each dict has 'job_id', 'job_name', 'end_date',
                       'status' keys.
        industry_type: Reserved for future terminology customisation.

    Returns:
        Plain text alert message ready to send via WhatsApp.

    Side effects:
        None — pure function.
    """
    from types import SimpleNamespace

    from app.services.message_formatters import format_for_whatsapp, format_jobs_list
    from app.services.message_templates import DELAY_ALERT

    job_count = len(delayed_jobs)

    # Adapt the dict-shaped rows to the duck-typed JobLike protocol that
    # format_jobs_list reads via getattr. Keeps the formatter contract
    # clean (one structural shape) while preserving the dict shape on
    # _get_delayed_jobs (which other tests may rely on).
    job_objs = [
        SimpleNamespace(name=row["job_name"], end_date=row["end_date"])
        for row in delayed_jobs
    ]
    jobs_block = format_jobs_list(job_objs, max_items=3)

    alert = DELAY_ALERT.format(
        count=job_count,
        plural_s="s" if job_count != 1 else "",
        jobs_block=jobs_block,
    )

    return format_for_whatsapp(alert)


def _build_conflict_alert(conflicts: list, industry_type: str) -> str:
    """
    Build a WhatsApp alert message for scheduling conflicts.

    v6.3.18: renders via message_templates.CONFLICT_ALERT (single English
    string per Q3 — the Hindi sibling exists in the JSON registry as
    `status: "draft_pending_meta_submission"` and is not yet wired up).
    Job list shaped via format_jobs_list with 3-item cap.

    Args:
        conflicts:     List of conflict dicts from _get_conflicts().
                       Each dict has 'job_id', 'job_name', 'status' keys
                       (no end_date — conflict listings don't carry due
                       dates).
        industry_type: Reserved for future terminology customisation.

    Returns:
        Plain text alert message ready to send via WhatsApp.

    Side effects:
        None — pure function.
    """
    from types import SimpleNamespace

    from app.services.message_formatters import format_for_whatsapp, format_jobs_list
    from app.services.message_templates import CONFLICT_ALERT

    conflict_count = len(conflicts)

    job_objs = [
        SimpleNamespace(name=row["job_name"], end_date=None)
        for row in conflicts
    ]
    jobs_block = format_jobs_list(job_objs, max_items=3)

    alert = CONFLICT_ALERT.format(
        count=conflict_count,
        plural_s="s" if conflict_count != 1 else "",
        jobs_block=jobs_block,
    )

    return format_for_whatsapp(alert)


async def _send_alert(
    phone_number: str,
    message: str,
    alert_type: str,
) -> None:
    """
    Dispatch a WhatsApp alert via the shared send helper.

    Logs the alert_type alongside the recipient so multi-alert log streams
    stay debuggable, then delegates the actual transport to
    _send_whatsapp_message which owns the mock > meta-direct > error
    branching.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210
        message:      Plain text message to send (already formatted).
        alert_type:   For logging — identifies what type of alert was sent.

    Side effects:
        Always logs an alert-type breadcrumb. The send itself is mock-aware
        inside _send_whatsapp_message — mock-mode writes to log only,
        non-mock posts to Meta per env-var configuration.
    """
    if settings.WHATSAPP_MOCK_MODE:
        logger.info(
            f"[MOCK ALERT] Type={alert_type} "
            f"To=****{phone_number[-4:]} "
            f"Message='{message[:150]}{'...' if len(message) > 150 else ''}'"
        )
    else:
        logger.info(
            f"Dispatching alert. Type={alert_type} To=****{phone_number[-4:]}"
        )

    await _send_whatsapp_message(phone_number, message)
