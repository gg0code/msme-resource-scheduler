"""
```python
"""
═══════════════════════════════════════════════════════════════════════════════
ALEMBIC DATABASE MIGRATION: Add Job Type and Quantity Fields to Jobs Table
═══════════════════════════════════════════════════════════════════════════════

FILE PURPOSE

This is an Alembic database migration file that adds two new columns to the 
existing 'jobs' table: 'job_type' (string) and 'quantity' (float). This 
migration was introduced in v4-dev branch as revision 015 and serves as a 
prerequisite for the v3.9.8 material estimate endpoint feature. It sits in 
the database migration chain at position 015, building upon the previous 
014_schedule_entries migration. These new fields enable the system to track 
what type of manufacturing job is being performed and how many units are 
being produced, which is essential for material cost calculations and 
inventory planning in the ZetaOps Copilot manufacturing scheduling system.

WHAT THIS FILE DOES — step by step

1. Defines Alembic migration metadata including revision ID '015', previous 
   revision '014_schedule_entries', and creation date
2. Imports required Alembic and SQLAlchemy modules for database schema operations
3. Implements upgrade() function that adds two new nullable columns to the jobs table
4. Implements downgrade() function that removes the same two columns if migration 
   needs to be rolled back
5. Sets up proper migration chain linkage to ensure this migration runs after 
   014_schedule_entries

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Executes the forward migration by adding job_type and quantity 
               columns to the jobs table. This function is automatically called 
               by Alembic when running "alembic upgrade" commands to move the 
               database schema forward.
Parameters   : None (Alembic migration functions are parameterless)
Returns      : None (void function that performs database schema changes)
Calls        : op.add_column() from Alembic operations module
DB/API       : Directly modifies PostgreSQL database schema by adding columns 
               to the jobs table
Side effects : Permanently adds two new columns to jobs table, affecting all 
               existing and future job records

Name         : downgrade  
Type         : function
Purpose      : Executes the reverse migration by removing job_type and quantity 
               columns from the jobs table. This function is automatically called 
               by Alembic when running "alembic downgrade" commands to roll back 
               the database schema to the previous state.
Parameters   : None (Alembic migration functions are parameterless)
Returns      : None (void function that performs database schema changes)
Calls        : op.drop_column() from Alembic operations module
DB/API       : Directly modifies PostgreSQL database schema by removing columns 
               from the jobs table
Side effects : Permanently removes two columns from jobs table, causing data 
               loss if those columns contain any values

WHO CALLS THIS FILE

This file is not directly imported or called by other Python files. Instead, 
it is executed by the Alembic migration system when database administrators 
or deployment scripts run migration commands like "alembic upgrade head" or 
"alembic upgrade 015". The Alembic system automatically discovers and executes 
this migration based on the revision chain defined in the alembic/versions/ 
directory structure.

IMPORTS EXPLAINED

from alembic import op: Imports the Alembic operations module which provides 
database schema manipulation functions like add_column and drop_column that 
are used to modify table structure during migrations.

import sqlalchemy as sa: Imports SQLAlchemy core module to access column type 
definitions like sa.String(100) and sa.Float() that are needed to specify the 
data types and constraints for the new columns being added to the database.

INTERN NOTES

• Easiest thing to break without realising: Running this migration on a 
  production database with existing job records - the new columns will be 
  NULL for all existing jobs, so any code expecting these fields to have 
  values will fail until jobs are updated with proper job_type and quantity data

• Non-obvious design decision and why: Both new columns are nullable=True rather 
  than having default values or being required, because existing jobs in the 
  database cannot be automatically assigned meaningful job types or quantities 
  - this data must be populated by business users after the migration runs

• Most common mistake when editing: Changing the revision ID or down_revision 
  without understanding the migration chain - this will break the sequential 
  migration system and prevent proper database upgrades/downgrades from working

• Which design principle this file implements: This file supports design 
  principle #2 (tenant scoping) by adding fields to the jobs table which 
  already has tenant_id, ensuring the new job_type and quantity fields will 
  be properly tenant-scoped through the existing jobs table structure

• What to check if this file behaves unexpectedly: Verify that revision '014' 
  exists and has been applied successfully, check that the jobs table exists 
  in the target database, and ensure no other processes are modifying the jobs 
  table schema during migration execution

• Database migration safety: Always backup production databases before running 
  this migration, and be aware that the downgrade() function will permanently 
  delete any job_type and quantity data that has been entered after the 
  migration was applied
"""
```
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '015'
down_revision = '014_schedule_entries'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('job_type', sa.String(100), nullable=True))
    op.add_column('jobs', sa.Column('quantity', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('jobs', 'quantity')
    op.drop_column('jobs', 'job_type')
