"""
```python
"""
FILE PURPOSE
This is Alembic migration 016 that adds the industry_type column to the tenants table in the PostgreSQL database. It was introduced in v4-dev to support multi-industry customization of the ZetaOps Copilot scheduling interface. This migration sits in the database schema layer and is part of the sequential migration chain (revises 015, revised by 017). The industry_type field enables tenant-specific UI customization and feature sets based on the manufacturing vertical they selected during registration.

WHAT THIS FILE DOES — step by step
1. Defines Alembic migration metadata (revision 016, down_revision 015, no branch labels or dependencies)
2. Imports required Alembic and SQLAlchemy modules for database schema operations
3. Implements upgrade() function that adds industry_type column to tenants table with String(50) type, nullable=True, and server_default='printing'
4. Implements downgrade() function that removes the industry_type column from tenants table to reverse the migration
5. Sets up the migration chain linkage to migration 015 and prepares for migration 017

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Applies the forward migration by adding the industry_type column to the tenants table. This column stores which manufacturing vertical profile the tenant selected during registration (printing, manufacturing, fabrication, chemical, or field_service). The column is nullable with a default value of 'printing' to handle existing tenants that registered before this feature existed.
Parameters   : None (follows Alembic migration function signature)
Returns      : None (void function that performs database schema modification)
Calls        : op.add_column() from Alembic operations, sa.Column() and sa.String() from SQLAlchemy
DB/API       : Executes ALTER TABLE ADD COLUMN SQL statement on the tenants table in PostgreSQL
Side effects : Permanently modifies the database schema by adding a new column, affects all existing and future tenant records

Name         : downgrade
Type         : function
Purpose      : Reverses the migration by removing the industry_type column from the tenants table. This function is called when rolling back migrations and ensures the database can return to the exact state it was in before migration 016 was applied. Critical for deployment rollback scenarios.
Parameters   : None (follows Alembic migration function signature)
Returns      : None (void function that performs database schema modification)
Calls        : op.drop_column() from Alembic operations
DB/API       : Executes ALTER TABLE DROP COLUMN SQL statement on the tenants table in PostgreSQL
Side effects : Permanently removes the industry_type column and all data stored in it, irreversibly loses industry type information for all tenants

WHO CALLS THIS FILE
- backend/alembic/env.py when running `alembic upgrade` or `alembic downgrade` commands
- Alembic's migration runner during application deployment when database schema updates are applied
- Development environment setup scripts that run migrations to prepare local databases
- CI/CD pipelines that automatically apply database migrations during deployment processes

IMPORTS EXPLAINED
- from alembic import op: Provides the `op` object which contains all Alembic database operation functions like add_column, drop_column, create_table, etc. Required for any schema modification in migrations.
- import sqlalchemy as sa: Provides SQLAlchemy's data types (String, Integer, Boolean, etc.) and column definition functions needed to define the new column's structure, constraints, and default values.

INTERN NOTES
- Easiest thing to break without realising: Changing the server_default value after this migration has been applied to production - existing tenants will keep 'printing' but new ones will get the new default, creating data inconsistency
- Non-obvious design decision and why: The column is nullable=True even with a server_default because existing tenants need to be handled gracefully, and the application code in backend/app/models/tenant.py handles the null case by defaulting to 'printing'
- Most common mistake when editing: Modifying this migration file after it has been applied to any environment - migrations are immutable once deployed and changes require creating a new migration file instead
- Which design principle this file implements: This migration supports principle #8 (feature flags gate all optional features) by providing the database foundation for industry-specific feature customization
- What to check if this file behaves unexpectedly: Verify the migration chain is intact by running `alembic current` and `alembic history`, check that no other migration is trying to modify the same column, and ensure PostgreSQL has sufficient permissions for ALTER TABLE operations
- If v5-whatsapp only: N/A - this migration exists in v4-dev and is part of the core multi-tenant industry customization feature that both v4 and v5 branches depend on
"""
```
"""

from alembic import op
import sqlalchemy as sa

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'tenants',
        sa.Column(
            'industry_type',
            sa.String(50),
            nullable=True,
            server_default='printing',
        )
    )


def downgrade() -> None:
    op.drop_column('tenants', 'industry_type')
