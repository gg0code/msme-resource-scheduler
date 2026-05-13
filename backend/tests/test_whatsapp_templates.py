# tests/test_whatsapp_templates.py
# Branch: v5-whatsapp
# Iteration: v6.3.21 follow-up
#
# Tests for app.services.whatsapp_templates.resolve_template and the
# coverage invariant that every EVENT_ROUTING entry has at least one
# (name, en_US) row in META_TEMPLATES with a python_constant binding.

from __future__ import annotations

import logging

import pytest

from app.services.whatsapp_templates import (
    EVENT_ROUTING,
    ResolvedTemplate,
    UnknownEventError,
    ArgCountMismatchError,
    known_events,
    resolve_template,
)
from app.services.whatsapp_meta_templates import (
    META_TEMPLATES,
    count_meta_placeholders,
)


# ---------------------------------------------------------------------------
# Coverage invariant: every event has an en_US row + a bound constant
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("event", sorted(EVENT_ROUTING.keys()))
def test_every_event_has_en_us_entry_with_bound_constant(event: str) -> None:
    """Every EVENT_ROUTING entry must resolve to a META_TEMPLATES row
    in en_US with a non-None python_constant. This makes the language
    fallback safe (because en_US is always there) and confirms wiring
    is complete for every event the helper knows about."""
    meta_name = EVENT_ROUTING[event]
    key = (meta_name, "en_US")
    assert key in META_TEMPLATES, (
        f"event={event!r} routes to meta_name={meta_name!r} but no "
        f"en_US row exists in META_TEMPLATES."
    )
    entry = META_TEMPLATES[key]
    assert entry["python_constant"] is not None, (
        f"event={event!r} resolves to ({meta_name!r}, 'en_US') but "
        f"python_constant is None. Wire it in PYTHON_CONSTANT_BINDINGS."
    )


# ---------------------------------------------------------------------------
# Happy path: English
# ---------------------------------------------------------------------------

def test_resolve_morning_briefing_en_us_happy_path() -> None:
    result = resolve_template(
        event="morning_briefing",
        language="en_US",
        args=(
            "Tuesday, 30 April",
            "3",
            "1 (Patel brochures)",
            "10 of 11",
            "Rakesh on leave — Bhatia cards may slip 2 hrs",
            "Confirm Bhatia paper before 9 AM, or move Ramesh to cover",
        ),
    )
    assert isinstance(result, ResolvedTemplate)
    assert result.meta_name == "zetaops_morning_briefing"
    assert result.meta_language == "en_US"
    assert result.used_fallback is False
    assert len(result.meta_params) == 6
    assert "Tuesday, 30 April" in result.rendered_text
    assert "Bhatia" in result.rendered_text


def test_resolve_morning_briefing_hi_happy_path() -> None:
    result = resolve_template(
        event="morning_briefing",
        language="hi",
        args=(
            "मंगलवार, 30 अप्रैल",
            "3",
            "1 (पटेल brochures)",
            "10 में से 11",
            "राकेश छुट्टी पर",
            "9 बजे से पहले भाटिया का paper confirm करें",
        ),
    )
    assert result.meta_language == "hi"
    assert result.used_fallback is False
    assert "मंगलवार" in result.rendered_text


# ---------------------------------------------------------------------------
# Language fallback: hi requested, only en_US wired
# ---------------------------------------------------------------------------

def test_language_fallback_fires_when_hi_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """welcome_consent has both en_US and hi, but evening_briefing is
    en_US only. Asking for evening_briefing in hi must fall back, log
    a warning, and return en_US."""
    with caplog.at_level(logging.WARNING, logger="app.services.whatsapp_templates"):
        result = resolve_template(
            event="evening_briefing",
            language="hi",
            args=(
                "Tuesday, 30 April",
                "2 (Bhatia cards, Reliance flyers)",
                "76 hrs across 9 workers",
                "10/11 present",
                "Machine 2 belt repair needed",
                "Start Modi pamphlets at 8 AM, paper already loaded",
            ),
        )
    assert result.meta_language == "en_US"
    assert result.used_fallback is True
    assert any(
        "language fallback fired" in rec.message
        for rec in caplog.records
    )


def test_no_fallback_logged_when_hi_exists() -> None:
    """welcome_consent has both languages — requesting hi should NOT
    trigger any fallback log."""
    result = resolve_template(
        event="welcome_consent",
        language="hi",
        args=("शर्मा जी",),
    )
    assert result.meta_language == "hi"
    assert result.used_fallback is False


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_unknown_event_raises_with_known_list() -> None:
    with pytest.raises(UnknownEventError) as exc_info:
        resolve_template(
            event="totally_made_up_event",
            language="en_US",
            args=(),
        )
    msg = str(exc_info.value)
    assert "totally_made_up_event" in msg
    assert "morning_briefing" in msg


def test_invalid_language_raises_value_error() -> None:
    with pytest.raises(ValueError) as exc_info:
        resolve_template(
            event="morning_briefing",
            language="fr_FR",
            args=("a", "b", "c", "d", "e", "f"),
        )
    assert "fr_FR" in str(exc_info.value)


def test_hinglish_not_accepted_directly() -> None:
    """Hinglish must be classified upstream (SRS Section 6.18). The
    helper rejects 'hinglish' as a language code to prevent silent
    coercion."""
    with pytest.raises(ValueError):
        resolve_template(
            event="morning_briefing",
            language="hinglish",
            args=("a", "b", "c", "d", "e", "f"),
        )


def test_arg_count_too_few_raises() -> None:
    with pytest.raises(ArgCountMismatchError) as exc_info:
        resolve_template(
            event="morning_briefing",
            language="en_US",
            args=("only", "three", "args"),
        )
    msg = str(exc_info.value)
    assert "morning_briefing" in msg
    assert "expects 6" in msg
    assert "got 3" in msg


def test_arg_count_too_many_raises() -> None:
    with pytest.raises(ArgCountMismatchError):
        resolve_template(
            event="welcome_consent",
            language="en_US",
            args=("Sharma ji", "extra arg that shouldn't be here"),
        )


# ---------------------------------------------------------------------------
# Non-string args are coerced to str for meta_params
# ---------------------------------------------------------------------------

def test_non_string_args_are_str_coerced_for_meta_params() -> None:
    """Dispatchers will pass ints, floats, dates etc. The helper must
    str()-coerce for meta_params (Meta wire format is string-only) and
    pass through unchanged to .format() for rendered_text."""
    result = resolve_template(
        event="workspace_ready",
        language="en_US",
        args=("Sharma Printing Press", "7:30 AM"),
    )
    assert all(isinstance(p, str) for p in result.meta_params)


def test_int_arg_is_str_coerced() -> None:
    """compliance_reminder_t30 takes (item_name, due_date_str, what_to_prepare).
    If a caller accidentally passes an int (e.g. days-until as an int),
    meta_params must still be all-strings."""
    result = resolve_template(
        event="compliance_reminder_t30",
        language="en_US",
        args=("Trade licence renewal", "30 May 2026", 0),
    )
    assert result.meta_params == ["Trade licence renewal", "30 May 2026", "0"]


# ---------------------------------------------------------------------------
# known_events() accessor
# ---------------------------------------------------------------------------

def test_known_events_sorted_and_complete() -> None:
    events = known_events()
    assert events == sorted(events), "known_events() must return sorted output"
    assert set(events) == set(EVENT_ROUTING.keys())
    assert "morning_briefing" in events
    assert "manager_checkin" in events
    assert "performance_summary_monthly" in events
    assert "owner_day7_insight" in events
    assert "engagement_give_up_nudge" in events
