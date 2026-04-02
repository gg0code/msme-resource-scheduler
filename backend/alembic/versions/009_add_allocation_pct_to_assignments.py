"""
```python
"""
FILE PURPOSE
This is an Alembic database migration file that adds partial resource allocation support
to the ZetaOps Copilot scheduling system. Introduced in v4-dev branch as migration 009,
this file extends the job_assignments table to track what percentage of an employee's or
machine's capacity is allocated to each job assignment. This sits in the database migration
chain at position 009 of 018 total migrations, enabling more granular resource scheduling
where workers and machines can be partially assigned to multiple jobs simultaneously.

WHAT THIS FILE DOES — step by step
1. Defines Alembic migration metadata (revision 009, depends on 008)
2. Imports required Alembic and SQLAlchemy modules for schema changes
3. Provides upgrade() function that adds allocation_pct column to job_assignments table
4. Sets the new column as INTEGER type, nullable, with server default of 100 (full allocation)
5. Provides downgrade() function that removes the allocation_pct column if rollback needed
6. Enables the scheduler engine to track partial resource assignments (e.g., 50% of worker's time)

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Applies the forward migration by adding the allocation_pct column to the
               job_assignments table. This column represents what percentage (0-100) of
               an employee's or machine's capacity is allocated to this specific job
               assignment, enabling partial resource allocation in the scheduling engine.
Parameters   : None
Returns      : None
Calls        : op.add_column() from Alembic operations, sa.Column() from SQLAlchemy
DB/API       : Executes ALTER TABLE job_assignments ADD COLUMN allocation_pct INTEGER DEFAULT 100
Side effects : Permanently modifies database schema, affects all existing job_assignments
               rows by setting their allocation_pct to 100 (backward compatibility)

Name         : downgrade
Type         : function  
Purpose      : Reverses the migration by removing the allocation_pct column from
               job_assignments table. Used when rolling back to migration 008 or earlier.
               This permanently destroys all allocation percentage data that was stored.
Parameters   : None
Returns      : None
Calls        : op.drop_column() from Alembic operations
DB/API       : Executes ALTER TABLE job_assignments DROP COLUMN allocation_pct
Side effects : Permanently removes allocation_pct column and all its data, makes
               job_assignments revert to binary (fully assigned or not assigned) model

WHO CALLS THIS FILE
- Alembic migration runner when executing `alembic upgrade` commands
- Database initialization scripts that apply all migrations to new installations  
- Rollback operations when executing `alembic downgrade` to revert schema changes
- No application code directly imports this file (it's migration infrastructure only)

IMPORTS EXPLAINED
- from alembic import op: Provides database operation functions like add_column() and 
  drop_column() for modifying table schema during migrations
- import sqlalchemy as sa: Provides column type definitions (sa.Integer()) and column
  configuration options like nullable and server_default for the new database column

INTERN NOTES
- Easiest thing to break: Running this migration on a database that already has allocation_pct
  column will fail with "column already exists" error, check current schema first
- Non-obvious design decision: Default value is 100 (full allocation) not 0, because existing
  job assignments should remain at full capacity for backward compatibility with v3.x behavior
- Most common mistake: Forgetting that downgrade() destroys data permanently, always backup
  allocation percentages before rolling back this migration in production environments
- Design principle #6: This migration supports the new Job/JobStep resource model by enabling
  fractional resource allocation instead of binary assigned/unassigned states
- What to check if unexpected behavior: Verify allocation_pct values sum to reasonable totals
  per employee/machine, and confirm scheduler engine respects these percentages in calculations
- Migration chain dependency: This must run after 008 (job_assignments table creation) and
  before any migrations that reference allocation_pct column in queries or constraints
"""
```
"""

from alembic import op
import sqlalchemy as sa

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('job_assignments', sa.Column('allocation_pct', sa.Integer(), nullable=True, server_default='100'))


def downgrade() -> None:
    op.drop_column('job_assignments', 'allocation_pct')
