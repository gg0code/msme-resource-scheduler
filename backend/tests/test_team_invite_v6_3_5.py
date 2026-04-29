# tests/test_team_invite_v6_3_5.py
#
# FILE PURPOSE
# v6.3.5 test coverage for the Team & Roles WhatsApp-invite consolidation:
#   - InviteRequest channel routing (whatsapp / desktop / inferred)
#   - consent gate fires only on explicit channel='whatsapp'
#   - WhatsApp invites stage a [MOCK ALERT] welcome + member.invited_whatsapp
#     event row + a PhoneTenantMap row with consent_given=False
#   - Synthesised emails are stripped from TeamMemberOut.email
#   - whatsapp_status is computed correctly from PhoneTenantMap state
#   - list_team_members_with_status is N+1-safe (constant query count)
#   - 4 router-level TestClient assertions for the HTTP shape
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.team_service (invite_member, list_team_members_with_status,
#       serialise_member_for_response, _is_synthesised_email,
#       _compute_whatsapp_status)
#   app.schemas.team (InviteRequest, TeamMemberOut)
#   app.models.{auth.User, auth.Tenant, event.Event, whatsapp.PhoneTenantMap}
#
# DESIGN NOTES
# - patch_now_defaults_for_sqlite mirrors test_team_management.py to keep
#   this file self-contained.
# - Mock-mode log assertions use caplog (pytest's log capture) - matches
#   how test_briefings.py asserts on dispatcher logs.

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import event as sa_event, text as sa_text
from sqlalchemy.sql.schema import DefaultClause

from app.core.security import create_access_token, hash_password
from app.models.auth import RefreshToken, Tenant, User
from app.models.event import Event
from app.models.whatsapp import PhoneTenantMap
from app.schemas.team import InviteRequest, TeamMemberOut
from app.services import team_service
from app.services.team_service import (
    _compute_whatsapp_status, _is_synthesised_email,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    """Swap text("now()") server defaults to CURRENT_TIMESTAMP for SQLite."""
    patched = []
    for table_attr in (
        Tenant.__table__,
        User.__table__,
        RefreshToken.__table__,
        PhoneTenantMap.__table__,
        Event.__table__,
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


_TENANT_COUNTER = {"n": 0}


def _make_tenant(db, *, name: str = "Acme Factory") -> Tenant:
    _TENANT_COUNTER["n"] += 1
    now = datetime.now(timezone.utc)
    tenant = Tenant(
        name=name,
        slug=f"acme-v635-{_TENANT_COUNTER['n']}",
        plan="free",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(tenant)
    db.flush()
    return tenant


def _make_user(
    db, *,
    tenant: Tenant,
    role: str = "proprietor",
    email: str | None = None,
    is_active: bool = True,
) -> User:
    now = datetime.now(timezone.utc)
    user = User(
        tenant_id=tenant.id,
        email=email or f"{role}-{_TENANT_COUNTER['n']}-{id(role)}@test.com",
        hashed_password=hash_password("testpass"),
        role=role,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# Service-direct: synthesised email helper
# ---------------------------------------------------------------------------

class TestSynthesisedEmail:

    def test_invite_synthesised_email_detected(self):
        assert _is_synthesised_email("invite-abcd1234@invite.zetaops.com") is True

    def test_legacy_whatsapp_local_synthesised_email_detected(self):
        assert _is_synthesised_email("acme+nomail@whatsapp.local") is True

    def test_real_email_not_synthesised(self):
        assert _is_synthesised_email("ravi@example.com") is False

    def test_none_is_not_synthesised(self):
        assert _is_synthesised_email(None) is False


# ---------------------------------------------------------------------------
# Service-direct: _compute_whatsapp_status truth table
# ---------------------------------------------------------------------------

class TestWhatsAppStatusComputation:

    def _mapping(self, *, is_active: bool, consent: bool) -> PhoneTenantMap:
        # Build a transient, unsaved instance - no DB round-trip needed.
        m = PhoneTenantMap()
        m.is_active = is_active
        m.consent_given = consent
        return m

    def test_no_mapping_is_none(self):
        assert _compute_whatsapp_status(None) == "none"

    def test_inactive_mapping_is_disconnected(self):
        m = self._mapping(is_active=False, consent=True)
        assert _compute_whatsapp_status(m) == "disconnected"

    def test_active_no_consent_is_invited(self):
        m = self._mapping(is_active=True, consent=False)
        assert _compute_whatsapp_status(m) == "invited"

    def test_active_with_consent_is_active(self):
        m = self._mapping(is_active=True, consent=True)
        assert _compute_whatsapp_status(m) == "active"


# ---------------------------------------------------------------------------
# Service-direct: invite_member channel routing
# ---------------------------------------------------------------------------

class TestInviteChannel:

    def test_whatsapp_channel_emits_welcome_alert(self, db, caplog):
        """Explicit channel='whatsapp' + consent -> [MOCK ALERT] log line +
        PhoneTenantMap row + member.invited_whatsapp event row."""
        import logging
        caplog.set_level(logging.INFO, logger="app.services.team_invite_whatsapp")

        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        new_user, temp_password = team_service.invite_member(
            tenant_id=tenant.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=InviteRequest(
                email_or_phone="+919999900001",
                role="manager",
                channel="whatsapp",
                consent_given=True,
                name="Suresh",
            ),
            db=db,
        )

        # The invitee authenticates via WhatsApp HAAN, so no temp password.
        assert temp_password is None

        # PhoneTenantMap row created with the right shape.
        mapping = (
            db.query(PhoneTenantMap)
            .filter(PhoneTenantMap.user_id == new_user.id)
            .one()
        )
        assert mapping.phone_number == "+919999900001"
        assert mapping.consent_given is False
        assert mapping.is_active is True
        assert mapping.display_name == "Suresh"

        # Mock-mode log line was emitted.
        assert any(
            "[MOCK ALERT] Type=invite_welcome" in r.message
            and "****0001" in r.message
            for r in caplog.records
        ), f"Expected mock alert log; got: {[r.message for r in caplog.records]}"

        # Audit event row staged.
        events = (
            db.query(Event)
            .filter(Event.event_type == "member.invited_whatsapp")
            .all()
        )
        assert len(events) == 1
        assert events[0].entity_id == new_user.id
        assert events[0].payload["dispatch_mode"] == "mock"
        assert events[0].payload["sent_ok"] is True

    def test_desktop_channel_unchanged_back_compat(self, db):
        """Explicit channel='desktop' returns temp_password and creates NO
        PhoneTenantMap, NO welcome alert."""
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        new_user, temp_password = team_service.invite_member(
            tenant_id=tenant.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=InviteRequest(
                email_or_phone="ravi@example.com",
                role="manager",
                channel="desktop",
                consent_given=False,  # not required for desktop
            ),
            db=db,
        )

        assert temp_password is not None and len(temp_password) > 10
        assert new_user.email == "ravi@example.com"
        # No PhoneTenantMap, no audit event for whatsapp dispatch.
        assert (
            db.query(PhoneTenantMap)
            .filter(PhoneTenantMap.user_id == new_user.id)
            .count() == 0
        )
        assert (
            db.query(Event)
            .filter(Event.event_type == "member.invited_whatsapp")
            .count() == 0
        )

    def test_whatsapp_channel_requires_consent(self, db):
        """Explicit channel='whatsapp' + consent_given=False -> HTTP 400."""
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        with pytest.raises(HTTPException) as excinfo:
            team_service.invite_member(
                tenant_id=tenant.id,
                actor_user_id=owner.id,
                actor_role=owner.role,
                payload=InviteRequest(
                    email_or_phone="+919999900002",
                    role="manager",
                    channel="whatsapp",
                    consent_given=False,
                ),
                db=db,
            )
        assert excinfo.value.status_code == 400
        assert "consent_given" in excinfo.value.detail

    def test_desktop_channel_does_not_require_consent(self, db):
        """Explicit channel='desktop' should ignore consent_given."""
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        new_user, _ = team_service.invite_member(
            tenant_id=tenant.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=InviteRequest(
                email_or_phone="kim@example.com",
                role="manager",
                channel="desktop",
                consent_given=False,
            ),
            db=db,
        )
        assert new_user.email == "kim@example.com"

    def test_back_compat_v6_3_3_phone_invite(self, db):
        """v6.3.3 caller (channel=None, phone) keeps working - no consent
        gate, no PhoneTenantMap, returns temp_password."""
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        new_user, temp_password = team_service.invite_member(
            tenant_id=tenant.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=InviteRequest(
                email_or_phone="+919999900003",
                role="manager",
            ),
            db=db,
        )
        assert temp_password is not None
        assert (
            db.query(PhoneTenantMap)
            .filter(PhoneTenantMap.user_id == new_user.id)
            .count() == 0
        )

    def test_explicit_channel_shape_mismatch_400(self, db):
        """channel='whatsapp' with an email address -> HTTP 400."""
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        with pytest.raises(HTTPException) as excinfo:
            team_service.invite_member(
                tenant_id=tenant.id,
                actor_user_id=owner.id,
                actor_role=owner.role,
                payload=InviteRequest(
                    email_or_phone="alpha@example.com",
                    role="manager",
                    channel="whatsapp",
                    consent_given=True,
                ),
                db=db,
            )
        assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# Service-direct: list_team_members_with_status
# ---------------------------------------------------------------------------

class TestListWithStatus:

    def test_synthesised_email_returned_as_none(self, db):
        tenant = _make_tenant(db)
        _make_user(db, tenant=tenant, role="proprietor", email="real@t.com")
        # Simulate an invite-by-phone user with synthesised placeholder.
        _make_user(
            db, tenant=tenant, role="manager",
            email="invite-abcdef12@invite.zetaops.com",
        )
        out = team_service.list_team_members_with_status(tenant.id, db)
        emails = [m.email for m in out]
        assert "real@t.com" in emails
        assert None in emails  # synthesised stripped to None
        # No member should leak the placeholder string.
        assert all(
            m.email is None or "@invite.zetaops.com" not in m.email
            for m in out
        )

    def test_status_active_when_consent_given(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        now = datetime.now(timezone.utc)
        db.add(PhoneTenantMap(
            tenant_id=tenant.id,
            user_id=owner.id,
            phone_number="+919998880001",
            is_active=True,
            consent_given=True,
            consent_at=now,
            phone_role="owner",
            linked_at=now,
        ))
        db.flush()
        out = team_service.list_team_members_with_status(tenant.id, db)
        assert next(m.whatsapp_status for m in out if m.id == owner.id) == "active"

    def test_status_invited_when_consent_pending(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        now = datetime.now(timezone.utc)
        db.add(PhoneTenantMap(
            tenant_id=tenant.id,
            user_id=owner.id,
            phone_number="+919998880002",
            is_active=True,
            consent_given=False,
            phone_role="owner",
            linked_at=now,
        ))
        db.flush()
        out = team_service.list_team_members_with_status(tenant.id, db)
        assert next(m.whatsapp_status for m in out if m.id == owner.id) == "invited"

    def test_status_disconnected_when_inactive(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        now = datetime.now(timezone.utc)
        db.add(PhoneTenantMap(
            tenant_id=tenant.id,
            user_id=owner.id,
            phone_number="+919998880003",
            is_active=False,
            consent_given=True,
            phone_role="owner",
            linked_at=now,
        ))
        db.flush()
        out = team_service.list_team_members_with_status(tenant.id, db)
        assert next(
            m.whatsapp_status for m in out if m.id == owner.id
        ) == "disconnected"

    def test_status_none_when_no_mapping(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        out = team_service.list_team_members_with_status(tenant.id, db)
        assert next(m.whatsapp_status for m in out if m.id == owner.id) == "none"

    def test_list_is_n_plus_one_safe(self, db):
        """Constant query count regardless of team size. We allow up to a
        few queries (users + mappings + connection-level metadata) but the
        count must NOT scale with the number of members."""
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        now = datetime.now(timezone.utc)
        for i in range(8):
            u = _make_user(
                db, tenant=tenant, role="manager",
                email=f"m{i}-{_TENANT_COUNTER['n']}@t.com",
            )
            db.add(PhoneTenantMap(
                tenant_id=tenant.id,
                user_id=u.id,
                phone_number=f"+9199988811{i:02d}",
                is_active=True,
                consent_given=(i % 2 == 0),
                phone_role="manager",
                linked_at=now,
            ))
        db.flush()

        # Count SELECTs issued during the listing call.
        bind = db.get_bind()
        seen = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            if statement.strip().lower().startswith("select"):
                seen.append(statement)

        sa_event.listen(bind, "before_cursor_execute", _record)
        try:
            out = team_service.list_team_members_with_status(tenant.id, db)
        finally:
            sa_event.remove(bind, "before_cursor_execute", _record)

        # 9 members in the tenant (1 owner + 8 managers). N+1 would mean ~10
        # SELECTs. The new implementation issues 2: one for users, one for
        # mappings. We allow up to 4 to give pytest fixture metadata some
        # slack; the key invariant is "does NOT scale with member count".
        assert len(out) == 9
        assert len(seen) <= 4, f"Expected <=4 SELECTs, got {len(seen)}: {seen}"


# ---------------------------------------------------------------------------
# Router E2E via TestClient
# ---------------------------------------------------------------------------

class TestRouterE2E:
    """4 router-level tests that exercise the FastAPI permission wiring +
    response shape. Lesson 17 says default to service-direct, but routing
    + response_model serialisation is exactly what these check."""

    def _seed_owner(self, db):
        """Create tenant + active proprietor; return (tenant, owner, headers)."""
        tenant = _make_tenant(db)
        now = datetime.now(timezone.utc)
        owner = User(
            tenant_id=tenant.id,
            email="owner-router@t.com",
            hashed_password=hash_password("pw"),
            role="proprietor",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(owner)
        db.flush()
        token = create_access_token(
            user_id=owner.id, tenant_id=tenant.id, role="proprietor",
        )
        return tenant, owner, {"Authorization": f"Bearer {token}"}

    def test_post_invite_whatsapp_channel_201(self, db, client, caplog):
        import logging
        caplog.set_level(logging.INFO, logger="app.services.team_invite_whatsapp")

        _, _, headers = self._seed_owner(db)
        resp = client.post(
            "/api/team/invite",
            headers=headers,
            json={
                "email_or_phone": "+919999900100",
                "role":           "manager",
                "channel":        "whatsapp",
                "consent_given":  True,
                "name":           "Priya",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["temp_password"] is None
        assert body["member"]["whatsapp_status"] == "invited"
        assert body["member"]["email"] is None  # synthesised, stripped
        assert body["member"]["name"] == "Priya"
        assert any(
            "[MOCK ALERT] Type=invite_welcome" in r.message
            for r in caplog.records
        )

    def test_post_invite_desktop_channel_201_returns_password(self, db, client):
        _, _, headers = self._seed_owner(db)
        resp = client.post(
            "/api/team/invite",
            headers=headers,
            json={
                "email_or_phone": "kim-router@example.com",
                "role":           "manager",
                "channel":        "desktop",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["temp_password"] and len(body["temp_password"]) > 10
        assert body["member"]["email"] == "kim-router@example.com"
        assert body["member"]["whatsapp_status"] == "none"

    def test_get_team_omits_synthesised_emails(self, db, client):
        _, owner, headers = self._seed_owner(db)
        # Simulate an old whatsapp_first user with synthesised email.
        now = datetime.now(timezone.utc)
        db.add(User(
            tenant_id=owner.tenant_id,
            email="invite-deadbeef@invite.zetaops.com",
            hashed_password=hash_password("pw"),
            role="manager",
            is_active=True,
            created_at=now,
            updated_at=now,
        ))
        db.flush()
        resp = client.get("/api/team/", headers=headers)
        assert resp.status_code == 200, resp.text
        emails = [m["email"] for m in resp.json()]
        assert None in emails
        assert all(
            e is None or "@invite.zetaops.com" not in e for e in emails
        )

    def test_post_invite_whatsapp_without_consent_400(self, db, client):
        _, _, headers = self._seed_owner(db)
        resp = client.post(
            "/api/team/invite",
            headers=headers,
            json={
                "email_or_phone": "+919999900200",
                "role":           "manager",
                "channel":        "whatsapp",
                "consent_given":  False,
            },
        )
        assert resp.status_code == 400, resp.text
        assert "consent_given" in resp.json()["detail"]
