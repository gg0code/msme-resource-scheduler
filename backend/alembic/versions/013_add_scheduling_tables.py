"""010_add_scheduling_tables.py

Alembic migration — adds step-based scheduling engine tables.
Extends existing migration sequence (migrations 001–009 are existing).

Creates:
  sched_resources
  sched_jobs
  sched_steps
  sched_step_machines
  sched_step_helpers
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "013_scheduling_tables"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    resource_type_enum   = postgresql.ENUM("machine", "helper",                        name="resource_type_enum",        create_type=True)
    sched_priority_enum  = postgresql.ENUM("critical", "urgent", "low",                name="sched_job_priority_enum",   create_type=True)
    sched_shift_enum     = postgresql.ENUM("morning", "evening",                       name="sched_job_shift_enum",      create_type=True)
    sched_job_stat_enum  = postgresql.ENUM("pending", "scheduled", "in_progress", "complete", name="sched_job_status_enum", create_type=True)
    step_type_enum       = postgresql.ENUM("regular", "setup",                         name="step_type_enum",            create_type=True)
    step_status_enum     = postgresql.ENUM("pending", "ready", "in_progress", "complete", name="step_status_enum",       create_type=True)

    for e in (resource_type_enum, sched_priority_enum, sched_shift_enum,
              sched_job_stat_enum, step_type_enum, step_status_enum):
        e.create(op.get_bind(), checkfirst=True)

    # ── sched_resources ──────────────────────────────────────────────────────
    op.create_table(
        "sched_resources",
        sa.Column("id",          sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("tenant_id",   sa.Integer(),     sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",        sa.String(150),   nullable=False),
        sa.Column("type",        postgresql.ENUM("machine", "helper", name="resource_type_enum", create_type=False), nullable=False),
        sa.Column("shift_start", sa.Time(),        nullable=False, server_default="08:00:00"),
        sa.Column("shift_end",   sa.Time(),        nullable=False, server_default="16:00:00"),
        sa.Column("created_at",  sa.DateTime(),    server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_sched_resource_tenant_name"),
    )
    op.create_index("ix_sched_resources_tenant_id", "sched_resources", ["tenant_id"])

    # ── sched_jobs ────────────────────────────────────────────────────────────
    op.create_table(
        "sched_jobs",
        sa.Column("id",              sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column("tenant_id",       sa.Integer(),  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",            sa.String(200), nullable=False),
        sa.Column("priority",        postgresql.ENUM("critical", "urgent", "low", name="sched_job_priority_enum", create_type=False), nullable=False, server_default="low"),
        sa.Column("expected_profit", sa.Float(),    nullable=True),
        sa.Column("deadline",        sa.DateTime(), nullable=False),
        sa.Column("shift",           postgresql.ENUM("morning", "evening", name="sched_job_shift_enum", create_type=False), nullable=False, server_default="morning"),
        sa.Column("lock_status",     sa.Boolean(),  nullable=False, server_default="false"),
        sa.Column("status",          postgresql.ENUM("pending", "scheduled", "in_progress", "complete", name="sched_job_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("created_at",      sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at",      sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_sched_jobs_tenant_id", "sched_jobs", ["tenant_id"])

    # ── sched_steps ───────────────────────────────────────────────────────────
    op.create_table(
        "sched_steps",
        sa.Column("id",                 sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id",             sa.Integer(), sa.ForeignKey("sched_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_order",     sa.Integer(), nullable=False),
        sa.Column("step_type",          postgresql.ENUM("regular", "setup", name="step_type_enum", create_type=False), nullable=False, server_default="regular"),
        sa.Column("duration_minutes",   sa.Integer(), nullable=False),
        sa.Column("status",             postgresql.ENUM("pending", "ready", "in_progress", "complete", name="step_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("reserve_machine_id", sa.Integer(), sa.ForeignKey("sched_resources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at",         sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at",         sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("job_id", "sequence_order", name="uq_sched_step_job_seq"),
    )
    op.create_index("ix_sched_steps_job_id", "sched_steps", ["job_id"])

    # ── sched_step_machines ───────────────────────────────────────────────────
    op.create_table(
        "sched_step_machines",
        sa.Column("id",          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("step_id",     sa.Integer(), sa.ForeignKey("sched_steps.id",    ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("sched_resources.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("step_id", "resource_id", name="uq_step_machine"),
    )

    # ── sched_step_helpers ────────────────────────────────────────────────────
    op.create_table(
        "sched_step_helpers",
        sa.Column("id",          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("step_id",     sa.Integer(), sa.ForeignKey("sched_steps.id",    ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("sched_resources.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("step_id", "resource_id", name="uq_step_helper"),
    )


def downgrade() -> None:
    op.drop_table("sched_step_helpers")
    op.drop_table("sched_step_machines")
    op.drop_table("sched_steps")
    op.drop_table("sched_jobs")
    op.drop_table("sched_resources")

    for name in (
        "step_status_enum", "step_type_enum", "sched_job_status_enum",
        "sched_job_shift_enum", "sched_job_priority_enum", "resource_type_enum",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name}")
