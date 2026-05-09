# tests/test_message_templates.py
# Branch: v5-whatsapp
# Iteration: v6.3.18 (WhatsApp message styling pass)
#
# FILE PURPOSE
# Snapshot + structural tests for the v6.3.18 named template constants
# and the Meta HSM template registry binding. Hand-rolled snapshots
# (the spec forbids adding new dependencies like syrupy unless they
# already exist in requirements). Each test name carries its AC ID so
# `pytest -k 11-AC` filters the v6.3.18 acceptance pass.
#
# WHO CALLS THIS FILE
# - pytest tests/ -m "not integration" (the v6.3.18 verification gate).
#
# WHAT THIS FILE CALLS
# - app/services/message_formatters.py    — template constants under test.
# - app/services/whatsapp_meta_templates.py — META_TEMPLATES registry.
# - app/services/message_emoji.py         — emoji vocabulary source.
#
# AC IDs covered:
#   23-AC1  no inline emoji in dispatcher modules.
#   23-AC3  every named template ends with a single action prompt line.
#   23-AC4  snapshot test exists for each named template (en_US + hi).
#   23-AC5  rendered output ≤ 1000 chars (hard) / ≤ 800 (soft).
#   23-AC6  every emoji used in any template is defined in message_emoji.
#   23-AC7  Python template ↔ Meta placeholder count parity.
#   23-AC8  Hindi conflict-alert draft entry exists with correct status.

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services import message_emoji
from app.services import message_formatters as f
from app.services.whatsapp_meta_templates import (
    META_TEMPLATES,
    bound_templates,
    count_meta_placeholders,
)


# Modules covered by the AC 23-AC1 inline-emoji ban. Mirrors the
# v6.3.18 verification-gate target set verbatim.
_DISPATCHER_PATHS = (
    "app/services/whatsapp_alerts.py",
    "app/services/briefing_intelligence",
    "app/routers/whatsapp.py",
    "app/routers/whatsapp_router.py",  # may not exist; ignore if missing
)

# Unicode ranges covering the WhatsApp-relevant emoji blocks. Same
# expression used by the verification-gate one-liner.
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF]",
    flags=re.UNICODE,
)


# ---------------------------------------------------------------------------
# Sample kwargs the snapshot + length tests render with. These are the
# canonical demo values the spec uses (taken verbatim from the Meta
# template `example` fields where available).
# ---------------------------------------------------------------------------

MORNING_BRIEFING_SAMPLE = {
    "date":           "Tuesday, 30 April",
    "jobs_starting":  "3",
    "continuing":     "1 (Patel brochures)",
    "crew_expected":  "10 of 11",
    "flag":           "Rakesh on leave — Bhatia cards may slip 2 hrs",
    "next_step":      "Confirm Bhatia paper before 9 AM, or move Ramesh to cover",
}

MORNING_BRIEFING_HI_SAMPLE = {
    "date":           "मंगलवार, 30 अप्रैल",
    "jobs_starting": "3",
    "continuing":    "1 (पटेल brochures)",
    "crew_expected": "10 में से 11",
    "flag":          "राकेश छुट्टी पर — भाटिया cards 2 घंटे लेट हो सकता है",
    "next_step":     "9 बजे से पहले भाटिया का paper confirm करें, या रमेश को मोदी job से शिफ्ट करें",
}

CONFLICT_ALERT_SAMPLE = {
    "job_a":     "Bhatia wedding cards",
    "job_b":     "Reliance flyers",
    "resource":  "Machine 2 (offset)",
    "window":    "Tomorrow 10 AM — 1 PM",
    "next_step": "Move Reliance to Machine 3, no impact on delivery",
}

DELAY_ALERT_SAMPLE = {
    "job_name":       "Wedding Card Run",
    "customer":       "Royal Events",
    "time_remaining": "about 45 minutes",
    "progress":       "820 of 850 cards printed",
    "next_job":       "Modi pamphlets — paper already loaded",
}


# ===========================================================================
# 23-AC1 — no inline emoji in dispatcher modules
# ===========================================================================

def _project_root() -> Path:
    """Walk up from this test file to the repo root (parent of backend/)."""
    here = Path(__file__).resolve()
    # tests/test_message_templates.py -> tests -> backend -> repo root
    return here.parent.parent.parent


def test_23_ac1_no_inline_emoji_in_dispatcher_modules() -> None:
    """Grep-equivalent: dispatcher modules must not contain bare emoji."""
    repo = _project_root()
    backend = repo / "backend"
    offenders: list[tuple[str, int, str]] = []
    for rel in _DISPATCHER_PATHS:
        target = backend / rel
        if not target.exists():
            # whatsapp_router.py is a likely-missing alias; allow the
            # absence so the test is robust to future renames.
            continue
        files = [target] if target.is_file() else list(target.rglob("*.py"))
        for fp in files:
            for ln, line in enumerate(fp.read_text(encoding="utf-8").splitlines(), start=1):
                if _EMOJI_RE.search(line):
                    offenders.append((str(fp.relative_to(repo)), ln, line.strip()))
    assert not offenders, (
        "Inline emoji forbidden in dispatcher modules — first offenders:\n"
        + "\n".join(f"  {p}:{ln}: {snip}" for p, ln, snip in offenders[:10])
    )


# ===========================================================================
# 23-AC3 — every named template ends with a single action prompt line
# ===========================================================================

# Pairs of (template constant, list of acceptable action-prompt phrases).
# Each rendered template must end with one of these phrases. For
# AI_REPLY_HEADER (which is a header, not a full message) the rule
# does not apply — covered by a dedicated test.
_NAMED_TEMPLATES_WITH_ACTION_PROMPTS = [
    ("MORNING_BRIEFING_EN", f.MORNING_BRIEFING_EN, MORNING_BRIEFING_SAMPLE,
     ["Reply OK to apply or HELP for options."]),
    ("MORNING_BRIEFING_HI", f.MORNING_BRIEFING_HI, MORNING_BRIEFING_HI_SAMPLE,
     ["Apply करने के लिए OK या HELP भेजें।"]),
    ("DELAY_ALERT_EN", f.DELAY_ALERT_EN, DELAY_ALERT_SAMPLE,
     ["Reply READY when packing is complete to mark this job done."]),
    ("CONFLICT_ALERT_EN", f.CONFLICT_ALERT_EN, CONFLICT_ALERT_SAMPLE,
     ["Reply YES to apply or REVIEW to see other options."]),
]


@pytest.mark.parametrize("name,template,sample,allowed_endings", _NAMED_TEMPLATES_WITH_ACTION_PROMPTS)
def test_23_ac3_template_ends_with_action_prompt(
    name: str, template: str, sample: dict, allowed_endings: list[str]
) -> None:
    rendered = template.format(**sample)
    last_line = rendered.rstrip().split("\n")[-1].strip()
    assert last_line in allowed_endings, (
        f"{name} ends with {last_line!r}; expected one of {allowed_endings}"
    )


def test_23_ac3_ai_reply_header_is_a_header_not_a_full_message() -> None:
    """AI_REPLY_HEADER is a session-message *header* (not a full message),
    so the action-prompt rule does not apply. Document the carve-out here
    so a future reader knows this is intentional, not an oversight."""
    rendered = f.AI_REPLY_HEADER.format(first_name="Sharma ji")
    # It must contain the warm greeting glyph.
    assert message_emoji.PROMPT_GREETING in rendered
    # And it must end with a newline so callers can append body text.
    assert rendered.endswith("\n")


# ===========================================================================
# 23-AC4 — snapshot test exists for each named template
# ===========================================================================

# Hand-rolled snapshots. Updating them is a deliberate review action;
# the diff tells a reviewer what wire content changed. Multi-line
# strings use explicit \n so a stray trailing-whitespace edit is loud.

_SNAP_MORNING_EN = (
    "Morning briefing — Tuesday, 30 April\n"
    "\n"
    "Today's plan\n"
    "- Jobs starting: 3\n"
    "- Continuing from yesterday: 1 (Patel brochures)\n"
    "- Crew expected: 10 of 11\n"
    "\n"
    "Flag: Rakesh on leave — Bhatia cards may slip 2 hrs\n"
    "\n"
    "Suggested next step: Confirm Bhatia paper before 9 AM, or move Ramesh to cover\n"
    "\n"
    "Reply OK to apply or HELP for options."
)

_SNAP_MORNING_HI = (
    "सुबह की briefing — मंगलवार, 30 अप्रैल\n"
    "\n"
    "आज का प्लान\n"
    "- आज शुरू होने वाले काम: 3\n"
    "- कल से जारी: 1 (पटेल brochures)\n"
    "- अपेक्षित crew: 10 में से 11\n"
    "\n"
    "ध्यान दें: राकेश छुट्टी पर — भाटिया cards 2 घंटे लेट हो सकता है\n"
    "\n"
    "सुझाव: 9 बजे से पहले भाटिया का paper confirm करें, या रमेश को मोदी job से शिफ्ट करें\n"
    "\n"
    "Apply करने के लिए OK या HELP भेजें।"
)

_SNAP_DELAY_EN = (
    "Hi, Wedding Card Run for Royal Events is on track to finish in about 45 minutes.\n"
    "\n"
    "Progress: 820 of 850 cards printed\n"
    "Next job in queue: Modi pamphlets — paper already loaded\n"
    "\n"
    "Reply READY when packing is complete to mark this job done."
)

_SNAP_CONFLICT_EN = (
    "Two jobs need the same resource at the same time.\n"
    "\n"
    "Job A: Bhatia wedding cards\n"
    "Job B: Reliance flyers\n"
    "Resource: Machine 2 (offset)\n"
    "Window: Tomorrow 10 AM — 1 PM\n"
    "\n"
    "Suggested resolution: Move Reliance to Machine 3, no impact on delivery\n"
    "\n"
    "Reply YES to apply or REVIEW to see other options."
)

_SNAP_AI_REPLY_HEADER = "Namaste Sharma ji! " + message_emoji.PROMPT_GREETING + "\n"


def test_23_ac4_morning_briefing_en_snapshot() -> None:
    assert f.MORNING_BRIEFING_EN.format(**MORNING_BRIEFING_SAMPLE) == _SNAP_MORNING_EN


def test_23_ac4_morning_briefing_hi_snapshot() -> None:
    assert f.MORNING_BRIEFING_HI.format(**MORNING_BRIEFING_HI_SAMPLE) == _SNAP_MORNING_HI


def test_23_ac4_delay_alert_en_snapshot() -> None:
    assert f.DELAY_ALERT_EN.format(**DELAY_ALERT_SAMPLE) == _SNAP_DELAY_EN


def test_23_ac4_conflict_alert_en_snapshot() -> None:
    assert f.CONFLICT_ALERT_EN.format(**CONFLICT_ALERT_SAMPLE) == _SNAP_CONFLICT_EN


def test_23_ac4_ai_reply_header_snapshot() -> None:
    assert f.AI_REPLY_HEADER.format(first_name="Sharma ji") == _SNAP_AI_REPLY_HEADER


# ===========================================================================
# 23-AC5 — length caps under standard fixtures
# ===========================================================================

_LENGTH_TARGETS = [
    ("MORNING_BRIEFING_EN", f.MORNING_BRIEFING_EN, MORNING_BRIEFING_SAMPLE),
    ("MORNING_BRIEFING_HI", f.MORNING_BRIEFING_HI, MORNING_BRIEFING_HI_SAMPLE),
    ("DELAY_ALERT_EN",      f.DELAY_ALERT_EN,      DELAY_ALERT_SAMPLE),
    ("CONFLICT_ALERT_EN",   f.CONFLICT_ALERT_EN,   CONFLICT_ALERT_SAMPLE),
]


@pytest.mark.parametrize("name,template,sample", _LENGTH_TARGETS)
def test_23_ac5_rendered_length_under_hard_cap(name: str, template: str, sample: dict) -> None:
    rendered = template.format(**sample)
    assert len(rendered) <= 1000, f"{name} rendered to {len(rendered)} chars (hard cap 1000)"


@pytest.mark.parametrize("name,template,sample", _LENGTH_TARGETS)
def test_23_ac5_rendered_length_under_soft_target(name: str, template: str, sample: dict) -> None:
    rendered = template.format(**sample)
    assert len(rendered) <= 800, f"{name} rendered to {len(rendered)} chars (soft target 800)"


# ===========================================================================
# 23-AC6 — every emoji used in any template is defined in message_emoji
# ===========================================================================

_TEMPLATES_TO_AUDIT_FOR_EMOJI = [
    ("MORNING_BRIEFING_EN", f.MORNING_BRIEFING_EN),
    ("MORNING_BRIEFING_HI", f.MORNING_BRIEFING_HI),
    ("DELAY_ALERT_EN",      f.DELAY_ALERT_EN),
    ("CONFLICT_ALERT_EN",   f.CONFLICT_ALERT_EN),
    ("AI_REPLY_HEADER",     f.AI_REPLY_HEADER),
]


def test_23_ac6_emoji_used_in_templates_defined_in_message_emoji() -> None:
    """Walk every codepoint of every named template; if any one of them
    matches the emoji ranges, that emoji must be a member of
    message_emoji.ALL_EMOJI. Catches the case where someone pastes a
    new emoji directly into a template constant instead of adding it
    to the vocabulary module first."""
    allowed = set(message_emoji.ALL_EMOJI)
    offenders: list[tuple[str, str]] = []
    for name, template in _TEMPLATES_TO_AUDIT_FOR_EMOJI:
        for ch in template:
            if _EMOJI_RE.fullmatch(ch) and ch not in allowed:
                offenders.append((name, ch))
    assert not offenders, (
        "Emoji used in template that is NOT defined in message_emoji.py:\n"
        + "\n".join(f"  {n}: {repr(c)}" for n, c in offenders)
    )


# ===========================================================================
# 23-AC7 — Python ↔ Meta placeholder count parity
# ===========================================================================

@pytest.mark.parametrize(
    "name,language,python_constant",
    [(k[0], k[1], v["python_constant"]) for k, v in bound_templates().items()],
)
def test_23_ac7_code_template_matches_meta_placeholder_count(
    name: str, language: str, python_constant: str
) -> None:
    """For every (Meta template, language) entry that has a python_constant
    binding, the count of distinct named kwargs in the Python format
    string must equal the count of {{n}} placeholders across HEADER +
    BODY in the Meta template. Submission-time order alignment is the
    Meta-binding docstring's job; this test guards count parity."""
    assert hasattr(f, python_constant), (
        f"whatsapp_meta_templates.py binds {(name, language)} to "
        f"{python_constant}, but message_formatters.py does not export it."
    )
    const = getattr(f, python_constant)
    py_kwargs = set(re.findall(r"\{(\w+)\}", const))
    meta_count = count_meta_placeholders(META_TEMPLATES[(name, language)])
    assert len(py_kwargs) == meta_count, (
        f"{python_constant} declares {len(py_kwargs)} kwargs "
        f"({sorted(py_kwargs)}); Meta {(name, language)} has "
        f"{meta_count} placeholders. Counts must match."
    )


# ===========================================================================
# 23-AC8 — Hindi conflict-alert draft entry
# ===========================================================================

def test_23_ac8_hindi_conflict_alert_draft_status() -> None:
    """The new Hindi sibling for zetaops_job_conflict_alert must be
    present in whatsapp_meta_templates.json and explicitly marked as
    a draft pending Meta submission. The status field is the
    contract that ops uses to know which entries still need to be
    pushed through Meta review."""
    entry = META_TEMPLATES.get(("zetaops_job_conflict_alert", "hi"))
    assert entry is not None, (
        "zetaops_job_conflict_alert (hi) missing from whatsapp_meta_templates.json"
    )
    assert entry["status"] == "draft_pending_meta_submission", (
        f"Expected draft_pending_meta_submission, got {entry['status']!r}. "
        "Update only when Meta has approved the Hindi entry; see SRS §11 AC8."
    )
    # Placeholder count parity with en_US sibling — submission-time
    # ordering must still line up so the JSON can ship verbatim.
    en = META_TEMPLATES[("zetaops_job_conflict_alert", "en_US")]
    assert count_meta_placeholders(entry) == count_meta_placeholders(en), (
        "Hindi draft placeholder count diverges from en_US — fix before Meta submit."
    )


def test_23_ac8_json_file_status_field_persists() -> None:
    """Round-trip the JSON file independently of META_TEMPLATES so that
    a future code change to the loader cannot mask a JSON regression.
    Reads whatsapp_meta_templates.json directly."""
    path = (
        Path(__file__).resolve().parent.parent
        / "app" / "services" / "whatsapp_meta_templates.json"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    hi_drafts = [
        x for x in raw
        if x["name"] == "zetaops_job_conflict_alert" and x["language"] == "hi"
    ]
    assert len(hi_drafts) == 1
    assert hi_drafts[0].get("status") == "draft_pending_meta_submission"
