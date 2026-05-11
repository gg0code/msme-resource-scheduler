# app/services/push_settings_service.py - Version 1.0
# Branch: v5-whatsapp
# Introduced: v6.3.20 (WhatsApp NL push-settings updater)
#
# FILE PURPOSE
# Server-side write surface for push-briefing settings. Backs three Groq AI
# tools (update_push_setting / pause_push / get_push_settings) with a fixed
# whitelist + per-field validators + tenant-isolated UPDATEs + an audit row
# per write.
#
# Architecturally: AI extracts intent + params from owner natural language;
# this module is the security boundary that decides what the LLM is
# *allowed* to change and how the value must be shaped. The LLM never gets
# raw SQL; the only writes it can produce are the ones EDITABLE_FIELDS
# enumerates here.
#
# WHO CALLS THIS FILE
# - app/services/ai_service.py — execute_tool() dispatches the three v6.3.20
#   tool names into update_push_setting / pause_push / get_push_settings.
# - tests/test_push_settings_service.py — unit coverage for the whitelist,
#   validators, audit shape, top-tier gate, tenant isolation, and the
#   today + (days - 1) pause arithmetic in tenant timezone.
#
# WHAT THIS FILE CALLS
# - app.models.auth.{Tenant, User, TOP_TIER_ROLES} — ORM + role tuple.
# - app.models.event.Event — audit row insert.
# - sqlalchemy.orm.Session — sync only (architecture rule 7: WhatsApp
#   services use sync Session, never AsyncSession).
# - zoneinfo.ZoneInfo — tenant-local "today" computation for the pause
#   arithmetic and the is_currently_paused derived bool.
#
# DESIGN NOTES
# - EDITABLE_FIELDS is the entire write surface. morning_sections and
#   evening_sections are deliberately *not* in it: structured section
#   editing is desktop-only by product decision (v6.3.20 ships timing +
#   pause; sections come later). Attempts to write them produce a
#   typed `field_not_editable_via_whatsapp` error whose user-facing
#   message redirects the owner to Settings → Push Briefings on
#   desktop. This is intentional scope, not a TODO.
# - Audit row is written in the same transaction as the column UPDATE.
#   If the audit insert fails the column UPDATE is rolled back, never
#   "the column changed but no audit row exists".
# - Pause arithmetic uses today + (days - 1) so days=5 sent on Tuesday
#   yields Saturday as the last paused date, with the dispatcher
#   resuming Sunday. The dispatcher pause check is inclusive on
#   push_paused_until (consolidated_briefing._dispatch_one:846-864).
# - User-scoped fields require actor==target OR actor.role in {owner,
#   proprietor}. Co-Owner and Factory Manager can change their own
#   overrides but not another top-tier user's. This is the minimum
#   surface that doesn't require a new permissions table.
# - All error messages are trilingual (English / Hinglish / Hindi).
#   The WhatsApp response layer picks the surface language from the
#   v5.12 detect_language() output.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models.auth import TOP_TIER_ROLES, Tenant, User
from app.models.event import Event


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

PUSH_SETTING_CHANGED_EVENT_TYPE: str = "tenant.push_setting_changed"

_DEFAULT_TIMEZONE: str = "Asia/Kolkata"

_OWNER_ROLES: frozenset[str] = frozenset({"owner", "proprietor"})

_MIN_PAUSE_DAYS: int = 1
_MAX_PAUSE_DAYS: int = 30

# Field names that exist on tenants but are deliberately not editable
# via WhatsApp NL. Surfaced read-only by get_push_settings.
_DESKTOP_ONLY_FIELDS: frozenset[str] = frozenset(
    {"morning_sections", "evening_sections"}
)


# ---------------------------------------------------------------------------
# EXCEPTIONS
# ---------------------------------------------------------------------------

class PushSettingValidationError(Exception):
    """Raised when a proposed setting value fails the whitelist or validator.

    Carries a machine-readable code and trilingual messages so the WhatsApp
    response layer can pick the surface language without parsing the string.
    """

    def __init__(self, code: str, messages: dict[str, str]) -> None:
        super().__init__(f"{code}: {messages.get('en', '')}")
        self.code = code
        self.messages = messages  # keys: 'en', 'hi_en', 'hi'


class PushSettingForbidden(Exception):
    """Raised when the actor lacks permission for the requested change."""

    def __init__(self, code: str, messages: dict[str, str]) -> None:
        super().__init__(f"{code}: {messages.get('en', '')}")
        self.code = code
        self.messages = messages


# ---------------------------------------------------------------------------
# TRILINGUAL MESSAGE TEMPLATES
# ---------------------------------------------------------------------------
# Kept as plain dict literals (not lazy-loaded) so test failures show the
# exact strings inline. These cover every error code raised below.

_MSG = {
    "unknown_field": {
        "en": "I don't recognise that setting. Try 'morning briefing time' or 'evening recap time'.",
        "hi_en": "Yeh setting samajh nahi aayi. 'Morning briefing time' ya 'evening recap time' bolkar dekhiye.",
        "hi": "यह सेटिंग नहीं समझ पाया। 'Morning briefing time' या 'evening recap time' कहकर देखिए।",
    },
    "field_not_editable_via_whatsapp": {
        "en": "Briefing sections can only be changed from the desktop app. Open Settings → Push Briefings on your computer.",
        "hi_en": "Briefing ke sections sirf desktop se badal sakte ho. Apne computer pe Settings → Push Briefings kholo.",
        "hi": "Briefing के sections सिर्फ़ desktop से बदल सकते हो। अपने computer पर Settings → Push Briefings खोलो।",
    },
    "invalid_bool": {
        "en": "Please answer with on/off or yes/no.",
        "hi_en": "On/off ya haan/nahi se jawab dijiye.",
        "hi": "On/off या हाँ/नहीं से जवाब दीजिए।",
    },
    "invalid_time_format": {
        "en": "Please give the time as HH:MM in 24-hour format, e.g. 08:00 or 20:00.",
        "hi_en": "Time HH:MM 24-hour format me dijiye, jaise 08:00 ya 20:00.",
        "hi": "Time HH:MM 24-hour format में दीजिए, जैसे 08:00 या 20:00।",
    },
    "unknown_timezone": {
        "en": "I don't recognise that timezone. Try 'Asia/Kolkata' or another IANA timezone name.",
        "hi_en": "Yeh timezone samajh nahi aaya. 'Asia/Kolkata' ya koi aur IANA name dijiye.",
        "hi": "यह timezone नहीं समझ पाया। 'Asia/Kolkata' या कोई और IANA name दीजिए।",
    },
    "weekday_out_of_range": {
        "en": "Working days must be a list of numbers 1-7 (Monday=1). Example: 1,2,3,4,5,6.",
        "hi_en": "Working days 1-7 ke numbers me dijiye (Monday=1). Example: 1,2,3,4,5,6.",
        "hi": "Working days 1-7 के numbers में दीजिए (Monday=1)। Example: 1,2,3,4,5,6।",
    },
    "pause_days_out_of_range": {
        "en": f"Pause must be between {_MIN_PAUSE_DAYS} and {_MAX_PAUSE_DAYS} days.",
        "hi_en": f"Pause {_MIN_PAUSE_DAYS} se {_MAX_PAUSE_DAYS} din ke beech ho sakta hai.",
        "hi": f"Pause {_MIN_PAUSE_DAYS} से {_MAX_PAUSE_DAYS} दिन के बीच हो सकता है।",
    },
    "forbidden_not_top_tier": {
        "en": "Only the Owner, Co-Owner, or Factory Manager can change push settings.",
        "hi_en": "Sirf Owner, Co-Owner, ya Factory Manager push settings badal sakte hain.",
        "hi": "सिर्फ़ Owner, Co-Owner, या Factory Manager push settings बदल सकते हैं।",
    },
    "forbidden_other_user_override": {
        "en": "Only the Owner can change another user's overrides. You can change your own.",
        "hi_en": "Doosre user ki settings sirf Owner badal sakte hain. Apni settings badal sakte ho.",
        "hi": "दूसरे user की settings सिर्फ़ Owner बदल सकते हैं। अपनी settings बदल सकते हो।",
    },
    "actor_not_found": {
        "en": "Could not identify your account. Please log in again.",
        "hi_en": "Aapka account nahi mila. Phir se login kijiye.",
        "hi": "आपका account नहीं मिला। फिर से login कीजिए।",
    },
    "tenant_not_found": {
        "en": "Tenant not found.",
        "hi_en": "Tenant nahi mila.",
        "hi": "Tenant नहीं मिला।",
    },
    "target_user_not_found": {
        "en": "Could not find that user.",
        "hi_en": "Woh user nahi mila.",
        "hi": "वह user नहीं मिला।",
    },
}


# ---------------------------------------------------------------------------
# VALIDATORS
# ---------------------------------------------------------------------------

_BOOL_TRUE: frozenset[str] = frozenset(
    {"true", "on", "haan", "yes", "1", "enable", "enabled", "chalu"}
)
_BOOL_FALSE: frozenset[str] = frozenset(
    {"false", "off", "nahi", "no", "0", "disable", "disabled", "band", "bandh"}
)


def _validate_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        if raw == 0:
            return False
        if raw == 1:
            return True
    if isinstance(raw, str):
        norm = raw.strip().lower()
        if norm in _BOOL_TRUE:
            return True
        if norm in _BOOL_FALSE:
            return False
    raise PushSettingValidationError("invalid_bool", _MSG["invalid_bool"])


def _validate_time_hhmm(raw: Any) -> time:
    """Strict HH:MM 24-hour. Rejects '8 baje', '8pm', '08:00 AM'.

    The LLM is responsible for normalising owner phrasing to HH:MM before
    calling the tool. If it cannot, the validator refuses and the LLM has
    to ask for clarification — silent coercion is the wrong answer here.
    """
    if not isinstance(raw, str):
        raise PushSettingValidationError("invalid_time_format", _MSG["invalid_time_format"])
    norm = raw.strip()
    if len(norm) != 5 or norm[2] != ":":
        raise PushSettingValidationError("invalid_time_format", _MSG["invalid_time_format"])
    hh, mm = norm[:2], norm[3:]
    if not (hh.isdigit() and mm.isdigit()):
        raise PushSettingValidationError("invalid_time_format", _MSG["invalid_time_format"])
    h, m = int(hh), int(mm)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise PushSettingValidationError("invalid_time_format", _MSG["invalid_time_format"])
    return time(h, m)


def _validate_iana_timezone(raw: Any) -> str:
    if not isinstance(raw, str):
        raise PushSettingValidationError("unknown_timezone", _MSG["unknown_timezone"])
    norm = raw.strip()
    try:
        ZoneInfo(norm)
    except (ZoneInfoNotFoundError, ValueError):
        raise PushSettingValidationError("unknown_timezone", _MSG["unknown_timezone"])
    except Exception:
        raise PushSettingValidationError("unknown_timezone", _MSG["unknown_timezone"])
    return norm


def _validate_weekday_csv(raw: Any) -> str:
    """ISO weekday CSV. Stored sorted ascending, deduplicated."""
    if not isinstance(raw, str):
        raise PushSettingValidationError("weekday_out_of_range", _MSG["weekday_out_of_range"])
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise PushSettingValidationError("weekday_out_of_range", _MSG["weekday_out_of_range"])
    days: set[int] = set()
    for p in parts:
        if not p.isdigit():
            raise PushSettingValidationError("weekday_out_of_range", _MSG["weekday_out_of_range"])
        n = int(p)
        if not (1 <= n <= 7):
            raise PushSettingValidationError("weekday_out_of_range", _MSG["weekday_out_of_range"])
        days.add(n)
    return ",".join(str(d) for d in sorted(days))


# ---------------------------------------------------------------------------
# WHITELIST
# ---------------------------------------------------------------------------
# Source of truth for what the LLM is allowed to write. AI-visible field name
# (== tool enum value) maps to the (table, column, validator, label) tuple.
# Anything off this list is rejected at the service boundary.

@dataclass(frozen=True)
class _FieldSpec:
    table: str  # 'tenants' or 'users'
    column: str
    validate: Any  # callable: raw_value -> Python value
    label_en: str  # for confirmation prompts and audit narration


EDITABLE_FIELDS: dict[str, _FieldSpec] = {
    # Tenant-scoped (top-tier role required; user_id ignored)
    "briefing_morning_enabled": _FieldSpec(
        "tenants", "briefing_morning_enabled", _validate_bool, "morning briefing on/off"
    ),
    "briefing_morning_time": _FieldSpec(
        "tenants", "briefing_morning_time", _validate_time_hhmm, "morning briefing time"
    ),
    "briefing_evening_enabled": _FieldSpec(
        "tenants", "briefing_evening_enabled", _validate_bool, "evening recap on/off"
    ),
    "briefing_evening_time": _FieldSpec(
        "tenants", "briefing_evening_time", _validate_time_hhmm, "evening recap time"
    ),
    "briefing_timezone": _FieldSpec(
        "tenants", "briefing_timezone", _validate_iana_timezone, "briefing timezone"
    ),
    "briefing_working_days": _FieldSpec(
        "tenants", "briefing_working_days", _validate_weekday_csv, "briefing working days"
    ),
    # User-scoped (top-tier role required; user_id required; non-Owner can
    # only change their own row)
    "briefing_time_override_morning": _FieldSpec(
        "users", "briefing_time_override_morning", _validate_time_hhmm, "your morning briefing time"
    ),
    "briefing_time_override_evening": _FieldSpec(
        "users", "briefing_time_override_evening", _validate_time_hhmm, "your evening recap time"
    ),
    "briefing_subscribed": _FieldSpec(
        "users", "briefing_subscribed", _validate_bool, "your briefing subscription on/off"
    ),
}


# ---------------------------------------------------------------------------
# RESULT TYPES
# ---------------------------------------------------------------------------

@dataclass
class PushSettingChangeResult:
    """Returned by update_push_setting + pause_push on success."""
    field: str
    old_value: Any
    new_value: Any
    table: str  # 'tenants' or 'users'
    entity_id: int  # tenant.id or user.id touched
    audit_event_id: int
    # Trilingual confirmation snippet for AI to narrate on YES.
    snippet: dict[str, str] = field(default_factory=dict)
    # pause_push fills these; update_push_setting leaves None.
    pause_range_human: str | None = None  # "Tue Sep 30 through Sat Oct 4, resume Sun Oct 5"
    paused_until: date | None = None


@dataclass
class PushSettingsView:
    """Read-only snapshot returned by get_push_settings."""
    tenant_id: int
    user_id: int | None
    # Tenant-scoped scalars
    briefing_morning_enabled: bool
    briefing_morning_time: time
    briefing_evening_enabled: bool
    briefing_evening_time: time
    briefing_timezone: str
    briefing_working_days: str
    # JSONB blobs (read-only over WhatsApp; desktop-edited)
    morning_sections: Any  # JSON-shaped (list/dict) or None
    evening_sections: Any
    # Pause state
    push_paused_until: date | None
    is_currently_paused: bool  # derived from push_paused_until + tenant tz today
    # User-scoped overrides (None when user_id is None)
    briefing_time_override_morning: time | None
    briefing_time_override_evening: time | None
    briefing_subscribed: bool | None


# ---------------------------------------------------------------------------
# AUTHORIZATION
# ---------------------------------------------------------------------------

def _require_top_tier(actor: User | None) -> None:
    if actor is None:
        raise PushSettingForbidden("actor_not_found", _MSG["actor_not_found"])
    if not actor.is_top_tier:
        raise PushSettingForbidden("forbidden_not_top_tier", _MSG["forbidden_not_top_tier"])


def _require_owner_or_self(actor: User, target_user_id: int) -> None:
    if actor.id == target_user_id:
        return
    if actor.role in _OWNER_ROLES:
        return
    raise PushSettingForbidden(
        "forbidden_other_user_override", _MSG["forbidden_other_user_override"]
    )


# ---------------------------------------------------------------------------
# AUDIT
# ---------------------------------------------------------------------------

def _serialize_for_audit(value: Any) -> Any:
    """JSON-safe representation for the audit payload.

    time / date / datetime become ISO strings; anything else is returned
    as-is (the caller has already filtered to scalar columns).
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return value


def _write_audit(
    *,
    db: Session,
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    actor_user_id: int,
    payload: dict[str, Any],
) -> Event:
    """Insert + flush the events row. Caller commits."""
    event = Event(
        tenant_id=tenant_id,
        event_type=PUSH_SETTING_CHANGED_EVENT_TYPE,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        source="whatsapp",
        payload=payload,
    )
    db.add(event)
    db.flush()
    return event


# ---------------------------------------------------------------------------
# TENANT-LOCAL DATE HELPER
# ---------------------------------------------------------------------------

def _tenant_today(tenant: Tenant) -> date:
    """Today in the tenant's briefing timezone, falling back to Asia/Kolkata.

    Used by pause_push for the today + (days - 1) arithmetic and by
    get_push_settings for the is_currently_paused derived bool. The
    dispatcher's pause check uses the same convention via
    consolidated_briefing._scheduled_date_for.
    """
    tz_name = tenant.briefing_timezone or _DEFAULT_TIMEZONE
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo(_DEFAULT_TIMEZONE)
    return datetime.now(tz).date()


# ---------------------------------------------------------------------------
# update_push_setting
# ---------------------------------------------------------------------------

def update_push_setting(
    db: Session,
    tenant_id: int,
    user_id: int | None,
    field: str,
    raw_value: Any,
    source_phrase: str,
    actor_user_id: int,
) -> PushSettingChangeResult:
    """Single-field update. Whitelist + validate + auth + UPDATE + audit.

    Tenant-scoped fields ignore user_id. User-scoped fields require user_id
    and apply the actor==target OR actor.role in {owner, proprietor} rule.

    Raises PushSettingValidationError or PushSettingForbidden on failure;
    no DB write happens on raise.

    Returns PushSettingChangeResult with the resolved old/new values and
    the inserted audit event id. Caller commits the session.
    """
    # Reject early: explicit desktop-only fields get a distinct error code
    # so the LLM can produce the helpful redirect message.
    if field in _DESKTOP_ONLY_FIELDS:
        raise PushSettingValidationError(
            "field_not_editable_via_whatsapp",
            _MSG["field_not_editable_via_whatsapp"],
        )

    spec = EDITABLE_FIELDS.get(field)
    if spec is None:
        raise PushSettingValidationError("unknown_field", _MSG["unknown_field"])

    new_value = spec.validate(raw_value)

    actor = db.query(User).filter(
        User.id == actor_user_id,
        User.tenant_id == tenant_id,  # rule 1: tenant_id on every query
    ).first()
    _require_top_tier(actor)

    if spec.table == "tenants":
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant is None:
            raise PushSettingValidationError("tenant_not_found", _MSG["tenant_not_found"])
        old_value = getattr(tenant, spec.column)
        setattr(tenant, spec.column, new_value)
        db.flush()
        entity_type = "tenant"
        entity_id = tenant.id

    else:  # spec.table == "users"
        if user_id is None:
            user_id = actor_user_id
        _require_owner_or_self(actor, user_id)
        target = db.query(User).filter(
            User.id == user_id,
            User.tenant_id == tenant_id,  # rule 1: tenant_id on every query
        ).first()
        if target is None:
            raise PushSettingValidationError("target_user_not_found", _MSG["target_user_not_found"])
        old_value = getattr(target, spec.column)
        setattr(target, spec.column, new_value)
        db.flush()
        entity_type = "user"
        entity_id = target.id

    payload = {
        "field": field,
        "old_value": _serialize_for_audit(old_value),
        "new_value": _serialize_for_audit(new_value),
        "source_phrase": source_phrase,
    }
    event = _write_audit(
        db=db,
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        payload=payload,
    )

    return PushSettingChangeResult(
        field=field,
        old_value=_serialize_for_audit(old_value),
        new_value=_serialize_for_audit(new_value),
        table=spec.table,
        entity_id=entity_id,
        audit_event_id=event.id,
        snippet={
            "en": f"Updated {spec.label_en} to {_serialize_for_audit(new_value)}.",
            "hi_en": f"{spec.label_en.capitalize()} {_serialize_for_audit(new_value)} kar diya.",
            "hi": f"{spec.label_en.capitalize()} {_serialize_for_audit(new_value)} कर दिया।",
        },
    )


# ---------------------------------------------------------------------------
# pause_push
# ---------------------------------------------------------------------------

def _format_pause_range(start: date, last_paused: date) -> str:
    """'Tue Sep 30 through Sat Oct 4, resume Sun Oct 5' for the confirm prompt."""
    resume = last_paused + timedelta(days=1)
    if start == last_paused:
        return f"{start.strftime('%a %b %d')} only, resume {resume.strftime('%a %b %d')}"
    return (
        f"{start.strftime('%a %b %d')} through {last_paused.strftime('%a %b %d')}, "
        f"resume {resume.strftime('%a %b %d')}"
    )


def pause_push(
    db: Session,
    tenant_id: int,
    days: int,
    source_phrase: str,
    actor_user_id: int,
) -> PushSettingChangeResult:
    """Set tenants.push_paused_until = tenant_today + (days - 1).

    days must be in [1, 30]. Replaces any existing pause (not additive) —
    "agle 5 din band karo" means exactly 5 days from today, not 5 plus
    whatever was already in place.

    Raises PushSettingValidationError or PushSettingForbidden on failure.
    Returns PushSettingChangeResult with paused_until + the human-readable
    range string. Caller commits.
    """
    if not isinstance(days, int) or isinstance(days, bool):
        raise PushSettingValidationError(
            "pause_days_out_of_range", _MSG["pause_days_out_of_range"]
        )
    if not (_MIN_PAUSE_DAYS <= days <= _MAX_PAUSE_DAYS):
        raise PushSettingValidationError(
            "pause_days_out_of_range", _MSG["pause_days_out_of_range"]
        )

    actor = db.query(User).filter(
        User.id == actor_user_id,
        User.tenant_id == tenant_id,
    ).first()
    _require_top_tier(actor)

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise PushSettingValidationError("tenant_not_found", _MSG["tenant_not_found"])

    today_local = _tenant_today(tenant)
    new_paused_until = today_local + timedelta(days=days - 1)

    old_value = tenant.push_paused_until
    tenant.push_paused_until = new_paused_until
    db.flush()

    range_human = _format_pause_range(today_local, new_paused_until)

    payload = {
        "field": "push_paused_until",
        "old_value": _serialize_for_audit(old_value),
        "new_value": _serialize_for_audit(new_paused_until),
        "days": days,
        "source_phrase": source_phrase,
        "timezone": tenant.briefing_timezone or _DEFAULT_TIMEZONE,
        "today_local": today_local.isoformat(),
    }
    event = _write_audit(
        db=db,
        tenant_id=tenant_id,
        entity_type="tenant",
        entity_id=tenant.id,
        actor_user_id=actor_user_id,
        payload=payload,
    )

    return PushSettingChangeResult(
        field="push_paused_until",
        old_value=_serialize_for_audit(old_value),
        new_value=_serialize_for_audit(new_paused_until),
        table="tenants",
        entity_id=tenant.id,
        audit_event_id=event.id,
        paused_until=new_paused_until,
        pause_range_human=range_human,
        snippet={
            "en": f"Push briefings paused {range_human}.",
            "hi_en": f"Push briefings band kar diye: {range_human}.",
            "hi": f"Push briefings band कर दिए: {range_human}।",
        },
    )


# ---------------------------------------------------------------------------
# get_push_settings
# ---------------------------------------------------------------------------

def get_push_settings(
    db: Session,
    tenant_id: int,
    user_id: int | None,
) -> PushSettingsView:
    """Read-only view of every editable + read-only push setting.

    No audit row written. No top-tier gate (the caller's permission to
    even reach the AI tool dispatch is the gate; reads are not a state
    mutation). morning_sections / evening_sections returned as opaque
    JSON-shaped values so the AI can narrate them.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise PushSettingValidationError("tenant_not_found", _MSG["tenant_not_found"])

    paused_until = tenant.push_paused_until
    today_local = _tenant_today(tenant)
    is_paused = bool(paused_until and paused_until >= today_local)

    user_override_morning: time | None = None
    user_override_evening: time | None = None
    user_subscribed: bool | None = None
    if user_id is not None:
        target = db.query(User).filter(
            User.id == user_id,
            User.tenant_id == tenant_id,  # rule 1
        ).first()
        if target is not None:
            user_override_morning = target.briefing_time_override_morning
            user_override_evening = target.briefing_time_override_evening
            user_subscribed = target.briefing_subscribed

    return PushSettingsView(
        tenant_id=tenant_id,
        user_id=user_id,
        briefing_morning_enabled=bool(tenant.briefing_morning_enabled),
        briefing_morning_time=tenant.briefing_morning_time,
        briefing_evening_enabled=bool(tenant.briefing_evening_enabled),
        briefing_evening_time=tenant.briefing_evening_time,
        briefing_timezone=tenant.briefing_timezone or _DEFAULT_TIMEZONE,
        briefing_working_days=tenant.briefing_working_days,
        morning_sections=tenant.morning_sections,
        evening_sections=tenant.evening_sections,
        push_paused_until=paused_until,
        is_currently_paused=is_paused,
        briefing_time_override_morning=user_override_morning,
        briefing_time_override_evening=user_override_evening,
        briefing_subscribed=user_subscribed,
    )
