"""
FILE PURPOSE
This is an Alembic database migration file (revision 006) that safely adds hourly rate and cost tracking columns to the employees, machines, and jobs tables. It was introduced in v4-dev to support cost calculation features in the ZetaOps scheduling system. The migration uses defensive programming to check if columns already exist before attempting to add them, preventing errors if the migration is run multiple times or if some columns were manually added previously. This sits in the database migration chain between revision 005 and 007, and is part of the backend's data layer evolution.

WHAT THIS FILE DOES — step by step
1. Imports Alembic operations module and SQLAlchemy for database schema changes
2. Imports Inspector from SQLAlchemy to introspect existing database schema
3. Sets up migration metadata (revision ID, parent revision, creation date)
4. Defines a helper function _column_exists() to safely check if a column already exists in a table
5. In upgrade(), checks if employees.hourly_rate column exists and adds it with default 0.0 if missing
6. Checks if employees.overtime_rate column exists and adds it with default 0.0 if missing
7. Checks if machines.hourly_rate column exists and adds it with default 0.0 if missing
8. Checks if jobs.misc_cost column exists and adds it with default 0.0 if missing
9. Defines an empty downgrade() function that intentionally does nothing for safety

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _column_exists
Type         : function
Purpose      : Helper function that safely checks whether a specific column exists in a given database table. This prevents migration errors if columns were already added manually or if the migration is run multiple times. Uses SQLAlchemy's Inspector to introspect the current database schema.
Parameters   : table (str) - name of the database table to check; column (str) - name of the column to look for
Returns      : bool - True if the column exists in the table, False if it doesn't exist
Calls        : op.get_bind() to get database connection, Inspector.from_engine() to create schema inspector, inspector.get_columns() to retrieve column metadata
DB/API       : Queries database metadata/schema information through SQLAlchemy Inspector
Side effects : None - this is a read-only introspection function

Name         : upgrade
Type         : function
Purpose      : The main migration function that adds hourly rate and cost tracking columns to multiple tables. Safely adds employees.hourly_rate, employees.overtime_rate, machines.hourly_rate, and jobs.misc_cost columns only if they don't already exist. Each column is nullable with a server default of 0.0 to ensure existing rows have valid data.
Parameters   : None
Returns      : None (void function)
Calls        : _column_exists() to check for existing columns, op.add_column() to add new columns
DB/API       : Executes ALTER TABLE statements through Alembic operations to modify database schema
Side effects : Permanently modifies database schema by adding new columns to employees, machines, and jobs tables

Name         : downgrade
Type         : function
Purpose      : The migration rollback function that would theoretically undo the changes made in upgrade(). Intentionally left empty because removing these columns could cause data loss and break the application. The comment indicates these are "additive columns" that are safe to leave in place.
Parameters   : None
Returns      : None (void function)
Calls        : Nothing - function body is empty
DB/API       : No database operations performed
Side effects : None - this is a no-op function for safety

WHO CALLS THIS FILE
- backend/alembic/env.py when running database migrations
- Alembic command line tool when executing `alembic upgrade head` or `alembic upgrade 006`
- Backend startup scripts that automatically run pending migrations
- Deployment scripts that ensure database schema is up to date

IMPORTS EXPLAINED
- `from alembic import op` - Provides the op object for executing database schema operations like adding columns, creating tables, etc.
- `import sqlalchemy as sa` - SQLAlchemy core for defining column types (sa.Column, sa.Float) and database schema elements.
- `from sqlalchemy.engine.reflection import Inspector` - Inspector class for introspecting existing database schema to safely check if columns already exist.

INTERN NOTES
- Easiest thing to break: Running this migration twice without the column existence checks would cause "column already exists" errors, which is why _column_exists() is critical
- Non-obvious design decision: The downgrade() function is intentionally empty because dropping these columns would break cost calculation features and potentially lose data
- Most common mistake: Forgetting to add server_default values when adding nullable columns, which could cause issues with existing data and ORM queries
- This implements design principle #2 (tenant scoping) by adding cost tracking fields that will be used in tenant-scoped cost calculations
- If this behaves unexpectedly: Check that the database user has ALTER TABLE permissions and verify the table names match exactly (employees, machines, jobs)
- Not v5-whatsapp specific: This migration is part of the core v4-dev branch and should merge cleanly since it only adds optional columns for cost tracking
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade():
    # employees.hourly_rate
    if not _column_exists("employees", "hourly_rate"):
        op.add_column("employees", sa.Column("hourly_rate", sa.Float(), nullable=True, server_default="0.0"))

    # employees.overtime_rate
    if not _column_exists("employees", "overtime_rate"):
        op.add_column("employees", sa.Column("overtime_rate", sa.Float(), nullable=True, server_default="0.0"))

    # machines.hourly_rate
    if not _column_exists("machines", "hourly_rate"):
        op.add_column("machines", sa.Column("hourly_rate", sa.Float(), nullable=True, server_default="0.0"))

    # jobs.misc_cost already exists in V1.0 schema — skip if present
    if not _column_exists("jobs", "misc_cost"):
        op.add_column("jobs", sa.Column("misc_cost", sa.Float(), nullable=True, server_default="0.0"))


def downgrade():
    # Only drop if they were added by this migration
    # Safe to leave — these are additive columns
    pass
