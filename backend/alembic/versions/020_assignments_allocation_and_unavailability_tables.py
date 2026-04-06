# alembic/versions/020_assignments_allocation_and_unavailability_tables.py
# Migration: add allocation_pct to job_assignments; create employee_leaves and machine_downtimes
# Introduced in: v4.0.9
# What it does:
#   1. Adds allocation_pct column to job_assignments (nullable, default 100.0)
#   2. Creates employee_leaves table
#   3. Creates machine_downtimes table
# Uses IF NOT EXISTS throughout - safe to re-run if partially applied

from alembic import op
from sqlalchemy import text

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Add allocation_pct to job_assignments
    # nullable=True, default 100.0 - existing rows get NULL, treated as 100% in app logic
    conn.execute(text("""
        ALTER TABLE job_assignments
        ADD COLUMN IF NOT EXISTS allocation_pct FLOAT NULL
    """))

    # 2. Create employee_leaves table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS employee_leaves (
            id          SERIAL PRIMARY KEY,
            tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            start_date  DATE NOT NULL,
            end_date    DATE NOT NULL,
            reason      VARCHAR(255),
            created_at  TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_employee_leaves_tenant_id
        ON employee_leaves (tenant_id)
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_employee_leaves_employee_id
        ON employee_leaves (employee_id)
    """))

    # 3. Create machine_downtimes table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS machine_downtimes (
            id         SERIAL PRIMARY KEY,
            tenant_id  INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            machine_id INTEGER NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
            start_date DATE NOT NULL,
            end_date   DATE NOT NULL,
            reason     VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_machine_downtimes_tenant_id
        ON machine_downtimes (tenant_id)
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_machine_downtimes_machine_id
        ON machine_downtimes (machine_id)
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DROP TABLE IF EXISTS machine_downtimes"))
    conn.execute(text("DROP TABLE IF EXISTS employee_leaves"))
    conn.execute(text("""
        ALTER TABLE job_assignments DROP COLUMN IF EXISTS allocation_pct
    """))
