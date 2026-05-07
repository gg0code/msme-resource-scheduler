# alembic/versions/032_add_source_to_skills.py
#
# FILE PURPOSE
# Migration 032 (v6.3.17) — add the structural `source` column to the
# skills table so skill provenance is tracked the same way it is for
# employees and machines.
#
# Background: migration 023 added `source` (VARCHAR(20) NOT NULL DEFAULT
# 'manual') to employees and machines. CLAUDE.md architecture rule #2
# calls this column out as a permanent structural decision that keeps
# the v7.0 ERP connector a sprint not a rewrite. Skill was the only
# entity table that lacked the same column — v6.3.17 closes that gap so
# WhatsApp-owner-asserted skills can be distinguished from imported,
# auto-promoted, or manually-created ones.
#
# CALLED BY
#   alembic upgrade head    (on deploy)
#   alembic downgrade -1    (on rollback)
#
# CALLS INTO
#   alembic.op.add_column / drop_column
#   sqlalchemy column types: String
#
# COLUMN ADDED
#   skills.source  VARCHAR(20)  NOT NULL  DEFAULT 'manual'
#       Vocabulary (app-enforced via VALID_SOURCE_VALUES, no DB CHECK):
#         'manual'           - Day 1 table UI / explicit owner setup
#         'whatsapp'         - captured via WhatsApp conversation
#                              (legacy / manager-typed flow)
#         'whatsapp_inferred'- bot-extracted-and-promoted via the
#                              v6.3.15 confirmation cycle
#         'whatsapp_owner'   - v6.3.17 owner-bypass direct write
#         'erp_sync'         - v7.0 ERP connector (planned)
#
# DESIGN NOTES
#   - server_default='manual' atomically back-fills every existing row
#     during the ADD COLUMN. No follow-up backfill script needed.
#   - Plain VARCHAR not ENUM so future versions can add source values
#     without a follow-up migration. Matches the precedent set by
#     employees/machines (migration 023) and extraction_candidates
#     entity_type / source_type.
#   - Reversible: downgrade drops the column. All provenance data is
#     lost on downgrade — acceptable because the audit trail in events
#     remains intact.
#
# FORWARD-COMPAT
#   - When the v7.0 ERP connector lands, ERP-imported skills will use
#     source='erp_sync' and live alongside whatsapp_owner / manual rows
#     without schema change.

from alembic import op
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------

revision      = "032"
down_revision = "031"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    """
    Add `source` column to skills with default 'manual'.

    Called by:    alembic upgrade head
    Calls into:   op.add_column()
    Side effects: ALTER TABLE skills ADD COLUMN source VARCHAR(20) NOT
                  NULL DEFAULT 'manual'. Existing rows back-fill to
                  'manual' atomically via the server_default.
    """
    op.add_column(
        "skills",
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="manual",
        ),
    )


def downgrade() -> None:
    """
    Drop the source column from skills.

    Called by:    alembic downgrade -1
    Calls into:   op.drop_column()
    Side effects: All provenance data on skills is lost. Acceptable
                  because the audit trail in events table is unaffected.
    """
    op.drop_column("skills", "source")
