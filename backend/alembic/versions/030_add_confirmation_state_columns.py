# alembic/versions/030_add_confirmation_state_columns.py
#
# FILE PURPOSE
# Migration 030 (v6.3.15 revised) — add owner-confirmation state to the
# extraction_candidates staging table. The original v6.3.15 promoted
# candidates by inserting directly into employees / machines on the
# nightly cron. The revised flow asks the owner first via WhatsApp; the
# four new columns track that ask/reply cycle per candidate.
#
# CALLED BY
#   alembic upgrade head    (on deploy)
#   alembic downgrade -1    (on rollback)
#
# CALLS INTO
#   alembic.op.add_column / drop_column
#   alembic.op.create_index / drop_index
#   sqlalchemy column types: DateTime, Integer, String
#
# COLUMNS ADDED (all on extraction_candidates)
#   confirmation_state         VARCHAR(20)  NOT NULL DEFAULT 'none'
#       Vocabulary (app-enforced, not DB CHECK):
#           'none'      - never asked about; eligible for next batch
#           'pending'   - asked; awaiting owner reply
#           'confirmed' - owner said HAAN, OR fuzzy-matched existing
#                         entity (silent skip per Q8)
#           'rejected'  - owner said NAHI, OR auto-rejected after
#                         PROMOTION_CONFIRMATION_MAX_RETRIES
#   confirmation_asked_at      TIMESTAMPTZ  NULL
#       Set when the bot's outbound proposal is queued. Drives the
#       7-day timeout window (PROMOTION_CONFIRMATION_TIMEOUT_DAYS).
#   confirmation_message_id    VARCHAR(120) NULL
#       The wamid of the OUTBOUND bot proposal. NULL in mock/dev when
#       Meta Cloud API is not reachable. Lets the inbound webhook
#       match a reply via WhatsApp's context.id quote-reference, and
#       lets the audit trail follow message -> state -> insertion.
#   confirmation_retry_count   INT          NOT NULL DEFAULT 0
#       Bumped each time a 'pending' candidate ages past timeout and
#       gets re-asked. When it hits PROMOTION_CONFIRMATION_MAX_RETRIES
#       (default 3) the candidate auto-flips to 'rejected'.
#
# INDEXES ADDED
#   idx_extraction_candidates_tenant_confirmation_state
#       (tenant_id, confirmation_state) - powers the per-tenant
#       pre-fire scan ("only state='none' qualifies for the next
#       batch") in compose_confirmation_for_tenant. Without this
#       index the scan would full-scan extraction_candidates per
#       tenant per nightly run.
#
# DESIGN NOTES
#   - confirmation_state is VARCHAR not ENUM so future versions can
#     add states ('expired', 'auto_confirmed_by_admin', etc.) without
#     a follow-up migration. Matches the precedent set by
#     extraction_candidates.entity_type and events.event_type.
#   - server_default values supply the back-fill: every existing row
#     gets confirmation_state='none' and confirmation_retry_count=0
#     atomically with the ADD COLUMN. No follow-up backfill script.
#   - Reversible: downgrade drops the index then the four columns in
#     reverse order. State is lost on downgrade — acceptable because
#     state is operational, not historical (the audit trail in events
#     remains).
#
# FORWARD-COMPAT
#   - When a customers table eventually lands (currently out of scope
#     per promoter.py header), customer candidates will use the same
#     state machine — no schema change needed.
#   - When v6.3.16 NL entity edits land, an additional state like
#     'corrected_pending' may be useful. Documented here so the
#     vocabulary survives the next round of changes.

from alembic import op
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------

revision      = "030"
down_revision = "029"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    """
    Add confirmation_state, confirmation_asked_at, confirmation_message_id,
    confirmation_retry_count columns + composite index to
    extraction_candidates.

    Called by:    alembic upgrade head
    Calls into:   op.add_column(), op.create_index()
    Side effects: ALTER TABLE extraction_candidates ADD COLUMN x4;
                  CREATE INDEX x1. Existing rows back-fill to
                  confirmation_state='none', confirmation_retry_count=0
                  via the server_default values.
    """
    op.add_column(
        "extraction_candidates",
        sa.Column(
            "confirmation_state",
            sa.String(20),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "extraction_candidates",
        sa.Column(
            "confirmation_asked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "extraction_candidates",
        sa.Column(
            "confirmation_message_id",
            sa.String(120),
            nullable=True,
        ),
    )
    op.add_column(
        "extraction_candidates",
        sa.Column(
            "confirmation_retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # (tenant_id, confirmation_state) - pre-fire scan filter for the
    # 19:00 IST nightly batch composer. Without this index, every
    # evening run would full-scan extraction_candidates per tenant.
    op.create_index(
        "idx_extraction_candidates_tenant_confirmation_state",
        "extraction_candidates",
        ["tenant_id", "confirmation_state"],
    )


def downgrade() -> None:
    """
    Drop the composite index then the four new columns in reverse
    order of creation.

    Called by:    alembic downgrade -1
    Calls into:   op.drop_index(), op.drop_column()
    Side effects: All confirmation-state data is lost. The state is
                  operational (drives next-batch eligibility) rather
                  than historical (the audit trail in events table
                  is unaffected), so loss is acceptable.
    """
    op.drop_index(
        "idx_extraction_candidates_tenant_confirmation_state",
        table_name="extraction_candidates",
    )
    op.drop_column("extraction_candidates", "confirmation_retry_count")
    op.drop_column("extraction_candidates", "confirmation_message_id")
    op.drop_column("extraction_candidates", "confirmation_asked_at")
    op.drop_column("extraction_candidates", "confirmation_state")
