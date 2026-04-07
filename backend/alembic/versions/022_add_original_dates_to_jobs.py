# alembic/versions/022_add_original_dates_to_jobs.py
# Migration: add original_start_date and original_end_date to jobs table
# Introduced in: v4.0.9
# What it does:
#   Adds two nullable Date columns to jobs:
#   - original_start_date: set by scheduler when it first moves a job's dates
#   - original_end_date:   set by scheduler when it first moves a job's dates
#   Non-null = scheduler moved this job, user should review new dates.
#   Cleared to NULL when user edits the job (signals fresh scheduling candidate).
#   Uses IF NOT EXISTS - safe to re-run if partially applied.

from alembic import op
from sqlalchemy import text

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("""
        ALTER TABLE jobs
        ADD COLUMN IF NOT EXISTS original_start_date DATE NULL
    """))

    conn.execute(text("""
        ALTER TABLE jobs
        ADD COLUMN IF NOT EXISTS original_end_date DATE NULL
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE jobs DROP COLUMN IF EXISTS original_end_date"))
    conn.execute(text("ALTER TABLE jobs DROP COLUMN IF EXISTS original_start_date"))
