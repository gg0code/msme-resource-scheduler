# app/services/push_config.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.19 slice 2A part 2 — per-tenant push config resolver. Bridges
# the existing briefing_* columns from migration 027 (v6.3.1) and the
# new push_* columns from migration 033 (v6.3.19) into a single
# PushConfig dataclass for downstream dispatchers (slice 2C+).
#
# Two-layer cascade:
#   1. Tenant override — read briefing_* and push_* columns from the
#      Tenant ORM row passed in.
#   2. System fallback — for fields where the tenant value is None,
#      read backend/config/push_defaults.yaml.
#
# WHO CALLS THIS FILE
# - tests/services/test_push_config.py
# - (planned) app/services/consolidated_briefing.py dispatch_morning /
#   dispatch_evening (slice 2C) — call resolve_push_config(tenant) once
#   per dispatch tick.
#
# WHAT THIS FILE CALLS
# - app.models.auth.Tenant (type only — does not touch the DB)
# - pathlib.Path (resolve YAML location relative to this module)
# - yaml.safe_load (parse the system fallback file)
#
# DESIGN NOTES
# - PushConfig is frozen — dispatcher cannot accidentally mutate it
#   between morning and evening ticks. Sections fields are tuples (not
#   lists) so the dataclass stays hashable / safe to share across
#   threads.
# - The naming bridge between briefing_* (migration 027) and the
#   PushConfig field names (morning_push_time, etc.) is intentional;
#   see the docstring on resolve_push_config and CHANGELOG [Unreleased]
#   "Naming bridge in resolve_push_config" for the slice 2A scope
#   decision.
# - YAML defaults are loaded once at import time and cached via
#   lru_cache. The path is configurable via the module-level
#   _DEFAULTS_PATH attribute so tests can monkeypatch a fixture and
#   call _load_yaml_defaults.cache_clear() to force a re-read.
# - locale is per-recipient, not per-tenant — resolved by the
#   dispatcher from the recipient User.language_preference, not here.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.models.auth import Tenant


# Path to the system fallback YAML. Tests may override this attribute
# directly (e.g. monkeypatch.setattr(push_config, "_DEFAULTS_PATH", p))
# and then call _load_yaml_defaults.cache_clear() to force a re-read.
_DEFAULTS_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent
    / "config"
    / "push_defaults.yaml"
)


@dataclass(frozen=True)
class PushConfig:
    """Resolved push config for one tenant after the cascade.

    Fields:
      morning_push_time   tenant local time; bridged from
                          tenant.briefing_morning_time (migration 027).
      evening_push_time   tenant local time; bridged from
                          tenant.briefing_evening_time (migration 027).
      push_timezone       IANA tz string; bridged from
                          tenant.briefing_timezone (migration 027).
      morning_enabled     bridged from tenant.briefing_morning_enabled
                          (migration 027). Independent of evening_enabled.
      evening_enabled     bridged from tenant.briefing_evening_enabled
                          (migration 027). Independent of morning_enabled.
      morning_sections    tuple of section keys, ordered. From
                          tenant.morning_sections (migration 033) or
                          YAML fallback when the column is NULL.
      evening_sections    tuple of section keys, ordered. Mirror of
                          morning_sections for the evening cadence.
      push_paused_until   single nullable date. From
                          tenant.push_paused_until (migration 033).
                          None means "not paused"; dispatcher is
                          expected to skip both pushes when the date is
                          set and >= today (in the tenant's timezone).
    """

    morning_push_time: time
    evening_push_time: time
    push_timezone: str
    morning_enabled: bool
    evening_enabled: bool
    morning_sections: tuple[str, ...]
    evening_sections: tuple[str, ...]
    push_paused_until: date | None


@lru_cache(maxsize=1)
def _load_yaml_defaults() -> dict[str, Any]:
    """Load and cache the system fallback YAML.

    Called by:    resolve_push_config (this file).
    Calls into:   yaml.safe_load over the file at _DEFAULTS_PATH.
    Side effects: reads disk on first call, then serves from lru_cache.
                  Tests that monkeypatch _DEFAULTS_PATH must call
                  _load_yaml_defaults.cache_clear() to force a re-read.
    """
    with _DEFAULTS_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _parse_time(value: Any) -> time:
    """Parse an "HH:MM" or "HH:MM:SS" YAML string into a datetime.time.

    Called by:    resolve_push_config (this file) — for the YAML
                  fallback path on the morning_push_time and
                  evening_push_time fields.
    Calls into:   datetime.time.fromisoformat with len-aware fallback.
    Side effects: none.

    Accepts a real datetime.time object as a no-op so the function is
    safe on values that have already been parsed by another layer.
    """
    if isinstance(value, time):
        return value
    s = str(value).strip()
    if len(s) == 5:  # "HH:MM"
        s = s + ":00"
    return time.fromisoformat(s)


def resolve_push_config(tenant: Tenant) -> PushConfig:
    """Resolve a tenant's effective push config via the two-layer cascade.

    Called by:    tests/services/test_push_config.py and (planned)
                  consolidated_briefing.dispatch_morning /
                  dispatch_evening (slice 2C).
    Calls into:   _load_yaml_defaults, _parse_time. No DB queries — the
                  caller is expected to pass a fully-loaded Tenant ORM
                  instance (the resolver reads attributes only).
    Side effects: none. The lru_cache on _load_yaml_defaults is the
                  only caching layer.

    NAMING BRIDGE — slice 2A scope decision (see CHANGELOG [Unreleased]
    "Naming bridge in resolve_push_config" for context):
      PushConfig.morning_push_time   reads from tenant.briefing_morning_time
      PushConfig.evening_push_time   reads from tenant.briefing_evening_time
      PushConfig.push_timezone       reads from tenant.briefing_timezone
      PushConfig.morning_enabled     reads from tenant.briefing_morning_enabled
      PushConfig.evening_enabled     reads from tenant.briefing_evening_enabled

    These five briefing_* columns were added by migration 027 (v6.3.1)
    and are NOT NULL with server_defaults — so the YAML fallback is
    operationally inert for them today and serves as documentation of
    design intent. Migration 033 (v6.3.19) added morning_sections,
    evening_sections, and push_paused_until as the only genuinely new
    columns; for the two sections fields the cascade is operational
    (nullable with no server_default). push_paused_until has no YAML
    fallback because None means "not paused" and is the same answer
    the resolver returns without consulting the YAML.

    A future slice 2A-rename can unify the namespace by renaming
    briefing_* → push_* in a single breaking migration when the cost
    of the inconsistency outweighs migration churn.
    """
    defaults = _load_yaml_defaults()

    morning_push_time = (
        tenant.briefing_morning_time
        if tenant.briefing_morning_time is not None
        else _parse_time(defaults["morning_push_time"])
    )
    evening_push_time = (
        tenant.briefing_evening_time
        if tenant.briefing_evening_time is not None
        else _parse_time(defaults["evening_push_time"])
    )
    push_timezone = (
        tenant.briefing_timezone
        if tenant.briefing_timezone is not None
        else str(defaults["push_timezone"])
    )
    morning_enabled = (
        tenant.briefing_morning_enabled
        if tenant.briefing_morning_enabled is not None
        else bool(defaults["morning_enabled"])
    )
    evening_enabled = (
        tenant.briefing_evening_enabled
        if tenant.briefing_evening_enabled is not None
        else bool(defaults["evening_enabled"])
    )
    morning_sections = tuple(
        tenant.morning_sections
        if tenant.morning_sections is not None
        else defaults["morning_sections"]
    )
    evening_sections = tuple(
        tenant.evening_sections
        if tenant.evening_sections is not None
        else defaults["evening_sections"]
    )
    push_paused_until = tenant.push_paused_until

    return PushConfig(
        morning_push_time=morning_push_time,
        evening_push_time=evening_push_time,
        push_timezone=push_timezone,
        morning_enabled=morning_enabled,
        evening_enabled=evening_enabled,
        morning_sections=morning_sections,
        evening_sections=evening_sections,
        push_paused_until=push_paused_until,
    )
