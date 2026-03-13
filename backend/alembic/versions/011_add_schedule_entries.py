"""011_add_schedule_entries.py

Alembic migration — creates schedule_entries table for persisted scheduler output.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedule_entries",
        sa.Column("id",                   sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column("tenant_id",            sa.Integer(),  nullable=False),
        sa.Column("job_id",               sa.Integer(),  nullable=False),
        sa.Column("step_id",              sa.Integer(),  nullable=False),
        sa.Column("assigned_machine_ids", postgresql.ARRAY(sa.Integer()), nullable=False, server_default="{}"),
        sa.Column("assigned_helper_ids",  postgresql.ARRAY(sa.Integer()), nullable=False, server_default="{}"),
        sa.Column("scheduled_start",      sa.DateTime(), nullable=False),
        sa.Column("scheduled_end",        sa.DateTime(), nullable=False),
        sa.Column("created_at",           sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_schedule_entries_tenant_id", "schedule_entries", ["tenant_id"])
    op.create_index("ix_schedule_entries_job_id",    "schedule_entries", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_schedule_entries_job_id",    table_name="schedule_entries")
    op.drop_index("ix_schedule_entries_tenant_id", table_name="schedule_entries")
    op.drop_table("schedule_entries")
