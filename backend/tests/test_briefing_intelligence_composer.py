# tests/test_briefing_intelligence_composer.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Integration tests for app/services/briefing_intelligence/composer.py.
# Covers spec sections D.1 (cap), D.3 (diversity), D.4 (cooldown), D.5
# (escalation), D.6 + Q10 (idle-case trailing line), and the quiet-
# period rule.

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.sql.schema import DefaultClause

from app.models.auth import RefreshToken, Tenant, User
from app.models.employee import Employee
from app.models.event import Event
from app.models.job import Job
from app.models.whatsapp import PhoneTenantMap
from app.services.briefing_intelligence import composer as composer_module
from app.services.briefing_intelligence.composer import (
    IDLE_TRAILING_LINE_HI_EN,
    compose_briefing,
)
from app.services.briefing_intelligence.cooldown import (
    SIGNAL_FIRED_EVENT_TYPE,
)
from app.services.briefing_intelligence.signals import SignalResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    patched = []
    for tbl in (
        Tenant.__table__, User.__table__, RefreshToken.__table__,
        PhoneTenantMap.__table__, Event.__table__,
        Job.__table__, Employee.__table__,
    ):
        for col in tbl.columns:
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


def _make_tenant(
    db,
    *,
    created_at: datetime | None = None,
    industry_type: str = "printing",
) -> Tenant:
    n = _next()
    now = datetime.now(timezone.utc)
    t = Tenant(
        name=f"Composer {n}", slug=f"composer-{n}", plan="free",
        is_active=True, industry_type=industry_type,
        created_at=created_at or (now - timedelta(days=30)),
        updated_at=now,
    )
    db.add(t)
    db.flush()
    return t


def _make_job(db, *, tenant: Tenant, name: str, end_date: date,
              status: str = "in_progress") -> Job:
    job = Job(
        tenant_id=tenant.id, name=name,
        start_date=end_date - timedelta(days=2),
        end_date=end_date, status=status,
    )
    db.add(job)
    db.flush()
    return job


def _make_signal(
    *,
    signal_id: str,
    category: str,
    tier: int = 1,
    confidence: str = "high",
    severity: float = 1.0,
    cooldown_days: int = 1,
) -> SignalResult:
    return SignalResult(
        signal_id=signal_id,
        category=category,
        tier=tier,
        confidence=confidence,
        subject_entity_type="tenant",
        subject_entity_id=None,
        severity_score=severity,
        message_hi_en=f"[{signal_id}] hi-en",
        message_en=f"[{signal_id}] en",
        cooldown_days=cooldown_days,
    )


def _patch_detectors(monkeypatch, signals: list[SignalResult]):
    """Replace ALL_DETECTORS with one detector per provided signal so
    composer tests can deterministically inject candidates regardless
    of DB state."""
    fakes = tuple(
        (lambda s: (lambda tenant_id, today, db: s))(sig)
        for sig in signals
    )
    monkeypatch.setattr(composer_module, "ALL_DETECTORS", fakes)


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

class TestComposeBriefing:

    def test_compose_briefing_no_signals_falls_back_to_templated(
        self, db, monkeypatch,
    ):
        """When no detector fires, the v6.3.4 templated builder runs."""
        tenant = _make_tenant(db)
        db.commit()

        # Force every detector to return None
        _patch_detectors(monkeypatch, [])

        out = compose_briefing(
            tenant_id=tenant.id, kind="morning",
            today=date(2026, 5, 4), db=db,
        )
        # Templated idle output uses the 'morning_idle' template — never
        # empty, never the pattern header.
        assert out
        assert "ZetaOps briefing" not in out  # pattern header absent

    def test_compose_briefing_returns_single_signal_correctly_formatted(
        self, db, monkeypatch,
    ):
        tenant = _make_tenant(db)
        db.commit()

        sig = _make_signal(signal_id="delayed_jobs_count", category="job",
                           severity=1.0)
        _patch_detectors(monkeypatch, [sig])

        out = compose_briefing(
            tenant_id=tenant.id, kind="morning",
            today=date(2026, 5, 4), db=db,
        )
        assert "ZetaOps briefing" in out
        assert "[delayed_jobs_count] hi-en" in out
        assert out.count("- ") >= 1

    def test_compose_briefing_quiet_period_blocks_signals_for_new_tenant(
        self, db, monkeypatch,
    ):
        """Tenant younger than QUIET_PERIOD_DAYS gets templated fallback,
        even when a detector fires."""
        # Created today → age 0 days → quiet period applies
        today = date(2026, 5, 4)
        recent_now = datetime(2026, 5, 4, 6, 0, tzinfo=timezone.utc)
        tenant = _make_tenant(db, created_at=recent_now)
        db.commit()

        sig = _make_signal(signal_id="delayed_jobs_count", category="job")
        _patch_detectors(monkeypatch, [sig])

        out = compose_briefing(
            tenant_id=tenant.id, kind="morning", today=today, db=db,
        )
        # Quiet period: pattern path suppressed, templated runs.
        assert "[delayed_jobs_count] hi-en" not in out
        assert "ZetaOps briefing" not in out

    def test_compose_briefing_cooldown_blocks_repeat_fire(
        self, db, monkeypatch,
    ):
        tenant = _make_tenant(db)
        # Prior fire today, same severity — cooldown must hold.
        prior = Event(
            tenant_id=tenant.id,
            event_type=SIGNAL_FIRED_EVENT_TYPE,
            entity_type="tenant", entity_id=None,
            actor_user_id=None, source="system",
            payload={"signal_id": "delayed_jobs_count",
                     "subject_entity_id": None,
                     "severity_score": 2.0,
                     "message": "prior"},
            created_at=datetime(2026, 5, 4, 7, 0, tzinfo=timezone.utc),
        )
        db.add(prior)
        db.commit()

        sig = _make_signal(signal_id="delayed_jobs_count", category="job",
                           severity=2.0, cooldown_days=1)
        _patch_detectors(monkeypatch, [sig])

        out = compose_briefing(
            tenant_id=tenant.id, kind="morning",
            today=date(2026, 5, 4), db=db,
        )
        # Cooldown blocks fire → templated fallback path
        assert "[delayed_jobs_count] hi-en" not in out

    def test_compose_briefing_escalation_overrides_cooldown(
        self, db, monkeypatch,
    ):
        tenant = _make_tenant(db)
        # Prior severity 2.0 today, new severity 4.0 → escalation
        prior = Event(
            tenant_id=tenant.id,
            event_type=SIGNAL_FIRED_EVENT_TYPE,
            entity_type="tenant", entity_id=None,
            actor_user_id=None, source="system",
            payload={"signal_id": "delayed_jobs_count",
                     "subject_entity_id": None,
                     "severity_score": 2.0,
                     "message": "prior"},
            created_at=datetime(2026, 5, 4, 7, 0, tzinfo=timezone.utc),
        )
        db.add(prior)
        db.commit()

        sig = _make_signal(signal_id="delayed_jobs_count", category="job",
                           severity=4.0, cooldown_days=1)
        _patch_detectors(monkeypatch, [sig])

        out = compose_briefing(
            tenant_id=tenant.id, kind="morning",
            today=date(2026, 5, 4), db=db,
        )
        # Escalation: signal fires even inside cooldown.
        assert "[delayed_jobs_count] hi-en" in out

    def test_compose_briefing_diversity_drops_same_category_after_first(
        self, db, monkeypatch,
    ):
        tenant = _make_tenant(db)
        db.commit()

        # Two job-category signals → diversity rule keeps slot 1, drops
        # the second-job. A non-job signal then fills slot 2.
        s_job_a = _make_signal(signal_id="delayed_jobs_count", category="job",
                                severity=3.0)
        s_job_b = _make_signal(signal_id="conflict_jobs_count", category="job",
                                severity=2.0)
        s_machine = _make_signal(signal_id="idle_machine", category="machine",
                                  tier=2, confidence="medium", severity=1.0)
        _patch_detectors(monkeypatch, [s_job_a, s_job_b, s_machine])

        out = compose_briefing(
            tenant_id=tenant.id, kind="morning",
            today=date(2026, 5, 4), db=db,
        )
        # slot 1 (top job) + slot 2 (machine) — second job dropped
        assert "[delayed_jobs_count] hi-en" in out
        assert "[idle_machine] hi-en" in out
        assert "[conflict_jobs_count] hi-en" not in out

    def test_compose_briefing_caps_at_three_signals(
        self, db, monkeypatch,
    ):
        tenant = _make_tenant(db)
        db.commit()

        # Five candidates of distinct categories — cap at 3.
        sigs = [
            _make_signal(signal_id=f"sig_{i}", category=cat, severity=float(i))
            for i, cat in enumerate(
                ["job", "machine", "attendance", "customer", "health"]
            )
        ]
        _patch_detectors(monkeypatch, sigs)

        out = compose_briefing(
            tenant_id=tenant.id, kind="morning",
            today=date(2026, 5, 4), db=db,
        )
        # Exactly 3 bullet lines
        bullet_count = sum(1 for line in out.splitlines() if line.startswith("- "))
        assert bullet_count == 3

    def test_compose_briefing_records_signal_fired_events_for_surfaced(
        self, db, monkeypatch,
    ):
        tenant = _make_tenant(db)
        db.commit()

        sig = _make_signal(signal_id="delayed_jobs_count", category="job")
        _patch_detectors(monkeypatch, [sig])

        compose_briefing(
            tenant_id=tenant.id, kind="morning",
            today=date(2026, 5, 4), db=db,
        )

        rows = (
            db.query(Event)
            .filter(Event.event_type == SIGNAL_FIRED_EVENT_TYPE)
            .all()
        )
        assert len(rows) == 1
        assert (rows[0].payload or {})["signal_id"] == "delayed_jobs_count"

    def test_compose_briefing_idle_case_appends_trailing_line_after_day_7(
        self, db, monkeypatch,
    ):
        # Tenant created 10 days ago — older than the day-7 threshold
        today = date(2026, 5, 4)
        old_created = datetime(2026, 4, 24, tzinfo=timezone.utc)
        tenant = _make_tenant(db, created_at=old_created)
        db.commit()

        _patch_detectors(monkeypatch, [])  # idle case

        out = compose_briefing(
            tenant_id=tenant.id, kind="morning", today=today, db=db,
        )
        assert IDLE_TRAILING_LINE_HI_EN in out

    def test_compose_briefing_idle_case_no_trailing_before_day_7(
        self, db, monkeypatch,
    ):
        # Tenant created 3 days ago — not yet at the day-7 threshold
        today = date(2026, 5, 4)
        new_created = datetime(2026, 5, 1, tzinfo=timezone.utc)
        tenant = _make_tenant(db, created_at=new_created)
        db.commit()

        _patch_detectors(monkeypatch, [])

        out = compose_briefing(
            tenant_id=tenant.id, kind="morning", today=today, db=db,
        )
        assert IDLE_TRAILING_LINE_HI_EN not in out
