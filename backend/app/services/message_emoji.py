# app/services/message_emoji.py
# Branch: v5-whatsapp
# Iteration: v6.3.18 (WhatsApp message styling pass)
#
# FILE PURPOSE
# Single source of truth for every emoji that may appear inside a
# WhatsApp message rendered by ZetaOps Copilot. Module-level constants
# only — no functions, no string formatting, no I/O. Importers reference
# these constants by name from `message_formatters.py` and from any
# future template module. This indirection lets us:
#   1. Audit the entire emoji vocabulary in one place.
#   2. Swap an emoji (e.g. when a WhatsApp client renders one poorly)
#      with a single edit instead of grepping the codebase.
#   3. Enforce SRS §23 AC 23-AC6 "every emoji used in a template comes
#      from message_emoji.py" by making any string-literal emoji in a
#      dispatcher module a review-gate violation.
#
# WHO CALLS THIS FILE
# - app/services/message_formatters.py — template constants reference
#   the names defined here. The current v6.3.18 templates only use
#   `PROMPT_GREETING` (in AI_REPLY_HEADER); the rest of the vocabulary
#   is staged for upcoming releases (v6.3.19 per-tenant config and
#   v6.4.0 engagement-ladder messages will lean on the status/severity
#   groups).
# - tests/test_message_templates.py — snapshot assertions read these
#   constants when comparing rendered strings against committed
#   golden fixtures.
#
# WHAT THIS FILE CALLS
# - Nothing. This is a pure data module — zero imports beyond stdlib
#   `__future__.annotations` for forward-compat with older callers.
#
# KEY DESIGN DECISIONS
# - One constant per *meaning*, not per emoji codepoint. STATUS_DONE
#   is the meaning; the codepoint behind it is incidental and may
#   change. Importers must reference by meaning name.
# - Group constants by the four semantic roles called out in the
#   v6.3.18 spec: STATUS / SEVERITY / DOMAIN / PROMPT. Adding a new
#   constant outside one of these groups requires a one-line note in
#   SRS §23.
# - Hindi script is NOT an emoji; do not add Devanagari characters
#   here. Hindi-English code-mixing is the formatters' job.
# - Codepoints chosen for cross-platform readability on Indian MSME
#   handsets (mostly mid-range Android, some KaiOS-era featurephones
#   in pilot deployments). Variation selectors (U+FE0F) are kept on
#   pictographic characters that need them so renderers don't fall
#   back to monochrome glyphs on older devices.
#
# POLICY (enforced by AC 23-AC6 in SRS §23)
# Any new emoji used in a dispatcher module or a template constant
# must FIRST appear here as a named constant. Adding emoji literals
# to whatsapp_alerts.py, briefing_intelligence/, the WhatsApp router,
# or any future template-rendering site is a v6.3.18 review-gate
# violation. The rule exists so the audit grep in
# whatsapp_alerts.py + briefing_intelligence/ + whatsapp.py +
# whatsapp_router.py stays empty.

from __future__ import annotations


# ---------------------------------------------------------------------------
# STATUS — used to mark the state of a job, machine, or task line
# ---------------------------------------------------------------------------

STATUS_DONE:        str = "✅"          # ✅ green check mark
STATUS_IN_PROGRESS: str = "\U0001F7E2"      # 🟢 green circle
STATUS_BLOCKED:     str = "\U0001F534"      # 🔴 red circle
STATUS_IDLE:        str = "⚪"          # ⚪ medium white circle


# ---------------------------------------------------------------------------
# SEVERITY — escalation level for advisory / warning / alert content
# ---------------------------------------------------------------------------

SEVERITY_INFO:    str = "ℹ️"       # ℹ️ info
SEVERITY_WARNING: str = "⚠️"       # ⚠️ warning
SEVERITY_ALERT:   str = "\U0001F6A8"         # 🚨 rotating alarm light


# ---------------------------------------------------------------------------
# DOMAIN — entity/topic markers
# ---------------------------------------------------------------------------

DOMAIN_JOB:      str = "\U0001F4CB"          # 📋 clipboard
DOMAIN_MACHINE:  str = "\U0001F3ED"          # 🏭 factory
DOMAIN_CREW:     str = "\U0001F465"          # 👥 busts in silhouette
DOMAIN_MATERIAL: str = "\U0001F4E6"          # 📦 package
DOMAIN_MONEY:    str = "\U0001F4B0"          # 💰 money bag


# ---------------------------------------------------------------------------
# PROMPT — markers for owner-facing calls to action and greeting glyphs
# ---------------------------------------------------------------------------

PROMPT_CONFIRM:       str = "✅"         # ✅ same codepoint as STATUS_DONE
PROMPT_ACTION_NEEDED: str = "\U0001F449"     # 👉 backhand index pointing right
PROMPT_GREETING:      str = "\U0001F44B"     # 👋 waving hand — used in AI_REPLY_HEADER


# ---------------------------------------------------------------------------
# Sentinel collections — useful for tests that want to enumerate the
# entire vocabulary (e.g. "every emoji rendered in a template appears
# in this set"). Keep these in sync if you add a new constant above.
# ---------------------------------------------------------------------------

ALL_STATUS:   tuple[str, ...] = (STATUS_DONE, STATUS_IN_PROGRESS, STATUS_BLOCKED, STATUS_IDLE)
ALL_SEVERITY: tuple[str, ...] = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ALERT)
ALL_DOMAIN:   tuple[str, ...] = (DOMAIN_JOB, DOMAIN_MACHINE, DOMAIN_CREW, DOMAIN_MATERIAL, DOMAIN_MONEY)
ALL_PROMPT:   tuple[str, ...] = (PROMPT_CONFIRM, PROMPT_ACTION_NEEDED, PROMPT_GREETING)

ALL_EMOJI:    tuple[str, ...] = ALL_STATUS + ALL_SEVERITY + ALL_DOMAIN + ALL_PROMPT
