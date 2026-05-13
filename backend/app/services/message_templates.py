# app/services/message_templates.py
# Branch: v5-whatsapp
# Iteration: v6.3.18 (WhatsApp message styling pass — dispatcher cleanup)
#
# FILE PURPOSE
# Locale-dict template constants used by the v5.10 cron dispatcher
# (`whatsapp_alerts.py` morning briefing fallback, delay alert, conflict
# alert, machine-down alert) and the WhatsApp AI reply path. These are
# distinct from the Meta-bound `MORNING_BRIEFING_EN` / `MORNING_BRIEFING_HI`
# / `DELAY_ALERT_EN` / `CONFLICT_ALERT_EN` constants in
# `message_formatters.py`. The split is deliberate:
#
#   - `message_formatters.py` constants — bound 1:1 to Meta HSM templates;
#     anticipate fields (`jobs_starting`, `continuing`, `crew_expected`,
#     `flag`, `next_step`) the v5.10 dispatcher does NOT yet compute. They
#     ship in v6.3.18 as infrastructure for the v6.4 engagement ladder.
#   - This module — mirrors what the v5.10 dispatcher actually sends today
#     (active / total / delayed counts, employee headcount), with visual
#     hierarchy + emoji + Hinglish tone applied. Drop-in replacements for
#     the inline f-strings in `whatsapp_alerts.py`.
#
# Section 23 of the SRS (Voice, Tone, and Formatting Standards) is the
# policy reference; this file is the compliant set for the v5.10 path.
#
# WHO CALLS THIS FILE
# - app/services/whatsapp_alerts.py — _build_morning_briefing,
#   _build_delay_alert, _build_conflict_alert, send_machine_down_alert.
# - app/routers/whatsapp.py — the AI reply path (uses AI_REPLY_HEADER).
# - tests/services/test_message_dispatcher_templates.py — snapshot tests.
#
# WHAT THIS FILE CALLS
# - app/services/message_emoji.py — every emoji rendered in any template
#   here is sourced from the named constants there (AC 23-AC6).
# - typing.Literal for the Locale type alias.
#
# KEY DESIGN DECISIONS
# - Locale dicts ({"en", "hi-en", "hi"}) match the shape used by
#   `briefings/templates.py` so future readers see a consistent pattern.
#   The default locale is "hi-en" (Hinglish) — the same default the
#   existing v5.10 strings use.
# - Hinglish strings mirror current production wording verbatim where it
#   exists ("Maafi kijiye, kuch gadbad ho gayi", "Details ke liye
#   poochein") so user-side muscle memory is preserved.
# - Visual hierarchy: every full-message template renders as
#       <header line>
#       <blank line>
#       <items>
#       <blank line>
#       <action prompt>
#   The blank line is a literal '\n\n' in the template — WhatsApp renders
#   blank lines verbatim, they are part of the wire payload.
# - AI_REPLY_HEADER is a single English string (not a locale dict). It
#   is a thin warm-greeting prefix appended to every raw AI reply on the
#   WhatsApp surface; the AI's body text already carries language-detected
#   content, so wrapping the header in English keeps the prefix
#   linguistically neutral.
# - Length cap: every rendered template under standard fixtures stays at
#   or under 800 characters (soft target) and 1000 characters (hard
#   ceiling). Enforced by tests.

from __future__ import annotations

from typing import Literal

from app.services.message_emoji import (
    DOMAIN_JOB,
    PROMPT_ACTION_NEEDED,
    PROMPT_GREETING,
    SEVERITY_ALERT,
    SEVERITY_WARNING,
)


# ---------------------------------------------------------------------------
# Locale type
# ---------------------------------------------------------------------------
# 'hi-en' is Hinglish (Hindi vocabulary in roman script); 'hi' is romanised
# Hindi (closest ASCII proxy to Devanagari for callers that haven't yet
# adopted the Devanagari templates in message_formatters.py); 'en' is plain
# English. The default (`DEFAULT_LOCALE`) is 'hi-en' — matches the existing
# v5.10 dispatcher behaviour.

Locale = Literal["en", "hi-en", "hi"]

DEFAULT_LOCALE: Locale = "hi-en"


# ---------------------------------------------------------------------------
# MORNING_BRIEFING — locale dict (Meta has approved both en + hi)
# ---------------------------------------------------------------------------
# Used by whatsapp_alerts._build_morning_briefing. Placeholder map:
#     {date}            "08 May 2026"
#     {active_jobs}     int
#     {total_jobs}      int
#     {delayed_line}    pre-formatted '⚠️ DELAYED: N jobs need attention\n'
#                       or empty string when nothing is delayed
#     {total_employees} int
# The {delayed_line} kwarg is pre-formatted by the caller because the
# delayed bullet is conditional — keeping the conditional logic in Python
# keeps the template a pure str.format string. Empty string renders cleanly.

MORNING_BRIEFING: dict[Locale, str] = {
    "en": (
        f"{DOMAIN_JOB} Good morning! ZetaOps daily briefing — {{date}}\n"
        "\n"
        "Jobs: {active_jobs} active, {total_jobs} total\n"
        "{delayed_line}"
        "Team: {total_employees} employees\n"
        "\n"
        f"{PROMPT_ACTION_NEEDED} Reply with \"show today's schedule\" for the full plan."
    ),
    "hi-en": (
        f"{DOMAIN_JOB} Suprabhat! ZetaOps daily briefing — {{date}}\n"
        "\n"
        "Jobs: {active_jobs} active, {total_jobs} total\n"
        "{delayed_line}"
        "Team: {total_employees} employees\n"
        "\n"
        f"{PROMPT_ACTION_NEEDED} Details ke liye poochein: 'aaj ka schedule dikhao'."
    ),
    "hi": (
        f"{DOMAIN_JOB} Suprabhat! ZetaOps ki daily briefing — {{date}}\n"
        "\n"
        "Jobs: {active_jobs} chal rahe, {total_jobs} kul.\n"
        "{delayed_line}"
        "Team: {total_employees} log kaam par.\n"
        "\n"
        f"{PROMPT_ACTION_NEEDED} Details ke liye poochein: 'aaj ka schedule dikhao'."
    ),
}

# The conditional 'delayed' bullet — kept as its own locale dict so the
# Python composer can blank it cleanly when delayed_count is zero.
MORNING_BRIEFING_DELAYED_LINE: dict[Locale, str] = {
    "en":    f"{SEVERITY_WARNING} DELAYED: {{delayed_count}} job(s) need attention\n",
    "hi-en": f"{SEVERITY_WARNING} DELAYED: {{delayed_count}} jobs ko attention chahiye\n",
    "hi":    f"{SEVERITY_WARNING} DELAYED: {{delayed_count}} jobs ko attention chahiye\n",
}


# ---------------------------------------------------------------------------
# DELAY_ALERT — single English string
# ---------------------------------------------------------------------------
# Per Q3 user decision: Meta has approved en_US only (zetaops_job_ending_soon).
# The Hindi sibling does not exist upstream so we ship single-string English.
# Placeholder map:
#     {count}      int — number of delayed jobs
#     {plural_s}   "" or "s" — caller computes
#     {jobs_block} pre-formatted bulleted list from format_jobs_list()
#     {n_more}     "" if all listed, " plus {extra} more" otherwise

DELAY_ALERT: str = (
    f"{SEVERITY_WARNING} ALERT: {{count}} delayed job{{plural_s}}\n"
    "\n"
    "{jobs_block}\n"
    "\n"
    f"{PROMPT_ACTION_NEEDED} Reply with 'delayed jobs dikhao' for the full list."
)


# ---------------------------------------------------------------------------
# CONFLICT_ALERT — single English string
# ---------------------------------------------------------------------------
# Dispatcher-shape template, distinct from the Meta-bound
# CONFLICT_ALERT_EN / JOB_CONFLICT_ALERT_HI constants in
# message_formatters.py. Placeholder map: same shape as DELAY_ALERT.

CONFLICT_ALERT: str = (
    f"{SEVERITY_ALERT} ALERT: {{count}} scheduling conflict{{plural_s}} detected\n"
    "\n"
    "{jobs_block}\n"
    "\n"
    f"{PROMPT_ACTION_NEEDED} Reply with 'schedule conflicts dikhao' for the full list."
)


# ---------------------------------------------------------------------------
# MACHINE_DOWN_ALERT — locale dict
# ---------------------------------------------------------------------------
# On-demand alert when a machine moves to maintenance/breakdown. Used by
# whatsapp_alerts.send_machine_down_alert. Placeholder map:
#     {machine_name} str — display name e.g. "Heidelberg 1"
#     {machine_id}   int — DB id, used in the suggested follow-up question

MACHINE_DOWN_ALERT: dict[Locale, str] = {
    "en": (
        f"{SEVERITY_ALERT} ALERT: Machine down\n"
        "\n"
        "{machine_name} is now in maintenance mode.\n"
        "Jobs scheduled on this machine may be affected.\n"
        "\n"
        f"{PROMPT_ACTION_NEEDED} To check the impact, ask: "
        "'machine {machine_id} ki wajah se kaunse jobs affect hue'."
    ),
    "hi-en": (
        f"{SEVERITY_ALERT} ALERT: Machine down\n"
        "\n"
        "'{machine_name}' abhi maintenance mode mein hai.\n"
        "Is machine par scheduled jobs affect ho sakte hain.\n"
        "\n"
        f"{PROMPT_ACTION_NEEDED} Schedule check karne ke liye poochein: "
        "'machine {machine_id} ki wajah se kaunse jobs affect hue'."
    ),
    "hi": (
        f"{SEVERITY_ALERT} ALERT: Machine band ho gayi\n"
        "\n"
        "'{machine_name}' abhi maintenance mein hai.\n"
        "Is machine par scheduled jobs par asar pad sakta hai.\n"
        "\n"
        f"{PROMPT_ACTION_NEEDED} Schedule check karne ke liye poochein: "
        "'machine {machine_id} ki wajah se kaunse jobs affect hue'."
    ),
}


# ---------------------------------------------------------------------------
# AI_REPLY_HEADER — single English string
# ---------------------------------------------------------------------------
# Prefixed onto every raw AI reply on the WhatsApp surface (whatsapp.py
# line 1089-ish). Single English string per Q3 — this is a session-message
# header, not bound to a Meta HSM template. Placeholder map:
#     {first_name}  str — empty string is acceptable; the composer in
#                   whatsapp.py squashes the resulting double-space.
# The trailing '\n' is intentional — the caller prepends '\n' again to
# create the blank-line visual hierarchy between header and body.

AI_REPLY_HEADER: str = "Namaste {first_name}! " + PROMPT_GREETING + "\n"


# ---------------------------------------------------------------------------
# Locale picker helper
# ---------------------------------------------------------------------------

def pick(template: dict[Locale, str], locale: Locale | None) -> str:
    """Resolve a locale-dict template to a single string.

    Called by:    whatsapp_alerts.py callers that hand a tenant locale.
    Calls into:   nothing — pure dict lookup with default fallback.
    Side effects: none.

    Args:
        template: One of MORNING_BRIEFING / MACHINE_DOWN_ALERT / etc.
        locale:   'en' / 'hi-en' / 'hi'. None resolves to DEFAULT_LOCALE.

    Returns:
        The locale-specific format string. Falls back through DEFAULT_LOCALE
        then the first available key when an unknown locale is requested.
    """
    chosen = locale or DEFAULT_LOCALE
    if chosen in template:
        return template[chosen]
    if DEFAULT_LOCALE in template:
        return template[DEFAULT_LOCALE]
    return next(iter(template.values()))


def render_ai_reply(body: str, first_name: str = "") -> str:
    """Wrap a raw AI reply body with AI_REPLY_HEADER.

    Called by:    app/routers/whatsapp.py around line 1089 — the WhatsApp
                  AI reply path.
    Calls into:   AI_REPLY_HEADER.format, str.replace for the empty-name
                  double-space squash.
    Side effects: none.

    Args:
        body:       The post-`format_for_whatsapp` AI response text.
        first_name: The recipient's first name. May be empty string when
                    the identity layer didn't resolve a display name; in
                    that case the template renders as "Namaste! ..." with
                    no name-shaped gap.

    Returns:
        '<AI_REPLY_HEADER>\\n<body>' — the extra '\\n' inserts the blank
        line that gives the visual hierarchy required by SRS §23.2.
    """
    header = AI_REPLY_HEADER.format(first_name=first_name)
    # Empty first_name leaves an awkward ' !' — collapse to plain '!'.
    header = header.replace("Namaste !", "Namaste!").replace("  ", " ")
    if not body:
        return header.rstrip()
    return header + "\n" + body
