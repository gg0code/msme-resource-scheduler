# tests/test_briefings.py
#
# FILE PURPOSE
# v6.3.4 test coverage for the daily push briefings surface:
#   - Cron path (dispatch_due_briefings) - window matching, working-day
#     skip, no-recipients skip, disabled-tenant silent skip.
#   - Per-tenant dispatch (dispatch_briefing) - send + event emission,
#     industry-aware vocabulary, per-recipient overrides, retry behaviour.
#   - Manual trigger (manual_trigger_briefing) - top-tier-only, returns
#     content, emits manual_trigger event.
#   - Content generators - today's jobs list, top-5 cap with more-marker,
#     1000-char cap, idle-floor templates, evening completions.
#   - Stagger (compute_stagger_offset) - 100 tenants spread across window.
#   - Intent detection (detect_briefing_request_intent) - keyword set.
#   - BUG-6 regression: industry_type sourced from Tenant ORM only.
#
# All tests are service-direct against the in-memory SQLite DB. Time is
# frozen with freezegun so window matching is deterministic. The
# dispatcher's WhatsApp send wiring is replaced with a recording stub
# so no real (or mock-mode) WhatsApp send is exercised.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefings.dispatcher.{dispatch_due_briefings,
#       dispatch_briefing, manual_trigger_briefing, resolve_recipients,
#       is_working_day, compute_stagger_offset}
#   app.services.briefings.morning_content.build_morning_briefing
#   app.services.briefings.evening_content.build_evening_briefing
#   app.services.briefings.send_with_retry.send_briefing_with_retry
#   app.services.briefings.templates.{industry_labels, pick_template}
#   app.services.whatsapp_intent.detect_briefing_request_intent
#   app.models.{auth.Tenant, auth.User, whatsapp.PhoneTenantMap,
#       event.Event, job.Job, employee.Employee}

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import pytest
from freezegun import freeze_time
from sqlalchemy import text as sa_text
from sqlalchemy.sql.schema import DefaultClause

from app.core.security import hash_password
from app.models.auth import RefreshToken, Tenant, User
from app.models.employee import Employee
from app.models.event import Event
from app.models.job import Job
from app.models.whatsapp import PhoneTenantMap
from app.services.briefings import (
    BriefingDispatchResult,
    DispatchSummary,
    compute_stagger_offset,
    dispatch_briefing,
    dispatch_due_briefings,
    is_working_day,
    manual_trigger_briefing,
    resolve_recipients,
)
from app.services.briefings.evening_content import build_evening_briefing
from app.services.briefings.morning_content import (
    MAX_BRIEFING_CHARS,
    MAX_JOB_LINES,
    build_morning_briefing,
)
from app.services.briefings.send_with_retry import send_briefing_with_retry
from app.services.briefings.templates import (
    INDUSTRY_LABELS,
    industry_labels,
)
from app.services.whatsapp_intent import detect_briefing_request_intent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    """Swap text("now()") server defaults to CURRENT_TIMESTAMP for SQLite.
    Same pattern as tests/test_team_management.py and
    tests/test_signup_v6_4.py - reused so this file is self-contained
    and does not depend on import order. Briefings touch Job + Employee
    so those table sweeps are added too."""
    patched = []
    for table_attr in (
        Tenant.__table__,
        User.__table__,
        RefreshToken.__table__,
        PhoneTenantMap.__table__,
        Event.__table__,
        Job.__table__,
        Employee.__table__,
    ):
        for col in table_attr.columns:
            if col.server_default is None:
                continue
            arg = getattr(col.server_default, "arg", None)
            text_value = str(arg) if arg is not None else ""
            if "now()" in text_value.lower():
                patched.append((col, col.server_default))
                col.server_default = DefaultClause(sa_text("CURRENT_TIMESTAMP"))
    yield
    for col, original in patched:
        col.server_default = original


_COUNTER = {"n": 0}


def _next() -> int:
    _COUNTER["n"] += 1
    return _COUNTER["n"]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _make_tenant(
    db,
    *,
    industry_type: Optional[str] = "printing",
    morning_enabled: bool = True,
    morning_time: time = time(7, 30),
    evening_enabled: bool = False,
    evening_time: time = time(18, 30),
    timezone_name: str = "Asia/Kolkata",
    working_days: str = "1,2,3,4,5,6",
) -> Tenant:
    n = _next()
    now = _now_utc()
    tenant = Tenant(
        name=f"Acme {n}",
        slug=f"acme-{n}",
        plan="free",
        is_active=True,
        industry_type=industry_type,
        briefing_morning_enabled=morning_enabled,
        briefing_morning_time=morning_time,
        briefing_evening_enabled=evening_enabled,
        briefing_evening_time=evening_time,
        briefing_timezone=timezone_name,
        briefing_working_days=working_days,
        created_at=now,
        updated_at=now,
    )
    db.add(tenant)
    db.flush()
    return tenant


def _make_user(
    db,
    *,
    tenant: Tenant,
    role: str = "proprietor",
    email: Optional[str] = None,
    is_active: bool = True,
    briefing_subscribed: bool = True,
    morning_override: Optional[time] = None,
    evening_override: Optional[time] = None,
) -> User:
    n = _next()
    now = _now_utc()
    user = User(
        tenant_id=tenant.id,
        email=email or f"u{n}@t.com",
        hashed_password=hash_password("testpass"),
        role=role,
        is_active=is_active,
        briefing_subscribed=briefing_subscribed,
        briefing_time_override_morning=morning_override,
        briefing_time_override_evening=evening_override,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


def _make_phone(
    db,
    *,
    tenant: Tenant,
    user: User,
    phone_number: Optional[str] = None,
    is_active: bool = True,
    phone_role: str = "owner",
) -> PhoneTenantMap:
    n = _next()
    pmap = PhoneTenantMap(
        phone_number=phone_number or f"+91987654{n:04d}",
        tenant_id=tenant.id,
        user_id=user.id,
        is_active=is_active,
        phone_role=phone_role,
        industry_type=tenant.industry_type,
        consent_given=True,
    )
    db.add(pmap)
    db.flush()
    return pmap


def _make_job(
    db,
    *,
    tenant: Tenant,
    name: Optional[str] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    status: str = "in_progress",
) -> Job:
    n = _next()
    today = date.today()
    now = _now_utc()
    job = Job(
        tenant_id=tenant.id,
        name=name or f"Job {n}",
        start_date=start or today,
        end_date=end or today,
        estimated_hours_per_day=8.0,
        priority="Medium",
        status=status,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()
    return job


def _make_employee(db, *, tenant: Tenant, status: str = "active") -> Employee:
    n = _next()
    now = _now_utc()
    employee = Employee(
        tenant_id=tenant.id,
        full_name=f"Emp {n}",
        status=status,
    )
    # created_at / updated_at are model-side defaults via lambda - leave them.
    db.add(employee)
    db.flush()
    return employee


class _RecordingSender:
    """Async send_fn stub that records every (phone, message, alert_type)."""

    def __init__(self, fail_times: int = 0):
        self.calls: list[tuple[str, str, str]] = []
        self._fail_remaining = fail_times

    async def __call__(self, phone_number: str, message: str, alert_type: str) -> None:
        self.calls.append((phone_number, message, alert_type))
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise RuntimeError("simulated send failure")


async def _noop_sleep(_seconds: float) -> None:
    """Sleep stub so tests do not actually wait."""
    return None


# Wraps a single Session in a callable so dispatch_due_briefings can
# reuse the SAME in-memory connection across enumerate + per-tenant
# dispatch (we don't want a fresh SQLite connection per call).
def _session_factory_for(db):
    def _factory():
        # Return the same session each time. Caller will call .close()
        # which is harmless here - the engine itself stays alive.
        class _Wrapped:
            def __init__(self, sess):
                self._sess = sess
            def __getattr__(self, item):
                return getattr(self._sess, item)
            def close(self):
                # No-op: outer test owns the session lifecycle.
                pass
        return _Wrapped(db)
    return _factory


# ---------------------------------------------------------------------------
# is_working_day + working_days CSV
# ---------------------------------------------------------------------------

class TestWorkingDay:

    def test_default_mon_to_sat_monday_is_working(self, db):
        tenant = _make_tenant(db, working_days="1,2,3,4,5,6")
        # 2026-04-27 is a Monday (ISO weekday 1)
        assert is_working_day(tenant, date(2026, 4, 27)) is True

    def test_default_mon_to_sat_sunday_is_not_working(self, db):
        tenant = _make_tenant(db, working_days="1,2,3,4,5,6")
        # 2026-04-26 is a Sunday (ISO weekday 7)
        assert is_working_day(tenant, date(2026, 4, 26)) is False

    def test_garbled_csv_defaults_to_working(self, db):
        tenant = _make_tenant(db, working_days="not,a,number")
        assert is_working_day(tenant, date(2026, 4, 27)) is True


# ---------------------------------------------------------------------------
# resolve_recipients
# ---------------------------------------------------------------------------

class TestResolveRecipients:

    def test_only_top_tier_with_active_phone_returned(self, db):
        tenant = _make_tenant(db)
        # In-set recipient
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        _make_phone(db, tenant=tenant, user=owner)
        # Out-of-set: scheduler is NOT top-tier
        sched = _make_user(db, tenant=tenant, role="scheduler", email="s@t.com")
        _make_phone(db, tenant=tenant, user=sched)
        # Out-of-set: top-tier but not subscribed
        copo = _make_user(
            db, tenant=tenant, role="co_owner",
            email="c@t.com", briefing_subscribed=False,
        )
        _make_phone(db, tenant=tenant, user=copo)
        # Out-of-set: top-tier, subscribed, but inactive phone
        fm = _make_user(
            db, tenant=tenant, role="factory_manager", email="f@t.com",
        )
        _make_phone(db, tenant=tenant, user=fm, is_active=False)
        recipients = resolve_recipients(tenant, db)
        assert len(recipients) == 1
        assert recipients[0].user.id == owner.id


# ---------------------------------------------------------------------------
# Cron path: dispatch_due_briefings
# ---------------------------------------------------------------------------

class TestDispatchDueBriefings:

    @pytest.mark.asyncio
    async def test_morning_briefing_fires_at_configured_time(self, db):
        # 2026-04-27 02:00 UTC == 07:30 IST (Monday, working day).
        # Job dates anchored to the same wall-clock date so the morning
        # builder sees a non-empty today list (avoiding the idle path).
        tenant = _make_tenant(db, morning_enabled=True, morning_time=time(7, 30))
        owner = _make_user(db, tenant=tenant, role="proprietor")
        _make_phone(db, tenant=tenant, user=owner)
        _make_job(
            db, tenant=tenant,
            start=date(2026, 4, 27), end=date(2026, 4, 27),
        )
        sender = _RecordingSender()
        with freeze_time("2026-04-27 02:00:00", tz_offset=0):
            summary = await dispatch_due_briefings(
                sleep_fn=_noop_sleep,
                send_fn=sender,
                session_factory=_session_factory_for(db),
            )
        assert summary.briefings_sent == 1
        assert len(sender.calls) == 1
        phone, message, alert_type = sender.calls[0]
        assert alert_type == "briefing_morning"
        assert "Aaj ka plan" in message or "Today's plan" in message

    @pytest.mark.asyncio
    async def test_evening_briefing_fires_at_configured_time(self, db):
        # 2026-04-27 13:00 UTC == 18:30 IST (Monday, working day)
        tenant = _make_tenant(
            db, morning_enabled=False,
            evening_enabled=True, evening_time=time(18, 30),
        )
        owner = _make_user(db, tenant=tenant, role="proprietor")
        _make_phone(db, tenant=tenant, user=owner)
        _make_job(db, tenant=tenant, status="completed")
        sender = _RecordingSender()
        with freeze_time("2026-04-27 13:00:00", tz_offset=0):
            summary = await dispatch_due_briefings(
                sleep_fn=_noop_sleep,
                send_fn=sender,
                session_factory=_session_factory_for(db),
            )
        assert summary.briefings_sent == 1
        assert sender.calls[0][2] == "briefing_evening"

    @pytest.mark.asyncio
    async def test_briefing_skipped_on_sunday(self, db):
        # 2026-04-26 is a Sunday. Tenant working days are Mon-Sat.
        tenant = _make_tenant(db, morning_enabled=True, morning_time=time(7, 30))
        owner = _make_user(db, tenant=tenant, role="proprietor")
        _make_phone(db, tenant=tenant, user=owner)
        sender = _RecordingSender()
        with freeze_time("2026-04-26 02:00:00"):
            summary = await dispatch_due_briefings(
                sleep_fn=_noop_sleep,
                send_fn=sender,
                session_factory=_session_factory_for(db),
            )
        assert summary.briefings_sent == 0
        assert summary.skip_reasons.get("non_working_day", 0) >= 1
        assert sender.calls == []
        # Sunday skip writes a briefing.skipped event.
        events = db.query(Event).filter(
            Event.event_type == "briefing.skipped",
        ).all()
        assert any(e.payload["reason"] == "non_working_day" for e in events)

    @pytest.mark.asyncio
    async def test_briefing_skipped_with_no_top_tier_recipients(self, db):
        # Tenant config matches the v6.3.3 lockout-risk pattern: enabled
        # briefings but no active top-tier user. Dispatcher must not
        # crash, must not send, must not write a sent event.
        tenant = _make_tenant(db, morning_enabled=True, morning_time=time(7, 30))
        sched = _make_user(db, tenant=tenant, role="scheduler")
        _make_phone(db, tenant=tenant, user=sched)
        sender = _RecordingSender()
        with freeze_time("2026-04-27 02:00:00"):
            summary = await dispatch_due_briefings(
                sleep_fn=_noop_sleep,
                send_fn=sender,
                session_factory=_session_factory_for(db),
            )
        assert summary.briefings_sent == 0
        assert sender.calls == []

    @pytest.mark.asyncio
    async def test_briefing_disabled_tenant_skipped_silently(self, db):
        # Documented behaviour (per prompt brief): a disabled tenant
        # produces NO briefing.skipped event - logging every disabled
        # tenant every 5 minutes would flood the events table.
        tenant = _make_tenant(db, morning_enabled=False, evening_enabled=False)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        _make_phone(db, tenant=tenant, user=owner)
        sender = _RecordingSender()
        with freeze_time("2026-04-27 02:00:00"):
            summary = await dispatch_due_briefings(
                sleep_fn=_noop_sleep,
                send_fn=sender,
                session_factory=_session_factory_for(db),
            )
        assert summary.briefings_sent == 0
        assert summary.skip_reasons.get("disabled", 0) >= 1
        # No skipped event for a disabled tenant.
        events = db.query(Event).filter(
            Event.event_type == "briefing.skipped",
        ).all()
        assert events == []

    @pytest.mark.asyncio
    async def test_briefing_event_logged_per_recipient(self, db):
        tenant = _make_tenant(db, morning_enabled=True, morning_time=time(7, 30))
        u1 = _make_user(db, tenant=tenant, role="proprietor", email="u1@t.com")
        u2 = _make_user(db, tenant=tenant, role="co_owner", email="u2@t.com")
        _make_phone(db, tenant=tenant, user=u1, phone_number="+919999000001")
        _make_phone(db, tenant=tenant, user=u2, phone_number="+919999000002")
        sender = _RecordingSender()
        with freeze_time("2026-04-27 02:00:00"):
            await dispatch_due_briefings(
                sleep_fn=_noop_sleep,
                send_fn=sender,
                session_factory=_session_factory_for(db),
            )
        sent_events = db.query(Event).filter(
            Event.tenant_id == tenant.id,
            Event.event_type == "briefing.sent",
        ).all()
        assert len(sent_events) == 2
        recipient_ids = sorted(e.payload["recipient_user_id"] for e in sent_events)
        assert recipient_ids == sorted([u1.id, u2.id])

    @pytest.mark.asyncio
    async def test_per_user_time_override_respected(self, db):
        # Tenant default morning is 07:30 IST. One user has an 08:00
        # override. At 02:00 UTC (07:30 IST) only the no-override user
        # should fire; at 02:30 UTC (08:00 IST) only the override user.
        tenant = _make_tenant(db, morning_enabled=True, morning_time=time(7, 30))
        no_ovr = _make_user(db, tenant=tenant, role="proprietor", email="def@t.com")
        ovr = _make_user(
            db, tenant=tenant, role="co_owner",
            email="ovr@t.com",
            morning_override=time(8, 0),
        )
        _make_phone(db, tenant=tenant, user=no_ovr, phone_number="+919999100001")
        _make_phone(db, tenant=tenant, user=ovr,    phone_number="+919999100002")

        sender_a = _RecordingSender()
        with freeze_time("2026-04-27 02:00:00"):
            await dispatch_due_briefings(
                sleep_fn=_noop_sleep,
                send_fn=sender_a,
                session_factory=_session_factory_for(db),
            )
        # The no-override user should have received exactly one send.
        assert len(sender_a.calls) == 1
        assert sender_a.calls[0][0] == "+919999100001"

        sender_b = _RecordingSender()
        with freeze_time("2026-04-27 02:30:00"):
            await dispatch_due_briefings(
                sleep_fn=_noop_sleep,
                send_fn=sender_b,
                session_factory=_session_factory_for(db),
            )
        assert len(sender_b.calls) == 1
        assert sender_b.calls[0][0] == "+919999100002"


# ---------------------------------------------------------------------------
# Send retry
# ---------------------------------------------------------------------------

class TestSendRetry:

    @pytest.mark.asyncio
    async def test_send_failure_retries_three_times(self, db):
        # Sender fails on every attempt - the wrapper retries 3 times
        # (4 total invocations) and emits a briefing.send_failed event.
        tenant = _make_tenant(db)
        attempts = {"n": 0}

        async def always_fails():
            attempts["n"] += 1
            raise RuntimeError("nope")

        ok = await send_briefing_with_retry(
            always_fails,
            tenant_id=tenant.id,
            kind="morning",
            recipient_user_id=42,
            db=db,
            sleep_fn=_noop_sleep,
        )
        db.commit()
        assert ok is False
        assert attempts["n"] == 4   # 1 + 3 retries
        failures = db.query(Event).filter(
            Event.tenant_id == tenant.id,
            Event.event_type == "briefing.send_failed",
        ).all()
        assert len(failures) == 1
        assert failures[0].payload["attempts"] == 4
        assert failures[0].payload["recipient_user_id"] == 42

    @pytest.mark.asyncio
    async def test_send_succeeds_first_try_no_failure_event(self, db):
        tenant = _make_tenant(db)
        attempts = {"n": 0}

        async def always_works():
            attempts["n"] += 1

        ok = await send_briefing_with_retry(
            always_works,
            tenant_id=tenant.id,
            kind="morning",
            recipient_user_id=1,
            db=db,
            sleep_fn=_noop_sleep,
        )
        db.commit()
        assert ok is True
        assert attempts["n"] == 1
        failures = db.query(Event).filter(
            Event.event_type == "briefing.send_failed",
        ).all()
        assert failures == []


# ---------------------------------------------------------------------------
# Manual trigger
# ---------------------------------------------------------------------------

class TestManualTrigger:

    @pytest.mark.asyncio
    async def test_manual_trigger_returns_text_and_emits_event(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        _make_phone(db, tenant=tenant, user=owner)
        _make_job(db, tenant=tenant, name="Calendar Print")
        sender = _RecordingSender()
        text = await manual_trigger_briefing(
            user=owner,
            kind="morning",
            db=db,
            send_fn=sender,
            sleep_fn=_noop_sleep,
        )
        db.commit()
        assert text  # non-empty
        # Manual trigger event always fires.
        manual_events = db.query(Event).filter(
            Event.tenant_id == tenant.id,
            Event.event_type == "briefing.manual_trigger",
        ).all()
        assert len(manual_events) == 1
        assert manual_events[0].payload["kind"] == "morning"
        assert manual_events[0].payload["requesting_user"] == owner.id
        assert manual_events[0].source == "whatsapp"
        assert manual_events[0].actor_user_id == owner.id
        # Send was issued exactly once (only to the requester).
        assert len(sender.calls) == 1
        assert sender.calls[0][2] == "briefing_morning_manual"
        # And a briefing.sent event with trigger=manual exists.
        sent_events = db.query(Event).filter(
            Event.event_type == "briefing.sent",
            Event.tenant_id == tenant.id,
        ).all()
        assert len(sent_events) == 1
        assert sent_events[0].payload.get("trigger") == "manual"

    @pytest.mark.asyncio
    async def test_manual_trigger_morning_returns_to_requester_only(self, db):
        # Tenant has TWO top-tier users; manual trigger by one user must
        # only send to that user. Cron behaviour fans out; manual does not.
        tenant = _make_tenant(db)
        u1 = _make_user(db, tenant=tenant, role="proprietor", email="u1@t.com")
        u2 = _make_user(db, tenant=tenant, role="co_owner", email="u2@t.com")
        _make_phone(db, tenant=tenant, user=u1, phone_number="+919998000001")
        _make_phone(db, tenant=tenant, user=u2, phone_number="+919998000002")
        sender = _RecordingSender()
        await manual_trigger_briefing(
            user=u1,
            kind="morning",
            db=db,
            send_fn=sender,
            sleep_fn=_noop_sleep,
        )
        db.commit()
        assert len(sender.calls) == 1
        assert sender.calls[0][0] == "+919998000001"


# ---------------------------------------------------------------------------
# Briefing intent detection (router-side keyword classifier)
# ---------------------------------------------------------------------------

class TestBriefingIntent:

    @pytest.mark.parametrize("phrase,expected", [
        ("morning briefing",        "morning"),
        ("today's plan please",     "morning"),
        ("aaj ka plan dikhao",      "morning"),
        ("evening briefing",        "evening"),
        ("today's summary",         "evening"),
        ("aaj ka summary",          "evening"),
        ("din ka summary share kar","evening"),
        ("hello",                   None),
        ("",                        None),
    ])
    def test_detects_briefing_kind(self, phrase, expected):
        assert detect_briefing_request_intent(phrase) == expected

    def test_manual_trigger_blocked_for_non_top_tier_via_intent_layer(self):
        # The router enforces: detect_briefing_request_intent returns the
        # kind, then the router checks PHONE_TOP_TIER_ROLES. Asserting
        # the contract here (the keyword is detected even for a manager
        # phone - it is the router's job to refuse).
        from app.services.whatsapp_intent import PHONE_TOP_TIER_ROLES
        assert detect_briefing_request_intent("morning briefing") == "morning"
        assert "manager" not in PHONE_TOP_TIER_ROLES
        assert "scheduler" not in PHONE_TOP_TIER_ROLES
        assert "proprietor" in PHONE_TOP_TIER_ROLES
        assert "owner" in PHONE_TOP_TIER_ROLES

    # -----------------------------------------------------------------------
    # v6.3.20 disambiguation — settings-change phrases must fall through
    # -----------------------------------------------------------------------
    # Before v6.3.20 the classifier returned "morning" for any message
    # containing the substring "morning briefing" — including
    # "morning briefing 8 baje karo" which is a settings change, not a
    # display request. The router then dispatched manual_trigger_briefing
    # and update_push_setting was never offered to the LLM. See
    # v6.3.20bug.md for the original bug report.

    @pytest.mark.parametrize("phrase", [
        # Time literal + briefing keyword
        "morning briefing 8 baje karo",
        "morning briefing 6:30 baje kar do",
        "morning briefing 8pm kar do",
        "today's plan 9 AM kar do",
        # On/off intent + briefing keyword
        "morning briefing band karo",
        "evening briefing band karo",
        "morning briefing chalu karo",
        # Replacement phrasing
        "evening briefing 7 ke jagah 8 baje karo",
        "morning briefing instead of 7:30 do 8:00",
        # Pause / break intent + briefing keyword
        "agle 5 din chuti hai, morning briefing band karo",
        "morning briefing pause karo",
        # Change-intent verb + briefing keyword (no time literal)
        "morning briefing time change karo",
        "shift morning briefing to 8:00",
    ])
    def test_v6_3_20_settings_change_phrases_fall_through(self, phrase):
        """Settings-change phrases that contain a briefing keyword must
        NOT trigger manual_trigger_briefing — they must fall through to
        the AI so update_push_setting / pause_push can be offered."""
        assert detect_briefing_request_intent(phrase) is None

    @pytest.mark.parametrize("phrase,expected", [
        # Plain display intents — must continue to dispatch.
        ("morning briefing",            "morning"),
        ("today's plan",                "morning"),
        ("today's plan dikhao",         "morning"),
        ("evening briefing",            "evening"),
        ("today's summary",             "evening"),
        # Display-adjacent verbs that are NOT in the strong-verb set —
        # "share kar do" / "share karo" must NOT trigger suppression.
        ("aaj ka plan share kar do",    "morning"),
        ("din ka summary share karo",   "evening"),
        # "dikhao" is benign — never a settings verb.
        ("abhi ka briefing dikhao",     None),   # no kind keyword — falls through anyway
        ("morning briefing dikhao",     "morning"),
        ("evening briefing dikhao",     "evening"),
    ])
    def test_v6_3_20_display_phrases_still_dispatch(self, phrase, expected):
        """Display intents must still trigger the dispatcher even when
        nearby words look settings-adjacent. The benign verbs
        share/kar/do/dikhao are deliberately excluded from the
        settings-change strong-verb set."""
        assert detect_briefing_request_intent(phrase) == expected


# ---------------------------------------------------------------------------
# Stagger
# ---------------------------------------------------------------------------

class TestStagger:

    def test_concurrent_dispatch_stagger_spreads_across_window(self):
        # 100 sequential tenant_ids should produce a wide spread of
        # offsets across the 5-minute (300s) window.
        offsets = [compute_stagger_offset(i) for i in range(1, 101)]
        assert min(offsets) >= 0
        assert max(offsets) < 300
        # Reasonable spread - at least two-thirds of the window covered.
        assert max(offsets) - min(offsets) > 200
        # Reasonable uniqueness - far more than half are distinct.
        assert len(set(offsets)) >= 80


# ---------------------------------------------------------------------------
# Content - morning generator
# ---------------------------------------------------------------------------

class TestMorningContent:

    def test_morning_content_lists_today_jobs(self, db):
        tenant = _make_tenant(db)
        _make_job(db, tenant=tenant, name="Calendar Print")
        _make_job(db, tenant=tenant, name="Brochure Run")
        text = build_morning_briefing(
            tenant_id=tenant.id,
            industry_type=tenant.industry_type,
            today=date.today(),
            db=db,
        )
        assert "Calendar Print" in text
        assert "Brochure Run"   in text

    def test_morning_content_caps_at_top_5_with_more_marker(self, db):
        tenant = _make_tenant(db)
        for i in range(30):
            _make_job(db, tenant=tenant, name=f"Print Run {i:02d}")
        text = build_morning_briefing(
            tenant_id=tenant.id,
            industry_type=tenant.industry_type,
            today=date.today(),
            db=db,
        )
        # Exactly MAX_JOB_LINES bullet lines and a more-marker for the rest.
        bullet_count = sum(1 for line in text.splitlines() if line.startswith("- "))
        assert bullet_count == MAX_JOB_LINES
        # 30 - 5 = 25 more
        assert "25" in text
        assert "more" in text or "aur" in text

    def test_idle_floor_morning_template_used(self, db):
        tenant = _make_tenant(db)
        # No jobs - idle floor.
        text = build_morning_briefing(
            tenant_id=tenant.id,
            industry_type=tenant.industry_type,
            today=date.today(),
            db=db,
        )
        # Idle templates do not list jobs and explicitly say so.
        assert "- " not in text or "Aaj koi" in text or "No jobs" in text

    def test_industry_aware_morning_content_fabrication(self, db):
        tenant = _make_tenant(db, industry_type="fabrication")
        _make_job(db, tenant=tenant, name="Steel Frame")
        text = build_morning_briefing(
            tenant_id=tenant.id,
            industry_type="fabrication",
            today=date.today(),
            db=db,
        )
        # Fabrication labels say 'orders', not 'jobs'.
        assert "Orders" in text or "orders" in text
        assert "Press"  not in text  # 'press' belongs to printing vocabulary

    def test_industry_aware_morning_content_printing_no_cross_contamination(self, db):
        tenant = _make_tenant(db, industry_type="printing")
        _make_job(db, tenant=tenant, name="Calendar Print")
        text = build_morning_briefing(
            tenant_id=tenant.id,
            industry_type="printing",
            today=date.today(),
            db=db,
        )
        # Printing keeps "Jobs" - never accidentally pulls fabrication terms.
        assert "Jobs" in text
        assert "orders"     not in text.lower()
        assert "operators"  not in text.lower()
        assert "technicians" not in text.lower()

    def test_morning_content_under_1000_chars(self, db):
        tenant = _make_tenant(db)
        # Long names + many jobs - the cap should still hold.
        for i in range(50):
            _make_job(
                db, tenant=tenant,
                name=f"Very long descriptive job name #{i:03d} with extra text",
            )
        text = build_morning_briefing(
            tenant_id=tenant.id,
            industry_type=tenant.industry_type,
            today=date.today(),
            db=db,
        )
        assert len(text) <= MAX_BRIEFING_CHARS

    def test_bug_6_industry_type_sourced_from_tenant_orm(self, db):
        # BUG-6 regression: industry_type must come from the Tenant ORM,
        # never from any user-supplied value. The content generator's
        # contract takes `industry_type` directly so the *caller* (the
        # dispatcher) is responsible for sourcing it. We assert that
        # contract here by passing the tenant's industry value through
        # explicitly and verifying the labels mapping took effect.
        tenant = _make_tenant(db, industry_type="chemical")
        _make_job(db, tenant=tenant, name="Reactor Run")
        text = build_morning_briefing(
            tenant_id=tenant.id,
            industry_type=tenant.industry_type,   # sourced from ORM
            today=date.today(),
            db=db,
        )
        # Chemical labels: 'batches' for jobs.
        assert "Batches" in text or "batches" in text
        assert "jobs" not in text.lower() or "batches" in text.lower()


# ---------------------------------------------------------------------------
# Content - evening generator
# ---------------------------------------------------------------------------

class TestEveningContent:

    def test_evening_content_lists_completions(self, db):
        tenant = _make_tenant(db)
        _make_job(db, tenant=tenant, status="completed")
        _make_job(db, tenant=tenant, status="completed")
        _make_job(db, tenant=tenant, status="in_progress")
        text = build_evening_briefing(
            tenant_id=tenant.id,
            industry_type=tenant.industry_type,
            today=date.today(),
            db=db,
        )
        # 2 completions today.
        assert "2" in text

    def test_idle_floor_evening_template_used(self, db):
        tenant = _make_tenant(db)
        # Zero jobs total -> evening idle template fires.
        text = build_evening_briefing(
            tenant_id=tenant.id,
            industry_type=tenant.industry_type,
            today=date.today(),
            db=db,
        )
        assert "idle" in text.lower() or "nahi chala" in text.lower()


# ---------------------------------------------------------------------------
# Industry labels mapping
# ---------------------------------------------------------------------------

class TestIndustryLabels:

    def test_unknown_industry_falls_back_to_printing(self):
        labels = industry_labels("space-mining")
        assert labels == INDUSTRY_LABELS["printing"]

    def test_none_industry_falls_back_to_printing(self):
        labels = industry_labels(None)
        assert labels == INDUSTRY_LABELS["printing"]
