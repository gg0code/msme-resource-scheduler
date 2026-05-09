# app/services/message_formatters.py
# Branch: v5-whatsapp
# Iteration: v6.3.18 (WhatsApp message styling pass)
#
# FILE PURPOSE
# Centralised, pure-function rendering layer for every user-facing
# WhatsApp string emitted by ZetaOps Copilot. Owns three things:
#
#   1. The legacy markdown -> WhatsApp post-processor that used to live
#      in `whatsapp_formatter.py` (folded here in v6.3.18 per the
#      release decision; the old module is now a re-export shim so
#      existing imports keep working).
#   2. The four v6.3.18 entity formatters: format_jobs_list,
#      format_employee_status, format_relative_date,
#      format_machine_status. Each is a pure function — no DB session,
#      no network I/O, no datetime.utcnow() — so they remain safe to
#      call from any layer (cron, webhook, test).
#   3. The named template constants (MORNING_BRIEFING_EN/HI,
#      DELAY_ALERT_EN, CONFLICT_ALERT_EN, AI_REPLY_HEADER) whose
#      docstrings declare their binding to a Meta HSM template name
#      + placeholder map. The bound subset is enforced by the
#      v6.3.18 alignment test (AC 23-AC7) in
#      tests/test_message_templates.py.
#
# WHO CALLS THIS FILE
# - app/services/whatsapp_alerts.py — _build_morning_briefing,
#   _build_delay_alert, _build_conflict_alert call into the formatters
#   and template constants here instead of building strings inline.
# - app/services/onboarding_message.py — uses format_for_whatsapp on
#   the rendered onboarding-complete string before dispatch.
# - app/services/whatsapp_formatter.py — re-exports the legacy
#   surface from this module so call sites that imported the old
#   names keep compiling without edits.
# - app/services/whatsapp_meta_templates.py — references the template
#   constant *names* via PYTHON_CONSTANT_BINDINGS so the alignment
#   audit can resolve them by getattr().
# - tests/test_message_formatters.py + tests/test_message_templates.py
#   — snapshot, unit, and Meta-binding alignment assertions.
#
# WHAT THIS FILE CALLS
# - app/services/message_emoji.py — emoji constants (PROMPT_GREETING
#   used in AI_REPLY_HEADER; rest of the vocabulary staged for future
#   releases).
# - stdlib: re, logging, datetime, zoneinfo, typing.Protocol.
#
# KEY DESIGN DECISIONS
# - All formatters are pure functions. `format_relative_date` takes
#   `now` as a required keyword arg so tests can inject a fixed time
#   and so day boundaries are deterministic across timezones (CRITICAL
#   for AC 23-AC2 — Asia/Kolkata day boundaries, not 24-hour deltas).
# - Truncation tail "+N more" is the v6.3.18 standard. The legacy
#   `format_for_whatsapp()` truncation suffix is kept verbatim because
#   it has been live since v5.0 and changing it would break user
#   muscle memory ("reply MORE" is a learned interaction).
# - Template constants are Python str.format strings using NAMED
#   placeholders (`{date}`, `{jobs_starting}`, ...). They are NOT the
#   Meta {{n}} positional format. The .py-side and Meta-side are two
#   independent surfaces that both render the same content; the
#   alignment test enforces parity in placeholder COUNT, not in the
#   placeholder names. The `whatsapp_meta_templates.py` module is the
#   bridge.
# - Hindi-English code-mixing is handled by the v5.12 `detect_language`
#   layer (kept here, folded from whatsapp_formatter.py). Formatters
#   do NOT translate; they assume the caller has selected the right
#   locale upstream and pass through Hindi-script kwargs verbatim.
# - JobLike / EmployeeLike / MachineLike are structural Protocols —
#   they document the attribute surface a formatter touches without
#   coupling to the SQLAlchemy ORM classes. Tests pass simple
#   dataclasses that match the protocol; production code passes the
#   ORM rows directly. Either works.
#
# DEFERRED IN v6.3.18 (intentionally NOT wired up at call sites)
# The four bound template constants below carry valid Meta-binding
# docstrings AND pass AC 23-AC7 placeholder-count parity, but they are
# NOT yet referenced by `whatsapp_alerts.py` or `briefings/morning_content.py`.
# Reason: the Meta templates (`zetaops_morning_briefing`,
# `zetaops_job_conflict_alert`, `zetaops_job_ending_soon`) anticipate
# fields that the current v5.10/v6.3.4 dispatcher code does not yet
# compute — `jobs_starting` vs `continuing`, `crew_expected` as a
# fraction, `flag`, `next_step`. Routing the existing dispatcher calls
# through these constants would change *what* is sent, which the v6.3.18
# spec explicitly forbids ("Do not change *what* is sent, only *how*
# it's formatted"). The actual wiring belongs to v6.4 when the morning
# briefing data shape catches up. v6.3.18 ships the *infrastructure*
# (constants, registry, alignment audit, formatters); v6.4 lights it up.

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from app.services.message_emoji import PROMPT_GREETING

logger = logging.getLogger(__name__)


# ===========================================================================
# Section 1 — Legacy markdown -> WhatsApp post-processing
# (folded from app/services/whatsapp_formatter.py in v6.3.18)
# ===========================================================================
# Surface preserved verbatim:
#   format_for_whatsapp(text)        — main entry point
#   detect_language(text)            — Hindi/Hinglish/English heuristic
#   MAX_MESSAGE_LENGTH               — truncation cap
#   TRUNCATION_SUFFIX                — appended on truncate
#   BULLET_REPLACEMENT               — bullet character
#
# Behaviour identical to v5.0+. The old module is now a re-export shim;
# any new caller should import from this module directly.

MAX_MESSAGE_LENGTH = 1500
TRUNCATION_SUFFIX = "\n\n... (poora jawaab ke liye reply karein: MORE)"
BULLET_REPLACEMENT = "• "


def format_for_whatsapp(text: str) -> str:
    """Convert a markdown-formatted AI response to WhatsApp-safe plain text.

    Called by:    app/routers/ai_chat.py, app/services/whatsapp_alerts.py,
                  any caller that hands the AI's raw markdown to a
                  WhatsApp send. Folded from whatsapp_formatter.py.
    Calls into:   _remove_code_blocks, _remove_headers,
                  _remove_bold_markers, _remove_italic_markers,
                  _convert_bullet_points, _convert_numbered_lists,
                  _convert_markdown_tables, _clean_extra_whitespace,
                  _truncate_if_too_long.
    Side effects: logs WARN on empty input, INFO on truncate.
    """
    if not text or not text.strip():
        logger.warning(
            "format_for_whatsapp received empty text. "
            "The AI returned an empty response. "
            "Check run_ai_chat() for errors upstream."
        )
        return "Maafi kijiye, kuch gadbad ho gayi. Dobara try karein."

    text = _remove_code_blocks(text)
    text = _remove_headers(text)
    text = _remove_bold_markers(text)
    text = _remove_italic_markers(text)
    text = _convert_bullet_points(text)
    text = _convert_numbered_lists(text)
    text = _convert_markdown_tables(text)
    text = _clean_extra_whitespace(text)
    text = _truncate_if_too_long(text)
    return text.strip()


def _remove_code_blocks(text: str) -> str:
    """Strip ``` fences and `inline` backticks; keep the wrapped content.

    Called by:    format_for_whatsapp.
    Calls into:   re.sub.
    Side effects: none.
    """
    text = re.sub(r"```[a-zA-Z]*\n?", "", text, flags=re.DOTALL)
    text = re.sub(r"```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def _remove_headers(text: str) -> str:
    """Strip leading #-marker on markdown headers, keep the line.

    Called by:    format_for_whatsapp.
    """
    return re.sub(r"^#{1,6}\s+(.+)$", r"\n\1", text, flags=re.MULTILINE)


def _remove_bold_markers(text: str) -> str:
    """Strip **double-asterisk** and __double-underscore__ bold marks.

    Called by:    format_for_whatsapp. Must run BEFORE
                  _remove_italic_markers; otherwise the single-asterisk
                  italic regex partial-matches `**` and leaves stray
                  asterisks behind.
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    return text


def _remove_italic_markers(text: str) -> str:
    """Strip *single-asterisk* / _underscore_ italic marks.

    Called by:    format_for_whatsapp. The underscore form uses lookarounds
                  so identifiers like `tenant_id` stay intact.
    """
    text = re.sub(r"\*([^*\n]+?)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"\1", text)
    return text


def _convert_bullet_points(text: str) -> str:
    """Replace markdown `- ` bullets with WhatsApp `• ` glyphs.

    Called by:    format_for_whatsapp.
    """
    text = re.sub(r"^- ", BULLET_REPLACEMENT, text, flags=re.MULTILINE)
    text = re.sub(r"^\s{2,}- ", BULLET_REPLACEMENT, text, flags=re.MULTILINE)
    return text


def _convert_numbered_lists(text: str) -> str:
    """Strip leading whitespace before numbered list entries.

    Called by:    format_for_whatsapp.
    """
    return re.sub(r"^\s+(\d+\.)", r"\1", text, flags=re.MULTILINE)


def _convert_markdown_tables(text: str) -> str:
    """Flatten markdown tables to one `cell | cell | cell` line per row.

    Called by:    format_for_whatsapp.
    """
    lines = text.split("\n")
    result_lines: list[str] = []
    for line in lines:
        if re.match(r"^\s*\|[-:\s|]+\|\s*$", line):
            continue
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [cell.strip() for cell in line.split("|")]
            cells = [c for c in cells if c]
            if cells:
                result_lines.append(" | ".join(cells))
            continue
        result_lines.append(line)
    return "\n".join(result_lines)


def _clean_extra_whitespace(text: str) -> str:
    """Collapse 3+ consecutive newlines into one blank line; rstrip lines.

    Called by:    format_for_whatsapp.
    """
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text)


def _truncate_if_too_long(text: str) -> str:
    """Cut at MAX_MESSAGE_LENGTH (preferring sentence boundaries) and append
    the v5.0 hinglish "reply MORE" hint.

    Called by:    format_for_whatsapp.
    """
    if len(text) <= MAX_MESSAGE_LENGTH:
        return text
    search_start = MAX_MESSAGE_LENGTH - 200
    search_window = text[search_start:MAX_MESSAGE_LENGTH]
    last_sentence_end = max(
        search_window.rfind(". "),
        search_window.rfind("! "),
        search_window.rfind("? "),
        search_window.rfind(".\n"),
    )
    if last_sentence_end != -1:
        cut_point = search_start + last_sentence_end + 1
    else:
        cut_point = MAX_MESSAGE_LENGTH
    truncated = text[:cut_point].rstrip()
    logger.info(
        "Response truncated from %d to %d characters. "
        "Owner can reply MORE to request full response.",
        len(text), len(truncated),
    )
    return truncated + TRUNCATION_SUFFIX


def detect_language(text: str) -> str:
    """Return 'hindi' / 'hinglish' / 'english' for a free-text message.

    Called by:    AI request path, briefing renderers, formatters that
                  need to pick a locale. Heuristic, not NLP — same
                  rules used since v5.12.
    Calls into:   re.search.
    Side effects: none.
    """
    if re.search(r"[ऀ-ॿ]", text):
        return "hindi"
    hinglish_words = [
        "aaj", "kal", "kya", "hai", "hain", "nahi", "nahin",
        "karo", "karo", "kab", "kaun", "kahan", "kitna", "kitne",
        "bahut", "thoda", "abhi", "jaldi", "theek", "accha",
        "bata", "dekho", "lao", "do", "ho", "gaya", "gayi",
        "schedule", "kaam", "kab", "banda", "log", "machine",
        "haan", "naya", "purana", "zyada", "kam",
    ]
    text_lower = text.lower()
    hinglish_count = sum(
        1 for word in hinglish_words
        if re.search(r"\b" + word + r"\b", text_lower)
    )
    if hinglish_count >= 2:
        return "hinglish"
    return "english"


# ===========================================================================
# Section 2 — Entity Protocols + v6.3.18 formatters
# ===========================================================================

_ASIA_KOLKATA_CACHE: Optional[ZoneInfo] = None


def _asia_kolkata() -> ZoneInfo:
    """Lazy, memoised ZoneInfo('Asia/Kolkata').

    Called by:    _to_ist_date.
    Calls into:   ZoneInfo (stdlib).
    Side effects: caches the resolved ZoneInfo on first call.

    Defers the lookup to first call so this module imports cleanly on
    environments where the IANA tzdb is not yet on the path (e.g. a
    fresh Windows venv without `tzdata` installed). Matches the lazy
    pattern in `app/services/briefings/dispatcher.py:_tenant_zoneinfo`
    and `app/services/day7_insight.py:_compute_day_count`.
    """
    global _ASIA_KOLKATA_CACHE
    if _ASIA_KOLKATA_CACHE is None:
        _ASIA_KOLKATA_CACHE = ZoneInfo("Asia/Kolkata")
    return _ASIA_KOLKATA_CACHE


# Truncation tail used by the v6.3.18 list formatters. Distinct from the
# legacy TRUNCATION_SUFFIX (which is end-of-message hint for AI replies);
# this one is mid-message for inline lists.
LIST_TRUNCATION_TAIL = "+{n} more"


@runtime_checkable
class JobLike(Protocol):
    """Structural protocol for objects that format_jobs_list can read.

    Used by:    format_jobs_list.
    Required attributes:
        name:     Human-readable job name (str). May be empty/None.
        end_date: date or None — used for the optional "(due: ...)" tail.
    """
    name: Optional[str]
    end_date: Optional[date]


@runtime_checkable
class EmployeeLike(Protocol):
    """Structural protocol for format_employee_status.

    Required attributes:
        full_name:      Display name (str).
        is_present:     bool — True if attended today.
        primary_skill:  Optional[str] — top skill name, may be None.
        is_contractor:  bool — True if contractor (renders "(contractor)").
    """
    full_name: str
    is_present: bool
    primary_skill: Optional[str]
    is_contractor: bool


@runtime_checkable
class MachineLike(Protocol):
    """Structural protocol for format_machine_status.

    Required attributes:
        name:        Display name (str).
        status:      str — e.g. 'Operational' / 'Maintenance' / 'Breakdown'.
        current_job: Optional[str] — name of job currently running, or None.
    """
    name: str
    status: str
    current_job: Optional[str]


def format_jobs_list(jobs: list[JobLike], *, max_items: int = 5) -> str:
    """Render a bulleted job list, truncating to max_items with "+N more".

    Called by:    morning briefing builders, delay/conflict alerts, any
                  list-rendering site that wants consistent shape.
    Calls into:   nothing — pure string assembly.
    Side effects: none.

    Args:
        jobs:      list of JobLike. Empty list returns the empty string.
        max_items: cap before the "+N more" tail kicks in. Default 5
                   matches the v5 conflict alert behaviour.

    Returns:
        Bulleted lines joined by "\\n", no leading or trailing newline.
        Each line: "- {name} (due: {end_date})" — the (due: ...) tail
        is omitted when end_date is None.
    """
    if not jobs:
        return ""
    visible = jobs[:max_items]
    lines: list[str] = []
    for j in visible:
        name = (getattr(j, "name", None) or "").strip() or "Untitled job"
        end = getattr(j, "end_date", None)
        if end is not None:
            lines.append(f"- {name} (due: {end})")
        else:
            lines.append(f"- {name}")
    overflow = len(jobs) - len(visible)
    if overflow > 0:
        lines.append(LIST_TRUNCATION_TAIL.format(n=overflow))
    return "\n".join(lines)


def format_employee_status(employee: EmployeeLike) -> str:
    """One-line summary of one employee's current status.

    Called by:    crew rosters, attendance lists in briefings.
    Calls into:   nothing — pure string assembly.
    Side effects: none.

    Args:
        employee: EmployeeLike.

    Returns:
        e.g. "Ravi Kumar — present, Cutting (contractor)" or
             "Sita Devi — absent, Operator"
        Single line, no trailing newline.
    """
    name = (getattr(employee, "full_name", "") or "Unnamed").strip()
    presence = "present" if getattr(employee, "is_present", False) else "absent"
    skill = (getattr(employee, "primary_skill", None) or "").strip()
    contractor_tag = " (contractor)" if getattr(employee, "is_contractor", False) else ""
    parts = [presence]
    if skill:
        parts.append(skill)
    return f"{name} — {', '.join(parts)}{contractor_tag}"


def format_relative_date(dt: datetime, *, now: datetime) -> str:
    """Express dt as a relative phrase using Asia/Kolkata day boundaries.

    Called by:    briefings, delay alerts, any user-facing date rendering.
    Calls into:   ZoneInfo.astimezone, .date() arithmetic.
    Side effects: none.

    Mapping:
        same calendar day (IST) -> "today"
        +1 calendar day         -> "tomorrow"
        -1 calendar day         -> "yesterday"
        +N (N >= 2)             -> "in N days"
        -N (N >= 2)             -> "N days ago"

    Args:
        dt:  the timestamp to render. Naive datetimes are interpreted
             as Asia/Kolkata local time (this is the project default
             timezone — IST — established in SRS §17.3).
        now: anchor timestamp. Naive treated as Asia/Kolkata. Required
             keyword so callers cannot accidentally pass datetime.utcnow.

    Returns:
        One of the strings above; never empty, never None.
    """
    dt_ist  = _to_ist_date(dt)
    now_ist = _to_ist_date(now)
    delta = (dt_ist - now_ist).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta == -1:
        return "yesterday"
    if delta > 1:
        return f"in {delta} days"
    return f"{-delta} days ago"


def _to_ist_date(value: datetime) -> date:
    """Convert a datetime (aware or naive) to an Asia/Kolkata calendar date.

    Called by:    format_relative_date.
    """
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(_asia_kolkata()).date()


def format_machine_status(machine: MachineLike) -> str:
    """One-line summary of one machine's current status.

    Called by:    morning briefing rosters, machine-down alerts.
    Calls into:   nothing.
    Side effects: none.

    Args:
        machine: MachineLike.

    Returns:
        e.g. "Heidelberg 1 — Operational, running Bhatia cards" or
             "Cutter 3 — Maintenance"
        Single line, no trailing newline.
    """
    name = (getattr(machine, "name", "") or "Unnamed machine").strip()
    status = (getattr(machine, "status", "") or "Unknown").strip()
    job = (getattr(machine, "current_job", None) or "").strip()
    if job:
        return f"{name} — {status}, running {job}"
    return f"{name} — {status}"


# ===========================================================================
# Section 3 — Template constants (bound to Meta HSM templates)
# ===========================================================================
# Each constant below is a Python str.format string with named kwargs.
# Its docstring declares (a) the Meta template name + language it maps
# to, (b) the Meta {{n}} -> kwarg map. The v6.3.18 alignment test
# enforces parity between the count of distinct kwargs in the Python
# string and the count of {{n}} placeholders across HEADER + BODY in
# the Meta entry. See AC 23-AC7 in SRS §11.

MORNING_BRIEFING_EN = (
    "Morning briefing — {date}\n"
    "\n"
    "Today's plan\n"
    "- Jobs starting: {jobs_starting}\n"
    "- Continuing from yesterday: {continuing}\n"
    "- Crew expected: {crew_expected}\n"
    "\n"
    "Flag: {flag}\n"
    "\n"
    "Suggested next step: {next_step}\n"
    "\n"
    "Reply OK to apply or HELP for options."
)
"""Maps to Meta template: zetaops_morning_briefing (en_US).

Placeholder map (Meta {{n}} -> kwarg):
    HEADER {{1}} = date
    BODY   {{1}} = jobs_starting
    BODY   {{2}} = continuing
    BODY   {{3}} = crew_expected
    BODY   {{4}} = flag
    BODY   {{5}} = next_step

Total placeholder count = 6 across HEADER + BODY. The Python format
string declares exactly 6 distinct named kwargs to satisfy AC 23-AC7.
"""


MORNING_BRIEFING_HI = (
    "सुबह की briefing — {date}\n"
    "\n"
    "आज का प्लान\n"
    "- आज शुरू होने वाले काम: {jobs_starting}\n"
    "- कल से जारी: {continuing}\n"
    "- अपेक्षित crew: {crew_expected}\n"
    "\n"
    "ध्यान दें: {flag}\n"
    "\n"
    "सुझाव: {next_step}\n"
    "\n"
    "Apply करने के लिए OK या HELP भेजें।"
)
"""Maps to Meta template: zetaops_morning_briefing (hi).

Placeholder map (Meta {{n}} -> kwarg):
    HEADER {{1}} = date
    BODY   {{1}} = jobs_starting
    BODY   {{2}} = continuing
    BODY   {{3}} = crew_expected
    BODY   {{4}} = flag
    BODY   {{5}} = next_step

Total placeholder count = 6. Code-mixing style: Devanagari sentences
with English nouns for technical terms (briefing, crew, Apply, OK,
HELP) — same convention as the existing `zetaops_welcome_consent` (hi)
template. Strings are passed through verbatim by the formatter; the
caller is responsible for selecting the locale upstream via
`detect_language()`.
"""


DELAY_ALERT_EN = (
    "Hi, {job_name} for {customer} is on track to finish in {time_remaining}.\n"
    "\n"
    "Progress: {progress}\n"
    "Next job in queue: {next_job}\n"
    "\n"
    "Reply READY when packing is complete to mark this job done."
)
"""Maps to Meta template: zetaops_job_ending_soon (en_US).

Placeholder map (Meta {{n}} -> kwarg):
    BODY {{1}} = job_name
    BODY {{2}} = customer
    BODY {{3}} = time_remaining
    BODY {{4}} = progress
    BODY {{5}} = next_job

Total placeholder count = 5. Bound only in en_US; a Hindi translation
is on the v6.3.19 backlog.
"""


CONFLICT_ALERT_EN = (
    "Two jobs need the same resource at the same time.\n"
    "\n"
    "Job A: {job_a}\n"
    "Job B: {job_b}\n"
    "Resource: {resource}\n"
    "Window: {window}\n"
    "\n"
    "Suggested resolution: {next_step}\n"
    "\n"
    "Reply YES to apply or REVIEW to see other options."
)
"""Maps to Meta template: zetaops_job_conflict_alert (en_US).

Placeholder map (Meta {{n}} -> kwarg):
    BODY {{1}} = job_a
    BODY {{2}} = job_b
    BODY {{3}} = resource
    BODY {{4}} = window
    BODY {{5}} = next_step

Total placeholder count = 5. The Hindi sibling
`zetaops_job_conflict_alert (hi)` exists as a draft in
whatsapp_meta_templates.json with status
'draft_pending_meta_submission' (added in v6.3.18); the corresponding
Python constant CONFLICT_ALERT_HI is not yet wired up. Add it when
Meta approves the Hindi entry — the alignment test (AC 23-AC7) will
catch any drift.
"""


AI_REPLY_HEADER = (
    "Namaste {first_name}! " + PROMPT_GREETING + "\n"
)
"""Free-form session message header — NOT bound to a Meta HSM template.

Used by:    AI Copilot reply path (app/routers/ai_chat.py and the
            WhatsApp AI surface) to prefix every reply with a warm,
            named greeting. The PROMPT_GREETING glyph (👋) is the
            only emoji the v6.3.18 templates render today.

Placeholder map: a single named kwarg `first_name` — empty string is
acceptable and renders as "Namaste ! 👋\\n" which the dispatcher should
collapse via `_clean_extra_whitespace` before send.
"""
