# alembic/versions/033_add_push_columns_to_tenants.py
#
# FILE PURPOSE
# Migration 033 (v6.3.19 slice 2A) — add three nullable columns to
# the tenants table to back the per-tenant push config introduced by
# the consolidated push dispatcher (v6.3.19 follow-up slices):
#
#   tenants.morning_sections  JSONB  NULL
#       Ordered list of section keys to render in the morning push body,
#       e.g. ["plan", "flag", "next_step"]. NULL means "use system
#       default from backend/config/push_defaults.yaml". Vocabulary
#       owned by the dispatcher render layer (slice 2C).
#
#   tenants.evening_sections  JSONB  NULL
#       Mirror of morning_sections for the evening cadence,
#       e.g. ["completed", "hours_logged", "tomorrow_preview"].
#
#   tenants.push_paused_until DATE   NULL
#       When set and >= today (in the tenant timezone), the dispatcher
#       silently skips both pushes. NULL means "not paused". Used by
#       owners to silence pushes during downtime or holidays without
#       flipping the briefing_morning_enabled / briefing_evening_enabled
#       toggles individually.
#
# WHY THESE ARE THE ONLY THREE NEW COLUMNS
# The v6.3.19 brief originally called out seven new fields
# (morning_push_time, evening_push_time, push_timezone, push_enabled,
# morning_sections, evening_sections, push_paused_until). The slice 2A
# audit found that migration 027 (v6.3.1) already added equivalents
# for the first four:
#   briefing_morning_time     (already covers "morning_push_time")
#   briefing_evening_time     (already covers "evening_push_time")
#   briefing_timezone         (already covers "push_timezone")
#   briefing_morning_enabled  (covers morning half of "push_enabled")
#   briefing_evening_enabled  (covers evening half of "push_enabled")
# Adding parallel push_* columns for those four would create a dual
# source of truth — see CHANGELOG [Unreleased] note "Naming bridge in
# resolve_push_config" for the deliberate scope decision. A future
# slice 2A-rename may unify the namespace if the cost of the
# inconsistency grows; for now the resolver in
# app/services/push_config.py bridges briefing_* into the PushConfig
# dataclass without renaming the columns.
#
# CALLED BY
#   alembic upgrade head    (on deploy)
#   alembic downgrade -1    (on rollback)
#
# CALLS INTO
#   alembic.op.add_column / drop_column
#   sqlalchemy.dialects.postgresql.JSONB
#   sqlalchemy column types: Date
#
# BACKFILL POLICY
#   None. All three columns are nullable with no server_default. The
#   resolve_push_config() resolver in app/services/push_config.py
#   (slice 2A part 2) interprets NULL as "fall through to the system
#   default in push_defaults.yaml", so existing tenants pick up sane
#   behaviour without any data migration.
#
# DESIGN NOTES
#   - JSONB (not JSON) — matches engagement_ladder_state (migration 031)
#     and events.payload conventions. The test conftest patches
#     JSONB->JSON for SQLite test runs.
#   - All three columns are nullable. No server_default text — adding
#     one would silently bake a default into existing rows that the
#     resolver could not distinguish from "owner set this explicitly".
#   - Reversible: downgrade drops all three in reverse order. Any
#     tenant-set values are lost; the resolver falls through to YAML
#     defaults on the next dispatch.
#
# FORWARD-COMPAT
#   - Section vocabulary is open — new section keys can land in
#     push_defaults.yaml + dispatcher render path without a schema
#     change.
#   - push_paused_until could be extended to a TIMESTAMP later if
#     hour-level pause semantics become useful; for v6.3.19 a
#     calendar date is sufficient.

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------

revision      = "033"
down_revision = "032"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    """
    Add morning_sections, evening_sections, push_paused_until columns
    to tenants. All nullable, no server_default, no backfill.

    Called by:    alembic upgrade head
    Calls into:   op.add_column()
    Side effects:
        - ALTER TABLE tenants ADD COLUMN morning_sections   JSONB NULL
        - ALTER TABLE tenants ADD COLUMN evening_sections   JSONB NULL
        - ALTER TABLE tenants ADD COLUMN push_paused_until  DATE  NULL
    """
    op.add_column(
        "tenants",
        sa.Column("morning_sections", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("evening_sections", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("push_paused_until", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    """
    Drop the three v6.3.19 push columns in reverse order of creation.

    Called by:    alembic downgrade -1
    Calls into:   op.drop_column()
    Side effects:
        - DROP COLUMN push_paused_until
        - DROP COLUMN evening_sections — any JSONB content lost
        - DROP COLUMN morning_sections — any JSONB content lost
    """
    op.drop_column("tenants", "push_paused_until")
    op.drop_column("tenants", "evening_sections")
    op.drop_column("tenants", "morning_sections")
