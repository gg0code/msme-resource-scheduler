"""
```python
"""
FILE PURPOSE
This is an Alembic database migration file that creates the foundational database tables for the step-based scheduling engine in ZetaOps Copilot. It was introduced in v4.0 to replace the legacy SchedJob-based system with a more granular Job/JobStep architecture. This migration sits in the backend database layer and defines the core data structures that the scheduler engine (backend/app/scheduler/engine.py) operates on. It creates five interconnected tables that model manufacturing jobs as sequences of steps, each requiring specific machines and helpers.

WHAT THIS FILE DOES — step by step
1. Defines revision metadata linking this migration to "012" in the single-chain migration sequence
2. Creates six PostgreSQL ENUM types for standardized values (resource types, priorities, shifts, statuses)
3. Creates the sched_resources table to store machines and helpers with their working shifts
4. Creates the sched_jobs table to store high-level job information with priorities and deadlines
5. Creates the sched_steps table to store individual manufacturing steps within jobs
6. Creates the sched_step_machines junction table to link steps with required machines
7. Creates the sched_step_helpers junction table to link steps with required human helpers
8. Adds appropriate indexes on tenant_id and foreign key columns for query performance
9. Defines the downgrade() function to completely reverse all table and enum creations

KEY FUNCTIONS / CLASSES / COMPONENTS
Name         : upgrade
Type         : function
Purpose      : Executes the forward migration by creating all scheduling-related database tables and enums. This function runs when the database is upgraded to migration 013 and establishes the core data structure for the step-based scheduling system.
Parameters   : None
Returns      : None (void function that performs database DDL operations)
Calls        : op.create_table(), op.create_index(), postgresql.ENUM.create() from Alembic
DB/API       : Creates 5 tables (sched_resources, sched_jobs, sched_steps, sched_step_machines, sched_step_helpers) and 6 ENUM types in PostgreSQL
Side effects : Permanently modifies the database schema by adding tables that the scheduling engine depends on

Name         : downgrade
Type         : function
Purpose      : Executes the reverse migration by dropping all tables and enums created in upgrade(). This function runs when rolling back from migration 013 and completely removes the step-based scheduling infrastructure from the database.
Parameters   : None
Returns      : None (void function that performs database DDL operations)
Calls        : op.drop_table(), op.execute() from Alembic
DB/API       : Drops 5 tables and 6 ENUM types from PostgreSQL in reverse dependency order
Side effects : Permanently removes all scheduling-related tables and data from the database

WHO CALLS THIS FILE
- backend/alembic/env.py (Alembic environment configuration that runs migrations)
- Alembic CLI commands: `alembic upgrade head`, `alembic upgrade 013`, `alembic downgrade 012`
- Deployment scripts that run database migrations in production and staging environments

IMPORTS EXPLAINED
- alembic: Core Alembic library providing the `op` object for database operations during migrations
- sqlalchemy as sa: SQLAlchemy core library providing Column, Integer, String, DateTime and other database type definitions
- sqlalchemy.dialects.postgresql: PostgreSQL-specific SQLAlchemy extensions, specifically the ENUM type for creating custom enum types in PostgreSQL

INTERN NOTES
- Easiest thing to break: Changing enum values or table names after this migration runs - existing data will be incompatible and the migration chain will break
- Non-obvious design decision: sched_steps has both reserve_machine_id (optional pre-assignment) and sched_step_machines (required machines list) to support both automated scheduling and manual machine reservations
- Most common mistake: Forgetting that downgrade() must drop tables in reverse dependency order (junction tables first, then main tables, then enums) or PostgreSQL will throw foreign key constraint errors
- Design principle #6: This migration creates the new Job/JobStep tables that replaced legacy SchedJob tables, ensuring the scheduler reads from the correct data structure
- What to check if behaving unexpectedly: Verify this migration actually ran with `alembic current`, check that all 6 ENUM types were created in PostgreSQL, and confirm foreign key constraints exist between tables
- Migration chain dependency: This is migration 013 in the single chain - migrations 014-018 may depend on these tables, so rolling back requires checking if later migrations reference these structures
"""
```
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
