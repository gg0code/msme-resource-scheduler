# tests/services/test_message_dispatcher_templates.py
# Branch: v5-whatsapp
# Iteration: v6.3.18 (WhatsApp message styling pass — dispatcher cleanup)
#
# FILE PURPOSE
# Snapshot + structural tests for the dispatcher-shape template constants
# in app/services/message_templates.py — the v5.10 path templates that
# replace inline f-strings inside whatsapp_alerts.py and the AI reply
# wrapper used at routers/whatsapp.py line 1089.
#
# These are *separate* from the Meta-bound _EN/_HI templates in
# message_formatters.py (already covered by tests/test_message_templates.py).
# The dispatcher templates mirror what the v5.10 cron alerts actually
# send today; the Meta-bound templates anticipate the v6.4 data shape.
#
# WHO CALLS THIS FILE
# - pytest tests/ -m "not integration" (the v6.3.18 verification gate).
#
# WHAT THIS FILE CALLS
# - app/services/message_templates.py — module under test.
# - app/services/message_emoji.py     — to assert emoji presence.
#
# AC IDs covered (per CLAUDE.md AC ID convention; SRS §23):
#   23-AC3  every full-message template ends with an action prompt.
#   23-AC4  snapshot tests exist for each dispatcher template.
#   23-AC5  rendered output stays under the 800/1000 length caps.
#   23-AC6  every emoji rendered comes from message_emoji.

from __future__ import annotations

import re

import pytest

from app.services import message_emoji
from app.services.message_templates import (
    AI_REPLY_HEADER,
    CONFLICT_ALERT,
    DEFAULT_LOCALE,
    DELAY_ALERT,
    MACHINE_DOWN_ALERT,
    MORNING_BRIEFING,
    MORNING_BRIEFING_DELAYED_LINE,
    pick,
    render_ai_reply,
)


_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF]",
    flags=re.UNICODE,
)


# ===========================================================================
# Sample fixtures — deterministic input the snapshots are pinned against
# ===========================================================================

MORNING_SAMPLE = {
    "date":            "08 May 2026",
    "active_jobs":     3,
    "total_jobs":      5,
    "total_employees": 4,
}

DELAY_JOBS_BLOCK = (
    "- Bhatia cards (due: 2026-05-05)\n"
    "- Modi flyers (due: 2026-05-06)"
)

CONFLICT_JOBS_BLOCK = (
    "- Patel brochures\n"
    "- Reliance flyers"
)


# ===========================================================================
# 23-AC4 — snapshot for MORNING_BRIEFING (default locale = hi-en)
# ===========================================================================

_SNAP_MORNING_HIEN_NO_DELAY = (
    "\U0001F4CB Suprabhat! ZetaOps daily briefing — 08 May 2026\n"
    "\n"
    "Jobs: 3 active, 5 total\n"
    "Team: 4 employees\n"
    "\n"
    "\U0001F449 Details ke liye poochein: 'aaj ka schedule dikhao'."
)

_SNAP_MORNING_HIEN_WITH_DELAY = (
    "\U0001F4CB Suprabhat! ZetaOps daily briefing — 08 May 2026\n"
    "\n"
    "Jobs: 3 active, 5 total\n"
    "⚠️ DELAYED: 2 jobs ko attention chahiye\n"
    "Team: 4 employees\n"
    "\n"
    "\U0001F449 Details ke liye poochein: 'aaj ka schedule dikhao'."
)


def test_23_ac4_morning_briefing_no_delay_snapshot() -> None:
    rendered = pick(MORNING_BRIEFING, DEFAULT_LOCALE).format(
        delayed_line="",
        **MORNING_SAMPLE,
    )
    assert rendered == _SNAP_MORNING_HIEN_NO_DELAY


def test_23_ac4_morning_briefing_with_delay_snapshot() -> None:
    delayed_line = pick(MORNING_BRIEFING_DELAYED_LINE, DEFAULT_LOCALE).format(
        delayed_count=2,
    )
    rendered = pick(MORNING_BRIEFING, DEFAULT_LOCALE).format(
        delayed_line=delayed_line,
        **MORNING_SAMPLE,
    )
    assert rendered == _SNAP_MORNING_HIEN_WITH_DELAY


# ===========================================================================
# 23-AC4 — snapshot for DELAY_ALERT
# ===========================================================================

_SNAP_DELAY_TWO_JOBS = (
    "⚠️ ALERT: 2 delayed jobs\n"
    "\n"
    "- Bhatia cards (due: 2026-05-05)\n"
    "- Modi flyers (due: 2026-05-06)\n"
    "\n"
    "\U0001F449 Reply with 'delayed jobs dikhao' for the full list."
)

_SNAP_DELAY_ONE_JOB = (
    "⚠️ ALERT: 1 delayed job\n"
    "\n"
    "- Bhatia cards (due: 2026-05-05)\n"
    "\n"
    "\U0001F449 Reply with 'delayed jobs dikhao' for the full list."
)


def test_23_ac4_delay_alert_two_jobs_snapshot() -> None:
    rendered = DELAY_ALERT.format(
        count=2,
        plural_s="s",
        jobs_block=DELAY_JOBS_BLOCK,
    )
    assert rendered == _SNAP_DELAY_TWO_JOBS


def test_23_ac4_delay_alert_singular_snapshot() -> None:
    rendered = DELAY_ALERT.format(
        count=1,
        plural_s="",
        jobs_block="- Bhatia cards (due: 2026-05-05)",
    )
    assert rendered == _SNAP_DELAY_ONE_JOB


# ===========================================================================
# 23-AC4 — snapshot for CONFLICT_ALERT
# ===========================================================================

_SNAP_CONFLICT_TWO = (
    "\U0001F6A8 ALERT: 2 scheduling conflicts detected\n"
    "\n"
    "- Patel brochures\n"
    "- Reliance flyers\n"
    "\n"
    "\U0001F449 Reply with 'schedule conflicts dikhao' for the full list."
)


def test_23_ac4_conflict_alert_snapshot() -> None:
    rendered = CONFLICT_ALERT.format(
        count=2,
        plural_s="s",
        jobs_block=CONFLICT_JOBS_BLOCK,
    )
    assert rendered == _SNAP_CONFLICT_TWO


# ===========================================================================
# 23-AC4 — snapshot for MACHINE_DOWN_ALERT (default locale)
# ===========================================================================

_SNAP_MACHINE_DOWN_HIEN = (
    "\U0001F6A8 ALERT: Machine down\n"
    "\n"
    "'Heidelberg 1' abhi maintenance mode mein hai.\n"
    "Is machine par scheduled jobs affect ho sakte hain.\n"
    "\n"
    "\U0001F449 Schedule check karne ke liye poochein: "
    "'machine 42 ki wajah se kaunse jobs affect hue'."
)


def test_23_ac4_machine_down_alert_snapshot() -> None:
    rendered = pick(MACHINE_DOWN_ALERT, DEFAULT_LOCALE).format(
        machine_name="Heidelberg 1",
        machine_id=42,
    )
    assert rendered == _SNAP_MACHINE_DOWN_HIEN


# ===========================================================================
# 23-AC4 — snapshot for AI_REPLY_HEADER wrapper
# ===========================================================================

def test_23_ac4_render_ai_reply_with_first_name() -> None:
    body = "3 jobs aaj scheduled hain."
    expected = (
        "Namaste Sharma! \U0001F44B\n"
        "\n"
        "3 jobs aaj scheduled hain."
    )
    assert render_ai_reply(body, first_name="Sharma") == expected


def test_23_ac4_render_ai_reply_no_first_name_squashes_space() -> None:
    body = "OK done."
    expected = (
        "Namaste! \U0001F44B\n"
        "\n"
        "OK done."
    )
    assert render_ai_reply(body, first_name="") == expected


def test_23_ac4_render_ai_reply_empty_body_returns_header_only() -> None:
    assert render_ai_reply("", first_name="Sharma") == "Namaste Sharma! \U0001F44B"


# ===========================================================================
# 23-AC3 — every full-message template ends with an action prompt line
# ===========================================================================

_FULL_MESSAGE_RENDERS = [
    ("MORNING_BRIEFING (no delay)",
     pick(MORNING_BRIEFING, DEFAULT_LOCALE).format(delayed_line="", **MORNING_SAMPLE),
     "\U0001F449 Details ke liye poochein: 'aaj ka schedule dikhao'."),
    ("DELAY_ALERT",
     DELAY_ALERT.format(count=2, plural_s="s", jobs_block=DELAY_JOBS_BLOCK),
     "\U0001F449 Reply with 'delayed jobs dikhao' for the full list."),
    ("CONFLICT_ALERT",
     CONFLICT_ALERT.format(count=2, plural_s="s", jobs_block=CONFLICT_JOBS_BLOCK),
     "\U0001F449 Reply with 'schedule conflicts dikhao' for the full list."),
    ("MACHINE_DOWN_ALERT",
     pick(MACHINE_DOWN_ALERT, DEFAULT_LOCALE).format(machine_name="X", machine_id=1),
     None),  # Machine-down ends with a question phrasing — assert presence of action emoji only.
]


@pytest.mark.parametrize("name,rendered,expected_last_line", _FULL_MESSAGE_RENDERS)
def test_23_ac3_template_ends_with_action_prompt(
    name: str, rendered: str, expected_last_line: str | None,
) -> None:
    last_line = rendered.rstrip().split("\n")[-1].strip()
    if expected_last_line is None:
        # Machine-down: the action prompt is a multi-line phrase; just
        # verify the action-prompt emoji is on the trailing block.
        assert message_emoji.PROMPT_ACTION_NEEDED in rendered.rstrip().split("\n\n")[-1]
    else:
        assert last_line == expected_last_line


# ===========================================================================
# 23-AC5 — length caps (800 soft, 1000 hard)
# ===========================================================================

_LENGTH_TARGETS = [
    ("MORNING_BRIEFING (with delay)",
     pick(MORNING_BRIEFING, DEFAULT_LOCALE).format(
         delayed_line=pick(MORNING_BRIEFING_DELAYED_LINE, DEFAULT_LOCALE).format(delayed_count=2),
         **MORNING_SAMPLE,
     )),
    ("DELAY_ALERT",
     DELAY_ALERT.format(count=2, plural_s="s", jobs_block=DELAY_JOBS_BLOCK)),
    ("CONFLICT_ALERT",
     CONFLICT_ALERT.format(count=2, plural_s="s", jobs_block=CONFLICT_JOBS_BLOCK)),
    ("MACHINE_DOWN_ALERT",
     pick(MACHINE_DOWN_ALERT, DEFAULT_LOCALE).format(machine_name="Heidelberg 1", machine_id=42)),
    ("AI_REPLY (with name)",
     render_ai_reply("3 jobs aaj scheduled hain. Sab on track.", first_name="Sharma")),
]


@pytest.mark.parametrize("name,rendered", _LENGTH_TARGETS)
def test_23_ac5_rendered_length_under_hard_cap(name: str, rendered: str) -> None:
    assert len(rendered) <= 1000, f"{name} rendered to {len(rendered)} chars (hard cap 1000)"


@pytest.mark.parametrize("name,rendered", _LENGTH_TARGETS)
def test_23_ac5_rendered_length_under_soft_target(name: str, rendered: str) -> None:
    assert len(rendered) <= 800, f"{name} rendered to {len(rendered)} chars (soft target 800)"


# ===========================================================================
# 23-AC6 — every emoji rendered comes from message_emoji.ALL_EMOJI
# ===========================================================================

_TEMPLATES_TO_AUDIT = [
    ("MORNING_BRIEFING.en",     MORNING_BRIEFING["en"]),
    ("MORNING_BRIEFING.hi-en",  MORNING_BRIEFING["hi-en"]),
    ("MORNING_BRIEFING.hi",     MORNING_BRIEFING["hi"]),
    ("MORNING_DELAY_LINE.en",   MORNING_BRIEFING_DELAYED_LINE["en"]),
    ("MORNING_DELAY_LINE.hi-en", MORNING_BRIEFING_DELAYED_LINE["hi-en"]),
    ("DELAY_ALERT",             DELAY_ALERT),
    ("CONFLICT_ALERT",          CONFLICT_ALERT),
    ("MACHINE_DOWN_ALERT.en",   MACHINE_DOWN_ALERT["en"]),
    ("MACHINE_DOWN_ALERT.hi-en", MACHINE_DOWN_ALERT["hi-en"]),
    ("MACHINE_DOWN_ALERT.hi",   MACHINE_DOWN_ALERT["hi"]),
    ("AI_REPLY_HEADER",         AI_REPLY_HEADER),
]


def test_23_ac6_emoji_in_dispatcher_templates_defined_in_message_emoji() -> None:
    """Every emoji rendered by any dispatcher template must be a member
    of message_emoji.ALL_EMOJI. Uses substring match (not codepoint
    iteration) so VS-16 / ZWJ sequences like '⚠️' match in
    one piece."""
    allowed = list(message_emoji.ALL_EMOJI)
    offenders: list[tuple[str, str]] = []
    for name, template in _TEMPLATES_TO_AUDIT:
        # Check character by character but greedily consume known emoji
        # constants from the allowed list first.
        residue = template
        for emoji in allowed:
            residue = residue.replace(emoji, "")
        # Anything left that matches the emoji range is an offender.
        for ch in residue:
            if _EMOJI_RE.fullmatch(ch):
                offenders.append((name, ch))
    assert not offenders, (
        "Emoji used in dispatcher template that is NOT in message_emoji.ALL_EMOJI:\n"
        + "\n".join(f"  {n}: {repr(c)}" for n, c in offenders)
    )
