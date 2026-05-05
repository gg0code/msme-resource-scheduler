# tests/services/test_promotion_promoter.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/promotion/promoter.py (v6.3.15). Covers:
#   - Threshold gating (mention_count, confidence)
#   - Tenant scoping via ENTITY_EXTRACTION_TENANT_IDS
#   - Per-tenant daily cap with deterministic ordering
#   - Customer skip path (no customers table → audit-only with dedupe)
#   - Idempotency (second run finds the just-inserted entity)
#   - Audit-event payload shapes (promoted, confirmed, skipped)
#   - Per-candidate failure isolation (one bad row, others still run)
#   - Per-industry happy paths (5 verticals)
#   - last_seen bump on every successful promote/confirm
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.promotion.promoter — promote_for_tenant +
#                                     EVENT_* / REASON_* constants.
#   app.services.extraction.feature_flag — _reset_cache after
#                                          monkeypatching settings.
#   tests.services.conftest — make_tenant, make_employee, make_machine.
#
# DESIGN NOTES
# - Each test sets ENTITY_EXTRACTION_TENANT_IDS for the tenant under
#   test and resets the lru_cache. Without that the flag stays empty
#   and promote_for_tenant short-circuits silently (correct behaviour
#   per Q4, but it would mask test intent).
# - All inserts go through helper builders that match the v6.3.14
#   extractor's row shape (mention_count, confidence, normalized_value).

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.employee import Employee
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate
from app.models.machine import Machine
from app.services.extraction import feature_flag as ff
from app.services.promotion import promoter as P

from tests.services.conftest import make_employee, make_machine, make_tenant


FIXED_NOW = datetime(2026, 5, 5, 2, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _opt_in(monkeypatch, tenant_ids: str) -> None:
    """Set ENTITY_EXTRACTION_TENANT_IDS and bust the lru_cache."""
    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS",
        tenant_ids, raising=False,
    )
    ff._reset_cache()


def _make_candidate(
    db,
    *,
    tenant_id: int,
    entity_type: str,
    raw_value: str,
    normalized_value: str | None = None,
    mention_count: int = 5,
    confidence: float = 0.9,
    seen_days_ago: int = 1,
) -> ExtractionCandidate:
    """Stage one ExtractionCandidate row and flush."""
    if normalized_value is None:
        normalized_value = raw_value.strip().lower()
    seen = FIXED_NOW - timedelta(days=seen_days_ago)
    c = ExtractionCandidate(
        tenant_id=tenant_id,
        entity_type=entity_type,
        raw_value=raw_value,
        normalized_value=normalized_value,
        confidence=confidence,
        mention_count=mention_count,
        first_seen=seen,
        last_seen=seen,
        source_type="whatsapp",
    )
    db.add(c)
    db.flush()
    return c


# ---------------------------------------------------------------------------
# Tests — happy path: employee + machine promotion
# ---------------------------------------------------------------------------

class TestEmployeePromotion:

    def test_promotes_new_employee(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Suresh", normalized_value="suresh",
            mention_count=5, confidence=0.9,
        )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.promoted == 1
        assert summary.confirmed == 0
        emps = db.query(Employee).filter(Employee.tenant_id == tenant.id).all()
        assert len(emps) == 1
        assert emps[0].full_name == "Suresh"
        assert emps[0].source == "whatsapp_inferred"
        assert emps[0].worker_type == "permanent"

    def test_writes_promoted_event_with_full_payload(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Ramesh", mention_count=4, confidence=0.85,
        )
        db.commit()

        P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        ev = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == P.EVENT_PROMOTED,
            )
            .one()
        )
        assert ev.entity_id == c.id
        assert ev.source == "system"
        payload = ev.payload
        assert payload["candidate_id"] == c.id
        assert payload["entity_type"] == "employee"
        assert payload["raw_value"] == "Ramesh"
        assert payload["promoted_to_table"] == "employees"
        assert payload["source_value_used"] == "whatsapp_inferred"
        assert payload["mention_count"] == 4
        assert payload["confidence"] == 0.85

    def test_confirms_when_existing_employee_matches_fuzzy(
        self, db, monkeypatch,
    ):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        # Existing employee with same name (normalised).
        make_employee(db, tenant=tenant, full_name="Suresh Kumar")
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Suresh Kumar", normalized_value="suresh kumar",
            mention_count=4, confidence=0.9,
        )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.promoted == 0
        assert summary.confirmed == 1
        # Still only one employee — no duplicate inserted.
        emps = db.query(Employee).filter(Employee.tenant_id == tenant.id).all()
        assert len(emps) == 1
        # Event written.
        confirmed = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == P.EVENT_CONFIRMED,
            )
            .all()
        )
        assert len(confirmed) == 1
        assert confirmed[0].payload["matched_entity_table"] == "employees"

    def test_idempotent_across_two_runs(self, db, monkeypatch):
        # Q9 verification — running twice produces the same final state.
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Vikram", mention_count=5, confidence=0.9,
        )
        db.commit()

        first = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)
        second = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert first.promoted == 1
        assert first.confirmed == 0
        assert second.promoted == 0   # second run sees the just-inserted row
        assert second.confirmed == 1
        emps = db.query(Employee).filter(Employee.tenant_id == tenant.id).all()
        assert len(emps) == 1

    def test_bumps_candidate_last_seen_on_promote(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Anil", mention_count=4, confidence=0.85,
            seen_days_ago=10,
        )
        old_last_seen = c.last_seen
        db.commit()

        P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        db.refresh(c)
        assert c.last_seen != old_last_seen
        # SQLite's DateTime(timezone=True) round-trips as naive — compare
        # without tz. Postgres preserves tz; this is a test-shim
        # concession, not a production behaviour change.
        actual = c.last_seen
        if actual.tzinfo is None:
            actual = actual.replace(tzinfo=timezone.utc)
        assert actual == FIXED_NOW


class TestMachinePromotion:

    def test_promotes_new_machine_with_null_machine_type(
        self, db, monkeypatch,
    ):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="machine",
            raw_value="Heidelberg", mention_count=6, confidence=0.95,
        )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.promoted == 1
        machines = db.query(Machine).filter(Machine.tenant_id == tenant.id).all()
        assert len(machines) == 1
        assert machines[0].name == "Heidelberg"
        assert machines[0].machine_type is None
        assert machines[0].source == "whatsapp_inferred"

    def test_confirms_when_existing_machine_matches(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        make_machine(db, tenant=tenant, name="Heidelberg")
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="machine",
            raw_value="Heidelberg", mention_count=4, confidence=0.9,
        )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.promoted == 0
        assert summary.confirmed == 1
        assert db.query(Machine).filter(Machine.tenant_id == tenant.id).count() == 1


# ---------------------------------------------------------------------------
# Tests — threshold gating
# ---------------------------------------------------------------------------

class TestThresholdGating:

    def test_does_not_promote_below_mention_threshold(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        # mention_count=2 < default 3 → not qualifying.
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Ravi", mention_count=2, confidence=0.95,
        )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.qualified == 0
        assert summary.promoted == 0
        assert db.query(Employee).filter(Employee.tenant_id == tenant.id).count() == 0

    def test_does_not_promote_below_confidence_threshold(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        # confidence=0.5 < default 0.7 → not qualifying.
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Mohan", mention_count=10, confidence=0.5,
        )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.qualified == 0
        assert summary.promoted == 0


# ---------------------------------------------------------------------------
# Tests — tenant scoping (Q4)
# ---------------------------------------------------------------------------

class TestTenantScoping:

    def test_skips_when_tenant_not_in_extraction_flag(self, db, monkeypatch):
        tenant = make_tenant(db)
        # Flag empty — tenant not opted in.
        _opt_in(monkeypatch, "")
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="ShouldSkip", mention_count=5, confidence=0.9,
        )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.qualified == 0
        assert summary.promoted == 0
        assert db.query(Employee).filter(Employee.tenant_id == tenant.id).count() == 0

    def test_runs_when_tenant_in_csv_with_others(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, f"99,{tenant.id},101")
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Included", mention_count=5, confidence=0.9,
        )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.promoted == 1


# ---------------------------------------------------------------------------
# Tests — daily cap (Q5)
# ---------------------------------------------------------------------------

class TestDailyCap:

    def test_respects_per_tenant_daily_cap(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        monkeypatch.setattr(
            "app.config.settings.PROMOTION_DAILY_CAP_PER_TENANT", 3,
            raising=False,
        )
        # Five qualifying employee candidates — only 3 should promote.
        for i in range(5):
            _make_candidate(
                db, tenant_id=tenant.id, entity_type="employee",
                raw_value=f"Worker{i}", normalized_value=f"worker{i}",
                mention_count=5, confidence=0.9,
            )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.qualified == 5
        assert summary.promoted == 3
        assert summary.skipped_cap == 2
        assert db.query(Employee).filter(Employee.tenant_id == tenant.id).count() == 3
        # Two skipped events emitted.
        skipped = db.query(Event).filter(
            Event.tenant_id == tenant.id,
            Event.event_type == P.EVENT_SKIPPED,
        ).all()
        assert len(skipped) == 2
        for ev in skipped:
            assert ev.payload["reason"] == P.REASON_DAILY_CAP

    def test_promotes_top_candidates_when_over_cap(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        monkeypatch.setattr(
            "app.config.settings.PROMOTION_DAILY_CAP_PER_TENANT", 1,
            raising=False,
        )
        # Two candidates: one with high mention_count, one with low.
        # Top-N ordering = (mention_count desc, confidence desc, id asc).
        low = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="LowCount", mention_count=3, confidence=0.7,
        )
        high = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="HighCount", mention_count=20, confidence=0.95,
        )
        db.commit()

        P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        emps = db.query(Employee).filter(Employee.tenant_id == tenant.id).all()
        assert len(emps) == 1
        assert emps[0].full_name == "HighCount"


# ---------------------------------------------------------------------------
# Tests — customer skip path (Q6b / Conflict-2)
# ---------------------------------------------------------------------------

class TestCustomerSkip:

    def test_customer_candidate_emits_skipped_event_with_reason(
        self, db, monkeypatch,
    ):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="customer",
            raw_value="Coca Cola", mention_count=8, confidence=0.95,
        )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.skipped_no_table == 1
        assert summary.promoted == 0
        ev = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == P.EVENT_SKIPPED,
            )
            .one()
        )
        assert ev.entity_id == c.id
        assert ev.payload["reason"] == P.REASON_NO_TABLE
        assert ev.payload["entity_type"] == "customer"
        assert ev.payload["raw_value"] == "Coca Cola"

    def test_customer_skip_dedupes_across_runs(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="customer",
            raw_value="ACME", mention_count=4, confidence=0.85,
        )
        db.commit()

        P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)
        P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)
        P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        # Only one skipped event despite three runs.
        n = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == P.EVENT_SKIPPED,
            )
            .count()
        )
        assert n == 1


# ---------------------------------------------------------------------------
# Tests — non-promotable, non-customer entity_types
# ---------------------------------------------------------------------------

class TestOtherEntityTypes:

    def test_skill_material_job_issue_count_as_skipped_other(
        self, db, monkeypatch,
    ):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        for et in ("skill", "material", "job", "issue"):
            _make_candidate(
                db, tenant_id=tenant.id, entity_type=et,
                raw_value=f"{et}-val", normalized_value=f"{et}-val",
                mention_count=5, confidence=0.9,
            )
        db.commit()

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.qualified == 4
        assert summary.skipped_other == 4
        assert summary.promoted == 0
        # No events written for these — they remain in the staging
        # table for future versions to consume.
        assert db.query(Event).filter(Event.tenant_id == tenant.id).count() == 0


# ---------------------------------------------------------------------------
# Tests — multi-tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:

    def test_only_promotes_for_target_tenant(self, db, monkeypatch):
        tenant_a = make_tenant(db)
        tenant_b = make_tenant(db)
        _opt_in(monkeypatch, f"{tenant_a.id},{tenant_b.id}")
        _make_candidate(
            db, tenant_id=tenant_a.id, entity_type="employee",
            raw_value="AOnly", mention_count=5, confidence=0.9,
        )
        _make_candidate(
            db, tenant_id=tenant_b.id, entity_type="employee",
            raw_value="BOnly", mention_count=5, confidence=0.9,
        )
        db.commit()

        summary_a = P.promote_for_tenant(tenant_a.id, db, now=FIXED_NOW)

        assert summary_a.promoted == 1
        assert db.query(Employee).filter(Employee.tenant_id == tenant_a.id).count() == 1
        assert db.query(Employee).filter(Employee.tenant_id == tenant_b.id).count() == 0


# ---------------------------------------------------------------------------
# Tests — failure isolation
# ---------------------------------------------------------------------------

class TestFailureIsolation:

    def test_one_bad_candidate_does_not_block_others(
        self, db, monkeypatch,
    ):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        # Good candidate.
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="GoodWorker", mention_count=5, confidence=0.9,
        )
        # Bad candidate — empty raw_value will violate Employee.full_name
        # NOT NULL when we pass raw_value through. Wait — empty string
        # is allowed. Force a failure by monkeypatching the inner
        # helper to raise on the second candidate.
        db.commit()

        # Add a candidate that we'll force to fail by patching the
        # employee promoter to raise once.
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="BadWorker", mention_count=4, confidence=0.85,
        )
        db.commit()

        original = P._promote_or_confirm_employee
        call_log: list[str] = []

        def flaky(candidate, db_, *, now, summary):
            call_log.append(candidate.raw_value)
            if candidate.raw_value == "BadWorker":
                raise RuntimeError("synthetic insert failure")
            original(candidate, db_, now=now, summary=summary)

        monkeypatch.setattr(P, "_promote_or_confirm_employee", flaky)

        summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.promoted == 1
        assert len(summary.errors) == 1
        assert "synthetic insert failure" in summary.errors[0]
        # Both candidates were attempted.
        assert "GoodWorker" in call_log
        assert "BadWorker" in call_log


# ---------------------------------------------------------------------------
# Tests — per-industry happy path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("industry", [
    "printing", "manufacturing", "fabrication", "chemical", "field_service",
])
def test_promotion_works_per_industry(db, monkeypatch, industry):
    """Smoke test — promoter is industry-agnostic, but verify each
    vertical's tenant flows end-to-end without surprises."""
    tenant = make_tenant(db, industry_type=industry)
    _opt_in(monkeypatch, str(tenant.id))
    _make_candidate(
        db, tenant_id=tenant.id, entity_type="employee",
        raw_value=f"{industry}-worker", mention_count=5, confidence=0.9,
    )
    db.commit()

    summary = P.promote_for_tenant(tenant.id, db, now=FIXED_NOW)

    assert summary.promoted == 1
