# alembic/versions/028_events_table.py
#
# FILE PURPOSE
# Migration 028 (v6.3.3) - audit events table. Backs the role-change audit
# trail emitted by app/routers/team_management.py and reserved for future
# briefing.* and other event types per SRS v6.4 Section 6.28.6.
#
# CALLED BY
#   alembic upgrade head    (on deploy)
#   alembic downgrade -1    (on rollback)
#
# CALLS INTO
#   alembic.op.create_table / drop_table / create_index / drop_index
#   sqlalchemy column types: Integer, String, DateTime, JSONB
#
# DESIGN NOTES
#   - tenant_id has CASCADE on tenants.id so a tenant purge cleans up its
#     audit trail. actor_user_id has SET NULL on users.id so deleting a
#     user does NOT erase their historical actions - audit is the point.
#   - entity_id has no FK. Events span entity types (user, job, briefing),
#     and a polymorphic FK across tables is more brittle than entity_type
#     + entity_id pair.
#   - payload is JSONB on Postgres; the test conftest patches it to JSON
#     so SQLite can create the table for unit tests.
#   - created_at uses server_default=text('now()') - Postgres only. Tests
#     use the patch_now_defaults_for_sqlite autouse fixture from
#     test_signup_v6_4.py to swap to CURRENT_TIMESTAMP.
#   - Composite index (tenant_id, event_type) backs the most common query
#     pattern: "what role changes happened in this tenant?". Single-column
#     idx_events_tenant_id covers the broader tenant scan.

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------

revision      = "028"
down_revision = "027"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    """
    Create the events table and its supporting indexes.

    Called by:    alembic upgrade head
    Calls into:   op.create_table(), op.create_index()
    Side effects: CREATE TABLE events; CREATE INDEX x3.
    """
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type",  sa.String(50),  nullable=False),
        sa.Column("entity_type", sa.String(50),  nullable=False),
        sa.Column("entity_id",   sa.Integer(),   nullable=True),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source",  sa.String(20),       nullable=False),
        sa.Column("payload", postgresql.JSONB(),  nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Tenant-scoped lookups - the hot path.
    op.create_index("idx_events_tenant_id", "events", ["tenant_id"])
    # Per-event-type scans within a tenant.
    op.create_index(
        "idx_events_tenant_event_type",
        "events",
        ["tenant_id", "event_type"],
    )
    # Per-entity history (e.g. all events about user 42).
    op.create_index(
        "idx_events_entity",
        "events",
        ["entity_type", "entity_id"],
    )


def downgrade() -> None:
    """
    Drop the events table and its indexes, in reverse order.

    Called by:    alembic downgrade -1
    Calls into:   op.drop_index(), op.drop_table()
    Side effects: DROP TABLE events; all event rows lost.
    """
    op.drop_index("idx_events_entity",            table_name="events")
    op.drop_index("idx_events_tenant_event_type", table_name="events")
    op.drop_index("idx_events_tenant_id",         table_name="events")
    op.drop_table("events")
