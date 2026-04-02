"""
```python
"""
FILE PURPOSE
This is Alembic database migration 008 that adds advanced job scheduling fields to support 
the ZetaOps Copilot scheduling engine. It was introduced in v4-dev as part of the core 
scheduling system upgrade and sits in the database migration chain between migration 007 
and 009. This migration enables jobs to have flexible start modes, locking mechanisms, 
conflict detection, and date constraints that the scheduling engine uses to optimize 
manufacturing workflows.

WHAT THIS FILE DOES — step by step
1. Defines Alembic migration metadata (revision ID 008, previous revision 007)
2. Imports required Alembic and SQLAlchemy modules for database schema changes
3. Implements upgrade() function that adds 5 new columns to the jobs table
4. Adds start_mode column to control how jobs are scheduled (defaults to 'pick_a_date')
5. Adds is_locked boolean to prevent jobs from being rescheduled once locked
6. Adds has_conflict boolean for the scheduler to flag resource conflicts
7. Adds earliest_date and latest_date nullable columns for job date constraints
8. Adds job_id_prefix column to tenants table for custom job numbering (e.g. "ABC-106")
9. Implements downgrade() function that removes all added columns in reverse order

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Applies the database schema changes by adding new columns to jobs and tenants 
               tables. This enables the scheduling engine to handle advanced job constraints 
               and custom job numbering per tenant.
Parameters   : None (Alembic migration function signature)
Returns      : None (modifies database schema directly)
Calls        : op.add_column() from Alembic operations module
DB/API       : Executes ALTER TABLE statements on PostgreSQL database
Side effects : Permanently adds 6 new columns to database schema, sets default values

Name         : downgrade  
Type         : function
Purpose      : Reverses the migration by dropping all columns added in upgrade(). This allows 
               rolling back the database schema if the migration needs to be undone during 
               deployment issues or testing.
Parameters   : None (Alembic migration function signature)
Returns      : None (modifies database schema directly)
Calls        : op.drop_column() from Alembic operations module
DB/API       : Executes ALTER TABLE DROP COLUMN statements on PostgreSQL database
Side effects : Permanently removes 6 columns from database schema, data loss occurs

WHO CALLS THIS FILE
This file is executed by Alembic migration system when running:
- `alembic upgrade head` or `alembic upgrade 008` (calls upgrade function)
- `alembic downgrade 007` (calls downgrade function)
- Backend application startup migration checks in backend/app/main.py
- Deployment scripts that run database migrations
- Developer migration commands during local development

IMPORTS EXPLAINED
- `from alembic import op`: Provides database operation functions like add_column() and 
  drop_column() that generate the actual SQL ALTER TABLE statements
- `import sqlalchemy as sa`: Provides column type definitions (String, Boolean, Date) and 
  column configuration options like nullable and server_default values

INTERN NOTES
- Easiest thing to break: Running this migration without checking if columns already exist 
  will cause PostgreSQL constraint errors and block deployment
- Non-obvious design decision: job_id_prefix goes on tenants table (not jobs) because each 
  tenant needs one prefix for all their jobs, following tenant scoping principle
- Most common mistake: Forgetting to update the corresponding SQLAlchemy ORM models in 
  backend/app/models/ after running this migration, causing ORM/schema mismatches
- This file implements design principle #2 (tenant scoping) by adding tenant-specific 
  job prefixes and principle #6 (scheduler reads Job tables) by extending Job model
- If this behaves unexpectedly: Check Alembic revision chain with `alembic history` and 
  verify PostgreSQL column constraints match the server_default values
- This is v4-dev stable code that WhatsApp Copilot v5 builds upon - never modify column 
  names or types as it will break the scheduling engine that depends on these exact fields
"""
```
"""

from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('start_mode',   sa.String(20),  nullable=False, server_default='pick_a_date'))
    op.add_column('jobs', sa.Column('is_locked',    sa.Boolean(),   nullable=False, server_default='false'))
    op.add_column('jobs', sa.Column('has_conflict', sa.Boolean(),   nullable=False, server_default='false'))
    op.add_column('jobs', sa.Column('earliest_date', sa.Date(),     nullable=True))
    op.add_column('jobs', sa.Column('latest_date',   sa.Date(),     nullable=True))
    op.add_column('tenants', sa.Column('job_id_prefix', sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column('jobs', 'start_mode')
    op.drop_column('jobs', 'is_locked')
    op.drop_column('jobs', 'has_conflict')
    op.drop_column('jobs', 'earliest_date')
    op.drop_column('jobs', 'latest_date')
    op.drop_column('tenants', 'job_id_prefix')
