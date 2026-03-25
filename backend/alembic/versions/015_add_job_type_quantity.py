"""013_add_job_type_quantity

Add job_type (string) and quantity (float) to the jobs table.
These fields are prerequisites for v3.9.8 material estimate endpoint.

Revision ID: 015
Revises: 014_schedule_entries
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '015'
down_revision = '014_schedule_entries'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('job_type', sa.String(100), nullable=True))
    op.add_column('jobs', sa.Column('quantity', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('jobs', 'quantity')
    op.drop_column('jobs', 'job_type')
