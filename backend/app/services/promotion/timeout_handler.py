# app/services/promotion/timeout_handler.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.15 (revised) timeout-handling service. Walks 'pending'
# extraction_candidates rows that have aged past
# PROMOTION_CONFIRMATION_TIMEOUT_DAYS (default 7) without an owner
# reply and either re-asks them (state -> 'none', retry_count +=1) or
# auto-rejects them (state -> 'rejected') once the retry cap
# (PROMOTION_CONFIRMATION_MAX_RETRIES, default 3) is hit.
#
# Per Q5 the cycle is: ask -> wait 7d -> re-ask -> wait 7d -> re-ask
# -> wait 7d -> auto-reject. Three patient nudges over ~21 days
# before the system stops asking. Each transition writes a
# extraction.confirmation_timeout audit event so the owner can see
# in the events log why a candidate was re-asked or auto-rejected.
#
# WHO CALLS THIS FILE
# - app/services/promotion/promoter.py - the 19:00 IST evening
#   confirmation cron calls process_timeouts_for_tenant immediately
#   before composing tonight's batch, so re-asked candidates can
#   be picked up by the same evening's cron run.
# - app/services/promotion/__init__.py - re-exports
#   process_timeouts_for_tenant for direct test access.
# - backend/tests/services/test_timeout_handler.py.
#
# WHAT THIS FILE CALLS
# - app.config.settings - PROMOTION_CONFIRMATION_TIMEOUT_DAYS,
#   PROMOTION_CONFIRMATION_MAX_RETRIES.
# - app.models.{event.Event, extraction_candidate.ExtractionCandidate}.
# - sqlalchemy.orm.Session - sync session, never AsyncSession.
#
# DESIGN NOTES (Q5)
# - The function is sync and per-tenant. Caller (promoter) opens the
#   session in a worker thread via asyncio.to_thread.
# - Per-candidate commit so a single bad row cannot block the rest
#   of the tenant's timeout sweep. Mirrors the per-candidate commit
#   pattern in promoter.evaluate_for_tenant.
# - The event payload includes retry_count and action so a downstream
#   reader can reconstruct the timeline ('re-asked' on bumps,
#   'auto-rejected' on the final transition).
# - State transitions:
#     pending + retry_count <  MAX  -> none      (re-ask next batch)
#     pending + retry_count >= MAX  -> rejected  (give up)
# - retry_count is incremented BEFORE the threshold check so the very
#   first re-ask happens at retry=1, second at retry=2, third (the
#   final transition) at retry=3 -> auto-reject.
#
# FAILURE SEMANTICS
# - Per-candidate failure: rolled back, logged with structured
#   context, summary.errors gets one entry, the loop continues.
# - Function never raises into the cron path.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit-event vocabulary - shared with promoter.py
# ---------------------------------------------------------------------------
# Event-type constant declared here to avoid an import cycle with
# promoter.py (timeout_handler is imported by promoter, not the other
# way around). The string is deliberately the same as the
# EVENT_CONFIRMATION_TIMEOUT constant promoter exposes - one source of
# truth, two import paths.
EVENT_CONFIRMATION_TIMEOUT: str = "extraction.confirmation_timeout"

# Action labels written into the event payload.
ACTION_RE_ASKED:      str = "re-asked"
ACTION_AUTO_REJECTED: str = "auto-rejected"

# Polymorphic entity_type for events. Matches promoter.py convention.
_EVENT_ENTITY_TYPE: str = "extraction_candidate"


# ---------------------------------------------------------------------------
# Telemetry shape
# ---------------------------------------------------------------------------

@dataclass
class TimeoutSummary:
    """Per-(tenant, run) timeout-sweep outcome.

    Used by:    process_timeouts_for_tenant return value;
                send_confirmations_for_all_tenants logs / aggregates.
    Fields:
        tenant_id:         Tenant the sweep targeted.
        scanned:           Number of 'pending' candidates examined.
        re_asked:          Transitioned pending -> none for re-asking.
        auto_rejected:     Transitioned pending -> rejected (cap hit).
        not_yet_due:       Pending but still within the timeout window.
        errors:            Per-candidate error strings; not raised.
    """
    tenant_id:     int
    scanned:       int = 0
    re_asked:      int = 0
    auto_rejected: int = 0
    not_yet_due:   int = 0
    errors:        list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def process_timeouts_for_tenant(
    tenant_id: int,
    db: Session,
    *,
    now: Optional[datetime] = None,
) -> TimeoutSummary:
    """Re-ask or auto-reject 'pending' candidates that aged past the window.

    Called by:    app/services/promotion/promoter.py
                  send_confirmations_for_tenant (sync per-tenant body
                  that runs inside asyncio.to_thread under the 19:00
                  IST cron). Also callable directly from tests.
    Calls into:   db.query, db.add, db.commit (per candidate),
                  _emit_timeout_event.
    Side effects:
        - Reads extraction_candidates rows where
          confirmation_state='pending' and confirmation_asked_at is
          older than now - PROMOTION_CONFIRMATION_TIMEOUT_DAYS.
        - For each: bumps confirmation_retry_count, flips state to
          'none' (re-ask) or 'rejected' (auto-reject), stages an
          extraction.confirmation_timeout event, commits.
        - Logs one INFO 'timeout_summary' line at end.

    Args:
        tenant_id: Tenant to sweep.
        db:        Sync SQLAlchemy session. THIS function commits per
                   candidate; callers must not nest a transaction.
        now:       UTC anchor for the 'older than' comparison. Tests
                   inject a fixed value. Defaults to
                   datetime.now(timezone.utc).

    Returns:
        TimeoutSummary with telemetry. Never raises.
    """
    summary = TimeoutSummary(tenant_id=tenant_id)
    if now is None:
        now = datetime.now(timezone.utc)

    timeout_days = max(1, int(settings.PROMOTION_CONFIRMATION_TIMEOUT_DAYS))
    max_retries  = max(1, int(settings.PROMOTION_CONFIRMATION_MAX_RETRIES))
    cutoff = now - timedelta(days=timeout_days)

    # All pending candidates for this tenant. Filter the
    # 'still within window' subset in Python so the summary can
    # report not_yet_due accurately - the alternative (filter in SQL)
    # would lose the count.
    pending = (
        db.query(ExtractionCandidate)
        .filter(
            ExtractionCandidate.tenant_id == tenant_id,
            ExtractionCandidate.confirmation_state == "pending",
        )
        .all()
    )
    summary.scanned = len(pending)
    if not pending:
        logger.info(
            "timeout_summary tenant=%d scanned=0 re_asked=0 "
            "auto_rejected=0 not_yet_due=0 errors=0",
            tenant_id,
        )
        return summary

    for cand in pending:
        try:
            asked_at = cand.confirmation_asked_at
            if asked_at is None:
                # Missing asked_at - shouldn't happen, but treat as
                # already-due so the row gets re-asked rather than
                # leaking forever.
                logger.warning(
                    "timeout_handler_no_asked_at tenant=%d candidate=%d - "
                    "treating as due.",
                    tenant_id, cand.id,
                )
            else:
                # Normalise tz - SQLite test backend strips tz info.
                if asked_at.tzinfo is None:
                    asked_at = asked_at.replace(tzinfo=timezone.utc)
                if asked_at > cutoff:
                    summary.not_yet_due += 1
                    continue

            # Bump retry count BEFORE deciding the verdict so the very
            # first re-ask is retry_count=1 and the third strike is
            # retry_count=3 -> auto-reject.
            cand.confirmation_retry_count = (
                int(cand.confirmation_retry_count or 0) + 1
            )

            # Decide the verdict + mutate the candidate, but DO NOT
            # bump the summary counter yet - we only count outcomes
            # after the commit succeeds so a per-candidate failure
            # rolls back cleanly without leaving the summary bumped.
            if cand.confirmation_retry_count >= max_retries:
                cand.confirmation_state = "rejected"
                action = ACTION_AUTO_REJECTED
                is_auto_reject = True
            else:
                cand.confirmation_state = "none"
                cand.confirmation_asked_at = None
                cand.confirmation_message_id = None
                action = ACTION_RE_ASKED
                is_auto_reject = False

            _emit_timeout_event(
                db,
                tenant_id=tenant_id,
                candidate_id=int(cand.id),
                retry_count=int(cand.confirmation_retry_count),
                days_pending=timeout_days,
                action=action,
            )
            db.commit()

            # Commit succeeded - now safe to bump the summary counter.
            if is_auto_reject:
                summary.auto_rejected += 1
            else:
                summary.re_asked += 1

        except Exception as exc:  # noqa: BLE001
            db.rollback()
            msg = (
                f"timeout_failed tenant={tenant_id} candidate={cand.id} "
                f"err={exc!r}"
            )
            logger.error(msg)
            summary.errors.append(msg)

    logger.info(
        "timeout_summary tenant=%d scanned=%d re_asked=%d "
        "auto_rejected=%d not_yet_due=%d errors=%d",
        tenant_id,
        summary.scanned,
        summary.re_asked,
        summary.auto_rejected,
        summary.not_yet_due,
        len(summary.errors),
    )
    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _emit_timeout_event(
    db: Session,
    *,
    tenant_id: int,
    candidate_id: int,
    retry_count: int,
    days_pending: int,
    action: str,
) -> None:
    """Stage one extraction.confirmation_timeout event row. Caller commits.

    Called by:    process_timeouts_for_tenant - one event per state
                  transition (re-ask OR auto-reject).
    Calls into:   db.add.
    Side effects: stages an INSERT on events. No flush, no commit.
    """
    db.add(Event(
        tenant_id=tenant_id,
        event_type=EVENT_CONFIRMATION_TIMEOUT,
        entity_type=_EVENT_ENTITY_TYPE,
        entity_id=candidate_id,
        actor_user_id=None,
        source="system",
        payload={
            "candidate_id": candidate_id,
            "retry_count":  retry_count,
            "days_pending": days_pending,
            "action":       action,
        },
    ))
