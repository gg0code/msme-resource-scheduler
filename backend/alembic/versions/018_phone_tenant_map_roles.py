"""
ZetaOps Copilot Database Migration 018: Phone Tenant Map Roles
==============================================================

FILE PURPOSE
This is an Alembic database migration file that adds role-based access control columns to the WhatsApp phone number mapping table. It was introduced in the v5-whatsapp branch for the WhatsApp Copilot feature, adding display_name and phone_role columns to track which family member or employee is sending WhatsApp commands. This migration sits in the database schema evolution chain at position 018, building upon migration 017 which created the original phone_tenant_map table.

WHAT THIS FILE DOES — step by step
1. Defines Alembic migration metadata (revision 018, depends on 017)
2. Provides an upgrade() function that adds two new columns to phone_tenant_map table
3. Adds display_name column (nullable string) to store human-readable labels like "Rajesh (Owner)"
4. Adds phone_role column (non-null string, defaults to "owner") for future role-based access control
5. Provides a downgrade() function that removes both columns if rollback is needed
6. Includes extensive documentation about collision risks with Factory GPT branch migrations

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : upgrade
Type         : function
Purpose      : Executes the forward migration by adding display_name and phone_role columns to the phone_tenant_map table. This allows the WhatsApp system to track which specific person (not just phone number) is sending commands, and sets up infrastructure for future role-based permissions.
Parameters   : None
Returns      : None
Calls        : op.add_column() from Alembic operations
DB/API       : Executes ALTER TABLE SQL statements on phone_tenant_map table
Side effects : Permanently modifies the database schema by adding two new columns

Name         : downgrade
Type         : function
Purpose      : Reverses the migration by removing the display_name and phone_role columns from phone_tenant_map table. This is used when rolling back to previous database states during development or deployment issues.
Parameters   : None
Returns      : None
Calls        : op.drop_column() from Alembic operations
DB/API       : Executes ALTER TABLE SQL statements to drop columns from phone_tenant_map table
Side effects : Permanently removes columns and any data stored in them from the database

WHO CALLS THIS FILE
This file is executed by the Alembic migration system when running:
- `alembic upgrade head` (calls upgrade function)
- `alembic downgrade -1` (calls downgrade function)
- Database initialization scripts during deployment
- Developer database setup commands

IMPORTS EXPLAINED
- `from alembic import op`: Provides database operation functions like add_column and drop_column for schema changes
- `import sqlalchemy as sa`: Provides SQLAlchemy data types (String, Column) needed to define the new database columns

INTERN NOTES
- Easiest thing to break: Modifying the revision number or down_revision creates migration chain conflicts that prevent database upgrades
- Non-obvious design decision: phone_role defaults to "owner" but isn't enforced yet - this allows gradual rollout of RBAC without breaking existing WhatsApp integrations
- Most common mistake: Forgetting that display_name is nullable while phone_role is not - new code must handle null display_name values gracefully
- Design principle #2: This implements tenant scoping infrastructure - phone_role will eventually enforce per-tenant permission boundaries
- What to check if behaving unexpectedly: Verify migration 017 ran successfully first, and check if you're on the correct git branch (v5-whatsapp vs v4-dev)
- v5-whatsapp merge note: This migration number conflicts with Factory GPT branch - must be renumbered to 024+ during merge to avoid Alembic revision collisions
"""

from alembic import op
import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------

revision = "018"

# This migration depends on 017 (phone_tenant_map table must exist first)
down_revision = "017"

branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add display_name and phone_role columns to phone_tenant_map.

    Both columns are nullable with defaults so existing rows are
    not affected — no data migration needed.

    Called by: alembic upgrade head
    """

    # display_name — who is this phone number?
    # nullable=True so existing rows stay valid without a value.
    # Factory owner sets this when linking their phone via LinkWhatsApp.tsx
    op.add_column(
        "phone_tenant_map",
        sa.Column(
            "display_name",
            sa.String(100),
            nullable=True,
            comment="Human label e.g. 'Rajesh (Owner)', 'Amit (Son)'"
        )
    )

    # phone_role — what level of access does this person have?
    # Default 'owner' — gives full access.
    # NOT enforced yet — all roles behave identically during pilot.
    # Enforcement added in v5.7 when RBAC is implemented.
    # Values: owner | manager | viewer
    op.add_column(
        "phone_tenant_map",
        sa.Column(
            "phone_role",
            sa.String(20),
            nullable=False,
            server_default="owner",
            comment="owner|manager|viewer — not enforced until v5.7"
        )
    )


def downgrade() -> None:
    """
    Remove display_name and phone_role columns from phone_tenant_map.

    Called by: alembic downgrade -1
    Safe — no other tables depend on these columns.
    """
    op.drop_column("phone_tenant_map", "phone_role")
    op.drop_column("phone_tenant_map", "display_name")