# tests/test_team_management.py
#
# FILE PURPOSE
# v6.3.3 test coverage for the Team & Roles surface:
#   - is_last_owner helper (3 cases)
#   - invite_member: success, role-grant guard, duplicate email, phone-only
#   - change_member_role: promote, demote, no-op, top-tier guard, last-owner
#   - delete_member: success, last-owner block, idempotency
#   - event emission: user.role_changed lands in events table with payload
#
# Most tests are service-direct (fast, no TestClient) because the role-gate
# behaviour is enforced at the dependency / service layer; only the two
# TestClient tests at the bottom exercise the FastAPI permission wiring.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.team_service.{is_last_owner, invite_member,
#       change_member_role, delete_member, TOP_TIER_GRANT_ROLES}
#   app.schemas.team.{InviteRequest, RoleChangeRequest}
#   app.models.{auth.User, auth.Tenant, event.Event}
#
# DESIGN NOTES
# - patch_now_defaults_for_sqlite is the same autouse fixture pattern as
#   test_signup_v6_4.py - swaps text("now()") server defaults for
#   CURRENT_TIMESTAMP so SQLite can INSERT rows.
# - Each test gets a fresh tenant via _make_tenant() so test isolation is
#   guaranteed even though we share the in-memory engine.

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text as sa_text
from sqlalchemy.sql.schema import DefaultClause

from app.core.security import hash_password
from app.models.auth import RefreshToken, Tenant, User
from app.models.event import Event
from app.models.whatsapp import PhoneTenantMap
from app.schemas.team import InviteRequest, RoleChangeRequest
from app.services import team_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    """Swap text("now()") server defaults to CURRENT_TIMESTAMP for SQLite.
    Same pattern as tests/test_signup_v6_4.py - reused so this file is
    self-contained and does not depend on import order."""
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


def _make_tenant(db, *, name: str = "Acme") -> Tenant:
    """Create + flush a fresh tenant. Slug auto-incremented per test."""
    _TENANT_COUNTER["n"] += 1
    now = datetime.now(timezone.utc)
    tenant = Tenant(
        name=name,
        slug=f"acme-{_TENANT_COUNTER['n']}",
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
    """Create + flush a User with a deterministic email if not provided."""
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
# is_last_owner helper
# ---------------------------------------------------------------------------

class TestIsLastOwner:

    def test_sole_top_tier_user_is_last_owner(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        assert team_service.is_last_owner(tenant.id, owner.id, db) is True

    def test_with_other_active_top_tier_not_last(self, db):
        tenant = _make_tenant(db)
        owner1 = _make_user(db, tenant=tenant, role="proprietor", email="o1@t.com")
        _make_user(db, tenant=tenant, role="factory_manager", email="o2@t.com")
        assert team_service.is_last_owner(tenant.id, owner1.id, db) is False

    def test_inactive_other_top_tier_does_not_save(self, db):
        # Other top-tier user is INACTIVE -> active count is still 1 -> last.
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        _make_user(
            db, tenant=tenant, role="co_owner",
            email="co@t.com", is_active=False,
        )
        assert team_service.is_last_owner(tenant.id, owner.id, db) is True

    def test_non_top_tier_user_never_is_last(self, db):
        tenant = _make_tenant(db)
        _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        viewer = _make_user(db, tenant=tenant, role="viewer", email="v@t.com")
        assert team_service.is_last_owner(tenant.id, viewer.id, db) is False


# ---------------------------------------------------------------------------
# invite_member
# ---------------------------------------------------------------------------

class TestInvite:

    def test_owner_invites_factory_manager_succeeds(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        new_user, temp_password = team_service.invite_member(
            tenant_id=tenant.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=InviteRequest(
                email_or_phone="newfm@example.com", role="factory_manager"
            ),
            db=db,
        )
        assert new_user.role == "factory_manager"
        assert new_user.tenant_id == tenant.id
        assert new_user.email == "newfm@example.com"
        assert temp_password is not None and len(temp_password) > 10
        assert new_user.created_via == "web_invite"

    def test_factory_manager_invites_factory_manager_blocked(self, db):
        tenant = _make_tenant(db)
        fm = _make_user(db, tenant=tenant, role="factory_manager")
        with pytest.raises(HTTPException) as excinfo:
            team_service.invite_member(
                tenant_id=tenant.id,
                actor_user_id=fm.id,
                actor_role=fm.role,
                payload=InviteRequest(
                    email_or_phone="another@example.com", role="factory_manager"
                ),
                db=db,
            )
        assert excinfo.value.status_code == 403
        assert "top-tier" in excinfo.value.detail

    def test_factory_manager_invites_manager_succeeds(self, db):
        tenant = _make_tenant(db)
        fm = _make_user(db, tenant=tenant, role="factory_manager")
        new_user, _ = team_service.invite_member(
            tenant_id=tenant.id,
            actor_user_id=fm.id,
            actor_role=fm.role,
            payload=InviteRequest(
                email_or_phone="mgr@example.com", role="manager"
            ),
            db=db,
        )
        assert new_user.role == "manager"

    def test_synthesized_invite_email_passes_pydantic_emailstr(self, db):
        # Regression: an earlier draft synthesised '+invite-XXX@whatsapp.local'
        # with a leading '+' that Pydantic's EmailStr (email-validator)
        # rejects, 422-ing the invitee at /auth/login. This test pipes the
        # synthesised email through the SAME validator the login endpoint
        # uses so any future format change that breaks login fails here.
        from pydantic import BaseModel, EmailStr
        from pydantic import ValidationError

        class _LoginShape(BaseModel):
            email: EmailStr

        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        new_user, _ = team_service.invite_member(
            tenant_id=tenant.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=InviteRequest(
                email_or_phone="+919876512345", role="manager"
            ),
            db=db,
        )
        # Must not raise - login path constructs the equivalent of _LoginShape
        # from the user-supplied form. The synthesised email lives in the DB
        # and is what the invitee will paste into the login form.
        try:
            _LoginShape(email=new_user.email)
        except ValidationError as exc:
            pytest.fail(
                f"Synthesised invite email {new_user.email!r} fails Pydantic "
                f"EmailStr validation - invitee would 422 at /auth/login. "
                f"Validator error: {exc}"
            )

    def test_invite_phone_only_returns_temp_password(self, db):
        # Phone-only invites synthesise a placeholder email AND get a
        # temp password (so the invitee can log in before the v6.3.5
        # WhatsApp identity flow ships). Behaviour changed mid-v6.3.3
        # after manual testing surfaced that phone-only invites with
        # empty hash were creating unreachable accounts.
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        new_user, temp_password = team_service.invite_member(
            tenant_id=tenant.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=InviteRequest(
                email_or_phone="+919876543210", role="manager"
            ),
            db=db,
        )
        assert new_user.phone_e164 == "+919876543210"
        assert new_user.email.startswith("invite-")
        assert "@invite.zetaops" in new_user.email
        assert temp_password is not None and len(temp_password) > 10
        # The hash must verify the password we returned - the invitee
        # has to be able to log in immediately.
        from app.core.security import verify_password
        assert verify_password(temp_password, new_user.hashed_password)

    def test_invite_duplicate_email_400(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        _make_user(db, tenant=tenant, role="manager", email="taken@t.com")
        with pytest.raises(HTTPException) as excinfo:
            team_service.invite_member(
                tenant_id=tenant.id,
                actor_user_id=owner.id,
                actor_role=owner.role,
                payload=InviteRequest(
                    email_or_phone="taken@t.com", role="manager"
                ),
                db=db,
            )
        assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# change_member_role
# ---------------------------------------------------------------------------

class TestChangeRole:

    def test_owner_promotes_manager_to_factory_manager(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        target = _make_user(db, tenant=tenant, role="manager", email="m@t.com")
        updated = team_service.change_member_role(
            tenant_id=tenant.id,
            target_user_id=target.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=RoleChangeRequest(role="factory_manager"),
            db=db,
        )
        assert updated.role == "factory_manager"

    def test_owner_demotes_factory_manager_to_manager(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        fm = _make_user(db, tenant=tenant, role="factory_manager", email="f@t.com")
        updated = team_service.change_member_role(
            tenant_id=tenant.id,
            target_user_id=fm.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=RoleChangeRequest(role="manager"),
            db=db,
        )
        assert updated.role == "manager"

    def test_factory_manager_cannot_promote_into_top_tier(self, db):
        tenant = _make_tenant(db)
        fm = _make_user(db, tenant=tenant, role="factory_manager", email="f@t.com")
        target = _make_user(db, tenant=tenant, role="manager", email="m@t.com")
        with pytest.raises(HTTPException) as excinfo:
            team_service.change_member_role(
                tenant_id=tenant.id,
                target_user_id=target.id,
                actor_user_id=fm.id,
                actor_role=fm.role,
                payload=RoleChangeRequest(role="co_owner"),
                db=db,
            )
        assert excinfo.value.status_code == 403

    def test_owner_cannot_demote_self_when_last_owner(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        with pytest.raises(HTTPException) as excinfo:
            team_service.change_member_role(
                tenant_id=tenant.id,
                target_user_id=owner.id,
                actor_user_id=owner.id,
                actor_role=owner.role,
                payload=RoleChangeRequest(role="manager"),
                db=db,
            )
        assert excinfo.value.status_code == 400
        assert "last top-tier" in excinfo.value.detail.lower()

    def test_owner_can_demote_self_when_other_owners_exist(self, db):
        tenant = _make_tenant(db)
        owner1 = _make_user(db, tenant=tenant, role="proprietor", email="o1@t.com")
        _make_user(db, tenant=tenant, role="co_owner", email="o2@t.com")
        updated = team_service.change_member_role(
            tenant_id=tenant.id,
            target_user_id=owner1.id,
            actor_user_id=owner1.id,
            actor_role=owner1.role,
            payload=RoleChangeRequest(role="manager"),
            db=db,
        )
        assert updated.role == "manager"

    def test_role_change_emits_event(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        target = _make_user(db, tenant=tenant, role="manager", email="m@t.com")
        team_service.change_member_role(
            tenant_id=tenant.id,
            target_user_id=target.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=RoleChangeRequest(role="factory_manager"),
            db=db,
        )
        events = db.query(Event).filter(
            Event.tenant_id == tenant.id,
            Event.event_type == "user.role_changed",
        ).all()
        assert len(events) == 1
        ev = events[0]
        assert ev.entity_type == "user"
        assert ev.entity_id == target.id
        assert ev.actor_user_id == owner.id
        assert ev.source == "web"
        assert ev.payload["old_role"] == "manager"
        assert ev.payload["new_role"] == "factory_manager"

    def test_no_op_role_change_emits_no_event(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        target = _make_user(db, tenant=tenant, role="manager", email="m@t.com")
        team_service.change_member_role(
            tenant_id=tenant.id,
            target_user_id=target.id,
            actor_user_id=owner.id,
            actor_role=owner.role,
            payload=RoleChangeRequest(role="manager"),  # same as current
            db=db,
        )
        events = db.query(Event).filter(
            Event.tenant_id == tenant.id,
            Event.event_type == "user.role_changed",
        ).all()
        assert events == []


# ---------------------------------------------------------------------------
# delete_member
# ---------------------------------------------------------------------------

class TestDelete:

    def test_delete_last_owner_blocked(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor")
        with pytest.raises(HTTPException) as excinfo:
            team_service.delete_member(
                tenant_id=tenant.id,
                target_user_id=owner.id,
                actor_user_id=owner.id,
                db=db,
            )
        assert excinfo.value.status_code == 400
        assert "last owner" in excinfo.value.detail.lower()

    def test_delete_non_last_owner_succeeds(self, db):
        tenant = _make_tenant(db)
        owner1 = _make_user(db, tenant=tenant, role="proprietor", email="o1@t.com")
        owner2 = _make_user(db, tenant=tenant, role="co_owner", email="o2@t.com")
        team_service.delete_member(
            tenant_id=tenant.id,
            target_user_id=owner2.id,
            actor_user_id=owner1.id,
            db=db,
        )
        db.refresh(owner2)
        assert owner2.is_active is False

    def test_delete_non_top_tier_user_succeeds(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        viewer = _make_user(db, tenant=tenant, role="viewer", email="v@t.com")
        team_service.delete_member(
            tenant_id=tenant.id,
            target_user_id=viewer.id,
            actor_user_id=owner.id,
            db=db,
        )
        db.refresh(viewer)
        assert viewer.is_active is False

    def test_delete_already_inactive_is_idempotent(self, db):
        tenant = _make_tenant(db)
        owner = _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        target = _make_user(
            db, tenant=tenant, role="manager",
            email="m@t.com", is_active=False,
        )
        team_service.delete_member(
            tenant_id=tenant.id,
            target_user_id=target.id,
            actor_user_id=owner.id,
            db=db,
        )
        # No event emitted on idempotent delete.
        events = db.query(Event).filter(
            Event.tenant_id == tenant.id,
            Event.event_type == "user.deactivated",
        ).all()
        assert events == []

    def test_delete_emits_user_deactivated_event(self, db):
        tenant = _make_tenant(db)
        owner1 = _make_user(db, tenant=tenant, role="proprietor", email="o1@t.com")
        owner2 = _make_user(db, tenant=tenant, role="co_owner", email="o2@t.com")
        team_service.delete_member(
            tenant_id=tenant.id,
            target_user_id=owner2.id,
            actor_user_id=owner1.id,
            db=db,
        )
        events = db.query(Event).filter(
            Event.tenant_id == tenant.id,
            Event.event_type == "user.deactivated",
        ).all()
        assert len(events) == 1
        assert events[0].entity_id == owner2.id
        assert events[0].payload["old_role"] == "co_owner"


# ---------------------------------------------------------------------------
# list_team_members
# ---------------------------------------------------------------------------

class TestList:

    def test_list_returns_active_and_inactive_users(self, db):
        tenant = _make_tenant(db)
        _make_user(db, tenant=tenant, role="proprietor", email="o@t.com")
        _make_user(db, tenant=tenant, role="manager", email="m@t.com")
        _make_user(
            db, tenant=tenant, role="viewer",
            email="v@t.com", is_active=False,
        )
        members = team_service.list_team_members(tenant.id, db)
        assert len(members) == 3
        assert {m.email for m in members} == {"o@t.com", "m@t.com", "v@t.com"}

    def test_list_does_not_leak_other_tenant(self, db):
        tenant_a = _make_tenant(db, name="A")
        tenant_b = _make_tenant(db, name="B")
        _make_user(db, tenant=tenant_a, role="proprietor", email="a@t.com")
        _make_user(db, tenant=tenant_b, role="proprietor", email="b@t.com")
        members_a = team_service.list_team_members(tenant_a.id, db)
        assert len(members_a) == 1
        assert members_a[0].email == "a@t.com"
