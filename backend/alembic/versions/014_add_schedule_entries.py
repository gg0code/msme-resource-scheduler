"""
```python
"""
ZetaOps Copilot - Schedule Entries Database Migration
═══════════════════════════════════════════════════════════════════════════════

FILE PURPOSE
This is Alembic database migration 014 for the ZetaOps Copilot project, running on the v4-dev branch. 
It creates the `schedule_entries` table which serves as persistent storage for the scheduler engine's 
output results. This migration was introduced to bridge the gap between the pure Python scheduling 
engine (which computes in-memory) and the database layer (which needs to persist and query scheduled 
assignments). The table stores the final computed schedule with machine and employee assignments for 
each job step, allowing the frontend to display scheduled work and enabling the system to track 
execution progress over time.

WHAT THIS FILE DOES — step by step
1. Defines Alembic migration metadata with revision "014_schedule_entries" and previous revision "013_scheduling_tables"
2. Creates the `schedule_entries` table with 8 columns covering tenant scoping, job/step references, resource assignments, and timing
3. Sets up PostgreSQL array columns for storing multiple assigned machine IDs and helper (employee) IDs per schedule entry
4. Adds database indexes on `tenant_id` and `job_id` columns for efficient querying and tenant isolation
5. Provides a downgrade function that cleanly removes the indexes and table if rollback is needed

KEY FUNCTIONS / CLASSES / COMPONENTS

upgrade
Name         : upgrade
Type         : function
Purpose      : Creates the schedule_entries table and its indexes during forward migration. This table 
               will store the persistent results when the scheduling engine computes job assignments. 
               Each row represents one scheduled job step with its assigned resources and time window.
Parameters   : None (standard Alembic upgrade signature)
Returns      : None (migration side effects only)
Calls        : op.create_table(), op.create_index() from Alembic operations
DB/API       : Creates schedule_entries table, ix_schedule_entries_tenant_id index, ix_schedule_entries_job_id index
Side effects : Modifies database schema by adding new table and indexes

downgrade
Name         : downgrade
Type         : function
Purpose      : Removes the schedule_entries table and its indexes during backward migration. This provides 
               a clean rollback path if the migration needs to be undone. Follows proper cleanup order 
               by dropping indexes before dropping the table.
Parameters   : None (standard Alembic downgrade signature)
Returns      : None (migration side effects only)
Calls        : op.drop_index(), op.drop_table() from Alembic operations
DB/API       : Drops ix_schedule_entries_job_id index, ix_schedule_entries_tenant_id index, schedule_entries table
Side effects : Removes database schema elements (table and indexes)

WHO CALLS THIS FILE
- backend/alembic/env.py (when running `alembic upgrade` or `alembic downgrade` commands)
- Deployment scripts that execute database migrations during application updates
- Developer commands during local database setup and testing

IMPORTS EXPLAINED
- `from alembic import op`: Provides Alembic operation functions like create_table, create_index, drop_table for schema changes
- `import sqlalchemy as sa`: Imports SQLAlchemy core for defining column types, constraints, and server defaults in the migration
- `from sqlalchemy.dialects import postgresql`: Imports PostgreSQL-specific data types like ARRAY for storing multiple IDs per row

INTERN NOTES
- Easiest thing to break: Forgetting tenant_id column or index - this would violate design principle #2 about tenant scoping and create security vulnerabilities
- Non-obvious design decision: Uses PostgreSQL ARRAY columns instead of separate junction tables because each schedule entry needs exactly one set of assignments, and arrays are more performant for this read-heavy use case
- Most common mistake: Running this migration without ensuring the previous migration 013_scheduling_tables completed successfully, which could leave the database in an inconsistent state
- Design principle implemented: #2 (Tenant scoping) - includes tenant_id column and index to ensure all schedule data is properly isolated between tenants
- What to check if unexpected behavior: Verify the migration chain is intact (013 → 014), check that PostgreSQL supports ARRAY columns, and confirm the indexes were created for query performance
- v4-dev specific: This migration is part of the stable production pipeline and must maintain backward compatibility - any changes require careful testing before merging to master
"""
```
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014_schedule_entries"
down_revision = "013_scheduling_tables"
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
