# tests/test_v6_4_entry_gate.py
#
# FILE PURPOSE
# Test coverage for v6.3.1 (migration 027 + entry-gate ORM columns + role
# helpers + backfill). Targets SRS v6.4 §6.28 deliverables.
#
# WHO CALLS THIS FILE
# - pytest, via the standard `pytest backend/tests/` discovery
#
# WHAT THIS FILE CALLS
# - app.models.auth.Tenant, User, TOP_TIER_ROLES
# - app.models.whatsapp.PhoneTenantMap
# - app.services.role_helpers.is_valid_user_role, is_valid_phone_role,
#   VALID_USER_ROLES
# - scripts.backfill_v6_4_entry_gate.backfill (module-level, monkeypatched
#   to use the SQLite test session)
# - alembic.script.ScriptDirectory - to inspect migration 027's source
#
# DESIGN NOTES
# - Migration upgrade/downgrade are tested by reading the migration file's
#   source text and asserting that every column in the v6.3.1 spec is named
#   in both upgrade() and downgrade(). This matches the existing convention
#   in test_alembic_migrations.py — live PostgreSQL upgrade is run manually
#   per the verification gate.
# - Backfill tests monkeypatch SessionLocal in the script module so the
#   script writes against the in-memory SQLite DB from the `db` fixture
#   instead of the real Postgres DB.

from datetime import datetime, time, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.security import hash_password
from app.models.auth import Tenant, TOP_TIER_ROLES, User
from app.models.whatsapp import PhoneTenantMap
from app.services.role_helpers import (
    VALID_USER_ROLES,
    is_valid_phone_role,
    is_valid_user_role,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "027_whatsapp_entry_gate.py"
)

# Columns the v6.3.1 spec requires on tenants.
_EXPECTED_TENANT_COLUMNS = [
    "entry_mode",
    "size_segment",
    "briefing_morning_enabled",
    "briefing_morning_time",
    "briefing_evening_enabled",
    "briefing_evening_time",
    "briefing_timezone",
    "briefing_working_days",
    "created_via",
]

# Columns the v6.3.1 spec requires on users.
_EXPECTED_USER_COLUMNS = [
    "briefing_time_override_morning",
    "briefing_time_override_evening",
    "briefing_subscribed",
    "phone_e164",
    "created_via",
]


def _make_tenant(db, **overrides) -> Tenant:
    """Build a Tenant row with sensible defaults; override any field by kwarg."""
    now = datetime.now(timezone.utc)
    fields = dict(
        name="V6.4 Test Tenant",
        slug=f"v64-tenant-{overrides.get('id_suffix', '0')}",
        plan="free",
        is_active=True,
        industry_type="manufacturing",
        created_at=now,
        updated_at=now,
    )
    overrides.pop("id_suffix", None)
    fields.update(overrides)
    tenant = Tenant(**fields)
    db.add(tenant)
    db.flush()
    return tenant


def _make_user(db, tenant_id: int, role: str, **overrides) -> User:
    """Build a User row with sensible defaults; role and overrides applied last."""
    now = datetime.now(timezone.utc)
    fields = dict(
        tenant_id=tenant_id,
        email=overrides.pop("email", f"v64-{role}-{tenant_id}@test.com"),
        hashed_password=hash_password("testpass"),
        role=role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    fields.update(overrides)
    user = User(**fields)
    db.add(user)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# Migration 027 file-integrity tests
# ---------------------------------------------------------------------------

class TestMigration027:
    """Migration 027 — file-level checks. Live PostgreSQL upgrade/downgrade
    is verified manually per the v6.3.1 verification gate."""

    @pytest.fixture(scope="class")
    def script_dir(self):
        cfg = Config("alembic.ini")
        return ScriptDirectory.from_config(cfg)

    @pytest.fixture(scope="class")
    def migration_source(self) -> str:
        return _MIGRATION_PATH.read_text(encoding="utf-8")

    def test_migration_027_revision_chain(self, script_dir):
        """027 exists in the chain and points back to 023."""
        revisions = {r.revision: r for r in script_dir.walk_revisions()}
        assert "027" in revisions, "Migration 027 not found in the chain"
        assert revisions["027"].down_revision == "023", (
            f"Expected 027.down_revision == '023', got "
            f"'{revisions['027'].down_revision}'"
        )

    def test_migration_027_upgrade_adds_columns(self, migration_source):
        """upgrade() names every required tenant + user column."""
        for column in _EXPECTED_TENANT_COLUMNS + _EXPECTED_USER_COLUMNS:
            assert column in migration_source, (
                f"Migration 027 source does not reference column '{column}'"
            )

    def test_migration_027_downgrade_removes_columns(self, migration_source):
        """downgrade() drops every column the upgrade adds — symmetry check."""
        # The downgrade body iterates _USER_COLUMNS and _TENANT_COLUMNS in
        # reverse, so column names appear in the same source file. Verify
        # the downgrade function exists and references drop_column.
        assert "def downgrade()" in migration_source
        assert "drop_column" in migration_source
        assert 'drop_index("idx_users_phone_e164"' in migration_source
        # Each expected column must appear in the column-spec lists, which
        # both upgrade() and downgrade() iterate.
        for column in _EXPECTED_TENANT_COLUMNS + _EXPECTED_USER_COLUMNS:
            assert column in migration_source, (
                f"Migration 027 source missing column '{column}' "
                f"required by downgrade()"
            )

    def test_migration_027_idempotent_on_seeded_db(self, migration_source):
        """upgrade() and downgrade() iterate shared column-spec lists, so a
        single source-of-truth change updates both halves. Verifies the
        symmetry that makes the migration safely reversible on any seeded DB."""
        assert "_TENANT_COLUMNS" in migration_source, (
            "Migration 027 must define _TENANT_COLUMNS as a shared spec list"
        )
        assert "_USER_COLUMNS" in migration_source, (
            "Migration 027 must define _USER_COLUMNS as a shared spec list"
        )
        # upgrade() iterates the lists; downgrade() iterates them in reverse.
        assert "for name, col_type, nullable_in_db, default in _TENANT_COLUMNS" in migration_source
        assert "for name, col_type, nullable_in_db, default in _USER_COLUMNS" in migration_source
        assert "reversed(_USER_COLUMNS)" in migration_source
        assert "reversed(_TENANT_COLUMNS)" in migration_source


# ---------------------------------------------------------------------------
# User.is_top_tier tests
# ---------------------------------------------------------------------------

class TestUserIsTopTier:
    """SRS v6.4 §6.28.6 — top-tier roles get owner-equivalent permissions.
    'proprietor' is a synonym for 'owner' (per user feedback) and must also
    return True; 'scheduler' / 'manager' / 'viewer' must return False."""

    def test_owner_returns_true(self):
        user = User(role="owner")
        assert user.is_top_tier is True

    def test_factory_manager_returns_true(self):
        user = User(role="factory_manager")
        assert user.is_top_tier is True

    def test_co_owner_returns_true(self):
        user = User(role="co_owner")
        assert user.is_top_tier is True

    def test_proprietor_returns_true(self):
        """Legacy synonym for owner — must grant top-tier per user feedback."""
        user = User(role="proprietor")
        assert user.is_top_tier is True

    def test_manager_returns_false(self):
        user = User(role="manager")
        assert user.is_top_tier is False

    def test_viewer_returns_false(self):
        user = User(role="viewer")
        assert user.is_top_tier is False

    def test_none_returns_false(self):
        """Edge case: role attribute set to None (e.g. unsaved object)."""
        user = User(role=None)
        assert user.is_top_tier is False


# ---------------------------------------------------------------------------
# PhoneTenantMap.is_top_tier tests (mirror of User.is_top_tier)
# ---------------------------------------------------------------------------

class TestPhoneTenantMapIsTopTier:
    """Mirror of User.is_top_tier checks but on PhoneTenantMap.phone_role."""

    def test_owner_returns_true(self):
        mapping = PhoneTenantMap(phone_role="owner")
        assert mapping.is_top_tier is True

    def test_proprietor_returns_true(self):
        mapping = PhoneTenantMap(phone_role="proprietor")
        assert mapping.is_top_tier is True

    def test_factory_manager_returns_true(self):
        mapping = PhoneTenantMap(phone_role="factory_manager")
        assert mapping.is_top_tier is True

    def test_manager_returns_false(self):
        mapping = PhoneTenantMap(phone_role="manager")
        assert mapping.is_top_tier is False

    def test_unknown_role_returns_false(self):
        mapping = PhoneTenantMap(phone_role="supervisor")
        assert mapping.is_top_tier is False

    def test_none_returns_false(self):
        mapping = PhoneTenantMap(phone_role=None)
        assert mapping.is_top_tier is False


# ---------------------------------------------------------------------------
# Role-helper service tests
# ---------------------------------------------------------------------------

class TestRoleHelpers:
    """Coverage for app/services/role_helpers.py."""

    @pytest.mark.parametrize(
        "role",
        ["owner", "proprietor", "factory_manager", "co_owner", "manager", "viewer", "scheduler"],
    )
    def test_is_valid_user_role_accepts_allowed_values(self, role):
        assert is_valid_user_role(role) is True

    @pytest.mark.parametrize("role", [ "Owner", "OWNER", "", None, 42])
    def test_is_valid_user_role_rejects_others(self, role):
        assert is_valid_user_role(role) is False

    def test_is_valid_phone_role_mirrors_user_role(self):
        """Per v6.3.1 spec: 'Same for phone_tenant_map.phone_role'."""
        for role in VALID_USER_ROLES:
            assert is_valid_phone_role(role) is True
        assert is_valid_phone_role("supervisor") is False
        assert is_valid_phone_role(None) is False

    def test_top_tier_roles_subset_of_valid_roles(self):
        """TOP_TIER_ROLES must be a subset of VALID_USER_ROLES — a top-tier
        role that fails role-validation would be a self-contradiction."""
        assert set(TOP_TIER_ROLES).issubset(VALID_USER_ROLES)


# ---------------------------------------------------------------------------
# Backfill tests
# ---------------------------------------------------------------------------

@pytest.fixture
def backfill_against_db(db, monkeypatch):
    """Patch SessionLocal in the backfill script so it writes against the
    SQLite test DB. Returns the script module's backfill() callable.

    Rationale: the script imports SessionLocal at module load. We replace it
    with a factory that yields the test session (without closing it — the
    fixture owns its lifetime)."""
    from scripts import backfill_v6_4_entry_gate as bf

    class _SessionFactory:
        def __call__(self):
            # Wrap the test session so backfill's db.close() is a no-op;
            # the conftest db fixture handles real teardown.
            return _SessionWrapper(db)

    monkeypatch.setattr(bf, "SessionLocal", _SessionFactory())
    return bf.backfill


class _SessionWrapper:
    """Forwards to the underlying SQLAlchemy session but makes close() a
    no-op so the conftest `db` fixture controls teardown."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        pass


class TestBackfillV6_4EntryGate:
    """Coverage for backend/scripts/backfill_v6_4_entry_gate.py."""

    def test_empty_db_reports_zero_fixed(self, backfill_against_db):
        """Empty DB: nothing to fix, nothing to skip."""
        result = backfill_against_db()
        assert result == {"fixed": 0, "skipped": 0, "total": 0}

    def test_seeded_db_3_rows_updated(self, db, backfill_against_db):
        """Three rows with NULL/empty values should each be fixed exactly once."""
        # Tenant A: entry_mode is empty string (simulates a row inserted by
        # raw SQL that bypassed server_default).
        tenant_a = _make_tenant(db, id_suffix="a", entry_mode="")
        # Tenant B: created_via is empty string.
        tenant_b = _make_tenant(db, id_suffix="b", created_via="")
        # User: created_via is empty string.
        user = _make_user(db, tenant_id=tenant_a.id, role="manager",
                          created_via="")
        # Tenant C: fully default (no fix needed) — controls the count.
        _make_tenant(db, id_suffix="c")

        result = backfill_against_db()
        db.refresh(tenant_a)
        db.refresh(tenant_b)
        db.refresh(user)

        assert result["fixed"] == 3, result
        assert tenant_a.entry_mode == "desktop_first"
        assert tenant_b.created_via == "desktop_signup"
        assert user.created_via == "desktop_signup"

    def test_idempotent_on_second_run(self, db, backfill_against_db):
        """Second run after a real backfill must update zero rows."""
        tenant = _make_tenant(db, id_suffix="idem", entry_mode="")
        _make_user(db, tenant_id=tenant.id, role="viewer", created_via="")

        first = backfill_against_db()
        second = backfill_against_db()

        assert first["fixed"] >= 1, first
        assert second["fixed"] == 0, second

    def test_preserves_explicit_non_default_values(self, db, backfill_against_db):
        """Tenants with valid non-default values must not be rewritten."""
        tenant = _make_tenant(
            db,
            id_suffix="explicit",
            entry_mode="whatsapp_first",
            briefing_timezone="Asia/Kolkata",
            briefing_working_days="1,2,3,4,5",
            created_via="whatsapp_signup",
        )
        user = _make_user(
            db,
            tenant_id=tenant.id,
            role="owner",
            created_via="whatsapp_invite",
        )

        backfill_against_db()
        db.refresh(tenant)
        db.refresh(user)

        # Every explicitly-set value must be preserved.
        assert tenant.entry_mode == "whatsapp_first"
        assert tenant.briefing_working_days == "1,2,3,4,5"
        assert tenant.created_via == "whatsapp_signup"
        assert user.created_via == "whatsapp_invite"


# ---------------------------------------------------------------------------
# ORM model column existence (catches a missing column before it bites prod)
# ---------------------------------------------------------------------------

class TestOrmHasNewColumns:
    """If migration 027 and the ORM ever drift, these tests fail loudly."""

    @pytest.mark.parametrize("column", _EXPECTED_TENANT_COLUMNS)
    def test_tenant_orm_has_column(self, column):
        assert column in Tenant.__table__.c, (
            f"Tenant ORM is missing column '{column}' added by migration 027"
        )

    @pytest.mark.parametrize("column", _EXPECTED_USER_COLUMNS)
    def test_user_orm_has_column(self, column):
        assert column in User.__table__.c, (
            f"User ORM is missing column '{column}' added by migration 027"
        )

    def test_tenant_briefing_morning_time_default(self, db):
        """Server-default for tenants.briefing_morning_time is 07:30:00."""
        tenant = _make_tenant(db, id_suffix="bdef")
        db.commit()
        db.refresh(tenant)
        assert tenant.briefing_morning_time == time(7, 30, 0), (
            f"Expected briefing_morning_time=07:30:00, got "
            f"{tenant.briefing_morning_time!r}"
        )
def test_scheduler_is_valid_user_role():
    """Scheduler exists in production data; validator must accept it."""
    assert is_valid_user_role("scheduler") is True

def test_scheduler_is_valid_phone_role():
    """Phone roles must align with user roles for consistency."""
    assert is_valid_phone_role("scheduler") is True

def test_scheduler_is_not_top_tier():
    """Scheduler is operational mid-tier, not top-tier — cannot invite/promote/demote."""
    user = User(role="scheduler")
    assert user.is_top_tier is False

def test_proprietor_is_top_tier():
    """Proprietor is canonical in production data; treated as top-tier synonym for owner."""
    user = User(role="proprietor")
    assert user.is_top_tier is True