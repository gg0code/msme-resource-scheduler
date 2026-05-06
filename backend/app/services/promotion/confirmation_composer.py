# app/services/promotion/confirmation_composer.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.15 (revised) message-composition service. Takes a list of
# qualifying ExtractionCandidate ORM rows + a tenant industry_type +
# locale, and returns the WhatsApp text the bot will send to the
# owner asking "are these your employees / machines?". This module is
# pure-ish: it reads templates from briefings/templates.py and ORM
# row attributes, but does no DB writes and no WhatsApp sends. The
# caller (promoter.compose_confirmation_for_tenant) handles the
# state-flip + commit, and the async wrapper handles the actual
# WhatsApp send.
#
# WHO CALLS THIS FILE
# - app/services/promotion/promoter.py - compose_confirmation_for_tenant
#   passes the candidate batch + industry context here, gets the text
#   back, then flips the state and commits.
# - app/services/promotion/__init__.py - re-exports compose_message
#   for direct test access.
# - backend/tests/services/test_confirmation_composer.py.
#
# WHAT THIS FILE CALLS
# - app/services/briefings/templates.{INDUSTRY_LABELS, industry_labels,
#   pick_template, Locale, DEFAULT_LOCALE} - the same locale-aware
#   templating layer the v6.3.4 morning/evening briefings use, so all
#   owner-facing prose stays consistent.
# - stdlib only otherwise.
#
# DESIGN NOTES (Q3, Q6, Q8)
# - Q3 / batch size: this module does NOT enforce the cap. The caller
#   pre-slices to PROMOTION_CONFIRMATION_BATCH_SIZE (default 5) and
#   passes only the in-batch candidates here. Keeps the composer's
#   signature simple and lets the caller decide whether to surface
#   "and N more tomorrow" hints (currently no, per Q6 "no padding").
# - Q6 / wording: per user's Stage-1 answer we use "Pichhle kuch dino
#   mein" (last few days) instead of "Pichhle hafte mein" (last week)
#   since accumulation period varies. Templates live in
#   briefings/templates.py with three locales (en/hi/hi-en).
# - Q6 / no confidence numerics: we surface mention_count ("5 baar
#   mention hua") not confidence ("0.87 confidence"). Mention count
#   is the trust signal a factory owner relates to.
# - Q8 / fuzzy-matched candidates absent: the caller pre-filters fuzzy-
#   matched candidates out (they get state='confirmed' silently in
#   the 02:00 evaluation tick). This composer never sees them, so no
#   special-case branch is needed here.
# - Industry vocabulary: resolved via industry_labels(industry_type).
#   Unknown industry falls back to printing per the existing helper.
#   Singular 'employee' / 'machine' labels live in INDUSTRY_LABELS
#   (added in v6.3.15 revised - new singular keys).
#
# OUTPUT SHAPE
# Single string, ready to pass to _send_whatsapp_message. Format:
#
#   <intro line>
#
#   1. <name> - <count> baar mention hua (employee?)
#   2. <name> - <count> baar mention hua (press?)
#   3. ...
#
#   <outro: HAAN/NAHI/specific/skip instructions>
#
# Per Q6 the message is intentionally transactional - no thank-you
# padding, no confidence scores, no "the bot has been listening for
# the past N days" framing. Owner reads, replies, moves on.
#
# FAILURE SEMANTICS
# - Empty candidate list -> returns None. Caller treats this as "no
#   message to send" and skips the WhatsApp call.
# - Unknown entity_type on a candidate -> the candidate is skipped
#   in the rendered list and a warning is logged. The intro/outro
#   still render so the message is not malformed; the missing index
#   is filled by the next valid candidate.
#   (entity_type ought to be in {employee, machine} since the
#   caller pre-filters; this is defence-in-depth.)
# - Pure function: never raises, never touches DB or network.

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from app.models.extraction_candidate import ExtractionCandidate
from app.services.briefings.templates import (
    DEFAULT_LOCALE,
    Locale,
    industry_labels,
    pick_template,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Telemetry shape
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ComposedMessage:
    """The text + context returned by compose_message.

    Used by:    promoter.compose_confirmation_for_tenant - the caller
                needs both the text (for the WhatsApp send) and the
                ordered list of candidate ids (so the same set can be
                state-flipped and audit-logged in one transaction).
    Fields:
        text:           Ready-to-send WhatsApp message string.
        candidate_ids:  IDs of the candidates rendered, in display
                        order (1, 2, 3...). The reply parser uses
                        this ordering to interpret '1, 2 haan' style
                        partial replies.
        candidate_index_map: 1-based-index -> candidate id, materialised
                        once here so the parser does not have to
                        reconstruct it from the rendered string.
    """
    text: str
    candidate_ids: list[int]
    candidate_index_map: dict[int, int]


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def compose_message(
    candidates: Iterable[ExtractionCandidate],
    *,
    industry_type: Optional[str],
    locale: Optional[Locale] = None,
) -> Optional[ComposedMessage]:
    """Build the WhatsApp confirmation message for one batch.

    Called by:    app/services/promotion/promoter.py
                  compose_confirmation_for_tenant (production) and
                  unit tests directly (composer is pure).
    Calls into:   industry_labels (resolves vocabulary), pick_template
                  (resolves the per-key, per-locale string).
    Side effects: none - pure function. Logs a WARNING if a candidate
                  has an unexpected entity_type (defence-in-depth).

    Args:
        candidates:    Pre-filtered, pre-sorted, pre-capped iterable of
                       ExtractionCandidate rows. Caller is responsible
                       for ordering by (mention_count desc, confidence
                       desc, id asc) and for slicing to the batch size
                       cap. This composer renders them in input order.
        industry_type: Tenant.industry_type (may be None for legacy
                       tenants - falls back to printing vocabulary).
        locale:        'en' / 'hi' / 'hi-en'. None defaults to
                       DEFAULT_LOCALE ('hi-en'), matching the v6.3.4
                       morning briefing convention for India MSMEs.

    Returns:
        ComposedMessage with text + ordered candidate id list +
        index map. Returns None when the input contains zero
        renderable candidates (caller skips the WhatsApp send).
    """
    locale = locale or DEFAULT_LOCALE
    labels = industry_labels(industry_type)

    rendered_lines: list[str] = []
    candidate_ids: list[int] = []
    index_map: dict[int, int] = {}

    idx = 0
    for cand in candidates:
        if cand.entity_type not in ("employee", "machine"):
            logger.warning(
                "confirmation_composer_unexpected_type tenant=%s "
                "candidate=%s entity_type=%r - skipping in render.",
                cand.tenant_id, cand.id, cand.entity_type,
            )
            continue

        idx += 1
        candidate_ids.append(int(cand.id))
        index_map[idx] = int(cand.id)

        if cand.entity_type == "employee":
            line_template = pick_template("confirmation_line_employee", locale)
            rendered_lines.append(
                line_template.format(
                    idx=idx,
                    name=cand.raw_value,
                    count=cand.mention_count,
                    employee_label=labels["employee"],
                )
            )
        else:  # 'machine'
            line_template = pick_template("confirmation_line_machine", locale)
            rendered_lines.append(
                line_template.format(
                    idx=idx,
                    name=cand.raw_value,
                    count=cand.mention_count,
                    machine_label=labels["machine"],
                )
            )

    if not rendered_lines:
        return None

    intro = pick_template("confirmation_intro", locale).format(
        workspace_label=labels["workspace_label"],
        employees_label=labels["employees"],
        machines_label=labels["machines"],
    )
    outro = pick_template("confirmation_outro", locale)

    text = intro + "\n\n" + "\n".join(rendered_lines) + "\n\n" + outro
    return ComposedMessage(
        text=text,
        candidate_ids=candidate_ids,
        candidate_index_map=index_map,
    )


def compose_ack(
    *,
    decisions: dict[int, str],
    candidates_by_id: dict[int, ExtractionCandidate],
    industry_type: Optional[str],
    locale: Optional[Locale] = None,
) -> str:
    """Build the owner-facing acknowledgement after a confirmation reply.

    Called by:    app/routers/whatsapp.py - the new Step 2.5 confirmation
                  reply branch, after the reply parser returns decisions
                  and the promoter applies them.
    Calls into:   industry_labels, pick_template.
    Side effects: none - pure function.

    Args:
        decisions:        candidate_id -> 'confirmed'|'rejected'|'deferred'.
                          Output of reply_parser.parse_reply.
        candidates_by_id: candidate_id -> ExtractionCandidate, for
                          rendering raw_value back to the owner. Caller
                          loads these from the same DB session that
                          performed the apply step.
        industry_type:    Tenant.industry_type (None falls back to
                          printing vocabulary).
        locale:           Locale for the ack text. None -> DEFAULT_LOCALE.

    Returns:
        A short single-message ack:
          - all confirmed -> "Theek hai. Add ho gaye: A, B, C."
          - mixed         -> "Theek hai. Add ho gaye: A. Skip kar diye: B."
          - all deferred  -> "Theek hai, kuch add nahi kiya. Pending mein rahenge..."
          - unparseable   -> "Samajh nahi aaya - HAAN ya NAHI bhejein..."
    """
    locale = locale or DEFAULT_LOCALE
    # industry_labels is resolved for parity with compose_message even
    # though the current ack templates do not use industry vocabulary;
    # leaving the call in keeps the surface consistent if a future
    # template variant wants e.g. "Add ho gaye {employees_label}: ...".
    industry_labels(industry_type)

    confirmed_names = [
        candidates_by_id[cid].raw_value
        for cid, dec in decisions.items()
        if dec == "confirmed" and cid in candidates_by_id
    ]
    rejected_names = [
        candidates_by_id[cid].raw_value
        for cid, dec in decisions.items()
        if dec == "rejected" and cid in candidates_by_id
    ]
    deferred_names = [
        candidates_by_id[cid].raw_value
        for cid, dec in decisions.items()
        if dec == "deferred" and cid in candidates_by_id
    ]

    # Edge case: parser returned nothing decisive (all deferred or empty).
    if not confirmed_names and not rejected_names:
        if deferred_names and len(deferred_names) == len(decisions):
            # Everything was treated as deferred - the parser couldn't
            # decide. Use the unparsed-ack template.
            return pick_template("confirmation_ack_unparsed", locale)
        # Empty decisions dict - shouldn't happen in production, but
        # handle gracefully.
        return pick_template("confirmation_ack_none", locale)

    if confirmed_names and not rejected_names:
        return pick_template("confirmation_ack_all_added", locale).format(
            added=", ".join(confirmed_names),
        )

    if rejected_names and not confirmed_names:
        return pick_template("confirmation_ack_none", locale)

    # Mixed: some confirmed, some rejected.
    return pick_template("confirmation_ack_partial", locale).format(
        added=", ".join(confirmed_names) if confirmed_names else "-",
        skipped=", ".join(rejected_names) if rejected_names else "-",
    )
