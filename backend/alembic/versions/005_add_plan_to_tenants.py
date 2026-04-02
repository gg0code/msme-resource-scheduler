"""005_add_plan_to_tenants

Add plan column to tenants table (free/paid).

Revision ID: 005
Revises: 004
Create Date: 2025-01-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade():
    if not _column_exists("tenants", "plan"):
        op.add_column(
            "tenants",
            sa.Column(
                "plan",
                sa.String(20),
                nullable=False,
                server_default="free",
            ),
        )


def downgrade():
    op.drop_column("tenants", "plan")
