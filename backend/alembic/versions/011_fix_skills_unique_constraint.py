"""011_fix_skills_unique_constraint

Revision ID: 011
Revises: 010
Create Date: 2026-03-09

Skills name uniqueness should be per-tenant, not global.
Drops the global UNIQUE(name) constraint and replaces with UNIQUE(tenant_id, name).
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
