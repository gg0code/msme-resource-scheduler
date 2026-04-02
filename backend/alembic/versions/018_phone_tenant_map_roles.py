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

    # display_name - who is this phone number?
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

    # phone_role - what level of access does this person have?
    # Default 'owner' - gives full access.
    # NOT enforced yet - all roles behave identically during pilot.
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