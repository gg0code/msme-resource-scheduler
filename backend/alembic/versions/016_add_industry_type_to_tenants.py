"""016_add_industry_type_to_tenants

Add industry_type column to tenants table.
Stores which industry profile the tenant selected during registration.

Valid values:
  printing      — PrintFlow Scheduler
  manufacturing — ShopFloor Resource Planner
  fabrication   — Fabrication Capacity Planner
  chemical      — Process Batch Scheduler
  field_service — Field Service Planner

Revision ID: 016
Revises: 015
Create Date: 2026-03-25
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
