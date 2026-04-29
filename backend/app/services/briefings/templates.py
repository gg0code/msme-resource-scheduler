# app/services/briefings/templates.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Locale-aware string templates for the daily push briefings (v6.3.4).
# All hardcoded strings the briefing generators emit live here so that
# vocabulary tweaks, language additions, and idle-floor messaging never
# require touching the data-collection or formatting code.
#
# WHO CALLS THIS FILE
# - app/services/briefings/morning_content.py - forward-looking strings.
# - app/services/briefings/evening_content.py - backward-looking strings.
# - tests/test_briefings.py                   - directly when asserting
#                                               idle-floor / locale paths.
#
# WHAT THIS FILE CALLS
# - Nothing. Pure data + small lookup helpers, no imports beyond stdlib
#   typing. The dispatcher chain stays unidirectional: dispatcher ->
#   {morning,evening}_content -> templates.
#
# DESIGN NOTES
# - Three locale variants per template: en (English), hi-en (Hinglish:
#   Hindi in roman script with English mixed in), and hi (romanised
#   Hindi). The codebase enforces ASCII-only source files (see CLAUDE.md
#   "No Non-ASCII in Source Files"), so the 'hi' locale stores the
#   Devanagari pronunciation in roman script - matching the existing
#   pattern in whatsapp_alerts.py (e.g. "abhi maintenance mode mein
#   hai"). Hinglish is the default in the field so it is the value
#   pickers fall back to when an unknown locale is requested.
# - Industry vocabulary (jobs vs orders vs runs, employees vs operators
#   vs technicians) is supplied via the labels mapping in
#   `INDUSTRY_LABELS` below. Templates accept named placeholders so the
#   content generators can substitute industry terms without branching.
# - The 1000-character cap (per SRS Section 6.28.4) is enforced by the
#   content generators - templates here are short on purpose so the cap
#   is reached only when the data list is genuinely long.

from typing import Literal

# ---------------------------------------------------------------------------
# LOCALE TYPE
# ---------------------------------------------------------------------------
# 'hi-en' is Hinglish (Hindi vocabulary in Latin script). 'hi' is the
# closest ASCII proxy to spoken Hindi (still roman script, no Devanagari
# in source files - see DESIGN NOTES above). 'en' is plain English. The
# dispatcher resolves locale from tenant or recipient context; manual
# triggers default to 'hi-en' to match v5.12 manager-checkin behaviour.

Locale = Literal["en", "hi", "hi-en"]

DEFAULT_LOCALE: Locale = "hi-en"


# ---------------------------------------------------------------------------
# INDUSTRY LABELS
# ---------------------------------------------------------------------------
# Maps tenant.industry_type -> vocabulary substitutions used inside the
# briefing strings. The keys mirror the frontend `useLabels()` hook so
# desktop and WhatsApp surfaces speak the same vertical-specific
# language. Fallback for unknown industries is `printing` (the v5.12
# pilot vertical) because every template was first written for it.
#
# IMPORTANT: do not branch control flow on industry_type. Use the
# `industry_labels(industry_type)` helper to resolve the mapping once
# and pass the result through templates. BUG-6 regression: industry
# comes from Tenant.industry_type, not from any user input.

INDUSTRY_LABELS: dict[str, dict[str, str]] = {
    "printing": {
        "job":         "job",
        "jobs":        "jobs",
        "employees":   "employees",
        "machine":     "press",
        "machines":    "presses",
    },
    "fabrication": {
        "job":         "order",
        "jobs":        "orders",
        "employees":   "operators",
        "machine":     "machine",
        "machines":    "machines",
    },
    "manufacturing": {
        "job":         "job",
        "jobs":        "jobs",
        "employees":   "operators",
        "machine":     "machine",
        "machines":    "machines",
    },
    "chemical": {
        "job":         "batch",
        "jobs":        "batches",
        "employees":   "operators",
        "machine":     "reactor",
        "machines":    "reactors",
    },
    "field_service": {
        "job":         "ticket",
        "jobs":        "tickets",
        "employees":   "technicians",
        "machine":     "asset",
        "machines":    "assets",
    },
}


def industry_labels(industry_type: str | None) -> dict[str, str]:
    """
    Resolve industry-specific vocabulary for briefing string templates.

    Called by:    morning_content.build_morning_briefing,
                  evening_content.build_evening_briefing.
    Calls into:   nothing - pure dict lookup with fallback.
    Side effects: none.

    Args:
        industry_type: Tenant.industry_type value. May be None for
                       legacy tenants whose industry was never set.

    Returns:
        The label dict for the matched industry, or the printing fallback
        when industry_type is None or not in INDUSTRY_LABELS. Never
        raises - unknown verticals degrade gracefully to printing
        vocabulary so the briefing still ships.
    """
    if industry_type is None:
        return INDUSTRY_LABELS["printing"]
    return INDUSTRY_LABELS.get(industry_type, INDUSTRY_LABELS["printing"])


# ---------------------------------------------------------------------------
# TEMPLATE STRINGS
# ---------------------------------------------------------------------------
# Each template key resolves to one of three locale variants. Missing
# variants fall back via `pick_template`. All placeholders use named
# substitution so callers can pass kwargs in any order.
#
# Per CLAUDE.md every string is ASCII-only - even the 'hi' variants use
# romanised Hindi (e.g. "Suprabhat" rather than the Devanagari
# equivalent). The existing whatsapp_alerts.py and whatsapp_checkin.py
# strings follow the same convention.

TEMPLATES: dict[str, dict[Locale, str]] = {
    # ------------------------------------------------------------------
    # MORNING BRIEFING - forward-looking, sent at the configured morning
    # time per tenant (default 07:30 IST). `{date}` resolves to a short
    # human date such as '15 Apr'. `{job_label}` and `{employee_label}`
    # come from industry_labels(industry_type).
    # ------------------------------------------------------------------
    "morning_header": {
        "en":    "Good morning! Today's plan - {date}",
        "hi":    "Suprabhat! Aaj ka plan - {date}",
        "hi-en": "Good morning! Aaj ka plan - {date}",
    },
    "morning_jobs_line": {
        "en":    "{job_label_caps}: {today_count} planned today",
        "hi-en": "{job_label_caps}: {today_count} aaj planned",
        "hi":    "{job_label_caps}: {today_count} aaj.",
    },
    "morning_blocker_line": {
        "en":    "Blockers: {blocker_count}",
        "hi-en": "Blockers: {blocker_count}",
        "hi":    "Rukawatein: {blocker_count}",
    },
    "morning_idle": {
        "en":    "Good morning! No {jobs_label} on the floor today. Quiet day ahead.",
        "hi-en": "Good morning! Aaj koi {jobs_label} schedule mein nahi hai. Aaram ka din.",
        "hi":    "Suprabhat! Aaj koi {jobs_label} nahi hai.",
    },
    "morning_more_marker": {
        "en":    "...and {n_more} more",
        "hi-en": "...aur {n_more} aur",
        "hi":    "...aur {n_more}",
    },

    # ------------------------------------------------------------------
    # EVENING BRIEFING - backward-looking, sent at the configured
    # evening time per tenant (default 18:30 IST). `{completed_count}`,
    # `{attendance_count}` come from data collectors.
    # ------------------------------------------------------------------
    "evening_header": {
        "en":    "End of day recap - {date}",
        "hi-en": "Aaj ka recap - {date}",
        "hi":    "Shubh sandhya! Aaj ka recap - {date}.",
    },
    "evening_done_line": {
        "en":    "{job_label_caps} completed today: {completed_count}",
        "hi-en": "Aaj complete hue {jobs_label}: {completed_count}",
        "hi":    "Pure hue {jobs_label}: {completed_count}.",
    },
    "evening_attendance_line": {
        "en":    "{employee_label_caps} present: {attendance_count}",
        "hi-en": "Present {employees_label}: {attendance_count}",
        "hi":    "Hazir {employees_label}: {attendance_count}.",
    },
    "evening_blocker_line": {
        "en":    "Blockers raised today: {blocker_count}",
        "hi-en": "Blockers aaj: {blocker_count}",
        "hi":    "Rukawatein: {blocker_count}.",
    },
    "evening_top_for_tomorrow_line": {
        "en":    "Top for tomorrow: {top_for_tomorrow}",
        "hi-en": "Kal ke liye sabse pehla: {top_for_tomorrow}",
        "hi":    "Kal ke liye sabse pehla: {top_for_tomorrow}.",
    },
    "evening_idle": {
        "en":    "End of day. Floor was idle today - no {jobs_label} ran. Plan ahead for tomorrow.",
        "hi-en": "Aaj floor idle tha - koi {jobs_label} nahi chala. Kal ka plan banao.",
        "hi":    "Shubh sandhya! Aaj koi {jobs_label} nahi chala.",
    },
}


def pick_template(key: str, locale: Locale | None = None) -> str:
    """
    Resolve a template key to its locale string.

    Called by:    morning_content + evening_content content generators.
    Calls into:   TEMPLATES dict lookup; falls back through DEFAULT_LOCALE
                  then English when a variant is missing.
    Side effects: none.

    Args:
        key:    One of the keys in TEMPLATES (morning_*, evening_*).
        locale: Target locale ('en', 'hi', 'hi-en'). Falls back to
                DEFAULT_LOCALE ('hi-en') when None or unknown.

    Returns:
        The string template (still containing {placeholders} - the
        caller substitutes via str.format(**kwargs)).

    Raises:
        KeyError if the template key itself does not exist - that is a
        programming error, not a runtime miss; surface it loudly.
    """
    locale_map = TEMPLATES[key]
    chosen = locale or DEFAULT_LOCALE
    if chosen in locale_map:
        return locale_map[chosen]
    # Fall back through the default locale, then English.
    if DEFAULT_LOCALE in locale_map:
        return locale_map[DEFAULT_LOCALE]
    return locale_map.get("en", "")
