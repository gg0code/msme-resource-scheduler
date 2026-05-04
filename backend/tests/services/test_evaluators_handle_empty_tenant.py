# tests/services/test_evaluators_handle_empty_tenant.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Defensive integration test: every evaluator must return None or a
# valid SignalResult on a brand-new tenant with no data. None of them
# may raise.
#
# Spec ref: prompt constraint "All new evaluators must handle empty /
# null / missing data gracefully. Never raise — return None."
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.composer.ALL_DETECTORS
#   app.services.briefing_intelligence.signals.SignalResult
#   tests/services/conftest.py builders (make_tenant)
#
# DESIGN NOTES
#   Iterates over ALL_DETECTORS rather than naming each evaluator so
#   any evaluator added in a future session is automatically covered
#   by this safety net. Three scenarios (empty tenant with normal
#   age, zero-age tenant, unknown tenant_id) cover the common "no
#   data" failure modes.

from datetime import date

from app.services.briefing_intelligence.composer import ALL_DETECTORS
from app.services.briefing_intelligence.signals import SignalResult

from tests.services.conftest import make_tenant


TODAY = date(2026, 5, 4)


class TestEvaluatorsHandleEmptyTenant:

    def test_all_evaluators_return_none_or_signalresult_on_empty_tenant(
        self, db,
    ):
        tenant = make_tenant(db, age_days=30)
        db.commit()

        # Empty tenant: no employees, no machines, no jobs, no events.
        for evaluator in ALL_DETECTORS:
            result = evaluator(tenant.id, TODAY, db)
            assert result is None or isinstance(result, SignalResult), (
                f"{evaluator.__name__} returned unexpected {type(result)}"
            )

    def test_all_evaluators_dont_raise_for_zero_age_tenant(self, db):
        tenant = make_tenant(db, age_days=0)
        db.commit()

        for evaluator in ALL_DETECTORS:
            # Must not raise even when the tenant is brand new.
            evaluator(tenant.id, TODAY, db)

    def test_all_evaluators_dont_raise_for_unknown_tenant_id(self, db):
        for evaluator in ALL_DETECTORS:
            # tenant_id 99999 does not exist; must still not raise.
            evaluator(99999, TODAY, db)
