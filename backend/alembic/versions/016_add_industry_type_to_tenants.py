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
