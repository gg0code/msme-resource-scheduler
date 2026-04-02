"""add tenant_id stub to all tables

Revision ID: 003_tenant_stub
Revises: 002_cost_timer
Create Date: 2026-03-05

Adds a nullable tenant_id INTEGER column to every core table.
NOT enforced yet — all queries still return all rows (single-tenant mode).
When V1.1 auth is built, this becomes a FK to a tenants table and
row-level filtering is added to every router dependency.
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
