"""
```python
"""
ZetaOps Copilot - Skills Unique Constraint Fix Migration

FILE PURPOSE
This is Alembic database migration 011 that fixes a tenant isolation issue in the skills 
table's unique constraint. Originally, skill names were globally unique across all tenants, 
which violated design principle #2 (tenant scoping). This migration was introduced in v4-dev 
to change the constraint so that skill names are only unique within each tenant, allowing 
different tenants to have skills with the same name. This sits in the database migration 
chain at position 011 of 18 total migrations.

WHAT THIS FILE DOES — step by step
1. Defines Alembic migration metadata (revision ID, parent revision, branch info)
2. Documents the purpose: fixing skills table uniqueness from global to per-tenant
3. Provides upgrade() function that drops the old global unique constraint on 'name'
4. Creates new composite unique constraint on ['tenant_id', 'name'] columns
5. Provides downgrade() function that reverses these changes for rollback capability
6. Uses Alembic's op.drop_constraint() and op.create_unique_constraint() operations

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Executes the forward migration to fix the skills table unique constraint. 
               Drops the problematic global uniqueness on skill names and replaces it 
               with proper tenant-scoped uniqueness. This ensures different tenants can 
               have skills with identical names without database constraint violations.
Parameters   : None (Alembic migration standard)
Returns      : None (migration executes database operations directly)
Calls        : op.drop_constraint() and op.create_unique_constraint() from Alembic
DB/API       : Modifies PostgreSQL skills table constraints via Alembic DDL operations
Side effects : Permanently changes database schema, affects all future skill creation

Name         : downgrade
Type         : function
Purpose      : Executes the reverse migration to undo the constraint changes. Drops the 
               tenant-scoped unique constraint and restores the original global uniqueness 
               on skill names. This rollback function allows reverting to the previous 
               (problematic) schema state if needed during deployment issues.
Parameters   : None (Alembic migration standard)
Returns      : None (migration executes database operations directly)
Calls        : op.drop_constraint() and op.create_unique_constraint() from Alembic
DB/API       : Modifies PostgreSQL skills table constraints via Alembic DDL operations
Side effects : Reverts database schema changes, may cause constraint violations if data exists

WHO CALLS THIS FILE
- backend/alembic/env.py when running `alembic upgrade` or `alembic downgrade` commands
- Database deployment scripts that execute migration chains
- Development setup scripts that initialize the database schema to head revision
- CI/CD pipelines that apply database migrations during deployment processes

IMPORTS EXPLAINED
- alembic.op: Alembic's operations module that provides DDL (Data Definition Language) 
  functions for modifying database schema including creating/dropping constraints, 
  tables, indexes, and columns during migrations.

INTERN NOTES
- Easiest thing to break: Running this migration on a database where different tenants 
  already have skills with the same name will cause the downgrade to fail with constraint 
  violations since the old global unique constraint cannot be recreated.
- Non-obvious design decision: The constraint names ('skills_name_key' and 'uq_skills_tenant_name') 
  must match exactly what PostgreSQL generated/expects, as Alembic relies on these exact 
  names to find and modify the constraints.
- Most common mistake: Forgetting that this migration requires the skills table to already 
  have a tenant_id column (added in an earlier migration), and not checking if duplicate 
  skill names exist across tenants before running the downgrade.
- This file implements design principle #2: Tenant scoping on ALL database operations, 
  ensuring that skills are properly isolated between different tenant organizations.
- What to check if unexpected behavior: Verify the skills table structure with \d skills 
  in PostgreSQL, confirm constraint names match what's in the migration, and check if 
  any existing data violates the uniqueness rules before applying.
- N/A - This is a v4-dev migration that applies to both v4 and v5 branches as it fixes 
  a fundamental tenant isolation issue in the core data model.
"""
```
"""

from alembic import op

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('skills_name_key', 'skills', type_='unique')
    op.create_unique_constraint('uq_skills_tenant_name', 'skills', ['tenant_id', 'name'])


def downgrade() -> None:
    op.drop_constraint('uq_skills_tenant_name', 'skills', type_='unique')
    op.create_unique_constraint('skills_name_key', 'skills', ['name'])
