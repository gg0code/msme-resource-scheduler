"""
FILE PURPOSE
This is an Alembic database migration file that adds the 'plan' column to the 'tenants' table in the PostgreSQL database. This migration was introduced in v4-dev to support subscription plan tracking (free/paid tiers) for tenant billing and feature restrictions. It sits in the database migration chain as revision 005, building on revision 004, and is executed by Alembic when upgrading the database schema to enable plan-based feature gating throughout the application.

WHAT THIS FILE DOES — step by step
1. Defines migration metadata (revision ID "005", depends on "004", created 2025-01-01)
2. Imports Alembic operations module and SQLAlchemy types for database schema changes
3. Imports SQLAlchemy Inspector for runtime database introspection
4. Defines helper function _column_exists() to check if a column already exists in a table
5. Defines upgrade() function that conditionally adds the 'plan' column to 'tenants' table
6. Sets up the new column as String(20), not-null, with default value "free"
7. Defines downgrade() function that removes the 'plan' column if migration is rolled back

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _column_exists
Type         : function
Purpose      : Helper function that inspects the current database schema to determine if a specific column already exists in a given table. This prevents migration errors if the column was already added manually or by a previous migration attempt.
Parameters   : table (str) - name of the database table to inspect, column (str) - name of the column to check for
Returns      : bool - True if the column exists in the table, False otherwise
Calls        : op.get_bind() from Alembic, Inspector.from_engine() from SQLAlchemy, inspector.get_columns() method
DB/API       : Queries the database metadata/information schema to get column information for the specified table
Side effects : None - this is a read-only database introspection operation

Name         : upgrade
Type         : function
Purpose      : The forward migration function that adds the 'plan' column to the tenants table. Only executes the column addition if the column doesn't already exist, making this migration idempotent and safe to run multiple times.
Parameters   : None
Returns      : None
Calls        : _column_exists() helper function, op.add_column() from Alembic
DB/API       : Executes ALTER TABLE statement to add the 'plan' column with String(20) type, NOT NULL constraint, and 'free' as default value
Side effects : Modifies the database schema by adding a new column to the 'tenants' table, setting all existing tenant records to 'free' plan

Name         : downgrade
Type         : function
Purpose      : The reverse migration function that removes the 'plan' column from the tenants table. This allows rolling back the migration if needed, though this will permanently delete all plan data for existing tenants.
Parameters   : None
Returns      : None
Calls        : op.drop_column() from Alembic
DB/API       : Executes ALTER TABLE statement to drop the 'plan' column from 'tenants' table
Side effects : Permanently removes the 'plan' column and all its data from the database

WHO CALLS THIS FILE
This file is called by:
- Alembic migration system when running 'alembic upgrade' command from backend/alembic/
- Database deployment scripts that execute pending migrations
- Docker containers during startup migration checks
- CI/CD pipeline database setup processes

IMPORTS EXPLAINED
- from alembic import op: Provides Alembic operations like add_column, drop_column, and get_bind for database schema modifications
- import sqlalchemy as sa: Imports SQLAlchemy core types like sa.Column and sa.String needed to define the new column schema
- from sqlalchemy.engine.reflection import Inspector: Imports the Inspector class which allows runtime introspection of database schema to check existing columns

INTERN NOTES
- Easiest thing to break: Running this migration on a database where the column already exists without the _column_exists() check would cause a fatal error and block all future migrations
- Non-obvious design decision: The migration uses server_default="free" instead of nullable=True because all existing tenants need a plan value immediately for plan_limits.py to work correctly
- Most common mistake: Forgetting to update backend/app/models/tenant.py to add the plan field to the SQLAlchemy model after running this migration
- This file implements design principle #8 (Feature flags gate all optional features) by adding the database foundation for plan-based feature restrictions
- What to check if behaving unexpectedly: Verify the migration ran successfully with 'alembic current', check that existing tenant records have plan='free', and ensure the column is NOT NULL
- Since this is v4-dev: This migration will need to be preserved when merging v5-whatsapp features, as both versions depend on tenant plan tracking for billing
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade():
    if not _column_exists("tenants", "plan"):
        op.add_column(
            "tenants",
            sa.Column(
                "plan",
                sa.String(20),
                nullable=False,
                server_default="free",
            ),
        )


def downgrade():
    op.drop_column("tenants", "plan")
