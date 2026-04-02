"""
FILE PURPOSE
This is Alembic migration 003 that adds a nullable tenant_id INTEGER column to all core database tables in preparation for multi-tenant support. This migration was introduced in the early development of ZetaOps Copilot (formerly MSME Resource Scheduler) as a foundational step toward implementing proper tenant isolation. The migration exists in the v4-dev branch and represents a "stub" approach where the column is added but not yet enforced - all queries still return all rows regardless of tenant. This sits in the database migration layer of the architecture, specifically in the Alembic version chain at position 003, and serves as the groundwork for future tenant-scoped data access that implements design principle #2 (tenant scoping on ALL DB queries).

WHAT THIS FILE DOES — step by step
1. Defines Alembic migration metadata including revision ID '003_tenant_stub', previous migration '002_cost_timer', and creation date
2. Declares a TABLES list containing all core table names that need tenant_id columns added
3. Implements upgrade() function that iterates through each table and adds a nullable tenant_id INTEGER column
4. Implements downgrade() function that removes the tenant_id column from each table to reverse the migration
5. Uses SQLAlchemy's op.add_column() and op.drop_column() operations to modify table schemas
6. Prepares database structure for future enforcement of tenant-based row-level security

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : TABLES
Type         : module-level constant list
Purpose      : Defines the complete list of core database tables that require tenant_id columns for multi-tenant support. This includes all primary entity tables (employees, machines, jobs) and their relationship tables (employee_skills, job_assignments, etc.).
Parameters   : N/A (constant)
Returns      : N/A (constant)
Calls        : N/A
DB/API       : N/A
Side effects : None - this is just data used by the migration functions

Name         : upgrade
Type         : function
Purpose      : Alembic upgrade function that adds the tenant_id column to all tables listed in TABLES. This function runs when migrating the database forward to this revision. The columns are created as nullable INTEGER fields because existing data has no tenant assignments yet.
Parameters   : None
Returns      : None (modifies database schema as side effect)
Calls        : op.add_column() from Alembic operations, sa.Column() and sa.Integer() from SQLAlchemy
DB/API       : Executes ALTER TABLE ADD COLUMN statements on PostgreSQL database for each table in TABLES
Side effects : Permanently modifies database schema by adding tenant_id columns to 9 core tables

Name         : downgrade
Type         : function
Purpose      : Alembic downgrade function that removes the tenant_id column from all tables in TABLES. This function runs when rolling back this migration to return the database to the previous schema state. Essential for migration reversibility.
Parameters   : None
Returns      : None (modifies database schema as side effect)
Calls        : op.drop_column() from Alembic operations
DB/API       : Executes ALTER TABLE DROP COLUMN statements on PostgreSQL database for each table in TABLES
Side effects : Permanently removes tenant_id columns from database tables, destroying any tenant association data

WHO CALLS THIS FILE
- Alembic migration runner when executing `alembic upgrade` or `alembic downgrade` commands
- Database initialization scripts that run all migrations to set up fresh environments
- Deployment pipelines that automatically apply database migrations during releases
- Developer local environment setup scripts that migrate to latest schema

IMPORTS EXPLAINED
- `from alembic import op`: Imports Alembic's operation interface for executing DDL statements like adding/dropping columns during migrations.
- `import sqlalchemy as sa`: Imports SQLAlchemy's column definition classes (Column, Integer) needed to specify the schema of the new tenant_id columns being added.

INTERN NOTES
- Easiest thing to break without realising: Modifying the TABLES list without understanding that adding/removing tables here affects both upgrade and downgrade operations - forgetting to test downgrade after adding a table will cause migration rollback failures
- Non-obvious design decision and why: The tenant_id columns are created as nullable rather than required because this is a "stub" migration that prepares for multi-tenancy without breaking existing single-tenant data - enforcement comes in later migrations once a tenants table exists
- Most common mistake when editing: Adding new tables to this migration after it's already been applied in production - new tables should get tenant_id in their CREATE TABLE statements in newer migrations, not by modifying this historical migration
- Which design principle this file implements: This migration sets up the foundation for design principle #2 (tenant scoping on ALL DB queries) by ensuring every core table has the tenant_id column needed for future row-level filtering
- What to check if this file behaves unexpectedly: Verify the migration chain is intact by checking that revision '002_cost_timer' exists and that no tables in TABLES list have been renamed or dropped since this migration was created - also check PostgreSQL permissions allow ALTER TABLE operations
- If v5-whatsapp only: This migration exists in both v4-dev and v5-whatsapp branches since tenant support is foundational - when merging v5 features back to v4, this migration should already exist in v4-dev so no conflicts should occur, but verify the TABLES list matches between branches
"""

from alembic import op
import sqlalchemy as sa

revision = '003_tenant_stub'
down_revision = '002_cost_timer'
branch_labels = None
depends_on = None

TABLES = [
    'employees', 'employee_skills',
    'machines', 'machine_skill_requirements',
    'jobs', 'job_skill_requirements', 'job_assignments',
    'skills', 'availability_overrides',
]

def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column('tenant_id', sa.Integer(), nullable=True))

def downgrade():
    for table in TABLES:
        op.drop_column(table, 'tenant_id')
