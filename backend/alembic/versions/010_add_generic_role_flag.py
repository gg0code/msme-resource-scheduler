"""
```python
"""
FILE PURPOSE
This is Alembic database migration 010 that adds a new boolean column 'is_generic_role' 
to the 'skills' table in the ZetaOps Copilot database. This migration was introduced in 
v4-dev branch to support distinguishing between specific skills (like "CNC Operator") 
and generic role categories (like "Supervisor" or "Quality Control") within the scheduling 
system's skill-based assignment logic.

WHAT THIS FILE DOES — step by step
1. Defines Alembic migration metadata (revision 010, depends on migration 009)
2. Imports required Alembic operation tools and SQLAlchemy column types
3. In upgrade(): adds 'is_generic_role' column as Boolean, non-nullable, defaulting to false
4. In downgrade(): removes the 'is_generic_role' column to revert the change
5. Uses server_default to ensure existing rows get false value without requiring data migration

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Executes the forward migration by adding the is_generic_role column to the 
               skills table. This column will allow the scheduling engine to differentiate 
               between specific technical skills and broader role categories when assigning 
               jobs to employees.
Parameters   : None
Returns      : None (void function)
Calls        : op.add_column() from Alembic operations, sa.Column() and sa.Boolean() from SQLAlchemy
DB/API       : Executes ALTER TABLE skills ADD COLUMN SQL command via Alembic
Side effects : Permanently modifies the database schema by adding a new column with default value

Name         : downgrade  
Type         : function
Purpose      : Executes the reverse migration by removing the is_generic_role column from 
               the skills table. This allows rolling back the database schema if this 
               migration needs to be reverted.
Parameters   : None
Returns      : None (void function) 
Calls        : op.drop_column() from Alembic operations
DB/API       : Executes ALTER TABLE skills DROP COLUMN SQL command via Alembic
Side effects : Permanently removes the column and all its data from the database

WHO CALLS THIS FILE
This file is executed by the Alembic migration system when running:
- `alembic upgrade` commands that include this revision
- Database initialization scripts that apply all migrations
- Deployment processes that run migrations automatically
- Manual migration runs via `alembic upgrade 010` or `alembic upgrade head`

IMPORTS EXPLAINED
- from alembic import op: Provides database operation functions like add_column and drop_column for schema changes
- import sqlalchemy as sa: Gives access to SQLAlchemy column types (Boolean) and Column constructor needed for defining the new column structure

INTERN NOTES
- Easiest thing to break: Forgetting the server_default='false' would cause existing skills records to have NULL values, violating the NOT NULL constraint and breaking queries
- Non-obvious design decision: Using server_default instead of nullable=True because the scheduling engine expects this field to always have a boolean value for logic decisions
- Most common mistake: Running this migration without ensuring the skills table exists (migration 009 should have created it) or trying to add the column twice
- Design principle #2: This maintains tenant scoping since it modifies the skills table structure that already has tenant_id filtering in the ORM models
- What to check if behaving unexpectedly: Verify migration 009 ran successfully first, check that PostgreSQL supports boolean columns, and confirm no existing 'is_generic_role' column exists
- Migration chain dependency: This is migration 010 in an 18-migration chain leading to head=018, so reverting this affects all subsequent migrations and requires careful coordination
"""
```
"""

from alembic import op
import sqlalchemy as sa

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('skills', sa.Column('is_generic_role', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('skills', 'is_generic_role')
