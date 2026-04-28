# tests/test_signup_v6_4.py
#
# FILE PURPOSE
# Test coverage for v6.3.2 — signup flow changes (SRS v6.4 Section 6.28).
# Exercises:
#   - Pydantic schema validation: team_size required, conditional phone,
#     conditional email/password, E.164 phone format.
#   - Service-level register_tenant_and_user: entry_mode + size_segment +
#     created_via wiring on Tenant; phone_e164 + created_via on User;
#     conditional PhoneTenantMap creation honouring tenant.industry_type
#     (BUG-6 regression extension); next_step routing key.
#   - Router-level /auth/register: demo seeder still runs, response
#     payload includes next_step.
#
# WHO CALLS THIS FILE
# - pytest via standard tests/ discovery (not marked @pytest.mark.integration)
#
# WHAT THIS FILE CALLS
# - app.schemas.auth.RegisterRequest
# - app.services.auth_service.register_tenant_and_user,
#   determine_entry_mode_and_segment
# - app.models.auth.Tenant, User
# - app.models.whatsapp.PhoneTenantMap
# - app.models.skill.Skill (demo seeder regression)
#
# DESIGN NOTES
# - phone_tenant_map.linked_at uses server_default=text("now()") — Postgres
#   only. The autouse fixture swaps it to CURRENT_TIMESTAMP for SQLite,
#   matching the pattern in tests/test_link_phone_industry.py.
# - Service-level tests call register_tenant_and_user(payload, db) directly
#   so they exercise the transaction boundary without needing the router's
#   seeder hooks. The single test that needs the seeder uses the client
#   fixture (TestClient) so the router actually runs.

import pytest
from pydantic import ValidationError
from sqlalchemy import text as sa_text
from sqlalchemy.sql.schema import DefaultClause

from app.models.auth import RefreshToken, Tenant, User
from app.models.whatsapp import PhoneTenantMap
from app.schemas.auth import RegisterRequest
from app.services import auth_service
from app.services.auth_service import determine_entry_mode_and_segment


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    """SQLite has no now() function. Several columns use server_default=
    text('now()') which fires at INSERT — patch them to CURRENT_TIMESTAMP
    for unit tests. PhoneTenantMap.linked_at follows the same pattern as
    tests/test_link_phone_industry.py.
    """
    patched = []
    for table_attr in (
        Tenant.__table__,
        User.__table__,
        RefreshToken.__table__,
        PhoneTenantMap.__table__,
    ):
        for col in table_attr.columns:
            if col.server_default is None:
                continue
            arg = getattr(col.server_default, "arg", None)
            text_value = str(arg) if arg is not None else ""
            if "now()" in text_value.lower():
                patched.append((col, col.server_default))
                col.server_default = DefaultClause(sa_text("CURRENT_TIMESTAMP"))
    yield
    for col, original in patched:
        col.server_default = original


def _payload(**overrides) -> dict:
    """Default valid signup payload with all required fields. Override per-test."""
    base = {
        "email": "owner@example.com",
        "password": "longenough",
        "company_name": "Example Co",
        "slug": "example-co",
        "industry_type": "printing",
        "team_size": "51+",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# determine_entry_mode_and_segment — pure mapping
# ---------------------------------------------------------------------------

class TestEntryModeMapping:

    def test_small_team_maps_to_whatsapp_first_small(self):
        assert determine_entry_mode_and_segment("1-15") == ("whatsapp_first", "small")

    def test_medium_team_maps_to_hybrid_medium(self):
        assert determine_entry_mode_and_segment("16-50") == ("hybrid", "medium")

    def test_large_team_maps_to_desktop_first_large(self):
        assert determine_entry_mode_and_segment("51+") == ("desktop_first", "large")

    def test_unknown_team_size_raises(self):
        with pytest.raises(ValueError, match="Unknown team_size"):
            determine_entry_mode_and_segment("100+")


# ---------------------------------------------------------------------------
# Pydantic schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:

    def test_small_team_no_phone_raises(self):
        # team_size '1-15' (whatsapp_first) requires phone_e164.
        with pytest.raises(ValidationError, match="phone_e164 is required"):
            RegisterRequest(**_payload(
                team_size="1-15",
                phone_e164=None,
                email=None,
                password=None,
            ))

    def test_small_team_with_phone_succeeds_without_password(self):
        req = RegisterRequest(**_payload(
            team_size="1-15",
            phone_e164="+919876543210",
            email=None,
            password=None,
        ))
        assert req.team_size == "1-15"
        assert req.phone_e164 == "+919876543210"
        assert req.password is None

    def test_medium_team_requires_email_and_password(self):
        # hybrid requires phone AND email AND password.
        with pytest.raises(ValidationError, match="email is required"):
            RegisterRequest(**_payload(
                team_size="16-50",
                phone_e164="+919876543210",
                email=None,
            ))
        with pytest.raises(ValidationError, match="password is required"):
            RegisterRequest(**_payload(
                team_size="16-50",
                phone_e164="+919876543210",
                password=None,
            ))

    def test_large_team_no_password_fails(self):
        with pytest.raises(ValidationError, match="password is required"):
            RegisterRequest(**_payload(team_size="51+", password=None))

    def test_invalid_phone_format(self):
        with pytest.raises(ValidationError, match="E.164"):
            RegisterRequest(**_payload(
                team_size="1-15",
                phone_e164="9876543210",  # missing leading +
                email=None,
                password=None,
            ))


# ---------------------------------------------------------------------------
# register_tenant_and_user — service-layer integration
# ---------------------------------------------------------------------------

class TestRegisterService:

    def test_signup_small_team_creates_whatsapp_first_tenant(self, db):
        result = auth_service.register_tenant_and_user(
            RegisterRequest(**_payload(
                slug="small-team-co",
                team_size="1-15",
                phone_e164="+919811111111",
                email=None,
                password=None,
            )),
            db,
        )
        tenant = db.query(Tenant).filter(Tenant.id == result["tenant_id"]).one()
        assert tenant.entry_mode == "whatsapp_first"
        assert tenant.size_segment == "small"
        assert tenant.created_via == "whatsapp_first_signup"
        assert result["next_step"] == "connect_whatsapp"

    def test_signup_small_team_creates_phone_tenant_map(self, db):
        # BUG-6 regression extension: PhoneTenantMap row must carry the
        # tenant's industry_type, not the legacy 'printing' fallback.
        auth_service.register_tenant_and_user(
            RegisterRequest(**_payload(
                slug="small-fab-co",
                industry_type="fabrication",
                team_size="1-15",
                phone_e164="+919811111112",
                email=None,
                password=None,
            )),
            db,
        )
        row = db.query(PhoneTenantMap).filter(
            PhoneTenantMap.phone_number == "+919811111112"
        ).one()
        assert row.industry_type == "fabrication"
        assert row.is_active is True
        assert row.phone_role == "owner"

    def test_signup_medium_team_creates_hybrid_tenant_with_phone_map(self, db):
        result = auth_service.register_tenant_and_user(
            RegisterRequest(**_payload(
                slug="hybrid-co",
                email="hybrid@example.com",
                team_size="16-50",
                phone_e164="+919811111113",
            )),
            db,
        )
        tenant = db.query(Tenant).filter(Tenant.id == result["tenant_id"]).one()
        assert tenant.entry_mode == "hybrid"
        assert tenant.size_segment == "medium"
        # hybrid still uses 'desktop_signup' marker because the user has both
        # a password (web login) and a phone (WhatsApp). Only entry_mode
        # 'whatsapp_first' uses the special 'whatsapp_first_signup' marker.
        assert tenant.created_via == "desktop_signup"
        assert result["next_step"] == "connect_whatsapp"
        assert db.query(PhoneTenantMap).filter(
            PhoneTenantMap.phone_number == "+919811111113"
        ).count() == 1

    def test_signup_large_team_creates_desktop_first_tenant_no_phone_map(self, db):
        result = auth_service.register_tenant_and_user(
            RegisterRequest(**_payload(
                slug="large-co",
                email="large@example.com",
                team_size="51+",
            )),
            db,
        )
        tenant = db.query(Tenant).filter(Tenant.id == result["tenant_id"]).one()
        assert tenant.entry_mode == "desktop_first"
        assert tenant.size_segment == "large"
        assert tenant.created_via == "desktop_signup"
        assert result["next_step"] == "dashboard"
        # No phone provided -> no PhoneTenantMap row.
        assert db.query(PhoneTenantMap).count() == 0

    def test_signup_large_team_with_phone_does_not_link(self, db):
        # Even if a 51+ tenant supplies a phone, the v6.3.2 contract leaves
        # PhoneTenantMap creation to the LinkWhatsApp.tsx page (post-signup).
        # Phone is stored on User.phone_e164 but no PhoneTenantMap row.
        auth_service.register_tenant_and_user(
            RegisterRequest(**_payload(
                slug="large-with-phone-co",
                email="lwp@example.com",
                team_size="51+",
                phone_e164="+919811111114",
            )),
            db,
        )
        user = db.query(User).filter(User.email == "lwp@example.com").one()
        assert user.phone_e164 == "+919811111114"
        assert db.query(PhoneTenantMap).count() == 0

    def test_signup_returns_correct_next_step(self, db):
        # Single check covering all three entry_mode values.
        # whatsapp_first
        r1 = auth_service.register_tenant_and_user(
            RegisterRequest(**_payload(
                slug="ns-small", team_size="1-15",
                phone_e164="+919811222201", email=None, password=None,
            )),
            db,
        )
        assert r1["next_step"] == "connect_whatsapp"
        # hybrid
        r2 = auth_service.register_tenant_and_user(
            RegisterRequest(**_payload(
                slug="ns-medium", email="ns2@x.com",
                team_size="16-50", phone_e164="+919811222202",
            )),
            db,
        )
        assert r2["next_step"] == "connect_whatsapp"
        # desktop_first
        r3 = auth_service.register_tenant_and_user(
            RegisterRequest(**_payload(
                slug="ns-large", email="ns3@x.com",
                team_size="51+",
            )),
            db,
        )
        assert r3["next_step"] == "dashboard"

    def test_signup_industry_attribution_per_vertical(self, db):
        # One whatsapp_first signup per vertical — assert each PhoneTenantMap
        # row carries the matching industry_type. Direct extension of
        # BUG-6 (link_phone-side) regression coverage to the signup path.
        verticals = [
            ("printing",      "+919811333301"),
            ("manufacturing", "+919811333302"),
            ("fabrication",   "+919811333303"),
            ("field_service", "+919811333304"),
        ]
        for industry, phone in verticals:
            auth_service.register_tenant_and_user(
                RegisterRequest(**_payload(
                    slug=f"attr-{industry.replace('_', '-')}",
                    industry_type=industry,
                    team_size="1-15",
                    phone_e164=phone,
                    email=None,
                    password=None,
                )),
                db,
            )
        for industry, phone in verticals:
            row = db.query(PhoneTenantMap).filter(
                PhoneTenantMap.phone_number == phone
            ).one()
            assert row.industry_type == industry, \
                f"Expected {industry}, got {row.industry_type} for {phone}"

    def test_signup_small_team_no_password_persists_empty_hash(self, db):
        # whatsapp_first omits password — service stores '' so the NOT NULL
        # constraint holds without producing a usable bcrypt verify.
        auth_service.register_tenant_and_user(
            RegisterRequest(**_payload(
                slug="no-pw-co",
                team_size="1-15",
                phone_e164="+919811444401",
                email=None,
                password=None,
            )),
            db,
        )
        # User email is synthesized when omitted.
        user = db.query(User).filter(User.tenant_id != None).order_by(User.id.desc()).first()
        assert user.hashed_password == ""
        assert user.phone_e164 == "+919811444401"


# ---------------------------------------------------------------------------
# Router-level — demo seeder regression + response shape
# ---------------------------------------------------------------------------

class TestRouterIntegration:

    def test_signup_response_includes_next_step(self, client):
        # POST through the real router. Demo seeder runs on the SQLite test
        # session via the get_db override.
        resp = client.post("/auth/register", json={
            "company_name": "Router Test Co",
            "slug": "router-test-co",
            "email": "router@example.com",
            "password": "longenough",
            "industry_type": "printing",
            "team_size": "51+",
        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["access_token"]
        assert body["next_step"] == "dashboard"

    def test_signup_demo_seeder_still_runs(self, db, client):
        # Router runs seed_demo_data in a try/except — if it fails it logs
        # and continues. We assert the seeded skills landed in the DB so a
        # future regression that drops the seeder hook is caught.
        from app.models.skill import Skill
        resp = client.post("/auth/register", json={
            "company_name": "Seed Test Co",
            "slug": "seed-test-co-v64",
            "email": "seed@example.com",
            "password": "longenough",
            "industry_type": "printing",
            "team_size": "51+",
        })
        assert resp.status_code == 201, resp.text
        # Find the new tenant by slug.
        tenant = db.query(Tenant).filter(Tenant.slug == "seed-test-co-v64").one()
        assert db.query(Skill).filter(Skill.tenant_id == tenant.id).count() > 0
