# tests/services/test_push_settings_service.py
# Branch: v5-whatsapp
# Introduced: v6.3.20 (WhatsApp NL push-settings updater)
#
# FILE PURPOSE
# Unit coverage for app/services/push_settings_service.py — the security
# boundary for the v6.3.20 WhatsApp NL push-settings AI tools.
#
# Inherits from tests/services/conftest.py:
#   - autouse `freeze_clock_at_detector_today` pins now() to 2026-05-04
#     (a Monday) — pause-arithmetic tests rely on this anchor.
#   - autouse `patch_now_defaults_for_sqlite` lets Event.created_at use
#     CURRENT_TIMESTAMP under SQLite.
#
# WHAT'S TESTED HERE
# - update_push_setting: whitelist (incl. desktop-only sections rejection),
#   validators, top-tier auth, owner-vs-self user override rule, audit row
#   payload shape, tenant isolation.
# - pause_push: today + (days - 1) arithmetic in tenant timezone, range
#   bounds (1..30), replacement-not-additive, audit payload.
# - get_push_settings: scalar + JSONB blobs returned as-is, no audit row,
#   is_currently_paused derived bool.
# - whatsapp_actions executors: confirmed-action path through
#   _execute_update_push_setting / _execute_pause_push delegating into
#   push_settings_service.
#
# NOT TESTED HERE (covered elsewhere)
# - Dispatcher pause skip behaviour — tests/services/test_consolidated_briefing.py
#   already covers paused-tenant skip + "today equals push_paused_until"
#   inclusive boundary at lines 693-712.

from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest
from freezegun import freeze_time

from app.models.auth import Tenant, User
from app.models.event import Event
from app.services import push_settings_service as pss
from app.services.push_settings_service import (
    PushSettingForbidden,
    PushSettingValidationError,
    EDITABLE_FIELDS,
    PUSH_SETTING_CHANGED_EVENT_TYPE,
)


# ---------------------------------------------------------------------------
# Local helpers — not in conftest because they're v6.3.20-specific
# ---------------------------------------------------------------------------

# Module-level counter for unique slugs (freezegun pins now() so timestamp-
# based slugs collide).
_SEED_COUNTER = {"n": 0}


def _seed_tenant(db, *, tz: str = "Asia/Kolkata") -> Tenant:
    _SEED_COUNTER["n"] += 1
    n = _SEED_COUNTER["n"]
    now = datetime.now(timezone.utc)
    t = Tenant(
        name=f"Test Tenant {n}",
        slug=f"pss-test-{n}",
        plan="free",
        is_active=True,
        industry_type="printing",
        briefing_morning_enabled=True,
        briefing_morning_time=time(7, 30),
        briefing_evening_enabled=True,
        briefing_evening_time=time(18, 30),
        briefing_timezone=tz,
        briefing_working_days="1,2,3,4,5,6",
        created_at=now,
        updated_at=now,
    )
    db.add(t)
    db.flush()
    return t


def _seed_user(
    db, *, tenant: Tenant, role: str = "owner", email_suffix: str = "owner"
) -> User:
    _SEED_COUNTER["n"] += 1
    n = _SEED_COUNTER["n"]
    now = datetime.now(timezone.utc)
    u = User(
        tenant_id=tenant.id,
        email=f"{email_suffix}-{n}@t.test",
        hashed_password="x" * 60,
        role=role,
        is_active=True,
        briefing_subscribed=True,
        created_at=now,
        updated_at=now,
    )
    db.add(u)
    db.flush()
    return u


def _seed_full(db, *, role: str = "owner") -> tuple[Tenant, User]:
    t = _seed_tenant(db)
    u = _seed_user(db, tenant=t, role=role)
    return t, u


# ===========================================================================
# update_push_setting — happy paths
# ===========================================================================

def test_update_push_setting_morning_time_happy_path(db):
    t, owner = _seed_full(db, role="owner")

    result = pss.update_push_setting(
        db=db,
        tenant_id=t.id,
        user_id=None,
        field="briefing_morning_time",
        raw_value="08:00",
        source_phrase="morning briefing 8 baje karo",
        actor_user_id=owner.id,
    )
    db.commit()

    assert result.field == "briefing_morning_time"
    assert result.new_value == "08:00"
    assert result.table == "tenants"
    assert result.entity_id == t.id

    # Column changed.
    db.refresh(t)
    assert t.briefing_morning_time == time(8, 0)

    # Audit row written with the right shape.
    row = db.query(Event).filter(
        Event.event_type == PUSH_SETTING_CHANGED_EVENT_TYPE,
    ).one()
    assert row.tenant_id == t.id
    assert row.entity_type == "tenant"
    assert row.entity_id == t.id
    assert row.actor_user_id == owner.id
    assert row.source == "whatsapp"
    assert row.payload["field"] == "briefing_morning_time"
    assert row.payload["new_value"] == "08:00"
    assert row.payload["source_phrase"] == "morning briefing 8 baje karo"


def test_update_push_setting_weekday_csv_normalized(db):
    """Weekday CSV is sorted + deduplicated on write."""
    t, owner = _seed_full(db, role="owner")

    pss.update_push_setting(
        db=db, tenant_id=t.id, user_id=None,
        field="briefing_working_days",
        raw_value="6,1,3,1,2",  # unsorted + duplicate
        source_phrase="weekdays + sat",
        actor_user_id=owner.id,
    )
    db.commit()
    db.refresh(t)
    assert t.briefing_working_days == "1,2,3,6"


def test_update_push_setting_owner_can_edit_other_user_override(db):
    t, owner = _seed_full(db, role="owner")
    other = _seed_user(db, tenant=t, role="factory_manager", email_suffix="fm")

    pss.update_push_setting(
        db=db, tenant_id=t.id, user_id=other.id,
        field="briefing_time_override_morning",
        raw_value="09:30",
        source_phrase="set FM morning override",
        actor_user_id=owner.id,
    )
    db.commit()
    db.refresh(other)
    assert other.briefing_time_override_morning == time(9, 30)


# ===========================================================================
# update_push_setting — rejections
# ===========================================================================

def test_update_push_setting_rejects_unknown_field(db):
    t, owner = _seed_full(db)
    with pytest.raises(PushSettingValidationError) as exc_info:
        pss.update_push_setting(
            db=db, tenant_id=t.id, user_id=None,
            field="not_a_real_field",
            raw_value="x",
            source_phrase="-",
            actor_user_id=owner.id,
        )
    assert exc_info.value.code == "unknown_field"
    # No audit row written on failure.
    assert db.query(Event).count() == 0


def test_update_push_setting_rejects_morning_sections(db):
    t, owner = _seed_full(db)
    with pytest.raises(PushSettingValidationError) as exc_info:
        pss.update_push_setting(
            db=db, tenant_id=t.id, user_id=None,
            field="morning_sections",
            raw_value=["plan", "flag"],
            source_phrase="hatao attendance",
            actor_user_id=owner.id,
        )
    assert exc_info.value.code == "field_not_editable_via_whatsapp"
    # User-facing message redirects to desktop in all three languages.
    assert "desktop" in exc_info.value.messages["en"].lower()
    assert "desktop" in exc_info.value.messages["hi_en"].lower()
    assert db.query(Event).count() == 0


def test_update_push_setting_rejects_evening_sections(db):
    t, owner = _seed_full(db)
    with pytest.raises(PushSettingValidationError) as exc_info:
        pss.update_push_setting(
            db=db, tenant_id=t.id, user_id=None,
            field="evening_sections",
            raw_value=["plan"],
            source_phrase="-",
            actor_user_id=owner.id,
        )
    assert exc_info.value.code == "field_not_editable_via_whatsapp"


def test_update_push_setting_rejects_invalid_time_format(db):
    t, owner = _seed_full(db)
    for bad in ["8pm", "8:00 AM", "25:00", "24:00", "8 baje", "07:5", "noon"]:
        with pytest.raises(PushSettingValidationError) as exc_info:
            pss.update_push_setting(
                db=db, tenant_id=t.id, user_id=None,
                field="briefing_morning_time",
                raw_value=bad,
                source_phrase=bad,
                actor_user_id=owner.id,
            )
        assert exc_info.value.code == "invalid_time_format", f"bad={bad!r}"


def test_update_push_setting_rejects_non_top_tier(db):
    t = _seed_tenant(db)
    manager = _seed_user(db, tenant=t, role="manager", email_suffix="mgr")

    with pytest.raises(PushSettingForbidden) as exc_info:
        pss.update_push_setting(
            db=db, tenant_id=t.id, user_id=None,
            field="briefing_morning_time",
            raw_value="08:00",
            source_phrase="-",
            actor_user_id=manager.id,
        )
    assert exc_info.value.code == "forbidden_not_top_tier"
    db.refresh(t)
    assert t.briefing_morning_time == time(7, 30)  # unchanged


def test_update_push_setting_co_owner_cannot_edit_other_user_override(db):
    t = _seed_tenant(db)
    co_owner = _seed_user(db, tenant=t, role="co_owner", email_suffix="co")
    fm = _seed_user(db, tenant=t, role="factory_manager", email_suffix="fm")

    with pytest.raises(PushSettingForbidden) as exc_info:
        pss.update_push_setting(
            db=db, tenant_id=t.id, user_id=fm.id,
            field="briefing_time_override_evening",
            raw_value="19:30",
            source_phrase="-",
            actor_user_id=co_owner.id,
        )
    assert exc_info.value.code == "forbidden_other_user_override"
    db.refresh(fm)
    assert fm.briefing_time_override_evening is None


def test_update_push_setting_proprietor_synonym_counts_as_top_tier(db):
    """Legacy 'proprietor' role is a synonym for 'owner' — must pass."""
    t = _seed_tenant(db)
    proprietor = _seed_user(db, tenant=t, role="proprietor", email_suffix="p")

    pss.update_push_setting(
        db=db, tenant_id=t.id, user_id=None,
        field="briefing_morning_enabled",
        raw_value="off",
        source_phrase="band karo",
        actor_user_id=proprietor.id,
    )
    db.commit()
    db.refresh(t)
    assert t.briefing_morning_enabled is False


# ===========================================================================
# pause_push
# ===========================================================================

def test_pause_push_today_plus_days_minus_one(db):
    """Frozen anchor 2026-05-04 (Mon). days=5 → last_paused = Fri 2026-05-08."""
    t, owner = _seed_full(db)

    result = pss.pause_push(
        db=db, tenant_id=t.id, days=5,
        source_phrase="agle 5 din chuti hai",
        actor_user_id=owner.id,
    )
    db.commit()

    assert result.paused_until == date(2026, 5, 8)
    db.refresh(t)
    assert t.push_paused_until == date(2026, 5, 8)

    # Audit row carries the new shape.
    row = db.query(Event).filter(
        Event.event_type == PUSH_SETTING_CHANGED_EVENT_TYPE,
    ).one()
    assert row.payload["field"] == "push_paused_until"
    assert row.payload["new_value"] == "2026-05-08"
    assert row.payload["days"] == 5
    assert row.payload["timezone"] == "Asia/Kolkata"
    assert row.payload["today_local"] == "2026-05-04"


def test_pause_push_days_one_pauses_today_only(db):
    """days=1 means "just today" — last_paused == today_local."""
    t, owner = _seed_full(db)
    result = pss.pause_push(
        db=db, tenant_id=t.id, days=1,
        source_phrase="aaj briefing band rakho",
        actor_user_id=owner.id,
    )
    db.commit()
    assert result.paused_until == date(2026, 5, 4)


def test_pause_push_replaces_existing_pause(db):
    """New pause replaces, not adds to, an existing pause."""
    t, owner = _seed_full(db)
    t.push_paused_until = date(2026, 5, 6)  # already 2 days out
    db.flush()

    pss.pause_push(
        db=db, tenant_id=t.id, days=5,
        source_phrase="-",
        actor_user_id=owner.id,
    )
    db.commit()
    db.refresh(t)
    # Replacement: today (May 4) + 4 = May 8. NOT May 6 + 5 = May 11.
    assert t.push_paused_until == date(2026, 5, 8)


def test_pause_push_rejects_zero_or_negative_days(db):
    t, owner = _seed_full(db)
    for bad in [0, -3, -1]:
        with pytest.raises(PushSettingValidationError) as exc_info:
            pss.pause_push(
                db=db, tenant_id=t.id, days=bad,
                source_phrase="-",
                actor_user_id=owner.id,
            )
        assert exc_info.value.code == "pause_days_out_of_range", f"bad={bad}"


def test_pause_push_rejects_more_than_30_days(db):
    t, owner = _seed_full(db)
    with pytest.raises(PushSettingValidationError) as exc_info:
        pss.pause_push(
            db=db, tenant_id=t.id, days=31,
            source_phrase="ek mahina",
            actor_user_id=owner.id,
        )
    assert exc_info.value.code == "pause_days_out_of_range"


def test_pause_push_rejects_non_top_tier(db):
    t = _seed_tenant(db)
    operator = _seed_user(db, tenant=t, role="viewer", email_suffix="op")
    with pytest.raises(PushSettingForbidden):
        pss.pause_push(
            db=db, tenant_id=t.id, days=3,
            source_phrase="-",
            actor_user_id=operator.id,
        )


def test_pause_push_rejects_bool_days_not_int(db):
    """`isinstance(True, int)` is True in Python; reject explicitly."""
    t, owner = _seed_full(db)
    with pytest.raises(PushSettingValidationError):
        pss.pause_push(
            db=db, tenant_id=t.id, days=True,  # type: ignore[arg-type]
            source_phrase="-",
            actor_user_id=owner.id,
        )


# ===========================================================================
# get_push_settings — read-only
# ===========================================================================

def test_get_push_settings_returns_sections_readable(db):
    t, owner = _seed_full(db)
    t.morning_sections = ["plan", "flag", "next_step"]
    t.evening_sections = ["wrap", "tomorrow"]
    db.flush()

    view = pss.get_push_settings(db=db, tenant_id=t.id, user_id=owner.id)
    assert view.morning_sections == ["plan", "flag", "next_step"]
    assert view.evening_sections == ["wrap", "tomorrow"]
    assert view.briefing_subscribed is True


def test_get_push_settings_no_audit_row(db):
    t, owner = _seed_full(db)
    pss.get_push_settings(db=db, tenant_id=t.id, user_id=owner.id)
    pss.get_push_settings(db=db, tenant_id=t.id, user_id=None)
    pss.get_push_settings(db=db, tenant_id=t.id, user_id=owner.id)
    assert db.query(Event).count() == 0


def test_get_push_settings_is_currently_paused_field(db):
    t, owner = _seed_full(db)
    # Frozen "today" is 2026-05-04.
    t.push_paused_until = date(2026, 5, 4)  # today itself → paused (inclusive)
    db.flush()
    view = pss.get_push_settings(db=db, tenant_id=t.id, user_id=None)
    assert view.is_currently_paused is True

    t.push_paused_until = date(2026, 5, 3)  # yesterday → not paused
    db.flush()
    view = pss.get_push_settings(db=db, tenant_id=t.id, user_id=None)
    assert view.is_currently_paused is False

    t.push_paused_until = None
    db.flush()
    view = pss.get_push_settings(db=db, tenant_id=t.id, user_id=None)
    assert view.is_currently_paused is False
    assert view.push_paused_until is None


# ===========================================================================
# Tenant isolation — the architecture-rule-1 belt-and-braces check
# ===========================================================================

def test_tenant_isolation_actor_cannot_use_other_tenant(db):
    """Actor lives in tenant A; cannot pose as actor for tenant B."""
    t_a, owner_a = _seed_full(db)
    t_b = _seed_tenant(db)

    # Try to edit tenant B using owner_a's id. owner_a does not exist
    # under tenant B's tenant_id filter, so the actor lookup returns
    # None and we get forbidden_actor_not_found.
    with pytest.raises(PushSettingForbidden) as exc_info:
        pss.update_push_setting(
            db=db, tenant_id=t_b.id, user_id=None,
            field="briefing_morning_time",
            raw_value="09:00",
            source_phrase="cross-tenant attempt",
            actor_user_id=owner_a.id,
        )
    assert exc_info.value.code == "actor_not_found"
    # B's column is unchanged.
    db.refresh(t_b)
    assert t_b.briefing_morning_time == time(7, 30)


# ===========================================================================
# Validators — direct unit coverage for the bool/timezone/csv paths
# ===========================================================================

def test_bool_validator_accepts_hindi_synonyms():
    from app.services.push_settings_service import _validate_bool
    assert _validate_bool("haan") is True
    assert _validate_bool("nahi") is False
    assert _validate_bool("on") is True
    assert _validate_bool("off") is False
    assert _validate_bool(True) is True
    assert _validate_bool(False) is False


def test_iana_timezone_validator():
    from app.services.push_settings_service import _validate_iana_timezone
    assert _validate_iana_timezone("Asia/Kolkata") == "Asia/Kolkata"
    assert _validate_iana_timezone("UTC") == "UTC"
    with pytest.raises(PushSettingValidationError) as e:
        _validate_iana_timezone("Mars/Olympus")
    assert e.value.code == "unknown_timezone"


# ===========================================================================
# whatsapp_actions executor integration — full confirmed-action path
# ===========================================================================

def test_execute_update_push_setting_via_executor(db):
    """The post-confirmation executor delegates correctly into the service."""
    from app.services.whatsapp_actions import (
        ActionType,
        _execute_update_push_setting,
    )
    t, owner = _seed_full(db)

    success, reply = _execute_update_push_setting(
        params={
            "field": "briefing_evening_time",
            "raw_value": "20:30",
            "user_id": None,
            "actor_user_id": owner.id,
            "source_phrase": "evening 8:30 karo",
            "snippet_en": "Set evening recap time to 20:30.",
        },
        db=db,
        tenant_id=t.id,
    )
    assert success is True
    assert "20:30" in reply or "evening" in reply.lower()
    db.refresh(t)
    assert t.briefing_evening_time == time(20, 30)


def test_execute_pause_push_via_executor(db):
    from app.services.whatsapp_actions import _execute_pause_push
    t, owner = _seed_full(db)

    success, reply = _execute_pause_push(
        params={
            "days": 3,
            "actor_user_id": owner.id,
            "source_phrase": "agle 3 din",
            "pause_range_human": "Mon May 04 through Wed May 06, resume Thu May 07",
        },
        db=db,
        tenant_id=t.id,
    )
    assert success is True
    db.refresh(t)
    assert t.push_paused_until == date(2026, 5, 6)


def test_execute_update_push_setting_handles_validation_error(db):
    """A malformed staged value rolls back without committing.

    Commit the seed first — the executor's rollback() on validation error
    would otherwise unwind the tenant/user inserts too. In production
    these inserts come from prior committed transactions; the test makes
    that boundary explicit here.
    """
    from app.services.whatsapp_actions import _execute_update_push_setting
    t, owner = _seed_full(db)
    db.commit()

    tenant_id = t.id
    success, reply = _execute_update_push_setting(
        params={
            "field": "briefing_morning_time",
            "raw_value": "8 baje",  # invalid
            "user_id": None,
            "actor_user_id": owner.id,
            "source_phrase": "8 baje",
        },
        db=db,
        tenant_id=tenant_id,
    )
    assert success is False
    # After rollback the in-memory `t` is detached; re-query to verify
    # the column did not change.
    fresh = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    assert fresh.briefing_morning_time == time(7, 30)  # unchanged
    assert db.query(Event).count() == 0
