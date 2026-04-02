"""
```python
"""
FILE PURPOSE
This Alembic database migration establishes the foundation for JWT-based authentication 
and multi-tenancy in ZetaOps Copilot. Migration 004 creates the core tenant/user/auth 
tables and enforces tenant isolation by making tenant_id required on all existing data 
tables. This migration was introduced in v4-dev and represents the critical security 
boundary that enables multiple businesses to safely share the same application instance.

WHAT THIS FILE DOES — step by step
1. Defines migration metadata (revision 004, depends on 003_tenant_stub)
2. Lists all existing tables that need tenant_id enforcement in TABLES constant
3. In upgrade(): Creates tenants table with id, name, slug, plan, and timestamps
4. Creates users table linked to tenants with email, password, role, and activation status
5. Creates refresh_tokens table for JWT refresh token management
6. Adds database indexes on frequently-queried columns (id, slug, email, tenant_id)
7. Enforces tenant isolation by deleting orphaned records and making tenant_id NOT NULL
8. Creates foreign key constraints linking all data tables to tenants with CASCADE delete
9. In downgrade(): Reverses all changes by dropping constraints, indexes, and new tables

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Executes the forward migration that establishes multi-tenancy and JWT auth 
               infrastructure. Creates three new tables (tenants, users, refresh_tokens) 
               and enforces tenant_id requirements on all existing business data tables.
Parameters   : None (Alembic migration convention)
Returns      : None (modifies database schema directly)
Calls        : op.create_table, op.create_index, op.execute, op.alter_column, op.create_foreign_key from Alembic
DB/API       : Creates tables: tenants, users, refresh_tokens. Modifies 9 existing tables in TABLES list
Side effects : Deletes any records with NULL tenant_id, makes tenant_id required on all data tables

Name         : downgrade  
Type         : function
Purpose      : Reverses the migration by removing all multi-tenancy infrastructure and 
               making tenant_id optional again. Used for rolling back this migration 
               during development or emergency rollback scenarios.
Parameters   : None (Alembic migration convention)  
Returns      : None (modifies database schema directly)
Calls        : op.drop_constraint, op.drop_index, op.alter_column, op.drop_table from Alembic
DB/API       : Drops tables: refresh_tokens, users, tenants. Removes constraints from 9 existing tables
Side effects : Removes tenant isolation - makes tenant_id nullable on all business data tables

WHO CALLS THIS FILE
- backend/alembic/env.py (Alembic migration runner discovers and executes this migration)
- Migration 005 and later migrations (depends on this migration's schema changes)
- Database deployment scripts and CI/CD pipelines that run `alembic upgrade`

IMPORTS EXPLAINED
- from alembic import op: Provides database schema modification operations (create_table, create_index, etc.) that are database-agnostic
- import sqlalchemy as sa: Provides column types (Integer, String, DateTime, Boolean) and schema definition helpers for Alembic operations

INTERN NOTES
- Easiest thing to break: Running this migration on production data without backup - the DELETE statements will permanently remove orphaned records that have NULL tenant_id
- Non-obvious design decision: CASCADE delete on tenant foreign keys means deleting a tenant will automatically delete ALL associated users, jobs, machines, etc. - this prevents orphaned data but requires careful tenant deletion handling
- Most common mistake: Forgetting to add tenant_id filtering in new queries after this migration - every business data query MUST include tenant_id filter (design principle #2)
- Design principle implemented: #2 (Tenant scoping on ALL DB queries) - this migration enforces the database-level foundation that makes tenant isolation mandatory
- What to check if this behaves unexpectedly: Verify all tables in TABLES constant actually exist and have tenant_id columns from migration 003, check for foreign key constraint naming conflicts in your database
- Migration rollback warning: Downgrading past this point will break all authentication and multi-tenancy - only safe in development environments with test data
"""
```
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003_tenant_stub"
branch_labels = None
depends_on = None

TABLES = [
    'employees', 'employee_skills',
    'machines', 'machine_skill_requirements',
    'jobs', 'job_skill_requirements', 'job_assignments',
    'skills', 'availability_overrides',
]


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_id", "tenants", ["id"])
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    for table in TABLES:
        op.execute(f"DELETE FROM {table} WHERE tenant_id IS NULL")
        op.alter_column(table, "tenant_id", existing_type=sa.Integer(), nullable=False)
        op.create_foreign_key(f"fk_{table}_tenant_id", table, "tenants", ["tenant_id"], ["id"], ondelete="CASCADE")
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(f"fk_{table}_tenant_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.alter_column(table, "tenant_id", existing_type=sa.Integer(), nullable=True)
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("tenants")
