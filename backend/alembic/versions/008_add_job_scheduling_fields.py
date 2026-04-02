"""008_add_job_scheduling_fields

Revision ID: 008
Revises: 007
Create Date: 2026-03-08

Adds to jobs table:
  start_mode     VARCHAR(20)  NOT NULL DEFAULT 'pick_a_date'
  is_locked      BOOLEAN      NOT NULL DEFAULT false
  has_conflict   BOOLEAN      NOT NULL DEFAULT false
  earliest_date  DATE         NULLABLE
  latest_date    DATE         NULLABLE

Adds to tenants table:
  job_id_prefix  VARCHAR(10)  NULLABLE   (e.g. "ABC" → jobs show as ABC-106)
"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('start_mode',   sa.String(20),  nullable=False, server_default='pick_a_date'))
    op.add_column('jobs', sa.Column('is_locked',    sa.Boolean(),   nullable=False, server_default='false'))
    op.add_column('jobs', sa.Column('has_conflict', sa.Boolean(),   nullable=False, server_default='false'))
    op.add_column('jobs', sa.Column('earliest_date', sa.Date(),     nullable=True))
    op.add_column('jobs', sa.Column('latest_date',   sa.Date(),     nullable=True))
    op.add_column('tenants', sa.Column('job_id_prefix', sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column('jobs', 'start_mode')
    op.drop_column('jobs', 'is_locked')
    op.drop_column('jobs', 'has_conflict')
    op.drop_column('jobs', 'earliest_date')
    op.drop_column('jobs', 'latest_date')
    op.drop_column('tenants', 'job_id_prefix')
