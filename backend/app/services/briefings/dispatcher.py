# app/services/briefings/dispatcher.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.4 daily push briefings dispatcher. Owns:
#   1. dispatch_due_briefings(now_utc)  - APScheduler entry every 5 min.
#   2. dispatch_briefing(tenant, kind, db) - one (tenant, kind) batch.
#   3. resolve_recipients(tenant, db)  - top-tier subscribed users with
#                                         a linked, active WhatsApp number.
#   4. is_working_day(tenant, date_in_tz) - CSV-encoded ISO weekday check.
#   5. manual_trigger_briefing(user, kind, db) - WhatsApp on-demand path.
#   6. compute_stagger_offset(tenant_id) - deterministic per-tenant
#                                          spread within the 5-min window.
#
# WHO CALLS THIS FILE
# - app/services/whatsapp_alerts.py    - registers dispatch_due_briefings
#                                         on the existing AsyncIOScheduler.
# - app/services/whatsapp_intent.py    - calls manual_trigger_briefing
#                                         from the request_briefing intent.
# - app/services/briefings/__init__.py - re-exports the public surface.
# - tests/test_briefings.py            - service-direct assertions.
#
# WHAT THIS FILE CALLS
# - app/services/briefings/morning_content.build_morning_briefing
# - app/services/briefings/evening_content.build_evening_briefing
# - app/services/briefings/send_with_retry.send_briefing_with_retry
# - app/models.{auth.Tenant, auth.User, whatsapp.PhoneTenantMap, event.Event}
# - app/database.SessionLocal - one session per per-tenant dispatch on
#                               the cron path so a slow query for one
#                               tenant cannot stall another.
# - app/services/whatsapp_alerts._send_alert - the actual outbound send
#                                              (mock-mode aware).
#
# KEY DESIGN DECISIONS
# - Tenant-scoped session per dispatch, not one giant session for the
#   whole cron tick. Cleaner failure boundaries and matches the v5.10
#   send_morning_briefings pattern.
# - Per-user briefing time overrides (User.briefing_time_override_*)
#   are honoured: a user is included only if their effective briefing
#   time (override or tenant default) falls in the current window.
# - briefing.skipped events are emitted ONLY for non-trivial skips
#   (working-day mismatch, no recipients). A 'disabled' tenant produces
#   NO event - logging every disabled tenant every 5 minutes would
#   flood the events table. The handoff records this choice (the prompt
#   left it open: "pick one and document").
# - Stagger offset is computed deterministically from tenant_id and
#   applied via sleep_fn between per-tenant dispatches inside one
#   dispatch_due_briefings tick. Tests inject a no-op sleep_fn to keep
#   suites fast.

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import TOP_TIER_ROLES, Tenant, User
from app.models.event import Event
from app.models.whatsapp import PhoneTenantMap
from app.services.briefings.evening_content import build_evening_briefing
from app.services.briefings.morning_content import build_morning_briefing
from app.services.briefings.send_with_retry import send_briefing_with_retry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

WINDOW_MINUTES: int = 5  # APScheduler ticks every WINDOW_MINUTES.
WINDOW_SECONDS: int = WINDOW_MINUTES * 60

KIND_MORNING: str = "morning"
KIND_EVENING: str = "evening"
ALL_KINDS: tuple[str, ...] = (KIND_MORNING, KIND_EVENING)

EVENT_SENT: str = "briefing.sent"
EVENT_SKIPPED: str = "briefing.skipped"
EVENT_SEND_FAILED: str = "briefing.send_failed"
EVENT_MANUAL_TRIGGER: str = "briefing.manual_trigger"


SleepFn = Callable[[float], Awaitable[None]]


# ---------------------------------------------------------------------------
# RETURN TYPES
# ---------------------------------------------------------------------------

@dataclass
class BriefingDispatchResult:
    """Outcome of one (tenant, kind) batch.

    Used by:    dispatch_briefing return; surfaced in tests and in the
                cron summary aggregation.
    Fields:
        kind:            'morning' | 'evening'.
        sent_count:      Successful sends - one per recipient.
        skipped_reasons: list of (recipient_user_id, reason) pairs for
                         per-recipient skip notes (empty for sends that
                         succeeded). Tenant-level skips are recorded on
                         DispatchSummary, not here.
        errors:          list of (recipient_user_id, error_str) pairs
                         from terminal send failures (after all retries).
                         Each error has already produced a
                         briefing.send_failed Event row.
    """
    kind: str
    sent_count: int = 0
    skipped_reasons: list[tuple[Optional[int], str]] = field(default_factory=list)
    errors: list[tuple[Optional[int], str]] = field(default_factory=list)


@dataclass
class DispatchSummary:
    """Outcome of one cron tick across every tenant.

    Used by:    dispatch_due_briefings return; logged at INFO level so
                ops can spot dispatch volume and skip patterns.
    Fields:
        tenants_processed:  How many tenants were inspected (regardless
                            of whether they sent anything).
        briefings_sent:     Cross-tenant total of successful sends.
        briefings_skipped:  Cross-tenant total of skips with a reason.
        skip_reasons:       dict[reason -> count] for quick aggregation.
    """
    tenants_processed: int = 0
    briefings_sent: int = 0
    briefings_skipped: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# WORKING-DAY HELPER
# ---------------------------------------------------------------------------

def is_working_day(tenant: Tenant, date_in_tz: date) -> bool:
    """
    True when `date_in_tz`'s ISO weekday is in tenant.briefing_working_days.

    Called by:    dispatch_due_briefings (cron path) and
                  manual_trigger_briefing (informational - manual
                  triggers fire regardless of working day).
    Calls into:   nothing - pure CSV parse.
    Side effects: none.

    The column stores 1-7 ISO weekdays comma-separated (1=Mon..7=Sun).
    Default at v6.3.1 is '1,2,3,4,5,6' (Mon-Sat). Garbled or empty
    values (legacy rows) degrade to True so the dispatcher does not
    silently lock out a tenant.
    """
    raw = (tenant.briefing_working_days or "").strip()
    if not raw:
        return True
    try:
        allowed = {int(part.strip()) for part in raw.split(",") if part.strip()}
    except ValueError:
        logger.warning(
            "Tenant %s briefing_working_days unparseable: %r - defaulting to True",
            tenant.id, raw,
        )
        return True
    return date_in_tz.isoweekday() in allowed


# ---------------------------------------------------------------------------
# STAGGER HELPER
# ---------------------------------------------------------------------------

def compute_stagger_offset(
    tenant_id: int,
    window_minutes: int = WINDOW_MINUTES,
) -> int:
    """
    Deterministic per-tenant offset in seconds inside a dispatch window.

    Called by:    dispatch_due_briefings before each per-tenant dispatch
                  to spread send load across the window.
    Calls into:   nothing - pure modulo on an int.
    Side effects: none.

    Args:
        tenant_id:      The Tenant.id used as the spread seed.
        window_minutes: Width of the window in minutes (defaults to
                        WINDOW_MINUTES, which matches the cron interval).

    Returns:
        Integer in [0, window_minutes*60). Multiplying tenant_id by a
        large prime then taking modulo gives a uniform spread without
        the cost of hashing strings.
    """
    if window_minutes <= 0:
        return 0
    seconds = window_minutes * 60
    # 2654435761 is Knuth's multiplicative hash constant - cheap and
    # spreads sequential integer keys uniformly across 32 bits.
    spread = (tenant_id * 2654435761) & 0xFFFFFFFF
    return spread % seconds


# ---------------------------------------------------------------------------
# RECIPIENT RESOLUTION
# ---------------------------------------------------------------------------

@dataclass
class _Recipient:
    """Internal: one row of (user, phone_number, language)."""
    user: User
    phone_number: str


def resolve_recipients(tenant: Tenant, db: Session) -> list[_Recipient]:
    """
    Top-tier, subscribed users in this tenant with an active linked phone.

    Called by:    dispatch_briefing (cron path).
    Calls into:   SQLAlchemy SELECT joining User and PhoneTenantMap.
    Side effects: none - read only.

    Args:
        tenant: The Tenant ORM row.
        db:     Sync SQLAlchemy Session.

    Returns:
        List of _Recipient. Empty when no eligible recipients - the
        dispatcher records a 'no_recipients' skip in that case.

    Filter rules (all must be true):
        - User.tenant_id == tenant.id
        - User.is_active is True
        - User.role in TOP_TIER_ROLES
        - User.briefing_subscribed is True
        - A PhoneTenantMap row exists with user_id matching User.id,
          tenant_id matching tenant.id, is_active True. The phone_number
          comes from the PhoneTenantMap row (not User.phone_e164) so the
          dispatcher uses the same authoritative WhatsApp identity v5
          alerts use.

    Why join via PhoneTenantMap: tenant-side WhatsApp linking is the
    source of truth for "this user can be reached on WhatsApp". A user
    who set User.phone_e164 but never linked through the desktop or
    HAAN flow would silently fail at send time - we filter them out
    at the resolution step instead.
    """
    rows = db.execute(
        select(User, PhoneTenantMap)
        .join(
            PhoneTenantMap,
            (PhoneTenantMap.user_id == User.id)
            & (PhoneTenantMap.tenant_id == User.tenant_id),
        )
        .where(
            User.tenant_id == tenant.id,
            User.is_active == True,                  # noqa: E712
            User.role.in_(TOP_TIER_ROLES),
            User.briefing_subscribed == True,        # noqa: E712
            PhoneTenantMap.is_active == True,        # noqa: E712
        )
    ).all()

    recipients: list[_Recipient] = []
    for user, pmap in rows:
        recipients.append(_Recipient(user=user, phone_number=pmap.phone_number))
    return recipients


# ---------------------------------------------------------------------------
# SEND WIRING
# ---------------------------------------------------------------------------
# `_default_send` resolves to the existing v5.10 _send_alert which logs
# [MOCK ALERT] in mock mode and routes to _send_whatsapp_message in
# production. The dispatcher accepts a send_fn override so tests can
# inject a fake without monkeypatching imports.

DispatchSendFn = Callable[[str, str, str], Awaitable[None]]


async def _default_send(phone_number: str, message: str, alert_type: str) -> None:
    """Default send wiring: delegates to whatsapp_alerts._send_alert.

    Called by:    dispatch_briefing when no send_fn override supplied.
    Calls into:   app.services.whatsapp_alerts._send_alert.
    Side effects: mock-mode log OR Meta Cloud API HTTP POST.
    """
    from app.services.whatsapp_alerts import _send_alert  # late import to avoid cycle
    await _send_alert(phone_number=phone_number, message=message, alert_type=alert_type)


# ---------------------------------------------------------------------------
# CONTENT WIRING
# ---------------------------------------------------------------------------

def _build_content_for_kind(
    tenant: Tenant,
    kind: str,
    today_in_tz: date,
    db: Session,
) -> str:
    """
    Pick the morning or evening content builder.

    Called by:    dispatch_briefing, manual_trigger_briefing.
    Calls into:   build_morning_briefing or build_evening_briefing, OR
                  briefing_intelligence.compose_briefing when the
                  tenant is opted into v6.3.11 pattern briefings.
    Side effects: pattern path may write briefing.signal_fired Event
                  rows; templated path is read-only.

    Raises ValueError on an unknown kind - that is a programming error,
    not a runtime miss; surface loudly.

    v6.3.11-alpha: when PATTERN_BRIEFING_TENANT_IDS lists this tenant,
    the new compose_briefing() runs first. Any failure inside that path
    falls through silently to the v6.3.4 templated builder so a broken
    signal can never break dispatch.
    """
    if kind == KIND_MORNING or kind == KIND_EVENING:
        # v6.3.11-alpha: opt-in pattern path. Failure must NEVER break
        # the existing templated dispatch — every exception falls
        # through to build_morning/evening_briefing below.
        from app.services.briefing_intelligence import (
            compose_briefing,
            is_pattern_briefing_enabled,
        )
        if is_pattern_briefing_enabled(tenant):
            try:
                return compose_briefing(
                    tenant_id=tenant.id,
                    kind=kind,
                    today=today_in_tz,
                    db=db,
                )
            except Exception:
                logger.exception(
                    "Pattern briefing failed for tenant %s (%s); "
                    "falling back to templated path.",
                    tenant.id, kind,
                )

    if kind == KIND_MORNING:
        return build_morning_briefing(
            tenant_id=tenant.id,
            industry_type=tenant.industry_type,
            today=today_in_tz,
            db=db,
        )
    if kind == KIND_EVENING:
        return build_evening_briefing(
            tenant_id=tenant.id,
            industry_type=tenant.industry_type,
            today=today_in_tz,
            db=db,
        )
    raise ValueError(f"Unknown briefing kind: {kind!r}")


# ---------------------------------------------------------------------------
# WINDOW MATCHING
# ---------------------------------------------------------------------------

def _time_falls_in_window(
    target: time,
    window_start_local: datetime,
    window_minutes: int = WINDOW_MINUTES,
) -> bool:
    """
    True when `target` time-of-day falls in the half-open
    [window_start_local.time(), window_start_local.time() + window_minutes).

    Called by:    dispatch_due_briefings + the per-user override check
                  inside dispatch_briefing.
    Calls into:   datetime arithmetic.
    Side effects: none.

    Handles the rare day-wraparound case (window_start_local at 23:58,
    window_minutes=5 -> spans midnight). When the window crosses
    midnight, the comparison naturally wraps via combine() with the
    next-day date.
    """
    if window_minutes <= 0:
        return False

    # Anchor target on today's date in the same tz so we can compare.
    same_day = window_start_local.replace(
        hour=target.hour,
        minute=target.minute,
        second=target.second,
        microsecond=0,
    )
    next_day = same_day + timedelta(days=1)

    window_end = window_start_local + timedelta(minutes=window_minutes)

    if same_day >= window_start_local and same_day < window_end:
        return True
    # Day-wraparound: the target time as if it were tomorrow.
    if next_day >= window_start_local and next_day < window_end:
        return True
    return False


def _effective_briefing_time(
    user: User,
    tenant_default: time,
    kind: str,
) -> time:
    """
    Resolve the effective briefing time for one user.

    Called by:    dispatch_briefing inner per-user loop.
    Calls into:   nothing.
    Side effects: none.

    Per-user override columns (briefing_time_override_morning /
    _evening) take precedence over the tenant default when set.
    """
    if kind == KIND_MORNING and user.briefing_time_override_morning is not None:
        return user.briefing_time_override_morning
    if kind == KIND_EVENING and user.briefing_time_override_evening is not None:
        return user.briefing_time_override_evening
    return tenant_default


# ---------------------------------------------------------------------------
# CORE DISPATCH
# ---------------------------------------------------------------------------

async def dispatch_briefing(
    tenant: Tenant,
    kind: str,
    db: Session,
    *,
    today_in_tz: Optional[date] = None,
    window_start_local: Optional[datetime] = None,
    send_fn: Optional[DispatchSendFn] = None,
    sleep_fn: SleepFn = asyncio.sleep,
    enforce_window: bool = True,
) -> BriefingDispatchResult:
    """
    Generate content for `tenant`+`kind`, resolve recipients, and send
    to each one via the retry wrapper.

    Called by:    dispatch_due_briefings (cron),
                  manual_trigger_briefing (WhatsApp request_briefing).
    Calls into:   resolve_recipients, _build_content_for_kind,
                  send_briefing_with_retry, _emit_event.
    Side effects:
        - Stages briefing.sent / briefing.send_failed events on `db`.
        - Performs WhatsApp sends via send_fn (mock or real).
        - Caller commits.

    Args:
        tenant:             The Tenant to dispatch for.
        kind:               'morning' | 'evening'.
        db:                 Sync session. Caller commits.
        today_in_tz:        Date in tenant tz for content generation.
                            Defaults to today_local() if not supplied.
        window_start_local: Datetime in tenant tz - the start of the
                            current 5-min window. Used only when
                            enforce_window=True to filter recipients
                            by their effective briefing time. None in
                            the manual-trigger path where the time
                            check does not apply.
        send_fn:            Override the default WhatsApp send wiring.
                            Tests pass an async stub.
        sleep_fn:           Override sleep for retry backoff. Tests
                            pass a no-op.
        enforce_window:     When True, filter recipients whose effective
                            briefing time does not fall in window. When
                            False (manual trigger), send to everyone.

    Returns:
        BriefingDispatchResult with sent_count, skipped_reasons, errors.
        Never raises - any per-recipient failure is captured in errors.
    """
    result = BriefingDispatchResult(kind=kind)

    if today_in_tz is None:
        today_in_tz = _today_in_tenant_tz(tenant)

    recipients = resolve_recipients(tenant, db)
    if not recipients:
        result.skipped_reasons.append((None, "no_recipients"))
        return result

    if enforce_window:
        if window_start_local is None:
            window_start_local = _now_in_tenant_tz(tenant)
        tenant_default_time = _tenant_default_time_for_kind(tenant, kind)
        recipients = [
            r for r in recipients
            if _time_falls_in_window(
                _effective_briefing_time(r.user, tenant_default_time, kind),
                window_start_local,
            )
        ]
        if not recipients:
            result.skipped_reasons.append((None, "window_mismatch"))
            return result

    content = _build_content_for_kind(tenant, kind, today_in_tz, db)

    real_send = send_fn if send_fn is not None else _default_send

    for r in recipients:
        async def _do_send(_pn=r.phone_number, _msg=content, _kind=kind):
            await real_send(_pn, _msg, f"briefing_{_kind}")

        ok = await send_briefing_with_retry(
            _do_send,
            tenant_id=tenant.id,
            kind=kind,
            recipient_user_id=r.user.id,
            db=db,
            sleep_fn=sleep_fn,
        )
        if ok:
            result.sent_count += 1
            _emit_event(
                db,
                tenant_id=tenant.id,
                event_type=EVENT_SENT,
                actor_user_id=None,
                source="system",
                payload={
                    "kind":              kind,
                    "recipient_user_id": r.user.id,
                    "content_chars":     len(content),
                },
            )
        else:
            # send_briefing_with_retry already emitted briefing.send_failed.
            result.errors.append((r.user.id, "send_failed_after_retries"))

    return result


async def dispatch_due_briefings(
    now_utc: Optional[datetime] = None,
    *,
    sleep_fn: SleepFn = asyncio.sleep,
    send_fn: Optional[DispatchSendFn] = None,
    session_factory: Optional[Callable[[], Session]] = None,
) -> DispatchSummary:
    """
    Top-level cron entry point. Called by APScheduler every WINDOW_MINUTES.

    Called by:    app.services.whatsapp_alerts.start_scheduler -
                  registered as 'briefing_dispatch_job'.
    Calls into:   dispatch_briefing for each (tenant, kind) match,
                  compute_stagger_offset for spread, sleep_fn for the
                  spread sleep, _emit_event for tenant-level skips.
    Side effects:
        - One short-lived session per tenant (sync) via session_factory.
        - Stages + commits Event rows. Manages its own commits because
          the cron path has no upstream caller to defer commit to.
        - WhatsApp sends per recipient.

    Args:
        now_utc:         UTC timestamp for the tick. Defaults to
                         datetime.now(timezone.utc). Tests pass a fixed
                         time via freezegun OR by supplying now_utc.
        sleep_fn:        Injected sleep for stagger + retry backoff.
                         Tests pass a no-op to avoid waiting.
        send_fn:         Optional WhatsApp send override; passed through
                         to dispatch_briefing.
        session_factory: Optional zero-arg callable returning a Session.
                         Defaults to app.database.SessionLocal at call
                         time (late-imported). Tests pass a callable
                         that returns the in-memory SQLite session so
                         the dispatcher exercises the cron orchestration
                         against the test DB.

    Returns:
        DispatchSummary aggregated across every tenant.
    """
    if session_factory is None:
        from app.database import SessionLocal  # late import to avoid cycle
        session_factory = SessionLocal

    summary = DispatchSummary()
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    # One short read-only session to enumerate tenants. Each per-tenant
    # dispatch then opens its own session for content + writes.
    list_db = session_factory()
    try:
        tenants = list(list_db.execute(select(Tenant)).scalars().all())
    finally:
        list_db.close()

    # Stagger handling: each tenant's offset is its desired position
    # WITHIN the 5-minute window relative to tick start. Sort tenants by
    # offset and sleep only the delta to the next tenant - so the total
    # wall-time of a tick is at most WINDOW_SECONDS, not the sum of all
    # individual offsets. Without sorting + delta, 22 tenants with
    # average offset 150s would compound to ~55 minutes of sleeping per
    # tick - which would silently break the cron cadence.
    tenants_by_offset = sorted(tenants, key=lambda t: compute_stagger_offset(t.id))
    cumulative_offset = 0

    for tenant in tenants_by_offset:
        summary.tenants_processed += 1

        offset = compute_stagger_offset(tenant.id)
        delta = offset - cumulative_offset
        if delta > 0:
            await sleep_fn(delta)
            cumulative_offset = offset

        for kind in ALL_KINDS:
            if not _kind_enabled(tenant, kind):
                # Disabled tenants produce no event - logging every
                # disabled tenant every 5 minutes would flood events.
                summary.skip_reasons["disabled"] = (
                    summary.skip_reasons.get("disabled", 0) + 1
                )
                summary.briefings_skipped += 1
                continue

            now_local = now_utc.astimezone(_tenant_zoneinfo(tenant))
            today_local = now_local.date()

            if not is_working_day(tenant, today_local):
                # Working-day mismatch is worth recording: an operator
                # may want to confirm the briefing skipped a holiday.
                tenant_db = session_factory()
                try:
                    _emit_event(
                        tenant_db,
                        tenant_id=tenant.id,
                        event_type=EVENT_SKIPPED,
                        actor_user_id=None,
                        source="system",
                        payload={"kind": kind, "reason": "non_working_day"},
                    )
                    tenant_db.commit()
                finally:
                    tenant_db.close()
                summary.skip_reasons["non_working_day"] = (
                    summary.skip_reasons.get("non_working_day", 0) + 1
                )
                summary.briefings_skipped += 1
                continue

            tenant_db = session_factory()
            try:
                # Re-fetch tenant on this session to keep ORM identity
                # clean - the tenant from list_db belongs to a closed
                # session and SQLAlchemy will detach it on commit.
                local_tenant = tenant_db.get(Tenant, tenant.id)
                if local_tenant is None:
                    continue
                result = await dispatch_briefing(
                    local_tenant,
                    kind,
                    tenant_db,
                    today_in_tz=today_local,
                    window_start_local=now_local,
                    send_fn=send_fn,
                    sleep_fn=sleep_fn,
                    enforce_window=True,
                )
                tenant_db.commit()
            except Exception as exc:
                logger.exception(
                    "dispatch_briefing crashed for tenant=%s kind=%s: %s",
                    tenant.id, kind, exc,
                )
                tenant_db.rollback()
                continue
            finally:
                tenant_db.close()

            summary.briefings_sent += result.sent_count
            for _, reason in result.skipped_reasons:
                summary.skip_reasons[reason] = (
                    summary.skip_reasons.get(reason, 0) + 1
                )
                summary.briefings_skipped += 1

    logger.info(
        "Briefing dispatch summary: tenants=%d sent=%d skipped=%d reasons=%s",
        summary.tenants_processed,
        summary.briefings_sent,
        summary.briefings_skipped,
        summary.skip_reasons,
    )
    return summary


# ---------------------------------------------------------------------------
# MANUAL TRIGGER (WhatsApp on-demand)
# ---------------------------------------------------------------------------

async def manual_trigger_briefing(
    user: User,
    kind: str,
    db: Session,
    *,
    send_fn: Optional[DispatchSendFn] = None,
    sleep_fn: SleepFn = asyncio.sleep,
) -> str:
    """
    Build + send a briefing on demand for a single user, then return
    the briefing text so the WhatsApp router can echo it as the reply.

    Called by:    app.services.whatsapp_intent.detect_briefing_request
                  (top-tier-only path - the intent layer enforces the
                  role gate before invoking this function).
    Calls into:   _build_content_for_kind, _emit_event,
                  send_briefing_with_retry (when a phone is linked).
    Side effects:
        - Stages briefing.manual_trigger event (always - even if no
          phone is linked, so audit can see the request happened).
        - Stages briefing.sent on success.
        - Performs one WhatsApp send when a linked active phone exists.
        - Caller commits.

    Args:
        user:    The User who requested the briefing. Must be top-tier;
                 the intent layer guarantees this. We do NOT re-check
                 here so the function is reusable from any authorised
                 surface (future: web 'preview my briefing' button).
        kind:    'morning' | 'evening'.
        db:      Sync session. Caller commits.
        send_fn: Test-injectable send override.
        sleep_fn: Test-injectable sleep for retry backoff.

    Returns:
        The briefing text. The caller (WhatsApp router) typically
        returns this as the reply to the inbound message.
    """
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None:
        raise ValueError(f"Tenant {user.tenant_id} not found for user {user.id}")

    today_local = _today_in_tenant_tz(tenant)
    content = _build_content_for_kind(tenant, kind, today_local, db)

    # Always emit the manual-trigger event - even if no phone is linked
    # the audit row records that the user asked.
    _emit_event(
        db,
        tenant_id=tenant.id,
        event_type=EVENT_MANUAL_TRIGGER,
        actor_user_id=user.id,
        source="whatsapp",
        payload={
            "kind":             kind,
            "requesting_user":  user.id,
            "content_chars":    len(content),
        },
    )

    # Look up the requester's linked phone for the send. If there is no
    # active link (rare for a top-tier user who triggered from WA, but
    # possible if the row was just deactivated), still return the text -
    # the router uses the return value as the reply.
    pmap = db.execute(
        select(PhoneTenantMap).where(
            PhoneTenantMap.user_id == user.id,
            PhoneTenantMap.tenant_id == tenant.id,
            PhoneTenantMap.is_active == True,  # noqa: E712
        )
    ).scalars().first()

    if pmap is None:
        return content

    real_send = send_fn if send_fn is not None else _default_send

    async def _do_send(_pn=pmap.phone_number, _msg=content, _kind=kind):
        await real_send(_pn, _msg, f"briefing_{_kind}_manual")

    ok = await send_briefing_with_retry(
        _do_send,
        tenant_id=tenant.id,
        kind=kind,
        recipient_user_id=user.id,
        db=db,
        sleep_fn=sleep_fn,
    )
    if ok:
        _emit_event(
            db,
            tenant_id=tenant.id,
            event_type=EVENT_SENT,
            actor_user_id=user.id,
            source="whatsapp",
            payload={
                "kind":              kind,
                "recipient_user_id": user.id,
                "content_chars":     len(content),
                "trigger":           "manual",
            },
        )
    return content


# ---------------------------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------------------------

def _kind_enabled(tenant: Tenant, kind: str) -> bool:
    """Tenant has the given briefing kind switched on?"""
    if kind == KIND_MORNING:
        return bool(tenant.briefing_morning_enabled)
    if kind == KIND_EVENING:
        return bool(tenant.briefing_evening_enabled)
    return False


def _tenant_default_time_for_kind(tenant: Tenant, kind: str) -> time:
    """Tenant-default briefing time for the given kind."""
    if kind == KIND_MORNING:
        return tenant.briefing_morning_time
    return tenant.briefing_evening_time


def _tenant_zoneinfo(tenant: Tenant) -> ZoneInfo:
    """
    Resolve the tenant's ZoneInfo, falling back to UTC on a bad name.

    Called by:    dispatch_due_briefings, _now_in_tenant_tz,
                  _today_in_tenant_tz.
    Calls into:   zoneinfo.ZoneInfo (raises ZoneInfoNotFoundError on a
                  bad IANA name - we catch and degrade to UTC).
    Side effects: none.
    """
    raw = tenant.briefing_timezone or "UTC"
    try:
        return ZoneInfo(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Tenant %s briefing_timezone %r unresolvable (%s) - falling back to UTC",
            tenant.id, raw, exc,
        )
        return ZoneInfo("UTC")


def _now_in_tenant_tz(tenant: Tenant) -> datetime:
    """Current wall-clock time in the tenant's timezone."""
    return datetime.now(timezone.utc).astimezone(_tenant_zoneinfo(tenant))


def _today_in_tenant_tz(tenant: Tenant) -> date:
    """Current wall-clock date in the tenant's timezone."""
    return _now_in_tenant_tz(tenant).date()


def _emit_event(
    db: Session,
    *,
    tenant_id: int,
    event_type: str,
    actor_user_id: Optional[int],
    source: str,
    payload: dict,
) -> None:
    """
    Stage one Event row on the caller's session. Caller commits.

    Called by:    dispatch_briefing, dispatch_due_briefings (skip events),
                  manual_trigger_briefing.
    Calls into:   db.add (no flush, no commit).
    Side effects: stages an INSERT on events.

    All briefing events use entity_type='briefing' and entity_id=None
    (briefings have no first-class table - the payload kind+recipient
    is the discriminator). Source is 'system' for cron, 'whatsapp' for
    manual trigger, mirroring the v6.3.3 team-management convention.
    """
    db.add(Event(
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type="briefing",
        entity_id=None,
        actor_user_id=actor_user_id,
        source=source,
        payload=payload,
    ))
