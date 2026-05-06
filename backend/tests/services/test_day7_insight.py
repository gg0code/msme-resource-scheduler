# tests/services/test_day7_insight.py
# Branch: v5-whatsapp
# Iteration: v6.3.16 (Day-7 First-Insight Gate)
#
# FILE PURPOSE
# Unit tests for app/services/day7_insight.py — the Day-7 First-Insight
# Gate. Covers the four signal detectors (attendance / skill bottleneck
# / machine utilisation / recurring customer), the fallback message
# composer, and the gate's idempotency + suppression contracts.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.day7_insight.evaluate_and_send (and the private
#     detectors when asserting at the unit level).
#   app.services.day7_thresholds — for threshold constants used in
#     fixture sizing.
#   tests/services/conftest.py builders (make_tenant, make_employee,
#     make_machine, make_job, make_assignment, make_attendance_event).
#
# DESIGN NOTES
#   - Tests pin TODAY = date(2026, 5, 4) and pass `today=TODAY` to
#     make_tenant so SQLite-driven boundary assertions are deterministic
#     across UTC midnight crossings (same convention as the v6.3.11
#     evaluator tests, see tests/services/conftest.py header).
#   - Recipients are minted inline (User + PhoneTenantMap) because the
#     conftest does not provide a builder for the full WhatsApp-linked
#     owner shape. Each test that exercises send fan-out calls
#     _make_owner_with_phone(db, tenant) to set up a valid recipient.
#   - send_fn fakes are tiny in-memory recorders; the gate's fan-out
#     loop is deterministic so list ordering matches recipient list.

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import pytest

from app.models.auth import User
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate
from app.models.job import JobAssignment, JobSkillRequirement
from app.models.skill import Skill
from app.models.whatsapp import PhoneTenantMap
from app.routers.scheduler_router import ScheduleEntryModel
from app.services import day7_insight
from app.services.day7_insight import (
    EVENT_DAY7_FAILED,
    EVENT_DAY7_SENT,
    EVENT_DAY7_SUPPRESSED,
    LADDER_KEY_DAY7_SENT,
    SIGNAL_ATTENDANCE,
    SIGNAL_CUSTOMER,
    SIGNAL_FALLBACK,
    SIGNAL_MACHINE,
    SIGNAL_SKILL,
    evaluate_and_send,
)
from app.services.day7_thresholds import (
    ATTENDANCE_MIN_ABSENT_DAYS_PER_WORKER,
    ATTENDANCE_MIN_WORKERS_SAME_WEEKDAY,
    CUSTOMER_RECURRING_MIN_MENTIONS,
    LOOKBACK_DAYS,
    MACHINE_UTILISATION_MIN_HOURS_PER_DAY,
    MACHINE_UTILISATION_RATIO_THRESHOLD,
    SKILL_BOTTLENECK_MIN_JOBS,
    SUPPRESS_IF_DAY_COUNT_OVER,
)

from tests.services.conftest import (
    make_assignment,
    make_attendance_event,
    make_employee,
    make_job,
    make_machine,
    make_tenant,
)


# Fixed wall-clock anchor — every test sets the tenant up so that
# TODAY's tenant-tz date is exactly LOOKBACK_DAYS days after first
# briefing, i.e. day_count == 7 (the trigger day).
TODAY = date(2026, 5, 4)
NOW_UTC = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class FakeSender:
    """In-memory recorder for the (phone, message, alert_type) async send.

    Used in:    every test that exercises evaluate_and_send's fan-out.
    Calls into: nothing — pure storage.
    Side effects: appends one tuple per call to .calls.

    Pass `raise_on_call=True` to simulate a hard send failure (the
    gate must catch the exception, NOT mark the ledger, and emit
    engagement.day7_owner_failed). Pass `raise_first_only=True` to
    simulate a partial fan-out failure where the first recipient
    fails but the rest succeed — the gate must still mark the ledger
    because at least one send landed.
    """
    def __init__(self, raise_on_call: bool = False, raise_first_only: bool = False):
        self.calls: list[tuple[str, str, str]] = []
        self.raise_on_call = raise_on_call
        self.raise_first_only = raise_first_only
        self._first_call = True

    async def __call__(self, phone: str, message: str, alert_type: str) -> None:
        if self.raise_on_call:
            self.calls.append((phone, message, alert_type))
            raise RuntimeError("fake send failure")
        if self.raise_first_only and self._first_call:
            self._first_call = False
            self.calls.append((phone, message, alert_type))
            raise RuntimeError("fake send failure on first")
        self._first_call = False
        self.calls.append((phone, message, alert_type))


def _make_owner_with_phone(
    db,
    tenant,
    *,
    phone_suffix: str = "0001",
) -> tuple[User, PhoneTenantMap]:
    """Mint a top-tier User + linked PhoneTenantMap so resolve_recipients fires.

    Called by:    every test that asserts on send fan-out.
    Calls into:   User + PhoneTenantMap ORM constructors.
    Side effects: stages two rows in the supplied test session.

    Owner role + briefing_subscribed=True (default) ensures the user
    passes resolve_recipients. The phone suffix lets multi-recipient
    tests mint two distinct numbers.
    """
    now = datetime.now(timezone.utc)
    user = User(
        tenant_id=tenant.id,
        email=f"owner-{tenant.id}-{phone_suffix}@test.local",
        hashed_password="x" * 40,
        role="owner",
        is_active=True,
        briefing_subscribed=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    # PhoneTenantMap has Postgres-only server_defaults on linked_at
    # (now()) and alert_preferences (a JSON literal cast). SQLite cannot
    # resolve either, so we set both explicitly here. The parent
    # patch_now_defaults_for_sqlite fixture in tests/services/conftest.py
    # does not include PhoneTenantMap in its target list, and adding it
    # there would touch other tests — so we work around at the call
    # site instead.
    pmap = PhoneTenantMap(
        phone_number=f"+9100000{phone_suffix}",
        tenant_id=tenant.id,
        user_id=user.id,
        is_active=True,
        linked_at=now,
        alert_preferences={},
    )
    db.add(pmap)
    db.flush()
    return user, pmap


def _anchor_tenant_at_day_seven(db, tenant) -> None:
    """Set first_briefing_sent_at so day_count == LOOKBACK_DAYS at TODAY.

    Called by:    every signal test.
    Calls into:   nothing — direct attribute set + flush.
    Side effects: stages an UPDATE on the tenant row.

    The anchor is set to TODAY - LOOKBACK_DAYS at midnight UTC. The
    gate's day-counting uses the tenant timezone (default Asia/Kolkata)
    which makes the local date precisely LOOKBACK_DAYS earlier, so
    day_count resolves to exactly 7 at NOW_UTC.
    """
    anchor = datetime.combine(
        TODAY - timedelta(days=LOOKBACK_DAYS), time.min,
    ).replace(tzinfo=timezone.utc)
    tenant.first_briefing_sent_at = anchor
    db.flush()


def _run(coro):
    """Synchronously drive an async coroutine inside a sync test.

    Called by:    every test that calls evaluate_and_send (async).
    Calls into:   asyncio.new_event_loop / run_until_complete.
    Side effects: creates and disposes a private event loop.

    pytest-asyncio is not on this project; the existing v6.3.x test
    suite drives async via this helper pattern. Keeping consistent.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _last_event(db, tenant_id: int, event_type: str) -> Event | None:
    """Return the most-recent Event row of `event_type` for the tenant.

    Called by:    every test that asserts an audit row was written.
    Calls into:   Event ORM read.
    Side effects: none — read-only.
    """
    return (
        db.query(Event)
        .filter(Event.tenant_id == tenant_id, Event.event_type == event_type)
        .order_by(Event.id.desc())
        .first()
    )


# ===========================================================================
# Suggested manual test cases (per $GGRULE step 5)
# ===========================================================================
#
# These three runnable Python snippets cover the happy path, a failure
# mode, and an edge case end-to-end. Run them after `alembic upgrade head`
# against a dev DB with WHATSAPP_MOCK_MODE=True so the [MOCK ALERT] log
# breadcrumbs surface in the FastAPI server output. They complement the
# pytest tests in this file by exercising the live dispatcher path.
#
# 1) Happy path — chronic-absence attendance signal fires for tenant 12.
#    python -c "
#    import asyncio, datetime as dt
#    from app.database import SessionLocal
#    from app.models.auth import Tenant
#    from app.models.event import Event
#    from app.services.day7_insight import evaluate_and_send
#
#    db = SessionLocal()
#    t = db.get(Tenant, 12)
#    t.first_briefing_sent_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
#    t.engagement_ladder_state = {}
#    # Insert 4 attendance.recorded events absent for the same employee_id.
#    # (Adjust employee_id to a real one in tenant 12.)
#    for i in range(4):
#        db.add(Event(
#            tenant_id=12, event_type='attendance.recorded',
#            entity_type='checkin', entity_id=None, source='whatsapp',
#            payload={'for_date': (dt.date.today() - dt.timedelta(days=i)).isoformat(),
#                     'absent_employee_ids': [<EMP_ID>], 'down_machine_ids': []},
#        ))
#    db.commit()
#    print(asyncio.run(evaluate_and_send(12, db)))
#    "
#
# 2) Failure mode — send_fn raises; ledger must NOT be marked.
#    python -c "
#    import asyncio
#    from app.database import SessionLocal
#    from app.services.day7_insight import evaluate_and_send
#
#    async def boom(*a, **k): raise RuntimeError('intentional')
#    db = SessionLocal()
#    print(asyncio.run(evaluate_and_send(12, db, send_fn=boom)))
#    # Re-read tenant: engagement_ladder_state['day7_owner_sent_at'] must be absent.
#    "
#
# 3) Edge case — tenant whose anchor is 30 days old must auto-suppress.
#    python -c "
#    import asyncio, datetime as dt
#    from app.database import SessionLocal
#    from app.models.auth import Tenant
#    from app.services.day7_insight import evaluate_and_send
#
#    db = SessionLocal()
#    t = db.get(Tenant, 12)
#    t.first_briefing_sent_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
#    t.engagement_ladder_state = {}
#    db.commit()
#    print(asyncio.run(evaluate_and_send(12, db)))
#    # Result: skipped='suppressed_too_late', ledger key set without a send.
#    "

# ===========================================================================
# Pytest tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Happy path — fallback when no detector qualifies
# ---------------------------------------------------------------------------

class TestFallback:

    def test_fallback_fires_when_no_signal(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.signal_id == SIGNAL_FALLBACK
        assert result.sent_count == 1
        assert "7 din ho gaye" in sender.calls[0][1]
        assert "Routine set" in sender.calls[0][1]

        # Ledger marked, audit row present.
        db.refresh(tenant)
        assert LADDER_KEY_DAY7_SENT in tenant.engagement_ladder_state
        ev = _last_event(db, tenant.id, EVENT_DAY7_SENT)
        assert ev is not None
        assert ev.payload["signal_id"] == SIGNAL_FALLBACK


# ---------------------------------------------------------------------------
# Idempotency — second call after a fire is a no-op
# ---------------------------------------------------------------------------

class TestIdempotency:

    def test_second_call_skips(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)
        db.commit()

        sender_1 = FakeSender()
        first = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender_1,
        ))
        db.commit()
        assert first.sent_count == 1

        sender_2 = FakeSender()
        second = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender_2,
        ))
        db.commit()
        assert second.skipped == "already_sent"
        assert sender_2.calls == []


# ---------------------------------------------------------------------------
# Skip paths — no anchor, too early, suppression
# ---------------------------------------------------------------------------

class TestSkipPaths:

    def test_no_anchor_returns_skip(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _make_owner_with_phone(db, tenant)
        db.commit()
        # first_briefing_sent_at intentionally NOT set.

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.skipped == "no_anchor"
        assert sender.calls == []

    def test_too_early_returns_skip(self, db):
        tenant = make_tenant(db, age_days=4, today=TODAY)
        # Anchor 3 days ago — day_count == 3, below LOOKBACK_DAYS.
        anchor = datetime.combine(
            TODAY - timedelta(days=3), time.min,
        ).replace(tzinfo=timezone.utc)
        tenant.first_briefing_sent_at = anchor
        _make_owner_with_phone(db, tenant)
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.skipped == "too_early"
        assert sender.calls == []
        # Ledger must NOT be touched on too_early.
        db.refresh(tenant)
        assert LADDER_KEY_DAY7_SENT not in (tenant.engagement_ladder_state or {})

    def test_suppression_when_anchor_too_old(self, db):
        tenant = make_tenant(db, age_days=40, today=TODAY)
        # Anchor 30 days ago — day_count > SUPPRESS_IF_DAY_COUNT_OVER.
        anchor = datetime.combine(
            TODAY - timedelta(days=SUPPRESS_IF_DAY_COUNT_OVER + 5), time.min,
        ).replace(tzinfo=timezone.utc)
        tenant.first_briefing_sent_at = anchor
        _make_owner_with_phone(db, tenant)
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.skipped == "suppressed_too_late"
        assert sender.calls == []
        # Ledger MUST be marked so this tenant never re-evaluates.
        db.refresh(tenant)
        assert LADDER_KEY_DAY7_SENT in tenant.engagement_ladder_state
        ev = _last_event(db, tenant.id, EVENT_DAY7_SUPPRESSED)
        assert ev is not None

    def test_no_recipients_does_not_mark_ledger(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        # No owner / phone created.
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.skipped == "no_recipients"
        assert sender.calls == []
        db.refresh(tenant)
        assert LADDER_KEY_DAY7_SENT not in (tenant.engagement_ladder_state or {})


# ---------------------------------------------------------------------------
# Send failure semantics
# ---------------------------------------------------------------------------

class TestSendFailure:

    def test_total_send_failure_does_not_mark_ledger(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)
        db.commit()

        sender = FakeSender(raise_on_call=True)
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.skipped == "send_failed"
        assert result.sent_count == 0
        # Ledger NOT marked — the gate retries on the next morning tick.
        db.refresh(tenant)
        assert LADDER_KEY_DAY7_SENT not in (tenant.engagement_ladder_state or {})
        # Failure event was written, even though ledger was not.
        ev = _last_event(db, tenant.id, EVENT_DAY7_FAILED)
        assert ev is not None
        assert ev.payload["recipient_count"] == 1

    def test_partial_send_failure_marks_ledger(self, db):
        # Two recipients — first send fails, second succeeds. Ledger
        # must mark sent because at least one recipient got it.
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant, phone_suffix="0001")
        _make_owner_with_phone(db, tenant, phone_suffix="0002")
        db.commit()

        sender = FakeSender(raise_first_only=True)
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.signal_id == SIGNAL_FALLBACK
        assert result.sent_count == 1
        db.refresh(tenant)
        assert LADDER_KEY_DAY7_SENT in tenant.engagement_ladder_state
        ev = _last_event(db, tenant.id, EVENT_DAY7_SENT)
        assert ev is not None
        assert len(ev.payload["send_errors"]) == 1


# ---------------------------------------------------------------------------
# Signal 1 — attendance pattern
# ---------------------------------------------------------------------------

class TestAttendanceSignal:

    def test_chronic_worker_fires(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        suresh = make_employee(db, tenant=tenant, full_name="Suresh")
        # Suresh absent on N consecutive days where N == threshold.
        for i in range(ATTENDANCE_MIN_ABSENT_DAYS_PER_WORKER):
            make_attendance_event(
                db, tenant=tenant,
                for_date=TODAY - timedelta(days=i),
                absent_employee_ids=[suresh.id],
            )
        _make_owner_with_phone(db, tenant)
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.signal_id == SIGNAL_ATTENDANCE
        assert "Suresh" in sender.calls[0][1]
        ev = _last_event(db, tenant.id, EVENT_DAY7_SENT)
        assert ev.payload["signal_payload"]["variant"] == "chronic_worker"
        assert ev.payload["signal_payload"]["employee_id"] == suresh.id

    def test_weekday_pattern_fires(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        a = make_employee(db, tenant=tenant, full_name="Worker A")
        b = make_employee(db, tenant=tenant, full_name="Worker B")
        # Same weekday (TODAY) absent for K distinct workers — but
        # neither one absent N days, so chronic-worker variant must NOT fire.
        # Pick a single weekday where both are absent on the SAME date,
        # and on no other date is anyone absent.
        same_day = TODAY
        make_attendance_event(
            db, tenant=tenant, for_date=same_day,
            absent_employee_ids=[a.id, b.id],
        )
        # Plenty of other days reported with no absences so the
        # timeline has data but no chronic worker.
        for i in range(1, 6):
            make_attendance_event(
                db, tenant=tenant,
                for_date=TODAY - timedelta(days=i),
                absent_employee_ids=[],
            )
        _make_owner_with_phone(db, tenant)
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.signal_id == SIGNAL_ATTENDANCE
        ev = _last_event(db, tenant.id, EVENT_DAY7_SENT)
        assert ev.payload["signal_payload"]["variant"] == "weekday_pattern"
        assert ev.payload["signal_payload"]["worker_count"] >= (
            ATTENDANCE_MIN_WORKERS_SAME_WEEKDAY
        )


# ---------------------------------------------------------------------------
# Signal 2 — skill bottleneck
# ---------------------------------------------------------------------------

class TestSkillBottleneck:

    def test_one_worker_dominates_a_skill(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)

        # Create skill, three jobs all requiring it, and assign all
        # three to the same employee → 100% concentration > 70%.
        skill = Skill(
            tenant_id=tenant.id, name="Heidelberg Operation",
            category="machine", is_active=True,
        )
        db.add(skill)
        db.flush()

        operator = make_employee(db, tenant=tenant, full_name="Mukesh")

        for n in range(SKILL_BOTTLENECK_MIN_JOBS):
            j = make_job(
                db, tenant=tenant,
                name=f"Job {n}",
                start_date=TODAY - timedelta(days=2),
                end_date=TODAY,
                customer="Patel Industries",
            )
            db.add(JobSkillRequirement(
                tenant_id=tenant.id, job_id=j.id, skill_id=skill.id,
                min_skill_level="Generic", employees_required=1,
            ))
            db.add(JobAssignment(
                tenant_id=tenant.id, job_id=j.id, employee_id=operator.id,
            ))
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.signal_id == SIGNAL_SKILL
        assert "Mukesh" in sender.calls[0][1]
        assert "Heidelberg Operation" in sender.calls[0][1]
        ev = _last_event(db, tenant.id, EVENT_DAY7_SENT)
        assert ev.payload["signal_payload"]["employee_id"] == operator.id
        assert ev.payload["signal_payload"]["ratio"] == 1.0

    def test_below_min_jobs_does_not_fire(self, db):
        # Only one job requiring the skill — 1/1 = 100% but below the
        # min-jobs floor, so the signal must NOT fire and we should
        # fall through to the fallback.
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)

        skill = Skill(
            tenant_id=tenant.id, name="Welding", category="machine", is_active=True,
        )
        db.add(skill)
        db.flush()
        op = make_employee(db, tenant=tenant, full_name="Solo")
        j = make_job(
            db, tenant=tenant, name="One Job",
            start_date=TODAY - timedelta(days=1), end_date=TODAY,
        )
        db.add(JobSkillRequirement(
            tenant_id=tenant.id, job_id=j.id, skill_id=skill.id,
            min_skill_level="Generic", employees_required=1,
        ))
        db.add(JobAssignment(tenant_id=tenant.id, job_id=j.id, employee_id=op.id))
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.signal_id == SIGNAL_FALLBACK


# ---------------------------------------------------------------------------
# Signal 3 — machine utilisation spread
# ---------------------------------------------------------------------------

class TestMachineUtilisation:

    def test_4x_spread_fires(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)
        busy = make_machine(db, tenant=tenant, name="Press A")
        idle = make_machine(db, tenant=tenant, name="Press B")

        # busy: ~40 hours, idle: ~5 hours over 7 days. Ratio = 8x > 4x.
        # Both meet the min-hours floor (5 hrs total > 0.5 × 7 = 3.5).
        for d in range(7):
            day = TODAY - timedelta(days=d)
            start = datetime.combine(day, time(8, 0))
            db.add(ScheduleEntryModel(
                tenant_id=tenant.id, job_id=1 + d, step_id=100 + d,
                assigned_machine_ids=[busy.id], assigned_helper_ids=[],
                scheduled_start=start, scheduled_end=start + timedelta(hours=6),
                created_at=datetime.now(timezone.utc),
            ))
        # Idle machine ran on only one of the seven days.
        idle_start = datetime.combine(TODAY - timedelta(days=2), time(8, 0))
        db.add(ScheduleEntryModel(
            tenant_id=tenant.id, job_id=999, step_id=999,
            assigned_machine_ids=[idle.id], assigned_helper_ids=[],
            scheduled_start=idle_start, scheduled_end=idle_start + timedelta(hours=5),
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.signal_id == SIGNAL_MACHINE
        assert "Press A" in sender.calls[0][1]
        ev = _last_event(db, tenant.id, EVENT_DAY7_SENT)
        assert ev.payload["signal_payload"]["ratio"] >= MACHINE_UTILISATION_RATIO_THRESHOLD

    def test_min_hours_floor_excludes_noise(self, db):
        # busy: 30 hours; "idle" candidate: 6 minutes total → below
        # MIN_HOURS_PER_DAY × 7 floor (0.5 × 7 = 3.5h). With only one
        # eligible machine, the signal must NOT fire — we fall through.
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)
        busy = make_machine(db, tenant=tenant, name="Press A")
        noisy = make_machine(db, tenant=tenant, name="Press B")
        for d in range(7):
            start = datetime.combine(TODAY - timedelta(days=d), time(8, 0))
            db.add(ScheduleEntryModel(
                tenant_id=tenant.id, job_id=10 + d, step_id=10 + d,
                assigned_machine_ids=[busy.id], assigned_helper_ids=[],
                scheduled_start=start, scheduled_end=start + timedelta(hours=4),
                created_at=datetime.now(timezone.utc),
            ))
        noise_start = datetime.combine(TODAY - timedelta(days=1), time(8, 0))
        db.add(ScheduleEntryModel(
            tenant_id=tenant.id, job_id=99, step_id=99,
            assigned_machine_ids=[noisy.id], assigned_helper_ids=[],
            scheduled_start=noise_start,
            scheduled_end=noise_start + timedelta(minutes=6),  # below floor
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.signal_id == SIGNAL_FALLBACK


# ---------------------------------------------------------------------------
# Signal 4 — recurring customer name
# ---------------------------------------------------------------------------

class TestRecurringCustomer:

    def _stub_candidate(
        self,
        db,
        tenant,
        normalized: str,
        mentions: int,
    ) -> ExtractionCandidate:
        now = datetime.now(timezone.utc)
        cand = ExtractionCandidate(
            tenant_id=tenant.id,
            entity_type="customer",
            raw_value=normalized,
            normalized_value=normalized,
            confidence=0.9,
            mention_count=mentions,
            first_seen=now - timedelta(days=2),
            last_seen=now,
            source_type="whatsapp",
            confirmation_state="none",
            confirmation_retry_count=0,
        )
        db.add(cand)
        db.flush()
        return cand

    def test_new_customer_fires(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)

        # Existing job with an unrelated customer name (no overlap).
        make_job(
            db, tenant=tenant, name="Legacy", customer="ACME Pvt",
            start_date=TODAY - timedelta(days=2), end_date=TODAY,
        )
        self._stub_candidate(
            db, tenant, "Heidelberg Trading", CUSTOMER_RECURRING_MIN_MENTIONS,
        )
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.signal_id == SIGNAL_CUSTOMER
        assert "Heidelberg Trading" in sender.calls[0][1]

    def test_alias_overlap_excludes_existing_customer(self, db):
        # "Patel Trading Co." already in jobs.customer; "Patel Traders"
        # extracted candidate must be rejected via the 4-char overlap
        # rule. With no other candidate, fall through to fallback.
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)
        make_job(
            db, tenant=tenant, name="Existing", customer="Patel Trading Co.",
            start_date=TODAY - timedelta(days=3), end_date=TODAY,
        )
        self._stub_candidate(
            db, tenant, "Patel Traders", CUSTOMER_RECURRING_MIN_MENTIONS,
        )
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        assert result.signal_id == SIGNAL_FALLBACK

    def test_below_mention_threshold_does_not_fire(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)
        self._stub_candidate(
            db, tenant, "Loudspeaker Trading",
            CUSTOMER_RECURRING_MIN_MENTIONS - 1,
        )
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()
        assert result.signal_id == SIGNAL_FALLBACK


# ---------------------------------------------------------------------------
# Signal priority — when multiple signals qualify, attendance wins
# ---------------------------------------------------------------------------

class TestPriority:

    def test_attendance_wins_over_machine(self, db):
        tenant = make_tenant(db, age_days=10, today=TODAY)
        _anchor_tenant_at_day_seven(db, tenant)
        _make_owner_with_phone(db, tenant)

        # Attendance: chronic-worker variant.
        suresh = make_employee(db, tenant=tenant, full_name="Suresh")
        for i in range(ATTENDANCE_MIN_ABSENT_DAYS_PER_WORKER):
            make_attendance_event(
                db, tenant=tenant,
                for_date=TODAY - timedelta(days=i),
                absent_employee_ids=[suresh.id],
            )
        # Machine: 4x spread that would also fire.
        busy = make_machine(db, tenant=tenant, name="Press A")
        idle = make_machine(db, tenant=tenant, name="Press B")
        for d in range(7):
            start = datetime.combine(TODAY - timedelta(days=d), time(8, 0))
            db.add(ScheduleEntryModel(
                tenant_id=tenant.id, job_id=1 + d, step_id=1 + d,
                assigned_machine_ids=[busy.id], assigned_helper_ids=[],
                scheduled_start=start, scheduled_end=start + timedelta(hours=6),
                created_at=datetime.now(timezone.utc),
            ))
        idle_start = datetime.combine(TODAY - timedelta(days=2), time(8, 0))
        db.add(ScheduleEntryModel(
            tenant_id=tenant.id, job_id=99, step_id=99,
            assigned_machine_ids=[idle.id], assigned_helper_ids=[],
            scheduled_start=idle_start, scheduled_end=idle_start + timedelta(hours=5),
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()

        sender = FakeSender()
        result = _run(evaluate_and_send(
            tenant.id, db, now_utc=NOW_UTC, send_fn=sender,
        ))
        db.commit()

        # Attendance is priority 1 — must win.
        assert result.signal_id == SIGNAL_ATTENDANCE
