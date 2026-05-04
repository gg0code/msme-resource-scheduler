# tests/services/test_detect_status_change_alert.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for detect_status_change_alert (catalog/machine.py, spec
# B.2.status_change_alert).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.catalog.machine.detect_status_change_alert
#   tests/services/conftest.py builders (make_tenant, make_machine)
#
# DESIGN NOTES
#   Covers the 24-hour window filter, status_in normalization (active
#   lowercase = operational), and most-recently-flipped tie-break.

from datetime import date

from app.services.briefing_intelligence.catalog.machine import (
    STATUS_CHANGE_SIGNAL_ID,
    detect_status_change_alert,
)

from tests.services.conftest import make_machine, make_tenant


TODAY = date(2026, 5, 4)


class TestDetectStatusChangeAlert:

    def test_returns_none_when_all_machines_operational(self, db):
        tenant = make_tenant(db)
        make_machine(db, tenant=tenant, name="A", status="Operational",
                     updated_days_ago=0.1)
        db.commit()
        assert detect_status_change_alert(tenant.id, TODAY, db) is None

    def test_fires_when_machine_recently_flipped_to_maintenance(self, db):
        tenant = make_tenant(db)
        m = make_machine(
            db, tenant=tenant, name="JustBroken",
            status="Under Maintenance", updated_days_ago=0.1,
        )
        db.commit()

        result = detect_status_change_alert(tenant.id, TODAY, db)
        assert result is not None
        assert result.signal_id == STATUS_CHANGE_SIGNAL_ID
        assert result.tier == 3
        assert result.confidence == "low"
        assert result.subject_entity_id == m.id
        assert "JustBroken" in result.message_hi_en
        assert "Under Maintenance" in result.message_hi_en

    def test_skips_old_status_changes(self, db):
        tenant = make_tenant(db)
        make_machine(
            db, tenant=tenant, name="OldFlip",
            status="Under Maintenance", updated_days_ago=5.0,
        )
        db.commit()
        assert detect_status_change_alert(tenant.id, TODAY, db) is None

    def test_skips_active_lowercase_machines(self, db):
        tenant = make_tenant(db)
        make_machine(
            db, tenant=tenant, name="Working",
            status="active", updated_days_ago=0.1,
        )
        db.commit()
        # 'active' is operational — should not fire as a status flip.
        assert detect_status_change_alert(tenant.id, TODAY, db) is None

    def test_picks_most_recently_flipped_when_multiple(self, db):
        tenant = make_tenant(db)
        make_machine(
            db, tenant=tenant, name="A",
            status="Under Maintenance", updated_days_ago=0.5,
        )
        make_machine(
            db, tenant=tenant, name="B",
            status="Under Maintenance", updated_days_ago=0.05,
        )
        db.commit()
        result = detect_status_change_alert(tenant.id, TODAY, db)
        assert result is not None
        assert "B" in result.message_hi_en
