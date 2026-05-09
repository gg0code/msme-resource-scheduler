# app/services/consolidated_briefing.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.19 morning-briefing flag/next_step selector. Picks the top
# blocker-class signal from a sorted SignalResult list and returns
# (flag_text, next_step_text) for rendering through the v6.3.18
# Meta-bound MORNING_BRIEFING templates.
#
# This file is the lookup-table-only slice of v6.3.19. The dispatcher
# rewrite, cascade resolver, migrations 033/034, and template registry
# wiring are deliberately deferred to follow-up prompts; nothing in
# the codebase imports this module yet.
#
# WHO CALLS THIS FILE
# - tests/services/test_consolidated_briefing.py
# - (planned) v6.3.19 morning dispatch path — wires this into the
#   template render layer once the consolidated dispatcher lands.
#
# WHAT THIS FILE CALLS
# - app.services.briefing_intelligence.signals.SignalResult (type
#   only — does not invoke detectors or any DB).
#
# DESIGN NOTES
# - Static next_step lookup chosen over extending SignalResult
#   (Choice 1 from the v6.3.19 audit). Smallest blast radius:
#   doesn't touch the 13-evaluator catalog or the 5 xfail tests in
#   the catalog test files. Trade-off: action text lives away from
#   the detector that fires it; future tone refresh updates one
#   table here, not 8 evaluators.
# - 8 blocker-class signal_ids cover job/machine/attendance
#   categories. The 5 informational ids
#   (recurring_customer_callout, revenue_at_risk,
#   day_2_first_observation, day_7_marker, manager_silence) are
#   deliberately excluded — they convey context, not actions.
# - Locale "hi_en" maps to SignalResult.message_hi_en (Hinglish);
#   "en" maps to SignalResult.message_en. Per-recipient locale
#   resolution lives in the dispatcher, not here.
# - Module-level assertion fails loud at import time when someone
#   adds a signal_id to _BLOCKER_CLASS_SIGNALS without registering a
#   template — preferred over silently skipping at runtime.

from app.services.briefing_intelligence.signals import SignalResult


# Blocker-class signal_ids — the 8 ids whose semantics are "operational
# blocker that warrants a one-line flag + a one-line next step". The
# literal strings match the SIGNAL_ID constants on the corresponding
# evaluators (see catalog/job.py, catalog/machine.py, catalog/attendance.py).
_BLOCKER_CLASS_SIGNALS: frozenset[str] = frozenset(
    {
        "delayed_jobs_count",
        "no_progress",
        "idle_machine",
        "low_utilization",
        "status_change_alert",
        "consecutive_absence",
        "attendance_ratio_concern",
        "new_employee_no_show",
    }
)


# next_step text per signal_id, per locale. Tone follows v6.3.18 SRS
# Section 23: calm, specific, no exclamation, no emoji, polite imperative
# (e.g. "...karein" / "Plan a..."). Each string stays under 70 chars so
# it fits on one WhatsApp line on small-screen devices.
_NEXT_STEP_TEMPLATES: dict[str, dict[str, str]] = {
    "delayed_jobs_count": {
        "hi_en": "Crew ke saath aaj inka revised plan tay kar lein.",
        "en": "Set a revised plan with the crew today.",
    },
    "no_progress": {
        "hi_en": "Assigned worker se status update lein.",
        "en": "Ask the assigned worker for a status update.",
    },
    "idle_machine": {
        "hi_en": "Is hafte ke liye iska koi job plan kar lein.",
        "en": "Plan a job for it this week.",
    },
    "low_utilization": {
        "hi_en": "Iska weekly schedule review karke job add karein.",
        "en": "Review its weekly schedule and add a job.",
    },
    "status_change_alert": {
        "hi_en": "Repair timeline confirm karein aur jobs reassign karein.",
        "en": "Confirm the repair timeline and reassign affected jobs.",
    },
    "consecutive_absence": {
        "hi_en": "Employee se baat karke wajah samjhein.",
        "en": "Speak with the employee to understand the reason.",
    },
    "attendance_ratio_concern": {
        "hi_en": "Employee ke saath 1-on-1 plan karein.",
        "en": "Plan a one-on-one with the employee.",
    },
    "new_employee_no_show": {
        "hi_en": "Call karke joining confirm karein.",
        "en": "Call to confirm their joining date.",
    },
}


# Loud-failure guard — fires at import time if a developer adds an id
# to _BLOCKER_CLASS_SIGNALS without registering a matching template
# (or vice versa). Preferred over silently skipping the signal at
# runtime when the dispatcher tries to look it up.
assert _BLOCKER_CLASS_SIGNALS == _NEXT_STEP_TEMPLATES.keys(), (
    "Blocker-class signals without next_step template: "
    f"{_BLOCKER_CLASS_SIGNALS - _NEXT_STEP_TEMPLATES.keys()}; "
    "extra templates without blocker entry: "
    f"{_NEXT_STEP_TEMPLATES.keys() - _BLOCKER_CLASS_SIGNALS}"
)


_VALID_LOCALES: frozenset[str] = frozenset({"hi_en", "en"})


def select_flag_and_next_step(
    signals: list[SignalResult],
    locale: str,
) -> tuple[str | None, str | None]:
    """Pick the top blocker-class signal for the morning briefing flag line.

    Called by:    (planned) v6.3.19 morning dispatch path. Today only
                  test_consolidated_briefing.py exercises it.
    Calls into:   nothing — pure function over the input list.
    Side effects: none. No DB, no logging, no clock reads.

    Iterates `signals` in given order and returns (flag_text,
    next_step_text) for the first entry whose signal_id is in
    _BLOCKER_CLASS_SIGNALS. The caller MUST pre-sort via composer's
    _sort_key (tier ASC, confidence DESC, severity DESC) — this
    function does not re-sort.

    Returns (None, None) when:
      - signals is empty
      - no blocker-class signal_id is present (only informational ones)

    Raises ValueError when locale is not in {"hi_en", "en"}.
    """
    if locale not in _VALID_LOCALES:
        raise ValueError(
            f"Invalid locale {locale!r}. "
            f"Expected one of {sorted(_VALID_LOCALES)}."
        )

    for sig in signals:
        if sig.signal_id not in _BLOCKER_CLASS_SIGNALS:
            continue
        flag_text = sig.message_hi_en if locale == "hi_en" else sig.message_en
        next_step_text = _NEXT_STEP_TEMPLATES[sig.signal_id][locale]
        return flag_text, next_step_text

    return None, None
