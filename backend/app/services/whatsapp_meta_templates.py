# app/services/whatsapp_meta_templates.py
# Branch: v5-whatsapp
# Iteration: v6.3.18 (WhatsApp message styling pass)
#
# FILE PURPOSE
# Registration metadata bridge between Meta's WhatsApp Business HSM
# template inventory (exported from the Interakt UI as JSON) and the
# code-side template constants in `message_formatters.py`. Loaded once
# at import time. Owns NO send logic — never POSTs to Meta. The single
# v6.3.18 contract is:
#
#     META_TEMPLATES[(name, language)]['python_constant']
#         is either a string naming a constant in message_formatters,
#         or None for templates that exist as Meta drafts but have no
#         code-side wiring this release.
#
# WHO CALLS THIS FILE
# - tests/test_message_templates.py — uses META_TEMPLATES to assert
#   that every wired (python_constant != None) entry has a matching
#   placeholder count between the Python format string and the Meta
#   {{n}} positions across HEADER + BODY (AC 23-AC7).
# - The v6.3.18 verification gate one-liner in CHANGELOG / SRS §22:
#       for (name, lang), entry in META_TEMPLATES.items():
#           if not entry.get('python_constant'): continue
#           ...
# - Future v6.3.x releases will wire additional constants by extending
#   PYTHON_CONSTANT_BINDINGS below; consumers should not import the
#   bindings dict directly — go through META_TEMPLATES so any future
#   binding-source switch (DB-backed, env-overridden) stays
#   transparent.
#
# WHAT THIS FILE CALLS
# - json (stdlib) — reads whatsapp_meta_templates.json once at import.
# - pathlib.Path — locates the JSON sibling file.
# - typing.TypedDict — typed shape for MetaTemplate dict entries.
#
# KEY DESIGN DECISIONS
# - The JSON file is preserved verbatim from the Interakt export format
#   so a future "submit drafts to Meta" run can POST it without re-
#   serialising. The lone deliberate divergence is the new Hindi
#   `zetaops_job_conflict_alert` entry that carries
#   `status: "draft_pending_meta_submission"` — additive field, ignored
#   by the Interakt API.
# - PYTHON_CONSTANT_BINDINGS lives here, not in the JSON. Putting it in
#   the JSON would smear v6.3.18-specific code wiring across what is
#   meant to be the Meta-portable registration source. Keeping it in
#   .py keeps the JSON portable and lets reviewers grep this dict for
#   "what does v6.3.18 actually wire up?".
# - We do NOT execute Meta submissions. The procedure is documented
#   below; running it is a release-engineering action gated on Meta
#   Business portfolio approval, not a code path that should ever
#   fire from a unit test or migration.
#
# META SUBMISSION PROCEDURE (DO NOT EXECUTE FROM CODE)
# When Meta Business portfolio approval lands and we are ready to
# register the inventory:
#   1. Open the Interakt UI (or the Meta Cloud API console).
#   2. For each entry in whatsapp_meta_templates.json with
#      `status != "draft_pending_meta_submission"`: confirm it already
#      exists upstream (these are pre-registered).
#   3. For each entry WITH that status: create a new template using
#      the JSON `name`, `language`, `category`, `components`,
#      `parameter_format` fields verbatim. Submit for Meta review.
#   4. After Meta approves, delete the `status` key from the entry in
#      whatsapp_meta_templates.json and commit the diff. The CHANGELOG
#      should reference v6.3.18 §11 acceptance criteria.
#   5. Re-run the v6.3.18 verification gates so the alignment audit
#      stays green.
# This procedure is intentionally manual — the v6.3.18 release is mock-
# mode only and ships no Meta-facing send code.

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TypedDict


# ---------------------------------------------------------------------------
# Typed shape
# ---------------------------------------------------------------------------

class MetaTemplate(TypedDict):
    """Typed shape of one entry in META_TEMPLATES.

    Used by:    the v6.3.18 alignment-test (11-AC7) and any future
                consumer that walks the registry. Backed by a plain
                dict so the verification one-liner in CHANGELOG can
                use `.get('python_constant')` and `entry['components']`
                without unwrapping a dataclass.
    Fields:
        name:             Meta template name (e.g. zetaops_morning_briefing).
        language:         Meta language code (e.g. en_US, hi).
        category:         Meta template category (UTILITY / MARKETING / AUTH).
        components:       List of HEADER/BODY/FOOTER/BUTTONS dicts as
                          submitted to Meta. Each component has 'type'
                          and (typically) 'text'; text may contain
                          {{n}} positional placeholders.
        parameter_format: 'POSITIONAL' or 'NAMED' per Meta API.
        status:           None for live templates, the string
                          'draft_pending_meta_submission' for entries
                          drafted in v6.3.18 but not yet submitted.
        python_constant:  Name of the matching constant in
                          app.services.message_formatters, or None if
                          v6.3.18 did not wire this entry up. The
                          alignment test enforces placeholder parity
                          for the not-None subset.
    """
    name: str
    language: str
    category: str
    components: list[dict]
    parameter_format: str
    status: Optional[str]
    python_constant: Optional[str]


# ---------------------------------------------------------------------------
# Code-side bindings (v6.3.18 initial coverage)
# ---------------------------------------------------------------------------
# Keys are (name, language) tuples; values are the Python constant name
# in app.services.message_formatters. Add a row here when a new template
# constant lands; the alignment audit will enforce placeholder parity on
# the next test run.
PYTHON_CONSTANT_BINDINGS: dict[tuple[str, str], str] = {
    # --- v6.3.18 initial wiring (named-kwarg constants in Section 3) ---
    ("zetaops_morning_briefing",            "en_US"): "MORNING_BRIEFING_EN",
    ("zetaops_morning_briefing",            "hi"):    "MORNING_BRIEFING_HI",
    ("zetaops_job_conflict_alert",          "en_US"): "CONFLICT_ALERT_EN",
    ("zetaops_job_ending_soon",             "en_US"): "DELAY_ALERT_EN",
    # --- v6.3.21 full inventory wiring (positional constants in Section 4) ---
    # Onboarding & consent
    ("zetaops_welcome_consent",             "en_US"): "WELCOME_CONSENT_EN",
    ("zetaops_welcome_consent",             "hi"):    "WELCOME_CONSENT_HI",
    ("zetaops_workspace_ready",             "en_US"): "WORKSPACE_READY_EN",
    # Briefings
    ("zetaops_evening_briefing",            "en_US"): "EVENING_BRIEFING_EN",
    # Manager check-in
    ("zetaops_manager_checkin",             "en_US"): "MANAGER_CHECKIN_EN",
    ("zetaops_manager_checkin",             "hi"):    "MANAGER_CHECKIN_HI",
    # Operational alerts
    ("zetaops_machine_breakdown_alert",     "en_US"): "MACHINE_BREAKDOWN_ALERT_EN",
    ("zetaops_job_conflict_alert",          "hi"):    "JOB_CONFLICT_ALERT_HI",
    ("zetaops_attendance_flag",             "en_US"): "ATTENDANCE_FLAG_EN",
    # Order intake
    ("zetaops_order_confirmation_request",  "en_US"): "ORDER_CONFIRMATION_REQUEST_EN",
    # Compliance
    ("zetaops_compliance_reminder_t30",     "en_US"): "COMPLIANCE_REMINDER_T30_EN",
    ("zetaops_compliance_reminder_t7",      "en_US"): "COMPLIANCE_REMINDER_T7_EN",
    ("zetaops_compliance_reminder_t1",      "en_US"): "COMPLIANCE_REMINDER_T1_EN",
    # Team invite
    ("zetaops_invite_team_member",          "en_US"): "INVITE_TEAM_MEMBER_EN",
    ("zetaops_invite_team_member",          "hi"):    "INVITE_TEAM_MEMBER_HI",
    ("zetaops_manager_activated",           "en_US"): "MANAGER_ACTIVATED_EN",
    ("zetaops_manager_activated",           "hi"):    "MANAGER_ACTIVATED_HI",
    ("zetaops_manager_joined_owner_notice", "en_US"): "MANAGER_JOINED_OWNER_NOTICE_EN",
    ("zetaops_manager_joined_owner_notice", "hi"):    "MANAGER_JOINED_OWNER_NOTICE_HI",
    ("zetaops_invite_pending_owner_nudge",  "en_US"): "INVITE_PENDING_OWNER_NUDGE_EN",
    ("zetaops_invite_pending_owner_nudge",  "hi"):    "INVITE_PENDING_OWNER_NUDGE_HI",
    # Manager engagement ladder
    ("zetaops_manager_input_acknowledged",  "en_US"): "MANAGER_INPUT_ACKNOWLEDGED_EN",
    ("zetaops_manager_input_acknowledged",  "hi"):    "MANAGER_INPUT_ACKNOWLEDGED_HI",
    ("zetaops_manager_reply_nudge",         "en_US"): "MANAGER_REPLY_NUDGE_EN",
    ("zetaops_manager_reply_nudge",         "hi"):    "MANAGER_REPLY_NUDGE_HI",
    ("zetaops_manager_day3_rhythm",         "en_US"): "MANAGER_DAY3_RHYTHM_EN",
    ("zetaops_manager_day3_rhythm",         "hi"):    "MANAGER_DAY3_RHYTHM_HI",
    ("zetaops_manager_day7_mirror",         "en_US"): "MANAGER_DAY7_MIRROR_EN",
    ("zetaops_manager_day7_mirror",         "hi"):    "MANAGER_DAY7_MIRROR_HI",
    # Performance & finance
    ("zetaops_performance_summary_monthly", "en_US"): "PERFORMANCE_SUMMARY_MONTHLY_EN",
    ("zetaops_performance_summary_monthly", "hi"):    "PERFORMANCE_SUMMARY_MONTHLY_HI",
    ("zetaops_gst_einvoice_ready",          "en_US"): "GST_EINVOICE_READY_EN",
    # --- Day-7 + engagement ladder (pending Meta approval) ---
    ("zetaops_owner_day7_insight",          "en_US"): "OWNER_DAY7_INSIGHT_EN",
    ("zetaops_owner_day7_insight",          "hi"):    "OWNER_DAY7_INSIGHT_HI",
    ("zetaops_engagement_give_up_nudge",    "en_US"): "ENGAGEMENT_GIVE_UP_NUDGE_EN",
    ("zetaops_engagement_give_up_nudge",    "hi"):    "ENGAGEMENT_GIVE_UP_NUDGE_HI",
}


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_JSON_PATH = Path(__file__).with_name("whatsapp_meta_templates.json")


def _load_meta_templates() -> dict[tuple[str, str], MetaTemplate]:
    """Read the sibling JSON file and merge with PYTHON_CONSTANT_BINDINGS.

    Called by:    module body (one call at import time, result cached
                  in META_TEMPLATES).
    Calls into:   json.load on _JSON_PATH; PYTHON_CONSTANT_BINDINGS
                  lookup per (name, language).
    Side effects: one read from disk at import. Subsequent imports of
                  this module hit the Python module cache; the file is
                  NOT re-read per call.

    Returns:
        dict keyed by (name, language) — strict, never duplicated. A
        duplicate key in the JSON is a programming error and raises
        ValueError so the import fails loudly rather than silently
        keeping only the last entry.

    Raises:
        FileNotFoundError if the JSON sibling went missing.
        ValueError on a duplicate (name, language) key in the JSON.
    """
    with _JSON_PATH.open(encoding="utf-8") as f:
        raw_entries = json.load(f)

    out: dict[tuple[str, str], MetaTemplate] = {}
    for entry in raw_entries:
        name = entry["name"]
        lang = entry["language"]
        key = (name, lang)
        if key in out:
            raise ValueError(
                f"Duplicate Meta template registration: {key!r}. "
                f"Each (name, language) must appear at most once in "
                f"whatsapp_meta_templates.json."
            )
        meta: MetaTemplate = {
            "name":             name,
            "language":         lang,
            "category":         entry.get("category", ""),
            "components":       list(entry.get("components", [])),
            "parameter_format": entry.get("parameter_format", "POSITIONAL"),
            "status":           entry.get("status"),
            "python_constant":  PYTHON_CONSTANT_BINDINGS.get(key),
        }
        out[key] = meta
    return out


META_TEMPLATES: dict[tuple[str, str], MetaTemplate] = _load_meta_templates()


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def bound_templates() -> dict[tuple[str, str], MetaTemplate]:
    """Subset of META_TEMPLATES with a non-None python_constant.

    Called by:    tests/test_message_templates.py to drive the AC 23-AC7
                  parametrisation; also useful for ops scripts that want
                  to print "what code wires up to what Meta template".
    Calls into:   nothing — pure dict comprehension.
    Side effects: none.
    """
    return {k: v for k, v in META_TEMPLATES.items() if v["python_constant"]}


def count_meta_placeholders(entry: MetaTemplate) -> int:
    """Count {{n}} positional placeholders across HEADER + BODY of an entry.

    Called by:    tests/test_message_templates.py and the v6.3.18
                  verification gate one-liner.
    Calls into:   re.findall on each component's 'text' field.
    Side effects: none.

    Notes:
        FOOTER components in Meta templates do not accept placeholders
        per the Cloud API spec, but if a future entry inadvertently
        includes one we still count it — the test surfaces the mismatch
        rather than silently ignoring it.
    """
    import re
    return sum(
        len(re.findall(r"\{\{\d+\}\}", (component.get("text") or "")))
        for component in entry["components"]
    )
