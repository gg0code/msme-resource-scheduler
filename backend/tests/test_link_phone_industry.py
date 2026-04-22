# test_link_phone_industry.py
# Branch: v5-whatsapp
#
# Tests for BUG-6 fix: link_phone() must store tenant.industry_type,
# not the stale "printing" default that came from the broken hasattr guard.
#
# Uses SQLite in-memory via conftest fixtures (db, client).

import pytest
from datetime import datetime, timezone
from sqlalchemy import text as sa_text
from sqlalchemy.sql.schema import DefaultClause

from app.models.auth import Tenant, User
from app.models.whatsapp import PhoneTenantMap
from app.core.security import create_access_token, hash_password


@pytest.fixture(autouse=True)
def patch_linked_at_for_sqlite():
    # phone_tenant_map.linked_at uses server_default=text("now()") — PostgreSQL
    # only. Swap to SQLite-compatible CURRENT_TIMESTAMP for in-memory tests.
    # Same pattern conftest uses for JSONB -> JSON.
    col = PhoneTenantMap.__table__.c.linked_at
    original = col.server_default
    col.server_default = DefaultClause(sa_text("CURRENT_TIMESTAMP"))
    yield
    col.server_default = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant_and_headers(db, industry_type):
    """Create a tenant+user with the given industry_type; return auth headers."""
    now = datetime.now(timezone.utc)
    tenant = Tenant(
        name="Bug6 Test Tenant",
        slug=f"bug6-test-{industry_type or 'none'}",
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
        email=f"bug6-{industry_type or 'none'}@test.com",
        hashed_password=hash_password("testpass"),
        role="proprietor",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()

    token = create_access_token(
        user_id=user.id,
        tenant_id=tenant.id,
        role="proprietor",
    )
    return {"Authorization": f"Bearer {token}"}


LINK_PAYLOAD = {
    "phone_number": "+919988776655",
    "display_name": "Test Owner",
    "phone_role": "owner",
    "consent_given": True,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_link_phone_stores_tenant_industry_type(db, client):
    """link_phone() stores tenant.industry_type, not the stale "printing" fallback."""
    headers = _make_tenant_and_headers(db, "fabrication")

    resp = client.post(
        "/api/v1/whatsapp/link-phone",
        json=LINK_PAYLOAD,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    row = db.query(PhoneTenantMap).filter(
        PhoneTenantMap.phone_number == LINK_PAYLOAD["phone_number"]
    ).first()
    assert row is not None
    assert row.industry_type == "fabrication"


def test_link_phone_industry_type_none_when_tenant_has_none(db, client):
    """When tenant.industry_type is None, the stored PhoneTenantMap value is also None.

    The "printing" fallback in link_phone() only fires when the tenant row is
    missing entirely (impossible in a live session). Downstream, resolve_identity()
    applies its own fallback (or "manufacturing") before reaching the AI.
    """
    headers = _make_tenant_and_headers(db, None)

    payload = {**LINK_PAYLOAD, "phone_number": "+919988776644"}
    resp = client.post(
        "/api/v1/whatsapp/link-phone",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    row = db.query(PhoneTenantMap).filter(
        PhoneTenantMap.phone_number == "+919988776644"
    ).first()
    assert row is not None
    assert row.industry_type is None
