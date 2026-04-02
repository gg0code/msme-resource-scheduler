from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade():
    # employees.hourly_rate
    if not _column_exists("employees", "hourly_rate"):
        op.add_column("employees", sa.Column("hourly_rate", sa.Float(), nullable=True, server_default="0.0"))

    # employees.overtime_rate
    if not _column_exists("employees", "overtime_rate"):
        op.add_column("employees", sa.Column("overtime_rate", sa.Float(), nullable=True, server_default="0.0"))

    # machines.hourly_rate
    if not _column_exists("machines", "hourly_rate"):
        op.add_column("machines", sa.Column("hourly_rate", sa.Float(), nullable=True, server_default="0.0"))

    # jobs.misc_cost already exists in V1.0 schema - skip if present
    if not _column_exists("jobs", "misc_cost"):
        op.add_column("jobs", sa.Column("misc_cost", sa.Float(), nullable=True, server_default="0.0"))


def downgrade():
    # Only drop if they were added by this migration
    # Safe to leave - these are additive columns
    pass
