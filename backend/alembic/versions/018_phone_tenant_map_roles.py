"""
MIGRATION: 018_phone_tenant_map_roles
PATH:      backend/alembic/versions/018_phone_tenant_map_roles.py
PURPOSE:   Adds display_name and phone_role columns to phone_tenant_map.

           display_name — human-readable label for who this phone belongs to.
                          e.g. "Rajesh (Owner)", "Amit (Son)", "Priya (Partner)"
                          Shows in logs and analytics so you know which family
                          member is sending commands, not just the phone number.

           phone_role   — reserved for future role-based access control.
                          Currently not enforced — all roles have equal access.
                          Values: 'owner', 'manager', 'viewer'
                          Will be enforced in v5.7 when RBAC is added.

           Why separate migration:
           Migration 017 created the table. Adding columns via ALTER TABLE
           in a separate migration is safer than modifying 017 — it means
           the DB can be rolled back to 017 state if needed.

BRANCH:    v5-whatsapp
VERSION:   v5.0
CREATED:   2026-03

TABLES MODIFIED:
  phone_tenant_map  — adds display_name and phone_role columns

ROLLBACK:
  Drops display_name and phone_role columns from phone_tenant_map.
  Safe to run — no data dependencies on these columns yet.

COLLISION NOTE:
  Factory GPT branch plans migrations 017-022.
  This migration uses 018 — also in the collision range.
  When merging v5-whatsapp into main alongside Factory GPT,
  renumber to 024 or higher. Tracked in V4_ALERTS.md.
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