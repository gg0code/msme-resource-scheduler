# alembic/versions/034_add_events_dedup_index.py
#
# FILE PURPOSE
# Migration 034 (v6.3.19 slice 2C) — add a composite index on
# events(tenant_id, event_type) to support the per-tick idempotency
# dedup query introduced by app/services/consolidated_briefing.
# dispatch_morning / dispatch_evening.
#
# Why this index
# Slice 2C dedup logic queries:
#   SELECT id FROM events
#   WHERE tenant_id = :tid AND event_type = :event_type
# (then filters payload->>'scheduled_for_date' in Python — see
# _already_dispatched_today). The events table already carries
# individual indexes on tenant_id and event_type from migration 028,
# but Postgres index intersection is consistently slower than a
# composite for the dispatcher's hot-path question "did this exact
# (tenant, event_type) pair already fire today?".
#
# Without this index every tick becomes a candidate scan that grows
# with the events table — at 1000 tenants firing two pushes a day for
# a year, that's 730K rows. With the composite, lookups are O(log N)
# inside the (tenant, type) prefix and the in-Python date filter
# touches only the per-tenant per-type slice (max ~365 rows even at
# steady state).
#
# CALLED BY
#   alembic upgrade head    (on deploy)
#   alembic downgrade -1    (on rollback)
#
# CALLS INTO
#   alembic.op.create_index / drop_index
#
# DESIGN NOTES
#   - btree composite, not GIN on payload. The payload->>'scheduled_for_date'
#     filter runs in Python after the index narrows by (tenant_id,
#     event_type) — this stays portable across Postgres + SQLite
#     (test conftest patches JSONB->JSON). A JSONB-aware expression
#     index would be Postgres-only and require a CREATE INDEX
#     CONCURRENTLY pattern that is harder to roll back cleanly. The
#     Python-side filter is acceptable because the index already
#     narrows to a small set (~hundreds of rows max per tenant per
#     event type at steady state).
#   - Index name: ix_events_tenant_type_dedup. Distinct from the
#     existing per-column indexes (ix_events_tenant_id /
#     ix_events_event_type from migration 028); kept as a separate
#     composite so a future migration can drop one without touching
#     the other.
#   - Reversible: downgrade drops only the composite; the per-column
#     indexes from 028 remain in place.
#
# FORWARD-COMPAT
#   - When per-day push counts cross ~1000 events/tenant/year, revisit
#     with a partial index (WHERE event_type LIKE 'push.%') or a
#     proper expression index on payload->>'scheduled_for_date'.

from alembic import op


# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------

revision      = "034"
down_revision = "033"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    """
    Add composite index ix_events_tenant_type_dedup on events
    (tenant_id, event_type).

    Called by:    alembic upgrade head
    Calls into:   op.create_index()
    Side effects: CREATE INDEX ix_events_tenant_type_dedup ON events
                  (tenant_id, event_type). Online build — does not
                  block writes on Postgres but holds an exclusive lock
                  briefly. Acceptable at v6.3.19 scale.
    """
    op.create_index(
        "ix_events_tenant_type_dedup",
        "events",
        ["tenant_id", "event_type"],
    )


def downgrade() -> None:
    """
    Drop the composite index. Per-column indexes from migration 028
    remain.

    Called by:    alembic downgrade -1
    Calls into:   op.drop_index()
    Side effects: DROP INDEX ix_events_tenant_type_dedup. Subsequent
                  dispatcher dedup queries fall back to index
                  intersection on the per-column indexes — slower but
                  still correct.
    """
    op.drop_index("ix_events_tenant_type_dedup", table_name="events")
