# alembic/versions/019_add_ai_usage_to_tenants.py
# Migration: add AI usage tracking columns to tenants table
# Introduced in: v4.0.9
# What it does: adds ai_queries_today, ai_tokens_today, ai_queries_date, industry_type
#               to tenants. Uses IF NOT EXISTS so safe to run even if columns
#               were added manually or by a previous failed migration attempt.

from alembic import op
from sqlalchemy import text

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Raw SQL with IF NOT EXISTS handles the case where columns already exist
    # in the DB from a previous failed/partial migration run that added columns
    # but never stamped revision 019 in alembic_version table.
    conn = op.get_bind()

    conn.execute(text(
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS ai_queries_today INTEGER NOT NULL DEFAULT 0"
    ))
    conn.execute(text(
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS ai_tokens_today INTEGER NOT NULL DEFAULT 0"
    ))
    conn.execute(text(
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS ai_queries_date DATE NULL"
    ))
    conn.execute(text(
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS industry_type VARCHAR(50) NULL"
    ))


def downgrade() -> None:
    op.drop_column("tenants", "industry_type")
    op.drop_column("tenants", "ai_queries_date")
    op.drop_column("tenants", "ai_tokens_today")
    op.drop_column("tenants", "ai_queries_today")
