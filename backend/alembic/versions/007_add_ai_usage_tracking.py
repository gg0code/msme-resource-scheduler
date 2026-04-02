"""
```python
"""
FILE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is Alembic database migration 007, introduced in v4-dev to add AI usage 
tracking columns to the tenants table. It enables per-tenant rate limiting of 
AI Copilot queries by tracking daily usage counts, token consumption, and 
configurable limits. This migration sits in the backend database layer and 
is part of the sequential migration chain that runs when deploying the 
application or running `alembic upgrade head`.

WHAT THIS FILE DOES — step by step
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Defines Alembic migration metadata (revision ID, parent revision, timestamps)
2. Implements upgrade() function that adds four new columns to the tenants table:
   - ai_queries_today: integer counter for daily AI queries (defaults to 0)
   - ai_queries_date: date field to track which day the counter applies to
   - ai_queries_limit: configurable limit per tenant (defaults to 50)
   - ai_tokens_today: integer counter for daily token consumption (defaults to 0)
3. Implements downgrade() function that removes all four columns in reverse order
4. Uses server_default values to ensure existing tenant records get safe defaults

KEY FUNCTIONS / CLASSES / COMPONENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name         : upgrade
Type         : function
Purpose      : Adds AI usage tracking columns to the tenants table. This enables
               the application to track and limit AI query usage per tenant on a
               daily basis. Uses server defaults to ensure existing tenants get
               reasonable initial values without breaking the application.
Parameters   : None (standard Alembic migration signature)
Returns      : None (performs database schema changes as side effect)
Calls        : op.add_column() from Alembic operations module
DB/API       : Executes ALTER TABLE statements on the tenants table in PostgreSQL
Side effects : Modifies database schema by adding four new columns with constraints

Name         : downgrade  
Type         : function
Purpose      : Removes the AI usage tracking columns added by upgrade(). This
               provides a rollback mechanism if the migration needs to be reversed.
               Drops columns in reverse order of creation to avoid dependency issues.
Parameters   : None (standard Alembic migration signature)
Returns      : None (performs database schema changes as side effect)
Calls        : op.drop_column() from Alembic operations module
DB/API       : Executes ALTER TABLE DROP COLUMN statements on tenants table
Side effects : Removes columns and all data they contain from the database permanently

WHO CALLS THIS FILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Alembic migration system when running `alembic upgrade` or `alembic downgrade`
- Application startup code that runs pending migrations automatically
- Deployment scripts that ensure database schema is up to date
- backend/app/models/tenant.py will reference these columns after migration runs

IMPORTS EXPLAINED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- alembic.op: Provides database operation functions like add_column and drop_column
- sqlalchemy as sa: Provides column type definitions (Integer, Date) and constraints

INTERN NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Easiest thing to break: Changing the revision ID or down_revision - this will 
  break the migration chain and prevent database upgrades from working
• Non-obvious design decision: server_default='0' ensures existing tenants get 
  safe defaults immediately, while nullable=False enforces data integrity for 
  new records without breaking existing data
• Most common mistake: Forgetting to update the Tenant model in models/tenant.py 
  to include these new columns after running this migration
• Design principle #2: These columns enable tenant-scoped AI usage tracking, 
  ensuring each tenant's AI queries are isolated and limited appropriately
• What to check if unexpected behavior: Verify migration ran successfully with 
  `alembic current`, check that Tenant model includes new columns, and confirm 
  ai_service.py is incrementing the counters properly
• The ai_queries_date field allows daily counter resets by comparing against 
  current date, enabling the "daily limit" behavior rather than lifetime limits
"""
```
"""

from alembic import op
import sqlalchemy as sa

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add AI usage tracking to tenants table
    op.add_column('tenants', sa.Column('ai_queries_today', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('tenants', sa.Column('ai_queries_date', sa.Date(), nullable=True))
    op.add_column('tenants', sa.Column('ai_queries_limit', sa.Integer(), nullable=False, server_default='50'))
    op.add_column('tenants', sa.Column('ai_tokens_today', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('tenants', 'ai_tokens_today')
    op.drop_column('tenants', 'ai_queries_limit')
    op.drop_column('tenants', 'ai_queries_date')
    op.drop_column('tenants', 'ai_queries_today')
