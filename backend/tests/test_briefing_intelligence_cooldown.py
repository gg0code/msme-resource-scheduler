# tests/test_briefing_intelligence_cooldown.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/briefing_intelligence/cooldown.py:
#   - get_last_fired() — most recent briefing.signal_fired Event match.
#   - record_fired() — stages an Event row (no commit).
#   - is_in_cooldown() — pure comparator (cooldown vs escalation, D.4/D.5).

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.sql.schema import DefaultClause

from app.models.auth import Tenant
from app.models.event import Event
from app.services.briefing_intelligence.cooldown import (
    SIGNAL_FIRED_EVENT_TYPE,
    get_last_fired,
    is_in_cooldown,
    record_fired,
)
from app.services.briefing_intelligence.signals import SignalResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    patched = []
    for table_attr in (Tenant.__table__, Event.__table__):
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


def _make_tenant(db) -> Tenant:
    n = _next()
    now = datetime.now(timezone.utc)
    t = Tenant(
        name=f"Cool {n}", slug=f"cool-{n}", plan="free",
        is_active=True, industry_type="printing",
        created_at=now, updated_at=now,
    )
    db.add(t)
    db.flush()
    return t


def _make_signal(
    *,
    signal_id: str = "delayed_jobs_count",
    category: str = "job",
    tier: int = 1,
    confidence: str = "high",
    severity: float = 1.0,
    subject_entity_id: int | None = None,
) -> SignalResult:
    return SignalResult(
        signal_id=signal_id,
        category=category,
        tier=tier,
        confidence=confidence,
        subject_entity_type="tenant",
        subject_entity_id=subject_entity_id,
        severity_score=severity,
        message_hi_en="msg",
        message_en="msg",
        cooldown_days=1,
    )


def _make_fired_event(
    db,
    tenant: Tenant,
    *,
    signal_id: str = "delayed_jobs_count",
    subject_entity_id: int | None = None,
    severity: float = 1.0,
    created_at: datetime | None = None,
) -> Event:
    ev = Event(
        tenant_id=tenant.id,
        event_type=SIGNAL_FIRED_EVENT_TYPE,
        entity_type="tenant",
        entity_id=subject_entity_id,
        actor_user_id=None,
        source="system",
        payload={
            "signal_id": signal_id,
            "subject_entity_id": subject_entity_id,
            "severity_score": severity,
            "message": "prior",
        },
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(ev)
    db.flush()
    return ev


# ---------------------------------------------------------------------------
# get_last_fired
# ---------------------------------------------------------------------------

class TestGetLastFired:

    def test_returns_none_when_never_fired(self, db):
        tenant = _make_tenant(db)
        db.commit()
        out = get_last_fired(
            tenant_id=tenant.id,
            signal_id="delayed_jobs_count",
            subject_entity_id=None,
            db=db,
        )
        assert out is None

    def test_returns_most_recent_within_30_days(self, db):
        tenant = _make_tenant(db)
        now = datetime.now(timezone.utc)
        # Older event (5 days ago)
        _make_fired_event(
            db, tenant, severity=1.0, created_at=now - timedelta(days=5),
        )
        # Newer event (1 day ago) — this is the one we expect
        recent = _make_fired_event(
            db, tenant, severity=2.0, created_at=now - timedelta(days=1),
        )
        # Out-of-window event (40 days ago) — must be ignored
        _make_fired_event(
            db, tenant, severity=99.0, created_at=now - timedelta(days=40),
        )
        db.commit()

        out = get_last_fired(
            tenant_id=tenant.id,
            signal_id="delayed_jobs_count",
            subject_entity_id=None,
            db=db,
        )
        assert out is not None
        assert out.id == recent.id
        assert (out.payload or {}).get("severity_score") == 2.0

    def test_subject_entity_id_distinguishes_per_employee_signals(self, db):
        tenant = _make_tenant(db)
        _make_fired_event(
            db, tenant, signal_id="consecutive_absence",
            subject_entity_id=84, severity=2.0,
        )
        _make_fired_event(
            db, tenant, signal_id="consecutive_absence",
            subject_entity_id=99, severity=3.0,
        )
        db.commit()

        out_84 = get_last_fired(
            tenant_id=tenant.id,
            signal_id="consecutive_absence",
            subject_entity_id=84,
            db=db,
        )
        out_99 = get_last_fired(
            tenant_id=tenant.id,
            signal_id="consecutive_absence",
            subject_entity_id=99,
            db=db,
        )
        assert out_84 is not None and (out_84.payload or {})["severity_score"] == 2.0
        assert out_99 is not None and (out_99.payload or {})["severity_score"] == 3.0


# ---------------------------------------------------------------------------
# record_fired
# ---------------------------------------------------------------------------

class TestRecordFired:

    def test_record_fired_writes_event_with_correct_payload(self, db):
        tenant = _make_tenant(db)
        sig = _make_signal(severity=4.0)
        record_fired(tenant.id, sig, db)
        # No commit inside record_fired — caller owns that
        db.commit()

        rows = (
            db.query(Event)
            .filter(Event.event_type == SIGNAL_FIRED_EVENT_TYPE)
            .all()
        )
        assert len(rows) == 1
        ev = rows[0]
        assert ev.tenant_id == tenant.id
        assert ev.source == "system"
        payload = ev.payload or {}
        assert payload["signal_id"] == "delayed_jobs_count"
        assert payload["severity_score"] == 4.0
        assert payload["subject_entity_id"] is None

    def test_record_fired_does_not_commit(self, db):
        """Caller owns the transaction boundary so all surfaced signals
        land atomically. record_fired must only stage."""
        tenant = _make_tenant(db)
        sig = _make_signal()
        record_fired(tenant.id, sig, db)
        # Roll back without committing — the staged event must vanish.
        db.rollback()

        rows = (
            db.query(Event)
            .filter(Event.event_type == SIGNAL_FIRED_EVENT_TYPE)
            .all()
        )
        assert rows == []


# ---------------------------------------------------------------------------
# is_in_cooldown — escalation logic (D.5)
# ---------------------------------------------------------------------------

class TestIsInCooldown:

    def test_no_prior_event_means_not_in_cooldown(self):
        sig = _make_signal(severity=1.0)
        assert is_in_cooldown(sig, prior=None, today=date(2026, 5, 4)) is False

    def test_prior_outside_cooldown_window_means_not_in_cooldown(self, db):
        tenant = _make_tenant(db)
        prior = _make_fired_event(
            db, tenant, severity=2.0,
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        db.commit()
        # cooldown_days=1, prior 3 days ago → outside cooldown
        sig = _make_signal(severity=1.0)
        assert is_in_cooldown(sig, prior=prior, today=date(2026, 5, 4)) is False

    def test_prior_within_cooldown_same_severity_blocks(self, db):
        tenant = _make_tenant(db)
        prior = _make_fired_event(
            db, tenant, severity=3.0,
            created_at=datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc),
        )
        db.commit()
        # Same day, same severity → cooldown holds
        sig = _make_signal(severity=3.0)
        assert is_in_cooldown(sig, prior=prior, today=date(2026, 5, 4)) is True

    def test_severity_escalation_compares_prior_to_new(self, db):
        """D.5 escalation: new severity strictly greater than prior →
        fire even inside cooldown."""
        tenant = _make_tenant(db)
        prior = _make_fired_event(
            db, tenant, severity=3.0,
            created_at=datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc),
        )
        db.commit()
        # Same day, severity went up → escalation overrides cooldown
        sig_up = _make_signal(severity=4.0)
        assert is_in_cooldown(sig_up, prior=prior, today=date(2026, 5, 4)) is False

        # Same day, severity went down → cooldown still holds
        sig_down = _make_signal(severity=2.0)
        assert is_in_cooldown(sig_down, prior=prior, today=date(2026, 5, 4)) is True
