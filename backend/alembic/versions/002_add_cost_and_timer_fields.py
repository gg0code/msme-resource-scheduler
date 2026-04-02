"""add cost and timer fields

Revision ID: 002_cost_timer
Revises: 46385051aa8d
Create Date: 2026-03-04

Adds:
  employees  : hourly_rate, overtime_rate
  machines   : hourly_rate
  jobs       : order_value, misc_cost, raw_materials, timer_status,
               actual_start_at, actual_end_at, paused_seconds, timer_log
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