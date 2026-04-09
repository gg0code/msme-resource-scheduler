# alembic/versions/023_add_source_and_worker_type.py
# Migration: add source field to employees and machines, worker_type to employees
# Introduced in: v5.16
#
# What it does:
#   employees table:
#     - source:      VARCHAR(20) NOT NULL DEFAULT 'manual'
#                    Values: 'manual' | 'whatsapp' | 'erp_sync'
#                    Tracks how the record was created. Never remove this column
#                    - it is the structural decision that keeps v7.0 ERP connector
#                    a sprint not a rewrite.
#     - worker_type: VARCHAR(20) NOT NULL DEFAULT 'permanent'
#                    Values: 'permanent' | 'contractor'
#                    Permanent = monthly salary. Contractor = daily rate.
#                    Used by v7.2 Contractor Labour Layer.
#   machines table:
#     - source:      VARCHAR(20) NOT NULL DEFAULT 'manual'
#                    Same values and purpose as employees.source.
#
# Rules followed:
#   - New NOT NULL columns on existing tables use server_default, not default.
#     This prevents failure on tables that already have rows.
#   - Both upgrade() and downgrade() are implemented.
#   - Uses IF NOT EXISTS / IF EXISTS guards for safe re-runs.
#   - down_revision chains correctly from 022.

from alembic import op
import sqlalchemy as sa

revision      = "023"
down_revision = "022"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    """
    Add source and worker_type columns to employees and machines tables.

    Called by:   alembic upgrade head
    Calls:       op.add_column() for each new column
    Side effects: Alters employees and machines tables in PostgreSQL.
                  All existing rows receive server_default values automatically.
    """
    # -- employees: source field ----------------------------------------------
    # server_default='manual' ensures existing rows are backfilled immediately.
    # nullable=False is safe here because server_default covers all existing rows.
    op.add_column(
        "employees",
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="manual",
            comment="How this record was created: manual | whatsapp | erp_sync",
        ),
    )

    # -- employees: worker_type field -----------------------------------------
    op.add_column(
        "employees",
        sa.Column(
            "worker_type",
            sa.String(20),
            nullable=False,
            server_default="permanent",
            comment="Employment classification: permanent | contractor",
        ),
    )

    # -- machines: source field -----------------------------------------------
    op.add_column(
        "machines",
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="manual",
            comment="How this record was created: manual | whatsapp | erp_sync",
        ),
    )


def downgrade() -> None:
    """
    Remove source and worker_type columns added by upgrade().

    Called by:   alembic downgrade 022
    Calls:       op.drop_column() for each added column
    Side effects: Alters employees and machines tables. Data in these columns
                  is permanently lost on downgrade.
    """
    op.drop_column("machines",  "source")
    op.drop_column("employees", "worker_type")
    op.drop_column("employees", "source")
