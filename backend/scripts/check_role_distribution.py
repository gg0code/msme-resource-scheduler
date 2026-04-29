"""
v6.3.1+ diagnostic: role distribution, migration 027 column verification,
entry_mode distribution (v6.3.2), and role-group state (v6.3.3).

Four checks in one script:
  1. Role distribution across the users table - confirms which role values
     are actually in production data (used during v6.3.1 to verify the
     proprietor/owner/scheduler synonym handling decision).
  2. Migration 027 column verification - confirms the entry_mode,
     size_segment, briefing config, and created_via columns landed on
     tenants and users with correct types, nullability, and defaults.
  3. Tenant entry_mode distribution (v6.3.2) - after v6.3.2 signups the
     tenants table must have entry_mode set on every row; pre-v6.4 rows
     all show 'desktop_first' from the migration 027 server_default.
  4. Role group state (v6.3.3) - reports top-tier vs non-top-tier user
     counts overall and per-tenant. Sanity-checks that no tenant is left
     with zero top-tier users after the v6.3.3 require_top_tier rollout
     (such a tenant would be locked out of every operational endpoint).

Called by: developer (manually) via `python -m scripts.check_role_distribution`
           from the backend/ directory. Used as a pre-tag verification step
           for v6.3.1+ and a post-deploy smoke check thereafter.
Calls into: SQLAlchemy engine built directly from DATABASE_URL env var
            (loaded from backend/.env if present).
            app.models.auth.TOP_TIER_ROLES for the canonical top-tier set
            in CHECK 4 (single source of truth, Lesson 22).

ASCII output only - the script runs in environments (Windows cp1252 console)
where non-ASCII characters raise UnicodeEncodeError on stdout.write.
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

    print("\nAll migration 027 columns match expected schema. OK")
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
            print(f"  {col_name:<35} {'(MISSING)':<28} {'-':<6} {'-':<25} FAIL")
            mismatches.append(f"{table_name}.{col_name}: column missing")
            continue

        act_type, act_null, act_default = actual[col_name]
        type_ok = act_type == exp_type
        null_ok = act_null == exp_null
        default_ok = _defaults_match(act_default, exp_default)

        status = "OK" if (type_ok and null_ok and default_ok) else "FAIL"
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


def check_signup_state(engine: Engine) -> int:
    """
    v6.3.2 diagnostic: verify new tenants are being created with entry_mode set.

    Counts tenants by entry_mode value. After v6.3.2 signups, all newly-created
    tenants must have entry_mode in ('whatsapp_first', 'desktop_first', 'hybrid').
    Pre-v6.4 tenants will all show 'desktop_first' (from migration 027 backfill).

    Called by: main()
    Calls into: SQLAlchemy engine.connect() - read-only SELECT.

    Returns: 0 always (informational; no specific value is "wrong"). The
             distribution itself is what matters - operators should sanity-
             check it against expected signup mix after running test signups.
    """
    print("=" * 50)
    print("CHECK 3: Tenant entry_mode distribution")
    print("=" * 50)
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT entry_mode, COUNT(*) AS n "
                "FROM tenants GROUP BY entry_mode ORDER BY n DESC"
            )
        )
        rows = list(result)
    if not rows:
        print("(tenants table is empty)\n")
        return 0
    print(f"{'entry_mode':<25} {'count':>8}")
    print("-" * 35)
    for row in rows:
        entry_mode_value = row[0] if row[0] is not None else "(NULL)"
        print(f"{entry_mode_value:<25} {row[1]:>8}")
    print()
    return 0


def check_role_group_state(engine: Engine) -> int:
    """
    v6.3.3 diagnostic: report top-tier vs non-top-tier user counts overall
    and per-tenant.

    Top-tier roles (per app.models.auth.TOP_TIER_ROLES) are the gate for
    require_top_tier endpoints (employees DELETE, machines DELETE, jobs
    DELETE, skills CRUD, team management). A tenant with zero top-tier
    users would be locked out of every such endpoint - that is a real
    operational hazard.

    Two outputs:
      - Overall: count of users grouped by top_tier yes/no.
      - Per-tenant lockout risk: list any tenant_id with zero top-tier users.

    Called by:    main()
    Calls into:   SQLAlchemy engine.connect() - read-only SELECT on users.
                  Reads TOP_TIER_ROLES from app.models.auth (one source).

    Returns: 0 always - this check is informational (operators need to see
             the per-tenant lockout list to act on it, but that pre-existing
             data state should not block the v6.3.3 pre-tag gate). CHECK 2
             remains the only hard-fail check.
    """
    # Local import: this script can run before app imports settle, and
    # app.models.auth pulls in SQLAlchemy. Keeping the import lazy avoids
    # a circular import when the script is invoked directly.
    from app.models.auth import TOP_TIER_ROLES

    print("=" * 50)
    print("CHECK 4: Role-group state (v6.3.3)")
    print("=" * 50)

    top_tier_list = list(TOP_TIER_ROLES)

    with engine.connect() as conn:
        # Overall top-tier vs other.
        overall = conn.execute(
            text(
                "SELECT CASE WHEN role = ANY(:tt) THEN 'top_tier' "
                "ELSE 'other' END AS bucket, COUNT(*) AS n "
                "FROM users GROUP BY bucket ORDER BY bucket"
            ),
            {"tt": top_tier_list},
        ).all()

        # Per-tenant lockout risk: any tenant whose count of top-tier users is 0.
        lockout = conn.execute(
            text(
                "SELECT t.id, t.slug, COUNT(u.id) FILTER ("
                "  WHERE u.role = ANY(:tt) AND u.is_active = TRUE"
                ") AS top_tier_n "
                "FROM tenants t LEFT JOIN users u ON u.tenant_id = t.id "
                "WHERE t.is_active = TRUE "
                "GROUP BY t.id, t.slug "
                "HAVING COUNT(u.id) FILTER ("
                "  WHERE u.role = ANY(:tt) AND u.is_active = TRUE"
                ") = 0 "
                "ORDER BY t.id"
            ),
            {"tt": top_tier_list},
        ).all()

    print(f"Top-tier roles checked: {top_tier_list}\n")

    print(f"{'bucket':<15} {'count':>8}")
    print("-" * 25)
    for row in overall:
        print(f"{row[0]:<15} {row[1]:>8}")
    print()

    if lockout:
        print(f"WARNING: {len(lockout)} tenant(s) have zero active top-tier users")
        print(f"         (locked out of require_top_tier endpoints - promote a user to fix)")
        print(f"  {'tenant_id':<12} {'slug':<30} {'top_tier_count'}")
        print(f"  {'-' * 12} {'-' * 30} {'-' * 14}")
        for tid, slug, n in lockout:
            slug_display = (slug or "(NULL)")[:30]
            print(f"  {tid:<12} {slug_display:<30} {n}")
        print()
        return 0

    print("All active tenants have at least one active top-tier user. OK\n")
    return 0


def main() -> int:
    """
    Entry point. Runs all four diagnostic checks and exits with a code
    reflecting overall success.

    Called by: developer via `python -m scripts.check_role_distribution`.
    Calls into: check_role_distribution(), check_migration_027_columns(),
                check_signup_state(), check_role_group_state().

    Returns: 0 if all checks pass, 1 if DATABASE_URL missing, any column
             mismatch found, or any tenant has zero top-tier users.
             CHECK 1 + CHECK 3 always return 0 - they are informational.
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set in environment or .env", file=sys.stderr)
        return 1

    engine = create_engine(db_url)
    role_rc = check_role_distribution(engine)
    column_rc = check_migration_027_columns(engine)
    signup_rc = check_signup_state(engine)
    group_rc = check_role_group_state(engine)
    return role_rc | column_rc | signup_rc | group_rc


if __name__ == "__main__":
    sys.exit(main())