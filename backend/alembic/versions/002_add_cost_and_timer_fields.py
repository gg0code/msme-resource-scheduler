"""
```python
"""
FILE PURPOSE
This is an Alembic database migration file (migration #002) that adds cost tracking and 
job timer functionality to the ZetaOps Copilot scheduling system. It was introduced in 
v4-dev to enable financial calculations, time tracking, and improved job monitoring 
capabilities. This migration sits in the database schema evolution chain and modifies 
three core tables (employees, machines, jobs) to support billing, cost estimation, 
and real-time job progress tracking that the scheduling engine and frontend dashboard require.

WHAT THIS FILE DOES — step by step
1. Defines migration metadata including revision ID '002_cost_timer' and links to previous migration '46385051aa8d'
2. Imports required Alembic and SQLAlchemy modules for database schema operations
3. Implements upgrade() function that adds cost-related columns to employees table (hourly_rate, overtime_rate)
4. Adds hourly_rate column to machines table for equipment cost calculations
5. Adds extensive job tracking fields to jobs table: order_value, misc_cost, raw_materials (JSON), timer_status, actual_start_at, actual_end_at, paused_seconds, timer_log (JSON)
6. Sets appropriate server defaults for timer_status ('idle') and paused_seconds (0) to ensure data consistency
7. Implements downgrade() function that removes all added columns in reverse order for rollback capability
8. Uses batch_alter_table context managers to ensure compatibility across different database backends

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Executes the forward migration by adding all cost tracking and timer fields to the database schema. This enables the application to track financial data, job timings, and material costs that the scheduling engine needs for optimization and the frontend needs for reporting.
Parameters   : None
Returns      : None (void function that performs database schema changes)
Calls        : op.batch_alter_table() from Alembic, sa.Column() and various SQLAlchemy data types
DB/API       : Directly modifies PostgreSQL schema by adding columns to employees, machines, and jobs tables
Side effects : Permanently alters database structure, adds new columns with default values, enables new application features

Name         : downgrade  
Type         : function
Purpose      : Executes the reverse migration by removing all columns added in upgrade(). This allows rolling back the migration if issues occur or if the cost/timer features need to be disabled. Essential for maintaining database version control and deployment safety.
Parameters   : None
Returns      : None (void function that performs database schema rollback)
Calls        : op.batch_alter_table() and batch_op.drop_column() from Alembic
DB/API       : Directly modifies PostgreSQL schema by removing columns from jobs, machines, and employees tables
Side effects : Permanently removes columns and their data, disables cost/timer features, reverts schema to previous state

WHO CALLS THIS FILE
- backend/alembic/env.py (Alembic migration runner when executing 'alembic upgrade' commands)
- Alembic CLI commands executed during deployment pipelines and local development
- Database initialization scripts that run the full migration chain to head revision
- Rollback procedures that may call the downgrade() function during emergency deployments

IMPORTS EXPLAINED
- from alembic import op: Provides the 'op' object that contains all database operation functions like batch_alter_table() needed to modify schema during migrations
- import sqlalchemy as sa: Imports SQLAlchemy's column types (Float, String, DateTime, Integer, JSON) and Column constructor needed to define the new database columns being added

INTERN NOTES
- Easiest thing to break without realising: Running this migration on a production database with existing jobs data - the new timer_status and paused_seconds fields will get default values but existing jobs won't have proper timer state
- Non-obvious design decision and why: Uses batch_alter_table() instead of direct ALTER TABLE commands because it provides better compatibility across SQLite (development) and PostgreSQL (production) databases
- Most common mistake when editing: Forgetting to update the downgrade() function when adding new columns in upgrade() - this breaks rollback capability and violates migration best practices
- Which design principle this implements: Principle #2 (tenant scoping) - while this migration doesn't add tenant_id fields, it supports the cost calculation features that must be tenant-scoped in the application layer
- What to check if this file behaves unexpectedly: Verify the down_revision matches the actual previous migration ID in the database, check that column names match exactly with the SQLAlchemy models in backend/app/models/, and ensure no duplicate column names exist
- Database migration chain integrity: This is migration #002 in an 18-migration sequence leading to head=018, so breaking this migration breaks the entire chain and prevents fresh database setups
"""
```
"""

from alembic import op
import sqlalchemy as sa

revision = '002_cost_timer'
down_revision = '46385051aa8d'   # ← FIXED: now chains to the real initial schema
branch_labels = None
depends_on = None


def upgrade():
    # employees
    with op.batch_alter_table('employees') as batch_op:
        batch_op.add_column(sa.Column('hourly_rate',   sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('overtime_rate', sa.Float(), nullable=True))

    # machines
    with op.batch_alter_table('machines') as batch_op:
        batch_op.add_column(sa.Column('hourly_rate', sa.Float(), nullable=True))

    # jobs — includes order_value & misc_cost which were missing before
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.add_column(sa.Column('order_value',     sa.Float(),     nullable=True))           # ← ADDED
        batch_op.add_column(sa.Column('misc_cost',       sa.Float(),     nullable=True))           # ← ADDED
        batch_op.add_column(sa.Column('raw_materials',   sa.JSON(),      nullable=True))
        batch_op.add_column(sa.Column('timer_status',    sa.String(20),  nullable=False, server_default='idle'))
        batch_op.add_column(sa.Column('actual_start_at', sa.DateTime(),  nullable=True))
        batch_op.add_column(sa.Column('actual_end_at',   sa.DateTime(),  nullable=True))
        batch_op.add_column(sa.Column('paused_seconds',  sa.Integer(),   nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('timer_log',       sa.JSON(),      nullable=True))


def downgrade():
    with op.batch_alter_table('jobs') as batch_op:
        for col in ['order_value', 'misc_cost', 'raw_materials', 'timer_status',
                    'actual_start_at', 'actual_end_at', 'paused_seconds', 'timer_log']:
            batch_op.drop_column(col)
    with op.batch_alter_table('machines') as batch_op:
        batch_op.drop_column('hourly_rate')
    with op.batch_alter_table('employees') as batch_op:
        batch_op.drop_column('overtime_rate')
        batch_op.drop_column('hourly_rate')