"""010_add_generic_role_flag

Revision ID: 010
Revises: 009
Create Date: 2026-03-09

Adds to skills table:
  is_generic_role  BOOLEAN  NOT NULL DEFAULT false
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
