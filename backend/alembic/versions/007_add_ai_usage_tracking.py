"""007_add_ai_usage_tracking

Revision ID: 007
Revises: 006
Create Date: 2026-03-07
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
