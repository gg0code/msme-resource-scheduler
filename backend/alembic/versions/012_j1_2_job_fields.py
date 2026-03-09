"""012_j1_2_job_fields

Revision ID: 012
Revises: 011
Create Date: 2026-03-09

J1.2 additions to jobs table:
  - delivery_date       : customer delivery deadline (separate from production end_date)
  - invoice_number      : invoice reference
  - invoice_date        : date invoice was raised
  - payment_status      : Unpaid | Partial | Paid
  - payment_amount      : amount received so far
  - payment_date        : date of full/last payment
  - actual_hours        : net working hours (stored on job end/stop)
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
