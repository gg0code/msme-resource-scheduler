"""
v6.3.1 diagnostic: role distribution and migration 027 column verification.

Two checks in one script:
  1. Role distribution across the users table — confirms which role values
     are actually in production data (used during v6.3.1 to verify the
     proprietor/owner/scheduler synonym handling decision).
  2. Migration 027 column verification — confirms the entry_mode,
     size_segment, briefing config, and created_via columns landed on
     tenants and users with correct types, nullability, and defaults.

Called by: developer (manually) via `python -m scripts.check_role_distribution`
           from the backend/ directory. Used as a pre-tag verification step
           for v6.3.1 and a post-deploy smoke check thereafter.
Calls into: SQLAlchemy engine built directly from DATABASE_URL env var
            (loaded from backend/.env if present).
"""
import os
import sys
from pathlib import Path

# Load .env if present (project uses python-dotenv elsewhere)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# Columns added by migration 027 — must match
# backend/alembic/versions/027_whatsapp_entry_gate.py exactly.
EXPECTED_TENANT_COLUMNS = {
    "entry_mode": ("character varying", "NO", "'desktop_first'"),
    "size_segment": ("character varying", "YES", None),
    "briefing_morning_enabled": ("boolean", "NO", "false"),
    "briefing_morning_time": ("time without time zone", "NO", "'07:30:00'"),
    "briefing_evening_enabled": ("boolean", "NO", "false"),
    "briefing_evening_time": ("time without time zone", "NO", "'18:30:00'"),
    "briefing_timezone": ("character varying", "NO", "'Asia/Kolkata'"),
    "briefing_working_days": ("character varying", "NO", "'1,2,3,4,5,6'"),
    "created_via": ("character varying", "NO", "'desktop_signup'"),
}

EXPECTED_USER_COLUMNS = {
    "briefing_time_override_morning": ("time without time zone", "YES", None),
    "briefing_time_override_evening": ("time without time zone", "YES", None),
    "briefing_subscribed": ("boolean", "NO", "true"),
    "phone_e164": ("character varying", "YES", None),
    "created_via": ("character varying", "NO", "'desktop_signup'"),
}


def check_role_distribution(engine: Engine) -> int:
    """
    Prints a count of users grouped by role value.

    Used to verify which role values are actually present in production data
    versus which are documented in SRS §6.17. Discrepancies inform whether
    a role name is canonical, a legacy synonym, or undocumented.

    Called by: main()
    Calls into: SQLAlchemy engine.connect() — read-only SELECT on users.

    Returns: 0 on success.
    """
    print("=" * 50)
    print("CHECK 1: Role distribution in users table")
    print("=" * 50)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT role, COUNT(*) AS n FROM users GROUP BY role ORDER BY n DESC")
        )
        rows = list(result)

    if not rows:
        print("(users table is empty)\n")
        return 0

    print(f"{'role':<25} {'count':>8}")
    print("-" * 35)
    for row in rows:
        role_value = row[0] if row[0] is not None else "(NULL)"
        print(f"{role_value:<25} {row[1]:>8}")
    print()
    return 0


def check_migration_027_columns(engine: Engine) -> int:
    """
    Verifies migration 027 columns exist on tenants and users with correct
    type, nullability, and default. Returns 0 if all expected columns
    match; returns 1 if any column is missing or mismatched.

    Used as a pre-tag gate for v6.3.1 — confirms the migration actually
    landed on the dev/staging DB, not just succeeded in alembic's tracker.

    Called by: main()
    Calls into: SQLAlchemy engine.connect() — read-only SELECT on
                information_schema.columns.

    Returns: 0 if all columns match expected; 1 if any mismatch found.
    """
    print("=" * 50)
    print("CHECK 2: Migration 027 column verification")
    print("=" * 50)

    mismatches = []
    mismatches.extend(_verify_table_columns(engine, "tenants", EXPECTED_TENANT_COLUMNS))
    mismatches.extend(_verify_table_columns(engine, "users", EXPECTED_USER_COLUMNS))

    if mismatches:
        print("\nMISMATCHES FOUND:")
        for msg in mismatches:
            print(f"  - {msg}")
        print(f"\nTotal mismatches: {len(mismatches)}")
        return 1

    print("\nAll migration 027 columns match expected schema. ✓")
    return 0


def _verify_table_columns(engine: Engine, table_name: str, expected: dict) -> list:
    """
    Queries information_schema.columns for the given table and compares
    against the expected column spec. Prints a per-column line.

    Called by: check_migration_027_columns()
    Calls into: SQLAlchemy engine.connect() — read-only SELECT on
                information_schema.columns.

    Returns: list of mismatch description strings. Empty list = all match.
    """
    print(f"\nTable: {table_name}")
    print(f"  {'column':<35} {'type':<28} {'null':<6} {'default':<25} {'status'}")
    print(f"  {'-' * 35} {'-' * 28} {'-' * 6} {'-' * 25} {'-' * 8}")

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = :tbl AND column_name = ANY(:cols)
                ORDER BY column_name
            """),
            {"tbl": table_name, "cols": list(expected.keys())},
        )
        actual = {row[0]: (row[1], row[2], row[3]) for row in result}

    mismatches = []
    for col_name, (exp_type, exp_null, exp_default) in expected.items():
        if col_name not in actual:
            print(f"  {col_name:<35} {'(MISSING)':<28} {'-':<6} {'-':<25} ✗")
            mismatches.append(f"{table_name}.{col_name}: column missing")
            continue

        act_type, act_null, act_default = actual[col_name]
        type_ok = act_type == exp_type
        null_ok = act_null == exp_null
        default_ok = _defaults_match(act_default, exp_default)

        status = "✓" if (type_ok and null_ok and default_ok) else "✗"
        default_display = (act_default[:22] + "...") if act_default and len(act_default) > 25 else (act_default or "-")
        print(f"  {col_name:<35} {act_type:<28} {act_null:<6} {default_display:<25} {status}")

        if not type_ok:
            mismatches.append(f"{table_name}.{col_name}: type {act_type!r} != expected {exp_type!r}")
        if not null_ok:
            mismatches.append(f"{table_name}.{col_name}: nullable {act_null!r} != expected {exp_null!r}")
        if not default_ok:
            mismatches.append(f"{table_name}.{col_name}: default {act_default!r} != expected {exp_default!r}")

    return mismatches


def _defaults_match(actual: str, expected: str) -> bool:
    """
    Compares column defaults loosely — Postgres normalises defaults
    in ways that make exact string match unreliable (e.g. it adds
    ::character varying type casts). We strip those for comparison.

    Called by: _verify_table_columns()
    Calls into: nothing (pure string ops).

    Returns: True if defaults are semantically equal, False otherwise.
    """
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    # Strip Postgres type casts like ::character varying or ::time without time zone
    actual_clean = actual.split("::")[0].strip()
    expected_clean = expected.strip()
    return actual_clean == expected_clean


def main() -> int:
    """
    Entry point. Runs both diagnostic checks and exits with a code
    reflecting overall success.

    Called by: developer via `python -m scripts.check_role_distribution`.
    Calls into: check_role_distribution(), check_migration_027_columns().

    Returns: 0 if all checks pass, 1 if DATABASE_URL missing or any
             column mismatch found.
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set in environment or .env", file=sys.stderr)
        return 1

    engine = create_engine(db_url)
    role_rc = check_role_distribution(engine)
    column_rc = check_migration_027_columns(engine)
    return role_rc | column_rc


if __name__ == "__main__":
    sys.exit(main())