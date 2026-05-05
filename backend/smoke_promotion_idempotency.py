#!/usr/bin/env python
# backend/smoke_promotion_idempotency.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.15 manual smoke #2 — idempotency under re-run (Q9 critical
# guarantee). Verifies that running the promoter TWICE against the
# same set of qualifying candidates yields the same final state:
#   - First run inserts the new entity row + writes a promoted event.
#   - Second run fuzzy-matches the just-inserted entity, writes a
#     candidate_confirmed event, and does NOT insert a duplicate.
# Also checks that the customer-skip dedupe holds across runs (only
# one extraction.candidate_skipped event, not two).
#
# This is the single most behaviourally-critical guarantee of the
# v6.3.15 design. If this smoke fails, every nightly run after the
# first one would create duplicate Suresh / Heidelberg rows for the
# same tenant — exactly the bug the design was structured to avoid.
#
# Uses scratch tenant id 9999 (same as smoke #1). Cleans up at end.
#
# USAGE
#   cd backend
#   ./venv/Scripts/python smoke_promotion_idempotency.py
#
# Exit code 0 on PASS, 1 on FAIL.

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


SCRATCH_TENANT_ID = 9999
NOW = datetime.now(timezone.utc)


def _opt_in_scratch() -> None:
    settings.ENTITY_EXTRACTION_TENANT_IDS = str(SCRATCH_TENANT_ID)
    ff._reset_cache()


def _setup(db) -> None:
    print(f"-- setup: creating scratch tenant {SCRATCH_TENANT_ID} + 3 candidates")
    db.add(Tenant(
        id=SCRATCH_TENANT_ID,
        name="SMOKE-IDEMPOTENT", slug="smoke-idempotent", plan="free",
        is_active=True, industry_type="printing",
        created_at=NOW, updated_at=NOW,
    ))
    db.flush()
    for entity_type, raw in [
        ("employee", "Vikram"),
        ("machine",  "Komori"),
        ("customer", "ACME Corp"),
    ]:
        db.add(ExtractionCandidate(
            tenant_id=SCRATCH_TENANT_ID,
            entity_type=entity_type,
            raw_value=raw, normalized_value=raw.strip().lower(),
            confidence=0.9, mention_count=4,
            first_seen=NOW, last_seen=NOW, source_type="whatsapp",
        ))
    db.commit()


def _check(condition: bool, message: str, failures: list[str]) -> None:
    if condition:
        print(f"  PASS  {message}")
    else:
        print(f"  FAIL  {message}")
        failures.append(message)


def _snapshot(db) -> dict:
    """Return current row counts for the scratch tenant."""
    return {
        "employees":          db.query(Employee).filter(Employee.tenant_id == SCRATCH_TENANT_ID).count(),
        "machines":           db.query(Machine).filter(Machine.tenant_id == SCRATCH_TENANT_ID).count(),
        "promoted_events":    db.query(Event).filter(Event.tenant_id == SCRATCH_TENANT_ID, Event.event_type == EVENT_PROMOTED).count(),
        "confirmed_events":   db.query(Event).filter(Event.tenant_id == SCRATCH_TENANT_ID, Event.event_type == EVENT_CONFIRMED).count(),
        "skipped_events":     db.query(Event).filter(Event.tenant_id == SCRATCH_TENANT_ID, Event.event_type == EVENT_SKIPPED).count(),
    }


def _print_snapshot(label: str, snap: dict) -> None:
    print(f"-- {label}: emp={snap['employees']} mach={snap['machines']} "
          f"promoted_ev={snap['promoted_events']} "
          f"confirmed_ev={snap['confirmed_events']} "
          f"skipped_ev={snap['skipped_events']}")


def _cleanup(db) -> None:
    print(f"\n-- cleanup: deleting scratch tenant {SCRATCH_TENANT_ID} (CASCADE)")
    db.execute(Tenant.__table__.delete().where(Tenant.id == SCRATCH_TENANT_ID))
    db.commit()


def main() -> int:
    failures: list[str] = []
    print("=" * 70)
    print("v6.3.15 SMOKE #2 — idempotency under re-run (Q9)")
    print("=" * 70)

    _opt_in_scratch()
    db = SessionLocal()
    try:
        db.execute(Tenant.__table__.delete().where(Tenant.id == SCRATCH_TENANT_ID))
        db.commit()
        _setup(db)

        # ------------------------------------------------------------
        print("\n-- FIRST RUN")
        s1 = promote_for_tenant(SCRATCH_TENANT_ID, db, now=NOW)
        snap1 = _snapshot(db)
        _print_snapshot("after run 1", snap1)
        _check(s1.promoted == 2,
               f"run 1: summary.promoted == 2 (got {s1.promoted})", failures)
        _check(s1.confirmed == 0,
               f"run 1: summary.confirmed == 0 (got {s1.confirmed})", failures)
        _check(s1.skipped_no_table == 1,
               f"run 1: summary.skipped_no_table == 1 (got {s1.skipped_no_table})",
               failures)
        _check(snap1["employees"] == 1, "run 1: 1 employee row", failures)
        _check(snap1["machines"] == 1,  "run 1: 1 machine row",  failures)
        _check(snap1["promoted_events"] == 2,
               "run 1: 2 promoted events", failures)
        _check(snap1["skipped_events"] == 1,
               "run 1: 1 skipped event (customer)", failures)

        # ------------------------------------------------------------
        print("\n-- SECOND RUN (against the same candidates + the just-inserted entities)")
        s2 = promote_for_tenant(SCRATCH_TENANT_ID, db, now=NOW)
        snap2 = _snapshot(db)
        _print_snapshot("after run 2", snap2)

        # The promoted/employee/machine row counts must NOT grow.
        _check(snap2["employees"] == 1,
               f"run 2: still 1 employee row (got {snap2['employees']}) — NO DUPLICATE",
               failures)
        _check(snap2["machines"] == 1,
               f"run 2: still 1 machine row (got {snap2['machines']}) — NO DUPLICATE",
               failures)
        _check(snap2["promoted_events"] == 2,
               f"run 2: still 2 promoted events (got {snap2['promoted_events']}) — "
               f"no new promotion writes",
               failures)

        # Confirmed events must INCREASE by 2 (employee + machine).
        _check(snap2["confirmed_events"] == 2,
               f"run 2: 2 confirmed events (got {snap2['confirmed_events']}) — "
               f"both entities matched fuzzily on re-run",
               failures)

        # Customer-skip dedupe: still only 1 skipped event after 2 runs.
        _check(snap2["skipped_events"] == 1,
               f"run 2: still 1 skipped event (got {snap2['skipped_events']}) — "
               f"customer-skip deduped across runs",
               failures)

        # Summary breakdown of run 2 reflects all-confirms.
        _check(s2.promoted == 0,
               f"run 2: summary.promoted == 0 (got {s2.promoted})", failures)
        _check(s2.confirmed == 2,
               f"run 2: summary.confirmed == 2 (got {s2.confirmed})", failures)
        _check(s2.skipped_no_table == 1,
               f"run 2: summary.skipped_no_table == 1 (still counts the "
               f"customer per-run; the dedupe affects events not the summary)",
               failures)

        # ------------------------------------------------------------
        print("\n-- THIRD RUN (one more, to confirm dedupe holds beyond 2)")
        s3 = promote_for_tenant(SCRATCH_TENANT_ID, db, now=NOW)
        snap3 = _snapshot(db)
        _print_snapshot("after run 3", snap3)

        _check(snap3["employees"] == 1,
               "run 3: still 1 employee row", failures)
        _check(snap3["machines"] == 1,
               "run 3: still 1 machine row", failures)
        _check(snap3["promoted_events"] == 2,
               "run 3: still 2 promoted events total", failures)
        _check(snap3["confirmed_events"] == 4,
               f"run 3: 4 confirmed events total "
               f"(2 from run 2 + 2 from run 3, got {snap3['confirmed_events']})",
               failures)
        _check(snap3["skipped_events"] == 1,
               f"run 3: still 1 skipped event "
               f"(got {snap3['skipped_events']}) — dedupe still holding",
               failures)

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
    print("PASS — re-run produced same final state (no duplicates)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
