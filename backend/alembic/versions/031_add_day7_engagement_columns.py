# alembic/versions/031_add_day7_engagement_columns.py
#
# FILE PURPOSE
# Migration 031 (v6.3.16) — add the two columns the Day-7 First-Insight
# Gate needs to fire exactly once per tenant:
#
#   tenants.first_briefing_sent_at  TIMESTAMPTZ  NULL
#       The anchor for Day-7 day-counting. Set the first time a morning
#       briefing is successfully sent for a tenant; never updated after.
#       NULL means "no morning briefing has ever landed for this tenant"
#       — the dispatcher's day_count check skips such tenants entirely
#       so they cannot trigger a Day-7 fire on stale data.
#
#   tenants.engagement_ladder_state JSONB        NOT NULL DEFAULT '{}'
#       Per-tenant idempotency ledger for engagement-ladder messages.
#       v6.3.16 writes one key: 'day7_owner_sent_at' (ISO-8601 UTC
#       timestamp string) when the Day-7 gate has fired for this
#       tenant. Subsequent ticks see the key and skip. v6.4.0 will
#       reuse the same column for the full ladder (Day-1 ack, Day-3
#       rhythm, Day-7 manager mirror, conditional nudges) — keys
#       added there must not collide with 'day7_owner_sent_at'.
#
# CALLED BY
#   alembic upgrade head    (on deploy)
#   alembic downgrade -1    (on rollback)
#
# CALLS INTO
#   alembic.op.add_column / drop_column
#   alembic.op.execute
#   sqlalchemy.dialects.postgresql.JSONB
#   sqlalchemy column types: DateTime, text
#
# BACKFILL POLICY
#   first_briefing_sent_at is back-filled from the earliest existing
#   briefing.sent event whose payload->>'kind' = 'morning'. This is
#   the same event the v6.3.4 dispatcher emits per successful morning
#   send, so the back-fill is a faithful reconstruction of when the
#   anchor would have been set if this migration had existed earlier.
#
#   Tenants with no morning briefing.sent history retain NULL. The
#   Day-7 gate skips NULL, so those tenants will only become eligible
#   once they begin receiving morning briefings going forward.
#
#   The runtime gate has its own > 14-day guard for tenants whose
#   back-filled day_count would already exceed the 7-day window —
#   those tenants are silently marked as "fired" without sending,
#   so existing pilot tenants do not receive a confusing post-hoc
#   "wow" message. That guard lives in app/services/day7_insight.py;
#   this migration's job is just to provide an honest anchor.
#
# IDEMPOTENCY KEY VOCABULARY (engagement_ladder_state)
#   Reserved keys for v6.3.16 — do not reuse:
#     day7_owner_sent_at : ISO-8601 timestamp string. Presence means
#                          the Day-7 gate has fired (whether it sent
#                          a real message or was suppressed by the
#                          > 14-day guard). Absence means eligible.
#   Reserved for v6.4.0 (do not write here in v6.3.16):
#     day1_ack_sent_at, day3_rhythm_sent_at, day7_manager_sent_at,
#     and conditional-nudge keys per the engagement-ladder design.
#
# DESIGN NOTES
#   - first_briefing_sent_at is nullable, has no server_default, and
#     is set by application code (briefings/dispatcher.dispatch_briefing
#     when kind='morning' AND the column is currently NULL). A migration
#     server_default would be wrong: existing tenants who have not yet
#     received a morning briefing must stay NULL until they actually do.
#   - engagement_ladder_state is NOT NULL with server_default '{}'::jsonb
#     so existing rows back-fill atomically with the ADD COLUMN. The
#     application can always rely on the column being a valid JSON
#     object, never NULL.
#   - JSONB (not JSON) — Postgres-only, but the events table already
#     uses JSONB and the test conftest patches JSONB→JSON for SQLite,
#     so this column slots into the same patch path with no extra work.
#   - Reversible: downgrade drops the two columns in reverse order. All
#     ledger state is lost; Day-7 firings are also recorded as 'briefing.
#     send' Event rows on the events table, so the audit trail survives
#     a downgrade even if the idempotency state does not.
#
# FORWARD-COMPAT
#   - v6.4.0 engagement ladder will append more keys to
#     engagement_ladder_state. No schema change needed.
#   - v6.4.0 may also move the back-fill logic into a per-tenant
#     reconciler (re-derive first_briefing_sent_at if it ever needs
#     to be re-anchored). v6.3.16 does the back-fill once at upgrade
#     time and never touches it again.

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------

revision      = "031"
down_revision = "030"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    """
    Add first_briefing_sent_at + engagement_ladder_state columns to
    tenants, then back-fill first_briefing_sent_at from the earliest
    morning briefing.sent event for each tenant.

    Called by:    alembic upgrade head
    Calls into:   op.add_column(), op.execute()
    Side effects:
        - ALTER TABLE tenants ADD COLUMN first_briefing_sent_at  (nullable)
        - ALTER TABLE tenants ADD COLUMN engagement_ladder_state (NOT NULL,
          server_default '{}'::jsonb — existing rows back-filled atomically)
        - UPDATE tenants SET first_briefing_sent_at = ... for every tenant
          that has at least one briefing.sent event with payload kind=morning.
          Tenants with no such history retain NULL.
    """
    op.add_column(
        "tenants",
        sa.Column(
            "first_briefing_sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "engagement_ladder_state",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Back-fill the anchor from the earliest morning briefing.sent event
    # per tenant. payload is JSONB; ->>'kind' extracts the 'kind' field
    # as text. Tenants without any such event keep NULL.
    op.execute(
        """
        UPDATE tenants
        SET first_briefing_sent_at = sub.first_sent_at
        FROM (
            SELECT tenant_id, MIN(created_at) AS first_sent_at
            FROM events
            WHERE event_type = 'briefing.sent'
              AND payload ->> 'kind' = 'morning'
            GROUP BY tenant_id
        ) AS sub
        WHERE tenants.id = sub.tenant_id
          AND tenants.first_briefing_sent_at IS NULL
        """
    )


def downgrade() -> None:
    """
    Drop the two new columns in reverse order of creation.

    Called by:    alembic downgrade -1
    Calls into:   op.drop_column()
    Side effects:
        - DROP COLUMN engagement_ladder_state — all idempotency state lost.
        - DROP COLUMN first_briefing_sent_at — anchor lost; can be rebuilt
          on the next upgrade via the same back-fill query.
    """
    op.drop_column("tenants", "engagement_ladder_state")
    op.drop_column("tenants", "first_briefing_sent_at")
