"""
```python
"""
FILE PURPOSE
This file is an Alembic database migration script (revision 012) that adds customer relationship 
management (CRM) and business tracking fields to the existing 'jobs' table. It was introduced 
as part of the J1.2 feature release in the v4-dev branch to extend job records beyond just 
production scheduling into customer delivery tracking, invoicing, and payment management. This 
migration sits in the backend database layer and is part of the linear chain of 18 migrations 
that transform the database schema from initial setup to the current production state.

WHAT THIS FILE DOES — step by step
1. Defines migration metadata (revision ID '012', previous revision '011', no branching)
2. Imports required Alembic operation tools and SQLAlchemy column type definitions
3. Implements upgrade() function that adds 7 new columns to the 'jobs' table for customer management
4. Implements downgrade() function that removes all 7 columns in reverse order for rollback capability
5. Sets up nullable columns with appropriate data types for delivery dates, invoicing, and payment tracking
6. Establishes 'Unpaid' as the default payment status for backward compatibility with existing jobs

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Applies the forward migration by adding 7 new CRM-related columns to the jobs table. 
               This extends job records to track customer delivery deadlines, invoice information, 
               payment status and amounts, and actual production hours worked.
Parameters   : None (follows Alembic migration function signature)
Returns      : None (executes database schema changes directly)
Calls        : op.add_column() from Alembic operations module
DB/API       : Executes 7 ALTER TABLE ADD COLUMN statements against the PostgreSQL jobs table
Side effects : Permanently modifies the jobs table schema, adds columns that will be populated 
               by future job creation and management operations

Name         : downgrade
Type         : function  
Purpose      : Applies the reverse migration by removing all 7 CRM columns added by upgrade(). 
               This allows rolling back to the previous schema state if the migration needs to 
               be undone due to issues or deployment rollbacks.
Parameters   : None (follows Alembic migration function signature)
Returns      : None (executes database schema changes directly)
Calls        : op.drop_column() from Alembic operations module
DB/API       : Executes 7 ALTER TABLE DROP COLUMN statements against the PostgreSQL jobs table
Side effects : Permanently removes columns and all data stored in them, cannot be undone without 
               data loss

WHO CALLS THIS FILE
- backend/alembic/env.py (Alembic migration environment automatically discovers and runs this migration)
- Database deployment scripts that execute `alembic upgrade` commands
- Rollback procedures that execute `alembic downgrade` commands
- No application code directly imports this file - it's executed only by Alembic migration system

IMPORTS EXPLAINED
- from alembic import op: Provides the op object with database operation functions like add_column() and drop_column() needed to modify table schemas
- import sqlalchemy as sa: Provides SQLAlchemy column type definitions (Date, String, Float) and column properties (nullable, server_default) for defining the new database columns

INTERN NOTES
- Easiest thing to break without realising: Running this migration on a production database with millions of jobs will lock the table during ALTER operations, potentially causing downtime
- Non-obvious design decision and why: payment_status defaults to 'Unpaid' with server_default so existing jobs don't have NULL payment status, maintaining data consistency for business logic
- Most common mistake when editing: Adding columns in upgrade() but forgetting to add corresponding drop_column() calls in downgrade(), or getting the order wrong in downgrade()
- Which design principle this implements: Principle #2 (tenant scoping) - while this migration doesn't add tenant_id, it extends the jobs table which already has tenant_id isolation
- What to check if this file behaves unexpectedly: Verify migration 011 completed successfully, check PostgreSQL logs for constraint violations, ensure no applications are writing to jobs table during migration
- Migration safety: This is a schema-only change with all nullable columns, so it's safe to run on production, but coordinate with operations team for maintenance windows on large datasets
"""
```
"""

from alembic import op
import sqlalchemy as sa

revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('delivery_date',  sa.Date(),         nullable=True))
    op.add_column('jobs', sa.Column('invoice_number', sa.String(50),     nullable=True))
    op.add_column('jobs', sa.Column('invoice_date',   sa.Date(),         nullable=True))
    op.add_column('jobs', sa.Column('payment_status', sa.String(20),     nullable=True, server_default='Unpaid'))
    op.add_column('jobs', sa.Column('payment_amount', sa.Float(),        nullable=True))
    op.add_column('jobs', sa.Column('payment_date',   sa.Date(),         nullable=True))
    op.add_column('jobs', sa.Column('actual_hours',   sa.Float(),        nullable=True))


def downgrade() -> None:
    op.drop_column('jobs', 'actual_hours')
    op.drop_column('jobs', 'payment_date')
    op.drop_column('jobs', 'payment_amount')
    op.drop_column('jobs', 'payment_status')
    op.drop_column('jobs', 'invoice_date')
    op.drop_column('jobs', 'invoice_number')
    op.drop_column('jobs', 'delivery_date')
