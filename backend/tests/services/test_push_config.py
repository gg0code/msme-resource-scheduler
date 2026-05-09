# tests/services/test_push_config.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/push_config.resolve_push_config — the
# v6.3.19 slice 2A part 2 cascade resolver. Exercises every "where
# does this value come from" path the resolver supports:
#   - briefing_* override wins for time / tz / enabled
#   - migration 033 column override wins for sections
#   - YAML fallback fires when a column is NULL
#   - push_paused_until passes through verbatim
#   - PushConfig is frozen (no mutation)
#
# WHO CALLS THIS FILE
# - pytest under the unit tier (mark "not integration").
#
# WHAT THIS FILE CALLS
# - app.services.push_config — module under test.
# - types.SimpleNamespace — stands in for the Tenant ORM row. The
#   resolver reads attributes only; no DB session is needed.

from datetime import date, time
from types import SimpleNamespace

import pytest

from app.services import push_config as pc
from app.services.push_config import resolve_push_config


def _make_tenant(**overrides):
    """Build a tenant-shaped SimpleNamespace with sane defaults.

    Called by:    every test in this file.
    Calls into:   types.SimpleNamespace.
    Side effects: none.

    Defaults mirror the post-migration-027 + post-migration-033 column
    state for a tenant who has NEVER touched any push config (server-
    default values for briefing_*; NULL for the migration 033
    additions). Tests pass overrides to model specific scenarios.
    """
    base = dict(
        briefing_morning_time=time(7, 30),
        briefing_evening_time=time(18, 30),
        briefing_timezone="Asia/Kolkata",
        briefing_morning_enabled=False,
        briefing_evening_enabled=False,
        morning_sections=None,
        evening_sections=None,
        push_paused_until=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_default_tenant_falls_through_to_yaml_for_sections():
    """Tenant with NULL morning_sections / evening_sections picks up
    the YAML defaults. briefing_* values flow through as-is."""
    cfg = resolve_push_config(_make_tenant())

    assert cfg.morning_push_time == time(7, 30)
    assert cfg.evening_push_time == time(18, 30)
    assert cfg.push_timezone == "Asia/Kolkata"
    assert cfg.morning_sections == ("plan", "flag", "next_step")
    assert cfg.evening_sections == (
        "completed", "hours_logged", "tomorrow_preview",
    )
    assert cfg.push_paused_until is None
    # briefing_*_enabled server_defaults are FALSE post-migration 027.
    assert cfg.morning_enabled is False
    assert cfg.evening_enabled is False


def test_tenant_override_wins_for_time():
    """briefing_morning_time set on the tenant beats the YAML value."""
    cfg = resolve_push_config(
        _make_tenant(briefing_morning_time=time(9, 0)),
    )
    assert cfg.morning_push_time == time(9, 0)
    # Other fields untouched.
    assert cfg.evening_push_time == time(18, 30)


def test_tenant_override_wins_for_sections():
    """morning_sections set on the tenant returns as a tuple, not the
    YAML default. evening_sections still falls through."""
    cfg = resolve_push_config(
        _make_tenant(morning_sections=["custom_a", "custom_b"]),
    )
    assert cfg.morning_sections == ("custom_a", "custom_b")
    assert cfg.evening_sections == (
        "completed", "hours_logged", "tomorrow_preview",
    )


def test_paused_tenant_carries_date_through():
    """push_paused_until propagates verbatim — None when unset, date
    object when set."""
    pause_until = date(2026, 5, 15)
    cfg = resolve_push_config(_make_tenant(push_paused_until=pause_until))
    assert cfg.push_paused_until == pause_until

    cfg_unset = resolve_push_config(_make_tenant())
    assert cfg_unset.push_paused_until is None


def test_enabled_flags_split_per_direction():
    """morning_enabled and evening_enabled are independent — a tenant
    can enable one without the other."""
    cfg = resolve_push_config(
        _make_tenant(
            briefing_morning_enabled=True,
            briefing_evening_enabled=False,
        ),
    )
    assert cfg.morning_enabled is True
    assert cfg.evening_enabled is False

    cfg_inverse = resolve_push_config(
        _make_tenant(
            briefing_morning_enabled=False,
            briefing_evening_enabled=True,
        ),
    )
    assert cfg_inverse.morning_enabled is False
    assert cfg_inverse.evening_enabled is True


def test_pushconfig_is_frozen():
    """PushConfig dataclass refuses attribute mutation — a dispatcher
    cannot accidentally rewrite a resolved config mid-tick."""
    cfg = resolve_push_config(_make_tenant())
    with pytest.raises(Exception):  # FrozenInstanceError subclasses AttributeError
        cfg.morning_push_time = time(8, 0)


def test_yaml_fallback_for_nulled_briefing_time():
    """Defensive path: if briefing_morning_time is somehow NULL (manual
    DB edit / future schema change), the resolver returns the YAML
    value rather than crashing. Mirrors the documented design intent."""
    cfg = resolve_push_config(_make_tenant(briefing_morning_time=None))
    assert cfg.morning_push_time == time(7, 30, 0)


def test_yaml_fallback_for_nulled_briefing_timezone():
    """Same defensive path for the timezone column."""
    cfg = resolve_push_config(_make_tenant(briefing_timezone=None))
    assert cfg.push_timezone == "Asia/Kolkata"


def test_yaml_fallback_for_nulled_briefing_enabled():
    """Same defensive path for the enabled flags. YAML carries
    morning_enabled: true and evening_enabled: true (design intent),
    so a NULL column returns True."""
    cfg = resolve_push_config(
        _make_tenant(
            briefing_morning_enabled=None,
            briefing_evening_enabled=None,
        ),
    )
    assert cfg.morning_enabled is True
    assert cfg.evening_enabled is True


def test_resolver_makes_no_db_queries(monkeypatch):
    """Sanity check: resolve_push_config must work on a plain Python
    object that has no SQLAlchemy session attached. This locks the
    'pure attribute reads, no DB calls' contract.
    """
    # SimpleNamespace cannot ever issue a DB query — if the resolver
    # tried to .query() or open a session, attribute access would
    # raise AttributeError immediately.
    cfg = resolve_push_config(_make_tenant())
    assert cfg is not None
