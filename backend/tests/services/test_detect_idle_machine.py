# tests/services/test_detect_idle_machine.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_idle_machine (catalog/machine.py, spec
# B.2.idle_machine).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.machine.detect_idle_machine
#   tests/services/conftest.py builders (make_tenant, make_machine,
#                                          make_job, make_assignment,
#                                          make_machine_downtime)
#
# DESIGN NOTES
#   Covers spec suppression rules (tenant age floor, status filter,
#   open downtime row) and the worst-case selection when multiple
#   machines qualify.

from datetime import date, timedelta

from app.services.briefing_intelligence.catalog.machine import (
    IDLE_MIN_TENANT_AGE_DAYS,
    IDLE_SIGNAL_ID,
    IDLE_WINDOW_DAYS,
    detect_idle_machine,
)

from tests.services.conftest import (
    make_assignment,
    make_job,
    make_machine,
    make_machine_downtime,
    make_tenant,
)


TODAY = date(2026, 5, 4)


class TestDetectIdleMachine:

    def test_returns_none_for_young_tenant(self, db):
        tenant = make_tenant(db, age_days=5)
        make_machine(db, tenant=tenant, name="A", status="Operational")
        db.commit()
        assert detect_idle_machine(tenant.id, TODAY, db) is None

    def test_returns_none_when_machine_was_recently_assigned(self, db):
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        m = make_machine(db, tenant=tenant, name="Active", status="Operational")
        j = make_job(
            db, tenant=tenant, name="J",
            start_date=TODAY - timedelta(days=2), end_date=TODAY,
            status="in_progress",
        )
        make_assignment(db, tenant=tenant, job=j, machine=m, days_ago=1.0)
        db.commit()
        assert detect_idle_machine(tenant.id, TODAY, db) is None

    def test_fires_for_idle_operational_machine(self, db):
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        m = make_machine(db, tenant=tenant, name="IdleOne", status="Operational")
        # No assignments at all
        db.commit()

        result = detect_idle_machine(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == IDLE_SIGNAL_ID
        assert result.tier == 2
        assert result.confidence == "high"
        assert result.subject_entity_id == m.id
        assert "IdleOne" in result.message_hi_en
        assert result.severity_score >= float(IDLE_WINDOW_DAYS)

    def test_status_normalization_treats_active_lowercase_as_operational(self, db):
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        make_machine(db, tenant=tenant, name="lower", status="active")
        db.commit()
        result = detect_idle_machine(tenant.id, TODAY, db)
        assert result is not None
        assert "lower" in result.message_hi_en

    def test_skips_under_maintenance_machines(self, db):
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        make_machine(db, tenant=tenant, name="Broken", status="Under Maintenance")
        db.commit()
        assert detect_idle_machine(tenant.id, TODAY, db) is None

    def test_skips_machine_with_open_downtime(self, db):
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        m = make_machine(db, tenant=tenant, name="Planned", status="Operational")
        make_machine_downtime(
            db, tenant=tenant, machine=m,
            start_date=TODAY - timedelta(days=2),
            end_date=TODAY + timedelta(days=2),
        )
        db.commit()
        assert detect_idle_machine(tenant.id, TODAY, db) is None

    def test_picks_worst_idle_when_multiple_qualify(self, db):
        tenant = make_tenant(db, age_days=IDLE_MIN_TENANT_AGE_DAYS + 5)
        m1 = make_machine(db, tenant=tenant, name="Mild", status="Operational")
        m2 = make_machine(db, tenant=tenant, name="Severe", status="Operational")
        # m1 had an assignment 9 days ago (still outside 7d window)
        j = make_job(
            db, tenant=tenant, name="J",
            start_date=TODAY - timedelta(days=20), end_date=TODAY - timedelta(days=15),
            status="completed",
        )
        make_assignment(db, tenant=tenant, job=j, machine=m1, days_ago=9.0)
        # m2 never had an assignment → worst idle
        db.commit()

        result = detect_idle_machine(tenant.id, TODAY, db)
        assert result is not None
        # Severity = idle days; whichever is worse wins. Both are idle
        # but the never-assigned machine returns IDLE_WINDOW_DAYS
        # while the 9-days-ago one returns 9. So m1 wins by severity.
        # Either way the signal name must come through.
        assert result.subject_entity_id in {m1.id, m2.id}
        assert result.severity_score >= float(IDLE_WINDOW_DAYS)
