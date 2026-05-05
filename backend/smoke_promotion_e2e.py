#!/usr/bin/env python
# backend/smoke_promotion_e2e.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.15 manual smoke #1 — end-to-end happy path. Verifies that one
# nightly run of the candidate-promotion job correctly:
#   - Inserts an Employee row for an employee candidate above threshold
#     (with source='whatsapp_inferred', worker_type='permanent').
#   - Inserts a Machine row for a machine candidate above threshold
#     (with source='whatsapp_inferred', machine_type=NULL).
#   - Skips a customer candidate (no customers table at v6.3.15) and
#     writes one extraction.candidate_skipped event with
#     reason='customer_table_not_yet_implemented'.
#   - Writes the audit-event payloads with the agreed Q7 shape.
#
# Uses a SCRATCH tenant id 9999 so production data is never touched.
# Cleanup at end deletes the scratch tenant; CASCADE removes its rows
# from employees, machines, extraction_candidates, events.
#
# USAGE
#   cd backend
#   ./venv/Scripts/python smoke_promotion_e2e.py
#
# Exit code 0 on PASS, 1 on FAIL. Stdout shows step-by-step state.

from __future__ import annotations

import sys
from datetime import datetime, timezone

from app.config import settings
from app.database import SessionLocal
from app.models.auth import Tenant
from app.models.employee import Employee
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate
from app.models.machine import Machine
from app.services.extraction import feature_flag as ff
from app.services.promotion import (
    EVENT_CONFIRMED,
    EVENT_PROMOTED,
    EVENT_SKIPPED,
    promote_for_tenant,
)
from app.services.promotion.promoter import REASON_NO_TABLE


SCRATCH_TENANT_ID = 9999
NOW = datetime.now(timezone.utc)


def _opt_in_scratch() -> None:
    """Force the feature flag to include the scratch tenant for this run."""
    settings.ENTITY_EXTRACTION_TENANT_IDS = str(SCRATCH_TENANT_ID)
    ff._reset_cache()


def _setup(db) -> None:
    """Create scratch tenant + 3 candidates (employee, machine, customer).

    Uses an explicit id=9999 so cleanup can reliably target it. Postgres
    will allow this because tenants.id is INT (not always-as-identity).
    """
    print(f"-- setup: creating scratch tenant {SCRATCH_TENANT_ID}")
    db.add(Tenant(
        id=SCRATCH_TENANT_ID,
        name="SMOKE-E2E", slug="smoke-e2e", plan="free",
        is_active=True, industry_type="printing",
        created_at=NOW, updated_at=NOW,
    ))
    db.flush()

    fixtures = [
        ("employee", "Suresh"),
        ("machine",  "Heidelberg"),
        ("customer", "Coca Cola"),
    ]
    for entity_type, raw in fixtures:
        db.add(ExtractionCandidate(
            tenant_id=SCRATCH_TENANT_ID,
            entity_type=entity_type,
            raw_value=raw,
            normalized_value=raw.strip().lower(),
            confidence=0.92,
            mention_count=5,
            first_seen=NOW, last_seen=NOW,
            source_type="whatsapp",
        ))
    db.commit()
    print(f"-- setup: 3 candidates inserted "
          f"(employee=Suresh, machine=Heidelberg, customer=Coca Cola)")


def _check(condition: bool, message: str, failures: list[str]) -> None:
    """Print PASS/FAIL line and accumulate failures."""
    if condition:
        print(f"  PASS  {message}")
    else:
        print(f"  FAIL  {message}")
        failures.append(message)


def _run_assertions(db, summary, failures: list[str]) -> None:
    """All assertions for the e2e happy path."""
    print("\n-- assertions on summary")
    _check(summary.qualified == 3, "summary.qualified == 3", failures)
    _check(summary.promoted == 2,  "summary.promoted == 2 (employee + machine)", failures)
    _check(summary.confirmed == 0, "summary.confirmed == 0 (no existing entities)", failures)
    _check(summary.skipped_no_table == 1,
           "summary.skipped_no_table == 1 (customer)", failures)
    _check(summary.skipped_cap == 0, "summary.skipped_cap == 0", failures)
    _check(len(summary.errors) == 0,
           f"summary.errors empty (got {summary.errors})", failures)

    print("\n-- assertions on employees table")
    emp = (db.query(Employee)
             .filter(Employee.tenant_id == SCRATCH_TENANT_ID)
             .one_or_none())
    _check(emp is not None, "exactly one Employee row inserted", failures)
    if emp is not None:
        _check(emp.full_name == "Suresh",
               f"employee.full_name == 'Suresh' (got {emp.full_name!r})", failures)
        _check(emp.source == "whatsapp_inferred",
               f"employee.source == 'whatsapp_inferred' (got {emp.source!r})", failures)
        _check(emp.worker_type == "permanent",
               f"employee.worker_type == 'permanent' (got {emp.worker_type!r})", failures)

    print("\n-- assertions on machines table")
    mach = (db.query(Machine)
              .filter(Machine.tenant_id == SCRATCH_TENANT_ID)
              .one_or_none())
    _check(mach is not None, "exactly one Machine row inserted", failures)
    if mach is not None:
        _check(mach.name == "Heidelberg",
               f"machine.name == 'Heidelberg' (got {mach.name!r})", failures)
        _check(mach.source == "whatsapp_inferred",
               f"machine.source == 'whatsapp_inferred' (got {mach.source!r})", failures)
        _check(mach.machine_type is None,
               f"machine.machine_type IS NULL (got {mach.machine_type!r})", failures)

    print("\n-- assertions on events table (audit)")
    promoted_evs = (db.query(Event)
                    .filter(Event.tenant_id == SCRATCH_TENANT_ID,
                            Event.event_type == EVENT_PROMOTED)
                    .all())
    _check(len(promoted_evs) == 2,
           f"two extraction.candidate_promoted events (got {len(promoted_evs)})",
           failures)

    confirmed_evs = (db.query(Event)
                     .filter(Event.tenant_id == SCRATCH_TENANT_ID,
                             Event.event_type == EVENT_CONFIRMED)
                     .all())
    _check(len(confirmed_evs) == 0,
           f"zero extraction.candidate_confirmed events (got {len(confirmed_evs)})",
           failures)

    skipped_evs = (db.query(Event)
                   .filter(Event.tenant_id == SCRATCH_TENANT_ID,
                           Event.event_type == EVENT_SKIPPED)
                   .all())
    _check(len(skipped_evs) == 1,
           f"one extraction.candidate_skipped event (got {len(skipped_evs)})",
           failures)
    if skipped_evs:
        payload = skipped_evs[0].payload or {}
        _check(payload.get("entity_type") == "customer",
               f"skipped.payload.entity_type == 'customer' (got {payload.get('entity_type')!r})",
               failures)
        _check(payload.get("reason") == REASON_NO_TABLE,
               f"skipped.payload.reason == {REASON_NO_TABLE!r} "
               f"(got {payload.get('reason')!r})", failures)

    print("\n-- assertions on promoted-event payload shape (Q7)")
    for ev in promoted_evs:
        p = ev.payload or {}
        for required in ("candidate_id", "entity_type", "raw_value",
                         "normalized_value", "mention_count", "confidence",
                         "promoted_to_table", "promoted_to_id",
                         "source_value_used"):
            _check(required in p,
                   f"  promoted-event payload contains '{required}' (entity={p.get('entity_type')})",
                   failures)
        _check(p.get("source_value_used") == "whatsapp_inferred",
               f"  promoted.source_value_used == 'whatsapp_inferred' "
               f"(got {p.get('source_value_used')!r})", failures)


def _cleanup(db) -> None:
    """Delete scratch tenant; CASCADE removes child rows."""
    print(f"\n-- cleanup: deleting scratch tenant {SCRATCH_TENANT_ID} (CASCADE)")
    db.execute(
        Tenant.__table__.delete().where(Tenant.id == SCRATCH_TENANT_ID)
    )
    db.commit()


def main() -> int:
    failures: list[str] = []
    print("=" * 70)
    print("v6.3.15 SMOKE #1 — end-to-end happy path")
    print("=" * 70)

    _opt_in_scratch()
    db = SessionLocal()
    try:
        # Defensive cleanup in case a prior failed run left state.
        db.execute(
            Tenant.__table__.delete().where(Tenant.id == SCRATCH_TENANT_ID)
        )
        db.commit()

        _setup(db)
        print("\n-- running promote_for_tenant ...")
        summary = promote_for_tenant(SCRATCH_TENANT_ID, db, now=NOW)
        print(f"-- summary: qualified={summary.qualified} "
              f"promoted={summary.promoted} confirmed={summary.confirmed} "
              f"skipped_cap={summary.skipped_cap} "
              f"skipped_no_table={summary.skipped_no_table} "
              f"errors={len(summary.errors)} "
              f"duration_ms={summary.duration_ms}")

        _run_assertions(db, summary, failures)
    finally:
        try:
            _cleanup(db)
        finally:
            db.close()

    print()
    print("=" * 70)
    if failures:
        print(f"FAIL — {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        print("=" * 70)
        return 1
    print("PASS — all assertions held")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
