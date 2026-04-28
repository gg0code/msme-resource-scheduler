# backend/scripts/backfill_v6_4_entry_gate.py
#
# FILE PURPOSE
# One-time idempotent backfill for migration 027 (v6.3.1).
# Normalises the entry-gate columns added to tenants and users:
#   tenants: entry_mode, briefing_*, briefing_timezone, briefing_working_days,
#            created_via
#   users:   briefing_subscribed, created_via
# For rows where one of these columns is NULL or the empty string (which
# can happen on a partially-applied migration, on rows imported via raw SQL
# that bypassed server_default, or on test fixtures created before column
# defaults landed), the script writes the canonical default value.
#
# WHO CALLS THIS FILE
# - Operators running `python -m scripts.backfill_v6_4_entry_gate` after
#   the v6.3.1 deploy on each environment (dev, staging, prod).
# - tests/test_v6_4_entry_gate.py (imports backfill() directly).
#
# WHAT THIS FILE CALLS
# - app.database.SessionLocal - opens a SQLAlchemy session against the
#   primary DB (URL from .env)
# - app.models.auth.Tenant, app.models.auth.User - ORM iteration targets
#
# DESIGN NOTES
# - Idempotent: running a second time updates zero rows, because the first
#   run replaces NULL/empty values with valid defaults that pass the same
#   "needs fix?" predicate.
# - Preserves explicit non-default values: if a tenant already has
#   entry_mode='whatsapp_first' or created_via='whatsapp_signup', the
#   script leaves it alone. Only NULL / empty-string triggers a write.
# - Pattern matches scripts/backfill_phone_industry_type.py — same shape
#   (dict return with 'fixed', 'skipped', 'total'; same try/finally on
#   the session; same __main__ guard with summary print).
# - No industry-specific logic — entry_mode is set from the column-level
#   default, not derived from tenant.industry_type. Cross-vertical clean.

from app.database import SessionLocal
from app.models.auth import Tenant, User


# Default values mirror migration 027's server_defaults. Single source of
# truth — change here and in the migration in the same commit.
_TENANT_DEFAULTS = {
    "entry_mode":             "desktop_first",
    "briefing_timezone":      "Asia/Kolkata",
    "briefing_working_days":  "1,2,3,4,5,6",
    "created_via":            "desktop_signup",
}
_TENANT_BOOL_DEFAULTS = {
    "briefing_morning_enabled": False,
    "briefing_evening_enabled": False,
}
_USER_DEFAULTS = {
    "created_via": "desktop_signup",
}
_USER_BOOL_DEFAULTS = {
    "briefing_subscribed": True,
}


def _needs_string_fix(value: object) -> bool:
    """True if `value` is None or an empty string — i.e. a NOT-NULL violation
    waiting to happen on PostgreSQL."""
    return value is None or value == ""


def _fix_string_columns(row: object, defaults: dict) -> bool:
    """For each (column, default) pair in `defaults`, set row.<column> to the
    default when the current value is NULL or empty. Returns True if any
    column was written, False otherwise."""
    changed = False
    for column, default_value in defaults.items():
        if _needs_string_fix(getattr(row, column)):
            setattr(row, column, default_value)
            changed = True
    return changed


def _fix_bool_columns(row: object, defaults: dict) -> bool:
    """For each (column, default) pair in `defaults`, set row.<column> to the
    default when the current value is NULL. Booleans use a stricter
    'is None' check — explicit False is a valid value and must be preserved.
    Returns True if any column was written, False otherwise."""
    changed = False
    for column, default_value in defaults.items():
        if getattr(row, column) is None:
            setattr(row, column, default_value)
            changed = True
    return changed


def backfill() -> dict:
    """
    Normalise v6.3.1 entry-gate columns on tenants and users.

    Called by:    __main__ block below; tests/test_v6_4_entry_gate.py.
    Calls into:   _fix_string_columns(), _fix_bool_columns(), SessionLocal().
    Side effects: UPDATEs tenants and users rows where new entry-gate columns
                  hold NULL or empty-string values; commits once at the end.

    Returns a dict {'fixed': int, 'skipped': int, 'total': int} where
    'fixed' is the number of rows updated (sum across both tables),
    'skipped' is always 0 in this script (no orphan-row case), and
    'total' is the count of rows examined.
    """
    db = SessionLocal()
    try:
        fixed = 0
        examined = 0

        for tenant in db.query(Tenant).all():
            examined += 1
            string_changed = _fix_string_columns(tenant, _TENANT_DEFAULTS)
            bool_changed   = _fix_bool_columns(tenant, _TENANT_BOOL_DEFAULTS)
            if string_changed or bool_changed:
                fixed += 1

        for user in db.query(User).all():
            examined += 1
            string_changed = _fix_string_columns(user, _USER_DEFAULTS)
            bool_changed   = _fix_bool_columns(user, _USER_BOOL_DEFAULTS)
            if string_changed or bool_changed:
                fixed += 1

        db.commit()
        return {"fixed": fixed, "skipped": 0, "total": examined}
    finally:
        db.close()


if __name__ == "__main__":
    result = backfill()
    if result["fixed"] == 0:
        print(
            f"No tenants or users needed v6.4 entry-gate backfill. "
            f"(Examined {result['total']} row(s).)"
        )
    else:
        print(
            f"Backfilled {result['fixed']} row(s) with v6.4 entry-gate defaults. "
            f"(Examined {result['total']}, skipped {result['skipped']}.)"
        )
