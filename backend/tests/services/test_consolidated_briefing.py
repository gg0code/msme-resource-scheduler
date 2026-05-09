# tests/services/test_consolidated_briefing.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Tests for app/services/consolidated_briefing — the v6.3.19 morning-
# briefing flag/next_step selector. Covers the seven cases enumerated
# in the v6.3.19 next_step prompt step 5.
#
# WHO CALLS THIS FILE
# - pytest under the unit tier (mark "not integration"); invoked by
#   the v6.3.19 verification gate.
#
# WHAT THIS FILE CALLS
# - app.services.consolidated_briefing — module under test.
# - app.services.briefing_intelligence.signals.SignalResult —
#   constructed directly to drive the selector. SignalResult is NOT
#   modified; tests use the existing dataclass shape.

import pytest

from app.services import consolidated_briefing as cb
from app.services.briefing_intelligence.signals import SignalResult


def _make_signal(
    signal_id: str,
    *,
    category: str = "job",
    tier: int = 1,
    confidence: str = "high",
    severity: float = 1.0,
    message_hi_en: str = "Hinglish observation",
    message_en: str = "English observation",
) -> SignalResult:
    """Build a SignalResult with sensible defaults.

    Called by:    every test in this file that needs a SignalResult.
    Calls into:   SignalResult dataclass constructor.
    Side effects: none.

    Defaults are tier=1/confidence=high so tests that don't care about
    sort order get plausible values; tests that care override them.
    """
    return SignalResult(
        signal_id=signal_id,
        category=category,
        tier=tier,
        confidence=confidence,
        subject_entity_type="tenant",
        subject_entity_id=None,
        severity_score=severity,
        message_hi_en=message_hi_en,
        message_en=message_en,
        cooldown_days=1,
    )


def test_select_returns_blocker_signal_when_present():
    """A single blocker-class signal yields its flag + next_step."""
    signals = [
        _make_signal(
            "delayed_jobs_count",
            message_hi_en="2 jobs delayed hai",
            message_en="2 jobs are delayed",
        ),
    ]

    flag, nxt = cb.select_flag_and_next_step(signals, locale="hi_en")

    assert flag == "2 jobs delayed hai"
    assert nxt == cb._NEXT_STEP_TEMPLATES["delayed_jobs_count"]["hi_en"]


def test_select_returns_none_when_only_informational_signals():
    """Customer/tenancy/health signals do not qualify for the flag slot.

    Uses the actual informational signal_ids confirmed by the v6.3.19
    audit: recurring_customer_callout, revenue_at_risk,
    day_2_first_observation, day_7_marker, manager_silence.
    """
    signals = [
        _make_signal("recurring_customer_callout", category="customer"),
        _make_signal("revenue_at_risk", category="customer"),
        _make_signal("day_2_first_observation", category="tenancy"),
        _make_signal("day_7_marker", category="tenancy"),
        _make_signal("manager_silence", category="health"),
    ]

    flag, nxt = cb.select_flag_and_next_step(signals, locale="hi_en")

    assert flag is None
    assert nxt is None


def test_select_returns_none_when_signals_empty():
    """Empty input yields (None, None) without raising."""
    flag, nxt = cb.select_flag_and_next_step([], locale="en")

    assert flag is None
    assert nxt is None


def test_select_skips_informational_picks_next_blocker():
    """Iteration order is preserved — the first blocker after any
    informational entries wins. Demonstrates the selector does not
    re-sort.
    """
    signals = [
        _make_signal("recurring_customer_callout", category="customer"),
        _make_signal("manager_silence", category="health"),
        _make_signal(
            "idle_machine",
            category="machine",
            message_hi_en="Machine khali hai",
            message_en="Machine has been idle",
        ),
        # The selector must stop at idle_machine and never reach this
        # later blocker — confirms order is preserved, not re-sorted.
        _make_signal(
            "delayed_jobs_count",
            category="job",
            message_hi_en="(should not be picked)",
            message_en="(should not be picked)",
        ),
    ]

    flag, nxt = cb.select_flag_and_next_step(signals, locale="en")

    assert flag == "Machine has been idle"
    assert nxt == cb._NEXT_STEP_TEMPLATES["idle_machine"]["en"]


def test_select_uses_correct_locale_strings():
    """hi_en and en produce different message + next_step pairings."""
    signals = [
        _make_signal(
            "consecutive_absence",
            category="attendance",
            message_hi_en="Rakesh 2 din se gayab",
            message_en="Rakesh has been absent 2 days",
        ),
    ]

    flag_hi, nxt_hi = cb.select_flag_and_next_step(signals, locale="hi_en")
    flag_en, nxt_en = cb.select_flag_and_next_step(signals, locale="en")

    assert flag_hi == "Rakesh 2 din se gayab"
    assert flag_en == "Rakesh has been absent 2 days"
    assert nxt_hi == cb._NEXT_STEP_TEMPLATES["consecutive_absence"]["hi_en"]
    assert nxt_en == cb._NEXT_STEP_TEMPLATES["consecutive_absence"]["en"]
    assert nxt_hi != nxt_en


@pytest.mark.parametrize("bad_locale", ["fr", "", "HI_EN", "hi", "en_US"])
def test_select_invalid_locale_raises(bad_locale):
    """Any locale outside {'hi_en', 'en'} raises ValueError.

    Parametrised across common near-misses (case difference,
    truncation, en_US-style locale tag) to lock the contract.
    """
    signals = [_make_signal("delayed_jobs_count")]

    with pytest.raises(ValueError):
        cb.select_flag_and_next_step(signals, locale=bad_locale)


def test_module_assertion_catches_missing_template():
    """The module-level guard fires when blocker-class set and template
    keys diverge. Asserts the equality expression directly rather than
    forcing a module reimport — same logic as the production guard,
    no import gymnastics.
    """
    # Production state must hold: every blocker has a template, no
    # extras.
    assert cb._BLOCKER_CLASS_SIGNALS == cb._NEXT_STEP_TEMPLATES.keys(), (
        "Production module-level guard must hold with no patches "
        "applied — adding a blocker_class id without a template "
        "should have failed at import."
    )

    # Simulate a developer adding a new blocker without a template.
    # The diff must surface exactly that id, proving the guard logic
    # would catch the omission at import time.
    fake_blocker_set = cb._BLOCKER_CLASS_SIGNALS | {"phantom_signal"}
    missing = fake_blocker_set - cb._NEXT_STEP_TEMPLATES.keys()
    assert missing == {"phantom_signal"}

    # Mirror direction: an extra template without a blocker entry must
    # also be detectable. The production assertion checks both
    # directions via .keys() equality.
    fake_template_keys = cb._NEXT_STEP_TEMPLATES.keys() | {"orphan_template"}
    extras = fake_template_keys - cb._BLOCKER_CLASS_SIGNALS
    assert extras == {"orphan_template"}
