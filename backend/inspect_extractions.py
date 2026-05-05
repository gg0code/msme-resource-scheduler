#!/usr/bin/env python
# backend/inspect_extractions.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Dev-only inspection tool for the v6.3.14 entity extractor. Dumps the
# most recent extraction_candidates rows for one tenant, grouped by
# entity_type and sorted by mention_count desc. Use this to tune the
# extractor prompt and to confirm rows are landing during smoke tests.
#
# Avoids exposing an admin HTTP endpoint that would need auth + RBAC.
# Lives in backend/ so it shares the app's Python path / config / DB.
#
# WHO CALLS THIS FILE
# - You (developer) — `python backend/inspect_extractions.py --tenant-id 12`.
# - Not imported by any application code.
#
# WHAT THIS FILE CALLS
# - app.database.SessionLocal — the production / dev DB session factory.
# - app.models.extraction_candidate.ExtractionCandidate — the row class.
#
# USAGE
#   cd backend
#   python inspect_extractions.py --tenant-id 12
#   python inspect_extractions.py --tenant-id 12 --limit 50
#   python inspect_extractions.py --tenant-id 12 --type machine
#   python inspect_extractions.py --tenant-id 12 --show-promotions
#   python inspect_extractions.py --tenant-id 12 --show-promotions --limit 50
#
# DESIGN NOTES
# - Read-only. Never mutates the table. Safe to run against prod (read
#   query only).
# - Output is plain text, terminal-width-friendly. No JSON, no fancy
#   table renderers — keeps deps minimal.
# - --show-promotions (v6.3.15) reads recent extraction.* events and
#   prints them grouped by event_type. Use this after a nightly
#   promotion run to see what got promoted, confirmed, or skipped.

from __future__ import annotations

import argparse
import sys
from collections import defaultdict


def main() -> int:
    """Parse CLI args, query, render. Returns process exit code.

    Called by:    `__main__` block at the bottom of this file.
    Calls into:   app.database.SessionLocal, ExtractionCandidate ORM.
    Side effects: opens + closes one DB session, prints to stdout.
    """
    parser = argparse.ArgumentParser(
        description="Dump recent extraction_candidates rows for a tenant.",
    )
    parser.add_argument("--tenant-id", type=int, required=True,
                        help="Tenant ID to inspect.")
    parser.add_argument("--limit", type=int, default=20,
                        help="Max rows per group (default 20).")
    parser.add_argument("--type", default=None,
                        help="Filter to a single entity_type (e.g. 'machine').")
    parser.add_argument(
        "--show-promotions",
        action="store_true",
        help="(v6.3.15) Dump recent extraction.* audit events instead "
             "of staging-table candidates. Use after a nightly "
             "promotion run to see what got promoted/confirmed/skipped.",
    )
    args = parser.parse_args()

    if args.show_promotions:
        return _render_promotions(args.tenant_id, args.limit)

    from app.database import SessionLocal
    from app.models.extraction_candidate import ExtractionCandidate

    db = SessionLocal()
    try:
        q = (
            db.query(ExtractionCandidate)
            .filter(ExtractionCandidate.tenant_id == args.tenant_id)
        )
        if args.type:
            q = q.filter(ExtractionCandidate.entity_type == args.type)
        rows = (
            q.order_by(
                ExtractionCandidate.entity_type.asc(),
                ExtractionCandidate.mention_count.desc(),
                ExtractionCandidate.last_seen.desc(),
            )
            .all()
        )
    finally:
        db.close()

    if not rows:
        print(f"No extraction_candidates rows for tenant_id={args.tenant_id}.")
        return 0

    grouped: dict[str, list] = defaultdict(list)
    for r in rows:
        grouped[r.entity_type].append(r)

    print(f"\nExtraction candidates for tenant_id={args.tenant_id}\n")
    for entity_type in sorted(grouped):
        bucket = grouped[entity_type][: args.limit]
        print(f"== {entity_type} ({len(grouped[entity_type])} rows, "
              f"showing {len(bucket)}) ==")
        for r in bucket:
            print(
                f"  count={r.mention_count:>3}  conf={r.confidence:.2f}  "
                f"value={r.normalized_value!r}  raw={r.raw_value!r}  "
                f"last_seen={r.last_seen}"
            )
        print()

    return 0


def _render_promotions(tenant_id: int, limit: int) -> int:
    """v6.3.15 — dump recent promoter audit events for a tenant.

    Called by:    main() when --show-promotions is passed.
    Calls into:   app.database.SessionLocal, Event ORM,
                  app.services.promotion.{EVENT_PROMOTED,
                  EVENT_CONFIRMED, EVENT_SKIPPED}.
    Side effects: opens / closes one DB session, prints to stdout.

    Bucketed by event_type, sorted by created_at desc within each
    bucket. `limit` caps rows per bucket so dumping a busy tenant is
    still readable.
    """
    from app.database import SessionLocal
    from app.models.event import Event
    from app.services.promotion import (
        EVENT_CONFIRMED,
        EVENT_PROMOTED,
        EVENT_SKIPPED,
    )

    event_types = (EVENT_PROMOTED, EVENT_CONFIRMED, EVENT_SKIPPED)

    db = SessionLocal()
    try:
        rows = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant_id,
                Event.event_type.in_(event_types),
            )
            .order_by(Event.created_at.desc())
            .all()
        )
    finally:
        db.close()

    if not rows:
        print(
            f"No extraction.* events for tenant_id={tenant_id}. "
            "(Has the nightly promotion job run yet for this tenant?)"
        )
        return 0

    grouped: dict[str, list] = defaultdict(list)
    for r in rows:
        grouped[r.event_type].append(r)

    print(f"\nPromotion events for tenant_id={tenant_id}\n")
    for event_type in event_types:
        bucket = grouped.get(event_type, [])
        if not bucket:
            continue
        shown = bucket[:limit]
        print(f"== {event_type} ({len(bucket)} rows, showing {len(shown)}) ==")
        for r in shown:
            payload = r.payload or {}
            # Render the most useful fields per event type. The raw
            # JSON is too noisy for terminal output.
            if event_type == EVENT_PROMOTED:
                print(
                    f"  at={r.created_at}  candidate={payload.get('candidate_id')}  "
                    f"type={payload.get('entity_type')}  "
                    f"raw={payload.get('raw_value')!r}  "
                    f"-> {payload.get('promoted_to_table')}#"
                    f"{payload.get('promoted_to_id')}  "
                    f"src={payload.get('source_value_used')}"
                )
            elif event_type == EVENT_CONFIRMED:
                print(
                    f"  at={r.created_at}  candidate={payload.get('candidate_id')}  "
                    f"matched={payload.get('matched_entity_table')}#"
                    f"{payload.get('matched_entity_id')}  "
                    f"score={payload.get('match_score')}  "
                    f"strat={payload.get('match_strategy')}"
                )
            else:  # EVENT_SKIPPED
                print(
                    f"  at={r.created_at}  candidate={payload.get('candidate_id')}  "
                    f"type={payload.get('entity_type')}  "
                    f"reason={payload.get('reason')}"
                )
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
