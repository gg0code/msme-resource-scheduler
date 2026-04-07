# alembic/versions/021_add_is_locked_to_jobs.py
# Migration: add is_locked column to jobs table
# Introduced in: v4.0.9
# What it does: adds is_locked (boolean, default False) to jobs table.
#               is_locked=True means the scheduler preserves this job's
#               current schedule slot and skips it during auto-scheduling.
#               Uses IF NOT EXISTS - safe to re-run if partially applied.

from alembic import op
from sqlalchemy import text

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # is_locked - False by default so all existing jobs start unlocked
    # server_default='false' handles existing rows without a data migration
    conn.execute(text("""
        ALTER TABLE jobs
        ADD COLUMN IF NOT EXISTS is_locked BOOLEAN NOT NULL DEFAULT FALSE
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        ALTER TABLE jobs DROP COLUMN IF EXISTS is_locked
    """))
