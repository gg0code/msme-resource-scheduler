# alembic/versions/027_whatsapp_entry_gate.py
#
# FILE PURPOSE
# Migration 027 (v6.3.1) — WhatsApp Entry Gate + Tenant Configuration Foundation.
# Adds columns required by SRS v6.4 §6.28 to the tenants and users tables.
# Schema-only; no business logic, no UI, no router behaviour change.
#
# CALLED BY
#   alembic upgrade head    (on deploy)
#   alembic downgrade -1    (on rollback)
#
# CALLS INTO
#   alembic.op.add_column / drop_column / create_index / drop_index
#   sqlalchemy column types: String, Boolean, Time
#
# DESIGN NOTES
#   - Every NOT NULL column uses server_default so existing tenants and users
#     survive the upgrade without a NULL-violation error. server_default is
#     applied as a DDL DEFAULT clause; the model's Python-side default kicks
#     in only when ORM creates new rows.
#   - Allowed-value validation is at the service layer (app/services/role_helpers.py
#     and app/services/tenant_config.py to be added in later iterations); the
#     DB stores plain String(20). This matches the existing convention from
#     migrations 017, 018, 023.
#   - phone_e164 on users gets an index because lookup-by-phone will be a
#     hot path once WhatsApp signup lands in v6.3.3.
#   - downgrade() drops every column added in upgrade(), in reverse order.
#     No data is preserved on downgrade.

from alembic import op
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Alembic revision identifiers
# ---------------------------------------------------------------------------

revision      = "027"
down_revision = "023"
branch_labels = None
depends_on    = None


# Column specs are kept in module-level lists so upgrade(), downgrade(), and
# the test suite can iterate them. Single source of truth — change here only.

_TENANT_COLUMNS = [
    # entry_mode: which surface the tenant primarily uses to drive the system.
    # Allowed: 'whatsapp_first' | 'desktop_first' | 'hybrid'. Default keeps
    # every existing tenant on the desktop UI; WhatsApp-first is opted-in.
    ("entry_mode", sa.String(20), False, "desktop_first"),

    # size_segment: small/medium/large factory bucket. Nullable because
    # existing tenants haven't been classified yet — v6.3.4 will populate.
    ("size_segment", sa.String(20), True, None),

    # Morning briefing: opt-in WhatsApp summary sent at briefing_morning_time.
    ("briefing_morning_enabled", sa.Boolean(), False, "false"),
    ("briefing_morning_time",    sa.Time(),    False, "07:30:00"),

    # Evening briefing: opt-in end-of-day recap sent at briefing_evening_time.
    ("briefing_evening_enabled", sa.Boolean(), False, "false"),
    ("briefing_evening_time",    sa.Time(),    False, "18:30:00"),

    # Timezone IANA string used to convert briefing times to UTC for delivery.
    # 'Asia/Kolkata' is the only supported value at v6.3.1; SRS §6.28.4
    # describes the v7.x multi-timezone roadmap.
    ("briefing_timezone", sa.String(50), False, "Asia/Kolkata"),

    # Comma-separated ISO weekday numbers (1=Mon..7=Sun). '1,2,3,4,5,6'
    # = Monday through Saturday, the default for Indian MSMEs.
    ("briefing_working_days", sa.String(20), False, "1,2,3,4,5,6"),

    # Where this tenant came from. 'desktop_signup' covers everyone who
    # registered before v6.3.1; 'whatsapp_signup' arrives in v6.3.3.
    ("created_via", sa.String(30), False, "desktop_signup"),
]


_USER_COLUMNS = [
    # Per-user briefing time overrides. Nullable — when NULL, the tenant-level
    # briefing_morning_time / briefing_evening_time apply. Used by SRS §6.28.7
    # to let a co_owner receive briefings on a different schedule.
    ("briefing_time_override_morning", sa.Time(), True,  None),
    ("briefing_time_override_evening", sa.Time(), True,  None),

    # briefing_subscribed: per-user opt-out flag. Default True so anyone whose
    # tenant enables briefings receives them; users can mute via /unsubscribe.
    ("briefing_subscribed", sa.Boolean(), False, "true"),

    # phone_e164: the user's WhatsApp number in E.164 format (e.g. +919876543210).
    # Nullable today; populated by link-phone flow and (in v6.3.3) signup-via-WA.
    # Indexed because resolve_identity() will look up users by phone.
    ("phone_e164", sa.String(20), True, None),

    # Mirrors tenants.created_via at the user level — distinguishes a user
    # created during desktop signup from one created via WhatsApp invite.
    ("created_via", sa.String(30), False, "desktop_signup"),
]


def upgrade() -> None:
    """
    Add v6.4 entry-gate columns to tenants and users.

    Called by:    alembic upgrade head
    Calls into:   op.add_column(), op.create_index()
    Side effects: ALTER TABLE on tenants and users; existing rows are filled
                  with each column's server_default by PostgreSQL automatically.
    """
    for name, col_type, nullable_in_db, default in _TENANT_COLUMNS:
        op.add_column(
            "tenants",
            sa.Column(
                name,
                col_type,
                nullable=(nullable_in_db is True),
                server_default=default,
            ),
        )

    for name, col_type, nullable_in_db, default in _USER_COLUMNS:
        op.add_column(
            "users",
            sa.Column(
                name,
                col_type,
                nullable=(nullable_in_db is True),
                server_default=default,
            ),
        )

    # phone_e164 index — hot lookup path for WhatsApp identity resolution.
    op.create_index("idx_users_phone_e164", "users", ["phone_e164"])


def downgrade() -> None:
    """
    Drop every column upgrade() added, in reverse order.

    Called by:    alembic downgrade -1
    Calls into:   op.drop_index(), op.drop_column()
    Side effects: ALTER TABLE on tenants and users; data in dropped columns
                  is permanently lost. No-op for the role-validator service
                  helper — that is reverted via git, not via alembic.
    """
    op.drop_index("idx_users_phone_e164", table_name="users")
    for name, *_ in reversed(_USER_COLUMNS):
        op.drop_column("users", name)
    for name, *_ in reversed(_TENANT_COLUMNS):
        op.drop_column("tenants", name)
