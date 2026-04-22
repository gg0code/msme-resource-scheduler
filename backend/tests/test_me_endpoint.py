# tests/test_me_endpoint.py
# BUG-5: Verify /auth/me returns industry_type sourced from the Tenant row.

from datetime import datetime, timezone
from app.models.auth import Tenant, User
from app.core.security import create_access_token, hash_password


def _setup(db, industry_type, slug_suffix):
    now = datetime.now(timezone.utc)
    tenant = Tenant(
        name="ME Test Tenant",
        slug=f"me-test-{slug_suffix}",
        plan="paid",
        is_active=True,
        industry_type=industry_type,
        created_at=now,
        updated_at=now,
    )
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"me-test-{slug_suffix}@test.com",
        hashed_password=hash_password("testpass"),
        role="proprietor",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    token = create_access_token(user_id=user.id, tenant_id=tenant.id, role="proprietor")
    return token


class TestMeEndpoint:

    def test_me_returns_industry_type_for_tenant_with_value(self, client, db):
        token = _setup(db, "fabrication", "fab")
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["industry_type"] == "fabrication"

    def test_me_returns_none_for_tenant_with_null_industry(self, client, db):
        token = _setup(db, None, "null")
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["industry_type"] is None

    def test_me_response_shape_includes_all_expected_fields(self, client, db):
        token = _setup(db, "printing", "shape")
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        for field in ("id", "email", "role", "tenant_id", "is_active", "industry_type"):
            assert field in data, f"Missing field: {field}"
