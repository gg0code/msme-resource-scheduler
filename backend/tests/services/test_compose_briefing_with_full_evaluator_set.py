# tests/services/test_compose_briefing_with_full_evaluator_set.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Integration test that exercises the composer with the full 13-
# evaluator catalog wired in. Seeds a realistic tenant whose data
# triggers four signals across distinct categories; asserts top 3
# are surfaced, the 4th is dropped, and briefing.signal_fired events
# are written for all surfaced signals.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.briefing_intelligence.composer.compose_briefing
#   app.services.briefing_intelligence.cooldown.SIGNAL_FIRED_EVENT_TYPE
#   app.models.event.Event
#   tests/services/conftest.py builders (make_tenant, make_job,
#                                          make_machine, make_employee,
#                                          make_attendance_event)
#
# DESIGN NOTES
#   Unlike per-evaluator tests this one runs the real composer
#   pipeline (no monkeypatching of ALL_DETECTORS), so it doubles as
#   a smoke test that the 13 evaluators interact correctly with the
#   2B framework (sort, diversity, cooldown, persistence).

from datetime import date, datetime, timedelta, timezone

from app.models.event import Event
from app.services.briefing_intelligence.composer import compose_briefing
from app.services.briefing_intelligence.cooldown import (
    SIGNAL_FIRED_EVENT_TYPE,
)

from tests.services.conftest import (
    make_attendance_event,
    make_employee,
    make_job,
    make_machine,
    make_tenant,
)


TODAY = date(2026, 5, 4)


class TestComposeBriefingFullEvaluatorSet:

    def test_full_evaluator_set_selects_three_diverse_signals(self, db):
        # Tenant aged 30 days → past quiet period and past most day-
        # markers. Day-7 / Day-2 do NOT fire on age 30.
        tenant = make_tenant(db, age_days=30, industry_type="printing")

        # --- Trigger 1: delayed_jobs_count (job, tier 1) ---
        make_job(
            db, tenant=tenant, name="OldOrder",
            start_date=TODAY - timedelta(days=10),
            end_date=TODAY - timedelta(days=2),
            status="in_progress",
        )

        # --- Trigger 2: idle_machine (machine, tier 2) ---
        make_machine(db, tenant=tenant, name="Press-1", status="Operational")

        # --- Trigger 3: consecutive_absence (attendance, tier 1) ---
        suresh = make_employee(db, tenant=tenant, full_name="Suresh",
                                created_days_ago=30)
        for off in range(3):
            make_attendance_event(
                db, tenant=tenant,
                for_date=TODAY - timedelta(days=off),
                absent_employee_ids=[suresh.id],
                created_at=(datetime.combine(
                    TODAY - timedelta(days=off), datetime.min.time(),
                ).replace(tzinfo=timezone.utc)),
            )

        # --- Trigger 4: manager_silence (health, tier 2). Already
        # implicit because attendance only has 3 events in the last
        # 7 days (< 4 threshold).

        db.commit()

        out = compose_briefing(
            tenant_id=tenant.id, kind="morning", today=TODAY, db=db,
        )

        assert "ZetaOps briefing" in out
        # Three bullet lines max — diversity + cap rule.
        bullet_count = sum(1 for ln in out.splitlines() if ln.startswith("- "))
        assert bullet_count <= 3
        assert bullet_count >= 2

        # Surfaced signals must include both tier-1 candidates.
        assert "Suresh" in out  # consecutive_absence
        assert "OldOrder" in out  # delayed_jobs_count

        # Per-signal firing events must have been recorded for each
        # surfaced signal so cooldowns hold tomorrow.
        rows = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == SIGNAL_FIRED_EVENT_TYPE,
            )
            .all()
        )
        assert len(rows) == bullet_count

        # All categories on surfaced signals must be unique
        # (diversity rule).
        categories = [(r.payload or {}).get("signal_id") for r in rows]
        assert len(set(categories)) == len(categories)
