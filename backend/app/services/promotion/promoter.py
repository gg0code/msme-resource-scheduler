# app/services/promotion/promoter.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.15 (revised) candidate-promotion service. The original v6.3.15
# silently inserted high-confidence, frequently-mentioned candidates
# from extraction_candidates into the canonical employees / machines
# tables on the 02:00 IST nightly tick. The revised model splits that
# into TWO crons and gates every real-table insertion on an explicit
# WhatsApp confirmation from the owner:
#
#   02:00 IST - evaluate_for_all_tenants
#     For each enabled tenant, scans extraction_candidates and:
#       * fuzzy-matches each promotable candidate against existing
#         employees/machines. On a match, flips state='confirmed' and
#         emits extraction.candidate_confirmed (silent skip per Q8).
#       * leaves non-matching candidates with state='none' so the
#         19:00 cron can ask the owner about them.
#       * preserves the customer-skip and over-cap-skip and skipped-
#         other paths from the original v6.3.15.
#     ZERO insertions into employees/machines on this tick.
#
#   19:00 IST - send_confirmations_for_all_tenants
#     For each enabled tenant:
#       a) process_timeouts_for_tenant - re-ask or auto-reject any
#          candidates that have been 'pending' past the timeout.
#       b) compose_confirmation_for_tenant - find the top-N qualifying
#          state='none' candidates, build the WhatsApp text, flip
#          their state to 'pending', commit.
#       c) await _send_whatsapp_message - actually transmit. Returns
#          a wamid (real or synthetic).
#       d) record_confirmation_sent - store the wamid on the pending
#          candidates and emit extraction.confirmation_requested.
#     If no top-tier phone is linked to the tenant, the run is
#     SKIPPED with a logger.critical entry (Q9 hard-fail).
#
#   Inbound reply (routers/whatsapp.py Step 2.5)
#     parse_reply -> apply_confirmation_decisions:
#       - Each 'confirmed' decision triggers the actual employees /
#         machines insertion + extraction.candidate_promoted event.
#       - 'rejected' flips state='rejected'; never inserted.
#       - 'deferred' leaves state='pending'; will time out in 7 days.
#     One aggregate extraction.confirmation_received event records
#     the parse strategy + raw reply + decisions for audit.
#
# IDEMPOTENCY GUARANTEE
# - 02:00 cron: re-running on the same data writes the same number of
#   confirmed events (existing fuzzy match still matches) and produces
#   no new state changes for state!='none' candidates.
# - 19:00 cron: re-running within 24h finds no state='none' candidates
#   for the just-asked batch (they're now 'pending'), so no second
#   message is composed. APScheduler is configured with
#   coalesce=True, max_instances=1 to prevent overlap; the state-flip
#   in compose_confirmation_for_tenant is the second-line defence.
#
# CUSTOMER PROMOTION IS OUT OF SCOPE AT v6.3.15
# As in the original v6.3.15: there is no customers table. Customer
# candidates emit one extraction.candidate_skipped event with
# reason='customer_table_not_yet_implemented' (deduped per candidate).
#
# WHO CALLS THIS FILE
# - app/services/whatsapp_alerts.py - registers evaluate_for_all_tenants
#   on the 02:00 IST cron AND send_confirmations_for_all_tenants on
#   the 19:00 IST cron. Both are async APScheduler entry points.
# - app/services/promotion/__init__.py - re-exports the public surface.
# - app/routers/whatsapp.py - Step 2.5 confirmation reply branch:
#   imports parse_reply and apply_confirmation_decisions.
# - backend/inspect_extractions.py - uses EVENT_* and the per-state
#   filtering for --show-confirmations.
#
# WHAT THIS FILE CALLS
# - app/services/extraction/feature_flag.is_entity_extraction_enabled
#   and ._enabled_tenant_ids - reuses the extractor's tenant scope so
#   a parallel parser cannot drift.
# - app/services/promotion/fuzzy_match.fuzzy_best_match.
# - app/services/promotion/confirmation_composer.compose_message.
# - app/services/promotion/timeout_handler.process_timeouts_for_tenant.
# - app/services/whatsapp_send._send_whatsapp_message (async, returns
#   Optional[wamid]).
# - app/models.{auth.TOP_TIER_ROLES, employee.Employee, machine.Machine,
#   extraction_candidate.ExtractionCandidate, event.Event,
#   whatsapp.PhoneTenantMap}.
# - app/database.SessionLocal.
# - app/config.settings.
#
# DESIGN NOTES (Q1-Q10 from the v6.3.15-revised discovery doc)
# - Q1: confirmation state lives on extraction_candidates (4 columns
#   added in migration 030). VARCHAR vocabulary, not DB ENUM, matching
#   the entity_type / source_type precedent.
# - Q2: 19:00 IST evening cron, separate from 02:00 IST evaluation.
# - Q3: per-batch cap = settings.PROMOTION_CONFIRMATION_BATCH_SIZE (5).
# - Q4: hybrid heuristic + LLM reply parser. Routing precedence rule
#   (the new branch runs BEFORE the v5.12 pending-action machine,
#   gated by the 48h pending-state filter) lives in routers/whatsapp.py,
#   not here.
# - Q5: 7-day timeout, 3 retries -> auto-reject. Implemented in
#   timeout_handler.process_timeouts_for_tenant; this module just
#   invokes it inside send_confirmations_for_tenant.
# - Q6: composer owns the per-vertical templates; this module passes
#   industry_type through.
# - Q7: pre-fire scan filters confirmation_state='none'. Already-asked
#   candidates are skipped on the next batch.
# - Q8: fuzzy-matched candidates flip state='confirmed' silently in
#   evaluate_for_tenant - they never reach the composer.
# - Q9: recipient is the most-recent active top-tier PhoneTenantMap.
#   If absent, the tenant is SKIPPED with logger.critical and no
#   confirmation message is sent (per user's modified Q9 — no fallback
#   to delegated managers).
# - Q10: three new event types (extraction.confirmation_requested,
#   extraction.confirmation_received, extraction.confirmation_timeout)
#   plus an augmented extraction.candidate_promoted payload carrying
#   confirmation_message_id and decided_by_user_id.
#
# FAILURE SEMANTICS
# - Per-candidate failure within evaluate / apply: rolled back, logged,
#   summary.errors gets one entry, the loop continues.
# - Per-tenant failure within either fan-out wrapper: caught, logged
#   with tenant_id, the next tenant still runs.
# - Send failures in send_confirmations: the candidate stays 'pending'
#   without a message_id; the timeout handler will re-ask in 7 days.
# - The cron entry points NEVER raise into APScheduler.

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.auth import TOP_TIER_ROLES
from app.models.employee import Employee
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate
from app.models.machine import Machine
from app.models.whatsapp import PhoneTenantMap
from app.services.extraction.feature_flag import (  # type: ignore[reportPrivateUsage]
    _enabled_tenant_ids,
    is_entity_extraction_enabled,
)
from app.services.promotion.confirmation_composer import (
    ComposedMessage,
    compose_message,
)
from app.services.promotion.fuzzy_match import fuzzy_best_match
from app.services.promotion.timeout_handler import (
    EVENT_CONFIRMATION_TIMEOUT,  # noqa: F401 - re-exported for callers
    process_timeouts_for_tenant,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit-event vocabulary - all `extraction.*` to match the v6.3.4
# `briefing.*` precedent (one dotted namespace per subsystem).
# ---------------------------------------------------------------------------

EVENT_PROMOTED:               str = "extraction.candidate_promoted"
EVENT_CONFIRMED:              str = "extraction.candidate_confirmed"
EVENT_SKIPPED:                str = "extraction.candidate_skipped"
EVENT_CONFIRMATION_REQUESTED: str = "extraction.confirmation_requested"
EVENT_CONFIRMATION_RECEIVED:  str = "extraction.confirmation_received"
# EVENT_CONFIRMATION_TIMEOUT is owned by timeout_handler.py and re-
# exported above so callers (tests, inspect script) have a single
# import surface.

# Polymorphic entity_type written into Event rows. Always paired with
# entity_id = candidate.id so audit records dereference back to the
# staging row.
_EVENT_ENTITY_TYPE: str = "extraction_candidate"

# Skip reasons - written into Event.payload['reason'] and used by the
# inspection script to bucket counts.
REASON_DAILY_CAP:        str = "daily_cap_reached"
REASON_NO_TABLE:         str = "customer_table_not_yet_implemented"
REASON_NO_TOP_TIER_PHONE: str = "no_top_tier_phone_linked"

# Entity types we promote into real tables at v6.3.15.
_PROMOTABLE_ENTITY_TYPES: frozenset[str] = frozenset({"employee", "machine"})

# Source value stamped on inserted rows.
_INFERRED_SOURCE: str = "whatsapp_inferred"

# Default for employee.worker_type on inserted rows.
_DEFAULT_WORKER_TYPE: str = "permanent"

# Window in which a 'pending' candidate is considered "in flight" for the
# purposes of routing inbound replies. Must comfortably exceed the 48h
# expectation in the routers/whatsapp.py routing-precedence rule (Q4).
INFLIGHT_REPLY_WINDOW_HOURS: int = 48


# ---------------------------------------------------------------------------
# Telemetry shapes
# ---------------------------------------------------------------------------

@dataclass
class EvaluationSummary:
    """Per-(tenant, run) outcome of evaluate_for_tenant (02:00 cron).

    Used by:    evaluate_for_tenant return; evaluate_for_all_tenants
                aggregates these.
    Logged at:  INFO level as the `evaluation_summary` line.
    Fields:
        tenant_id:                 Tenant the run targeted.
        qualified:                 Total candidates above threshold.
        confirmed_via_fuzzy:       Fuzzy-matched -> state='confirmed'.
        ready_for_confirmation:    state='none' qualifying candidates
                                   that the 19:00 cron will ask about.
                                   (Counted, not modified, here.)
        skipped_cap:               Promotable candidates beyond the
                                   per-tenant daily cap.
        skipped_no_table:          Customer candidates skipped (Q6b).
        skipped_other:             Non-promotable, non-customer types
                                   (skill, material, job, issue) that
                                   future versions will consume.
        already_asked:             Promotable candidates already in
                                   state in {'pending','confirmed','rejected'}.
                                   Counted for visibility; no-ops.
        duration_ms:               Wall-clock for the run.
        errors:                    Per-candidate error strings; not raised.
    """
    tenant_id:              int
    qualified:              int = 0
    confirmed_via_fuzzy:    int = 0
    ready_for_confirmation: int = 0
    skipped_cap:            int = 0
    skipped_no_table:       int = 0
    skipped_other:          int = 0
    already_asked:          int = 0
    duration_ms:            int = 0
    errors:                 list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BatchToSend:
    """One tenant's confirmation batch ready for the WhatsApp send.

    Used by:    compose_confirmation_for_tenant return value;
                send_confirmations_for_all_tenants consumes it.
    Fields:
        tenant_id:           Tenant the batch belongs to.
        recipient_phone:     E.164 phone number of the chosen
                             top-tier recipient.
        recipient_user_id:   PhoneTenantMap.user_id of the recipient,
                             stored in the audit event payload.
        message_text:        Ready-to-send WhatsApp text from
                             confirmation_composer.compose_message.
        candidate_ids:       Candidate ids in display order.
        candidate_index_map: 1-based-index -> candidate id, materialised
                             once by the composer.
    """
    tenant_id:           int
    recipient_phone:     str
    recipient_user_id:   int
    message_text:        str
    candidate_ids:       list[int]
    candidate_index_map: dict[int, int]


@dataclass
class ApplyConfirmationsSummary:
    """Per-(tenant, reply) outcome of apply_confirmation_decisions.

    Used by:    apply_confirmation_decisions return;
                routers/whatsapp.py logs and surfaces ack to owner.
    Fields:
        tenant_id:           Tenant the reply belongs to.
        confirmed_inserted:  Owner-confirmed candidates inserted into
                             the canonical table.
        rejected:            Owner-rejected candidates flipped to
                             state='rejected'.
        deferred:            Candidates left in state='pending' for
                             the next timeout cycle.
        not_found:           Decisions referenced candidate ids that
                             did not exist or were no longer in
                             state='pending'. Counted; no-ops.
        errors:              Per-candidate error strings; not raised.
    """
    tenant_id:          int
    confirmed_inserted: int = 0
    rejected:           int = 0
    deferred:           int = 0
    not_found:          int = 0
    errors:             list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _emit_event(
    db: Session,
    *,
    tenant_id: int,
    event_type: str,
    entity_id: Optional[int],
    payload: dict,
    actor_user_id: Optional[int] = None,
) -> None:
    """Stage one Event row. Caller commits.

    Called by:    every promote/confirm/skip/request/receive helper.
    Calls into:   db.add.
    Side effects: stages an INSERT on events. No flush, no commit.

    Convention matches v6.3.4 dispatcher:
      - entity_type = 'extraction_candidate' (or None if entity_id None)
      - source      = 'system' for cron paths; 'whatsapp' for reply path.
      - actor_user_id = None for cron paths; user id for reply path.
    """
    src = "system" if actor_user_id is None else "whatsapp"
    db.add(Event(
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type=_EVENT_ENTITY_TYPE,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        source=src,
        payload=payload,
    ))


def _qualifying_candidates(
    db: Session, tenant_id: int,
) -> list[ExtractionCandidate]:
    """Threshold-filtered + ranked candidates for one tenant.

    Called by:    evaluate_for_tenant.
    Calls into:   db.query.
    Side effects: read-only.
    Returns:      Candidates with mention_count >= threshold AND
                  confidence >= threshold, ordered by mention_count
                  desc, confidence desc, id asc (deterministic).
                  Includes candidates of every entity_type and every
                  confirmation_state - the caller filters further.
    """
    return (
        db.query(ExtractionCandidate)
        .filter(
            ExtractionCandidate.tenant_id == tenant_id,
            ExtractionCandidate.mention_count
                >= settings.PROMOTION_MENTION_THRESHOLD,
            ExtractionCandidate.confidence
                >= settings.PROMOTION_CONFIDENCE_THRESHOLD,
        )
        .order_by(
            ExtractionCandidate.mention_count.desc(),
            ExtractionCandidate.confidence.desc(),
            ExtractionCandidate.id.asc(),
        )
        .all()
    )


def _existing_employees(
    db: Session, tenant_id: int,
) -> list[tuple[int, str]]:
    """Tenant's current employees as (id, full_name) pairs."""
    rows = (
        db.query(Employee.id, Employee.full_name)
        .filter(Employee.tenant_id == tenant_id)
        .all()
    )
    return [(int(r[0]), str(r[1] or "")) for r in rows]


def _existing_machines(
    db: Session, tenant_id: int,
) -> list[tuple[int, str]]:
    """Tenant's current machines as (id, name) pairs."""
    rows = (
        db.query(Machine.id, Machine.name)
        .filter(Machine.tenant_id == tenant_id)
        .all()
    )
    return [(int(r[0]), str(r[1] or "")) for r in rows]


def _customer_already_skipped(
    db: Session, tenant_id: int, candidate_id: int,
) -> bool:
    """Has a skipped event already been emitted for this customer candidate?

    Why: customer candidates persist in the staging table run-over-run
    while there is no customers table. Without dedupe, the events
    table would gain a duplicate row every night for every qualifying
    customer.
    """
    return (
        db.query(Event.id)
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == EVENT_SKIPPED,
            Event.entity_id == candidate_id,
        )
        .first()
    ) is not None


def _industry_type_for_tenant(db: Session, tenant_id: int) -> Optional[str]:
    """Resolve Tenant.industry_type via a single read.

    Called by:    compose_confirmation_for_tenant. Returned as input to
                  confirmation_composer.compose_message; the composer
                  falls back to printing vocabulary on None / unknown.
    Side effects: read-only.
    """
    from app.models.auth import Tenant
    row = db.execute(
        select(Tenant.industry_type).where(Tenant.id == tenant_id)
    ).first()
    if row is None:
        return None
    return row[0]


def _resolve_recipient_phone_mapping(
    db: Session, tenant_id: int,
) -> Optional[PhoneTenantMap]:
    """Most-recently-active top-tier PhoneTenantMap for the tenant, or None.

    Called by:    compose_confirmation_for_tenant.
    Calls into:   db.execute on PhoneTenantMap.
    Side effects: read-only.

    Per Q9 (modified): only top-tier roles (TOP_TIER_ROLES) are eligible.
    There is NO fallback to delegated manager / operator phones — those
    do not have authority to add data-model entities. Returns None when
    the tenant has no active top-tier phone, in which case the caller
    skips the tenant and logs a critical warning.

    Ordering: NULLS LAST on last_seen_at so a fresh-but-never-seen phone
    is preferred only when nothing more recent exists. Tie-break by id
    DESC for determinism.
    """
    rows = (
        db.execute(
            select(PhoneTenantMap)
            .where(
                PhoneTenantMap.tenant_id == tenant_id,
                PhoneTenantMap.is_active == True,  # noqa: E712
                PhoneTenantMap.phone_role.in_(list(TOP_TIER_ROLES)),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    # Sort in Python: most-recent first, NULLs last, then id DESC.
    rows.sort(
        key=lambda r: (
            r.last_seen_at is None,                       # False (=0) first
            -(r.last_seen_at.timestamp()) if r.last_seen_at else 0.0,
            -int(r.id),
        )
    )
    return rows[0]


# ---------------------------------------------------------------------------
# 02:00 cron - evaluate_for_tenant
# ---------------------------------------------------------------------------

def _check_fuzzy_employee(
    candidate: ExtractionCandidate,
    db: Session,
    *,
    now: datetime,
    summary: EvaluationSummary,
) -> bool:
    """Fuzzy-match an employee candidate against existing rows.

    Called by:    evaluate_for_tenant for each promotable employee.
    Calls into:   _existing_employees, fuzzy_best_match, _emit_event.
    Side effects: on a match, stages a candidate_confirmed event +
                  flips candidate.confirmation_state='confirmed' +
                  bumps last_seen. Caller commits.

    Returns:
        True  - matched an existing employee; state flipped to 'confirmed'.
        False - no match; candidate left in state='none' for the
                evening cron to ask about.
    """
    existing = _existing_employees(db, candidate.tenant_id)
    match = fuzzy_best_match(candidate.normalized_value, existing)
    if match is None:
        return False
    _emit_event(
        db,
        tenant_id=candidate.tenant_id,
        event_type=EVENT_CONFIRMED,
        entity_id=candidate.id,
        payload={
            "candidate_id":         candidate.id,
            "matched_entity_table": "employees",
            "matched_entity_id":    match.matched_id,
            "match_score":          match.score,
            "match_strategy":       match.strategy,
            "decided_by":           "fuzzy_match",
        },
    )
    candidate.last_seen = now
    candidate.confirmation_state = "confirmed"
    summary.confirmed_via_fuzzy += 1
    return True


def _check_fuzzy_machine(
    candidate: ExtractionCandidate,
    db: Session,
    *,
    now: datetime,
    summary: EvaluationSummary,
) -> bool:
    """Fuzzy-match a machine candidate against existing rows.

    Called by:    evaluate_for_tenant for each promotable machine.
    Behaviour:    same as _check_fuzzy_employee, against machines.
    """
    existing = _existing_machines(db, candidate.tenant_id)
    match = fuzzy_best_match(candidate.normalized_value, existing)
    if match is None:
        return False
    _emit_event(
        db,
        tenant_id=candidate.tenant_id,
        event_type=EVENT_CONFIRMED,
        entity_id=candidate.id,
        payload={
            "candidate_id":         candidate.id,
            "matched_entity_table": "machines",
            "matched_entity_id":    match.matched_id,
            "match_score":          match.score,
            "match_strategy":       match.strategy,
            "decided_by":           "fuzzy_match",
        },
    )
    candidate.last_seen = now
    candidate.confirmation_state = "confirmed"
    summary.confirmed_via_fuzzy += 1
    return True


def _skip_customer(
    candidate: ExtractionCandidate,
    db: Session,
    *,
    summary: EvaluationSummary,
) -> None:
    """Emit one candidate_skipped event for a customer candidate, deduped."""
    summary.skipped_no_table += 1
    if _customer_already_skipped(db, candidate.tenant_id, candidate.id):
        return
    _emit_event(
        db,
        tenant_id=candidate.tenant_id,
        event_type=EVENT_SKIPPED,
        entity_id=candidate.id,
        payload={
            "candidate_id":     candidate.id,
            "entity_type":      "customer",
            "reason":           REASON_NO_TABLE,
            "raw_value":        candidate.raw_value,
            "normalized_value": candidate.normalized_value,
            "mention_count":    candidate.mention_count,
            "confidence":       candidate.confidence,
        },
    )


def _skip_over_cap(
    candidate: ExtractionCandidate,
    db: Session,
    *,
    summary: EvaluationSummary,
) -> None:
    """Emit one candidate_skipped event for an over-cap candidate."""
    summary.skipped_cap += 1
    _emit_event(
        db,
        tenant_id=candidate.tenant_id,
        event_type=EVENT_SKIPPED,
        entity_id=candidate.id,
        payload={
            "candidate_id":  candidate.id,
            "entity_type":   candidate.entity_type,
            "reason":        REASON_DAILY_CAP,
            "mention_count": candidate.mention_count,
            "confidence":    candidate.confidence,
        },
    )


def evaluate_for_tenant(
    tenant_id: int,
    db: Session,
    *,
    now: Optional[datetime] = None,
) -> EvaluationSummary:
    """Run the 02:00 IST candidate-evaluation pipeline for one tenant.

    Called by:    evaluate_for_all_tenants (cron path) and direct
                  invocation from tests / smoke scripts.
    Calls into:   is_entity_extraction_enabled, _qualifying_candidates,
                  _check_fuzzy_employee, _check_fuzzy_machine,
                  _skip_customer, _skip_over_cap.
    Side effects:
        - Reads extraction_candidates, employees, machines, events.
        - Stages and COMMITS rows on `db` (one commit per candidate so
          a single bad row cannot poison the rest of the run).
        - Mutates candidate.last_seen + candidate.confirmation_state on
          fuzzy-matched promotable candidates ONLY. NO insertions into
          employees / machines tables on this tick (that's gated on
          owner confirmation in apply_confirmation_decisions).
        - Logs one INFO `evaluation_summary` line at end.

    Args:
        tenant_id: Tenant to run for.
        db:        Sync SQLAlchemy session; this function commits.
        now:       UTC anchor for last_seen bumps. Tests inject a
                   fixed value. Defaults to datetime.now(timezone.utc).

    Returns:
        EvaluationSummary with telemetry. Never raises.

    Idempotency:
        Two consecutive runs against the same data produce the same
        final state. The fuzzy match against existing entities catches
        the same row twice and writes one extra confirmed event on
        each run; the candidate's state stays 'confirmed' so it is
        not re-ranked by the cap.
    """
    summary = EvaluationSummary(tenant_id=tenant_id)
    started = monotonic()
    if now is None:
        now = datetime.now(timezone.utc)

    if not is_entity_extraction_enabled(tenant_id):
        # Q4: extractor-off implies promoter-off. Silent skip.
        summary.duration_ms = int((monotonic() - started) * 1000)
        return summary

    qualifying = _qualifying_candidates(db, tenant_id)
    summary.qualified = len(qualifying)
    if not qualifying:
        summary.duration_ms = int((monotonic() - started) * 1000)
        logger.info(
            "evaluation_summary tenant=%d qualified=0 confirmed_via_fuzzy=0 "
            "ready_for_confirmation=0 skipped_cap=0 skipped_no_table=0 "
            "skipped_other=0 already_asked=0 errors=0 duration_ms=%d",
            tenant_id, summary.duration_ms,
        )
        return summary

    # Bucket by entity_type. Customer is a separate skipped path; only
    # 'employee' and 'machine' are subject to the per-tenant cap.
    promotable: list[ExtractionCandidate] = []
    customers:  list[ExtractionCandidate] = []
    others:     list[ExtractionCandidate] = []
    for c in qualifying:
        if c.entity_type == "customer":
            customers.append(c)
        elif c.entity_type in _PROMOTABLE_ENTITY_TYPES:
            promotable.append(c)
        else:
            others.append(c)

    summary.skipped_other = len(others)

    cap = max(0, int(settings.PROMOTION_DAILY_CAP_PER_TENANT))
    to_process = promotable[:cap]
    over_cap   = promotable[cap:]

    # Customer skips first - cheap, deduped, no commit churn if all
    # already-emitted on prior runs.
    for c in customers:
        try:
            _skip_customer(c, db, summary=summary)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            msg = f"skip_customer_failed tenant={tenant_id} candidate={c.id} err={exc!r}"
            logger.error(msg)
            summary.errors.append(msg)

    for c in over_cap:
        try:
            _skip_over_cap(c, db, summary=summary)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            msg = f"skip_cap_failed tenant={tenant_id} candidate={c.id} err={exc!r}"
            logger.error(msg)
            summary.errors.append(msg)

    for c in to_process:
        try:
            # Q7: candidates already in pending/confirmed/rejected are
            # never re-evaluated. They were either decided already or
            # are mid-conversation with the owner.
            if c.confirmation_state and c.confirmation_state != "none":
                summary.already_asked += 1
                continue

            if c.entity_type == "employee":
                matched = _check_fuzzy_employee(
                    c, db, now=now, summary=summary,
                )
            elif c.entity_type == "machine":
                matched = _check_fuzzy_machine(
                    c, db, now=now, summary=summary,
                )
            else:
                matched = False  # unreachable: bucketing above.

            if not matched:
                # No fuzzy match - this candidate stays in state='none'
                # to be picked up by the 19:00 cron and asked about.
                summary.ready_for_confirmation += 1

            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            msg = (
                f"evaluation_failed tenant={tenant_id} candidate={c.id} "
                f"entity_type={c.entity_type} err={exc!r}"
            )
            logger.error(msg)
            summary.errors.append(msg)

    summary.duration_ms = int((monotonic() - started) * 1000)
    logger.info(
        "evaluation_summary tenant=%d qualified=%d confirmed_via_fuzzy=%d "
        "ready_for_confirmation=%d skipped_cap=%d skipped_no_table=%d "
        "skipped_other=%d already_asked=%d errors=%d duration_ms=%d",
        tenant_id,
        summary.qualified,
        summary.confirmed_via_fuzzy,
        summary.ready_for_confirmation,
        summary.skipped_cap,
        summary.skipped_no_table,
        summary.skipped_other,
        summary.already_asked,
        len(summary.errors),
        summary.duration_ms,
    )
    return summary


# ---------------------------------------------------------------------------
# 19:00 cron - compose_confirmation_for_tenant + record_confirmation_sent
# ---------------------------------------------------------------------------

def _eligible_for_confirmation(
    db: Session, tenant_id: int,
) -> list[ExtractionCandidate]:
    """state='none' promotable candidates above threshold, top-N ordered.

    Called by:    compose_confirmation_for_tenant.
    Calls into:   db.query.
    Side effects: read-only.

    Ordering matches _qualifying_candidates: (mention_count desc,
    confidence desc, id asc). Caller slices to
    settings.PROMOTION_CONFIRMATION_BATCH_SIZE.
    """
    return (
        db.query(ExtractionCandidate)
        .filter(
            ExtractionCandidate.tenant_id == tenant_id,
            ExtractionCandidate.confirmation_state == "none",
            ExtractionCandidate.entity_type.in_(
                list(_PROMOTABLE_ENTITY_TYPES),
            ),
            ExtractionCandidate.mention_count
                >= settings.PROMOTION_MENTION_THRESHOLD,
            ExtractionCandidate.confidence
                >= settings.PROMOTION_CONFIDENCE_THRESHOLD,
        )
        .order_by(
            ExtractionCandidate.mention_count.desc(),
            ExtractionCandidate.confidence.desc(),
            ExtractionCandidate.id.asc(),
        )
        .all()
    )


def compose_confirmation_for_tenant(
    tenant_id: int,
    db: Session,
    *,
    now: Optional[datetime] = None,
) -> Optional[BatchToSend]:
    """Build (and reserve) one tenant's confirmation batch.

    Called by:    send_confirmations_for_tenant (sync per-tenant body
                  inside asyncio.to_thread under the 19:00 IST cron).
                  Also callable directly from tests / smoke scripts.
    Calls into:   _resolve_recipient_phone_mapping,
                  _eligible_for_confirmation,
                  _industry_type_for_tenant,
                  confirmation_composer.compose_message,
                  db.commit.
    Side effects:
        - Reads PhoneTenantMap, Tenant, ExtractionCandidate.
        - On success: flips state='pending' + sets
          confirmation_asked_at=now on each batched candidate; commits.
        - On Q9 hard-fail (no top-tier phone): logs CRITICAL and
          returns None without writing anything.
        - On no-eligible-candidates: returns None without writing
          anything.

    Args:
        tenant_id: Tenant to run for.
        db:        Sync SQLAlchemy session; this function commits.
        now:       UTC anchor for confirmation_asked_at. Defaults to
                   datetime.now(timezone.utc).

    Returns:
        BatchToSend ready for the async wrapper to transmit, or None
        when there is nothing to send.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if not is_entity_extraction_enabled(tenant_id):
        return None

    # Q9 hard-fail check FIRST so we don't waste DB work on a tenant
    # whose data-model writes can't be authorised.
    recipient = _resolve_recipient_phone_mapping(db, tenant_id)
    if recipient is None:
        logger.critical(
            "confirmation_send_skipped_no_top_tier tenant=%d - no active "
            "phone with role in %s; v6.3.15 (revised) refuses to ask a "
            "non-top-tier user about data-model changes. Operator must "
            "link a proprietor / owner / factory_manager / co_owner "
            "phone before this tenant's confirmations can resume.",
            tenant_id, list(TOP_TIER_ROLES),
        )
        return None

    eligible = _eligible_for_confirmation(db, tenant_id)
    if not eligible:
        return None

    cap = max(1, int(settings.PROMOTION_CONFIRMATION_BATCH_SIZE))
    batch = eligible[:cap]

    industry = _industry_type_for_tenant(db, tenant_id)
    composed = compose_message(batch, industry_type=industry)
    if composed is None:
        # All-defensive: composer rejected every candidate (unexpected
        # entity_type sneak-through). Don't reserve, don't send.
        logger.warning(
            "confirmation_compose_empty tenant=%d - composer rendered "
            "no candidates from %d eligible.",
            tenant_id, len(batch),
        )
        return None

    # Reserve: flip state to 'pending' BEFORE the send. If the send
    # later fails, the candidate stays 'pending' until the timeout
    # handler re-asks it 7 days later. Acceptable cost for a robust
    # idempotent state machine (Q7).
    for cand in batch:
        cand.confirmation_state = "pending"
        cand.confirmation_asked_at = now
    db.commit()

    return BatchToSend(
        tenant_id=tenant_id,
        recipient_phone=recipient.phone_number,
        recipient_user_id=int(recipient.user_id),
        message_text=composed.text,
        candidate_ids=composed.candidate_ids,
        candidate_index_map=composed.candidate_index_map,
    )


def record_confirmation_sent(
    db: Session,
    *,
    tenant_id: int,
    candidate_ids: list[int],
    message_id: Optional[str],
    recipient_user_id: int,
) -> None:
    """Update message_id on the just-sent batch + emit requested event.

    Called by:    send_confirmations_for_tenant after the async
                  WhatsApp send returns.
    Calls into:   db.query, _emit_event.
    Side effects:
        - UPDATE extraction_candidates SET confirmation_message_id=?
          WHERE id IN (...) AND tenant_id=?.
        - INSERT one extraction.confirmation_requested event.
        - COMMIT.

    Args:
        message_id: wamid returned by _send_whatsapp_message. May be
                    None when the send failed (mid-2xx parse error or
                    network error). The candidates remain 'pending'
                    either way so the timeout handler can re-ask later.
    """
    if message_id is not None and candidate_ids:
        (
            db.query(ExtractionCandidate)
            .filter(
                ExtractionCandidate.tenant_id == tenant_id,
                ExtractionCandidate.id.in_(candidate_ids),
            )
            .update(
                {ExtractionCandidate.confirmation_message_id: message_id},
                synchronize_session=False,
            )
        )

    _emit_event(
        db,
        tenant_id=tenant_id,
        event_type=EVENT_CONFIRMATION_REQUESTED,
        entity_id=None,
        payload={
            "candidate_ids":     list(candidate_ids),
            "message_id":        message_id,
            "recipient_user_id": recipient_user_id,
            "channel":           "whatsapp",
        },
    )
    db.commit()


# ---------------------------------------------------------------------------
# Reply path - apply_confirmation_decisions
# ---------------------------------------------------------------------------

def find_inflight_batch_for_tenant(
    db: Session, tenant_id: int, *, now: Optional[datetime] = None,
) -> list[ExtractionCandidate]:
    """Return the most recent in-flight pending batch for this tenant.

    Called by:    routers/whatsapp.py Step 2.5 - the new confirmation-
                  reply branch uses this to decide "does this tenant
                  have an open question we sent in the last 48h?"
    Calls into:   db.query.
    Side effects: read-only.

    Returns the candidates from the single most recent batch (grouped
    by confirmation_message_id, max(confirmation_asked_at)). Older
    pending candidates from prior batches are NOT included - they will
    be picked up by the next timeout sweep.

    Empty list when no pending candidates within the in-flight window.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now.replace(microsecond=0)
    from datetime import timedelta as _td
    cutoff = cutoff - _td(hours=INFLIGHT_REPLY_WINDOW_HOURS)

    pending = (
        db.query(ExtractionCandidate)
        .filter(
            ExtractionCandidate.tenant_id == tenant_id,
            ExtractionCandidate.confirmation_state == "pending",
            ExtractionCandidate.confirmation_asked_at.isnot(None),
        )
        .all()
    )

    # Filter on the in-flight window in Python to handle the SQLite
    # naive-datetime test backend (asked_at may have no tz).
    fresh: list[ExtractionCandidate] = []
    for c in pending:
        asked = c.confirmation_asked_at
        if asked is None:
            continue
        if asked.tzinfo is None:
            asked = asked.replace(tzinfo=timezone.utc)
        if asked >= cutoff:
            fresh.append(c)
    if not fresh:
        return []

    # Group by confirmation_message_id; take the group with the latest
    # asked_at. Candidates with NULL message_id (send failed) cluster
    # together under the None key and are returned together.
    fresh.sort(
        key=lambda c: (c.confirmation_asked_at or now),
        reverse=True,
    )
    latest = fresh[0]
    target_msg_id = latest.confirmation_message_id
    target_asked  = latest.confirmation_asked_at

    out: list[ExtractionCandidate] = []
    for c in fresh:
        # Same message id wins primarily; fall back to "asked within 5
        # minutes of the latest" so a single batch isn't fragmented by
        # rounding differences.
        same_msg = (
            target_msg_id is not None
            and c.confirmation_message_id == target_msg_id
        )
        from datetime import timedelta as _td2
        same_burst = (
            target_asked is not None
            and c.confirmation_asked_at is not None
            and abs((c.confirmation_asked_at - target_asked).total_seconds())
                < 5 * 60
        )
        if same_msg or same_burst:
            out.append(c)
    return out


def _insert_confirmed_employee(
    candidate: ExtractionCandidate,
    db: Session,
    *,
    now: datetime,
    message_id: Optional[str],
    decided_by_user_id: int,
) -> None:
    """Insert one Employee row + emit candidate_promoted event.

    Called by:    apply_confirmation_decisions when an owner says HAAN
                  for an employee candidate.
    Calls into:   db.add, db.flush, _emit_event.
    Side effects: stages an INSERT on employees + a candidate_promoted
                  event; mutates candidate.confirmation_state='confirmed',
                  candidate.last_seen=now. Caller commits.
    """
    new_emp = Employee(
        tenant_id=candidate.tenant_id,
        full_name=candidate.raw_value,
        source=_INFERRED_SOURCE,
        worker_type=_DEFAULT_WORKER_TYPE,
    )
    db.add(new_emp)
    db.flush()  # populate new_emp.id for the audit payload
    _emit_event(
        db,
        tenant_id=candidate.tenant_id,
        event_type=EVENT_PROMOTED,
        entity_id=candidate.id,
        actor_user_id=decided_by_user_id,
        payload={
            "candidate_id":             candidate.id,
            "entity_type":              "employee",
            "raw_value":                candidate.raw_value,
            "normalized_value":         candidate.normalized_value,
            "mention_count":            candidate.mention_count,
            "confidence":               candidate.confidence,
            "promoted_to_table":        "employees",
            "promoted_to_id":           new_emp.id,
            "source_value_used":        _INFERRED_SOURCE,
            # Q10 augmentation - audit chain link from message -> insert.
            "confirmation_message_id":  message_id,
            "decided_by_user_id":       decided_by_user_id,
        },
    )
    candidate.last_seen = now
    candidate.confirmation_state = "confirmed"


def _insert_confirmed_machine(
    candidate: ExtractionCandidate,
    db: Session,
    *,
    now: datetime,
    message_id: Optional[str],
    decided_by_user_id: int,
) -> None:
    """Insert one Machine row + emit candidate_promoted event."""
    new_mach = Machine(
        tenant_id=candidate.tenant_id,
        name=candidate.raw_value,
        source=_INFERRED_SOURCE,
        # machine_type is nullable; left NULL for owner correction.
    )
    db.add(new_mach)
    db.flush()
    _emit_event(
        db,
        tenant_id=candidate.tenant_id,
        event_type=EVENT_PROMOTED,
        entity_id=candidate.id,
        actor_user_id=decided_by_user_id,
        payload={
            "candidate_id":             candidate.id,
            "entity_type":              "machine",
            "raw_value":                candidate.raw_value,
            "normalized_value":         candidate.normalized_value,
            "mention_count":            candidate.mention_count,
            "confidence":               candidate.confidence,
            "promoted_to_table":        "machines",
            "promoted_to_id":           new_mach.id,
            "source_value_used":        _INFERRED_SOURCE,
            "confirmation_message_id":  message_id,
            "decided_by_user_id":       decided_by_user_id,
        },
    )
    candidate.last_seen = now
    candidate.confirmation_state = "confirmed"


def apply_confirmation_decisions(
    tenant_id: int,
    db: Session,
    *,
    decisions: dict[int, str],
    message_id: Optional[str],
    decided_by_user_id: int,
    parse_strategy: str,
    raw_reply: str,
    now: Optional[datetime] = None,
) -> ApplyConfirmationsSummary:
    """Apply per-candidate decisions from a parsed owner reply.

    Called by:    routers/whatsapp.py Step 2.5 confirmation-reply branch.
    Calls into:   _insert_confirmed_employee / _machine, _emit_event.
    Side effects:
        - For each 'confirmed' decision: INSERT employees/machines +
          candidate_promoted event + state='confirmed'. Per-candidate
          commit so a single bad row does not block the rest.
        - For each 'rejected' decision: state='rejected'. No insert.
          No standalone event - the aggregate confirmation_received
          event below carries the full decision dict.
        - For each 'deferred' decision: leave state='pending'. The
          timeout handler re-asks in
          PROMOTION_CONFIRMATION_TIMEOUT_DAYS days.
        - One aggregate extraction.confirmation_received event with
          the full decision dict + parse strategy + raw reply text.

    Args:
        decisions:           candidate_id -> 'confirmed'|'rejected'|'deferred'.
                             Only ids in state='pending' are acted on;
                             ids referencing already-decided candidates
                             are counted as not_found and skipped.
        message_id:          The wamid the reply is responding to. May
                             be None when the original send failed.
        decided_by_user_id:  user_id of the phone that REPLIED.
        parse_strategy:      'heuristic' | 'llm' | 'fallback' from the
                             reply parser. Stored in the audit event.
        raw_reply:           Owner's exact (lowercased + stripped)
                             reply text. Stored for human review.

    Returns:
        ApplyConfirmationsSummary with telemetry. Never raises.
    """
    summary = ApplyConfirmationsSummary(tenant_id=tenant_id)
    if now is None:
        now = datetime.now(timezone.utc)

    # Pull the candidates referenced by the decisions in one shot.
    cand_ids = list(decisions.keys())
    if not cand_ids:
        return summary
    rows = (
        db.query(ExtractionCandidate)
        .filter(
            ExtractionCandidate.tenant_id == tenant_id,
            ExtractionCandidate.id.in_(cand_ids),
        )
        .all()
    )
    by_id = {int(c.id): c for c in rows}

    for cid, verdict in decisions.items():
        cand = by_id.get(int(cid))
        if cand is None or cand.confirmation_state != "pending":
            summary.not_found += 1
            continue
        try:
            if verdict == "confirmed":
                if cand.entity_type == "employee":
                    _insert_confirmed_employee(
                        cand, db,
                        now=now,
                        message_id=message_id,
                        decided_by_user_id=decided_by_user_id,
                    )
                elif cand.entity_type == "machine":
                    _insert_confirmed_machine(
                        cand, db,
                        now=now,
                        message_id=message_id,
                        decided_by_user_id=decided_by_user_id,
                    )
                else:
                    # Defensive - composer should have filtered these out.
                    cand.confirmation_state = "rejected"
                    summary.rejected += 1
                    continue
                summary.confirmed_inserted += 1

            elif verdict == "rejected":
                cand.confirmation_state = "rejected"
                summary.rejected += 1

            elif verdict == "deferred":
                # Leave state='pending'. Timeout handler re-asks later.
                summary.deferred += 1

            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            msg = (
                f"apply_failed tenant={tenant_id} candidate={cand.id} "
                f"verdict={verdict} err={exc!r}"
            )
            logger.error(msg)
            summary.errors.append(msg)

    # Aggregate received event - one row per reply, regardless of how
    # many candidates were decided. Per Q10.
    try:
        _emit_event(
            db,
            tenant_id=tenant_id,
            event_type=EVENT_CONFIRMATION_RECEIVED,
            entity_id=None,
            actor_user_id=decided_by_user_id,
            payload={
                "message_id":     message_id,
                "reply_text":     raw_reply,
                "parse_strategy": parse_strategy,
                "decisions":      {str(k): v for k, v in decisions.items()},
            },
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        msg = (
            f"apply_received_event_failed tenant={tenant_id} "
            f"message_id={message_id!r} err={exc!r}"
        )
        logger.error(msg)
        summary.errors.append(msg)

    logger.info(
        "apply_confirmations_summary tenant=%d confirmed=%d rejected=%d "
        "deferred=%d not_found=%d errors=%d strategy=%s",
        tenant_id,
        summary.confirmed_inserted,
        summary.rejected,
        summary.deferred,
        summary.not_found,
        len(summary.errors),
        parse_strategy,
    )
    return summary


# ---------------------------------------------------------------------------
# APScheduler entry points (async fan-out wrappers)
# ---------------------------------------------------------------------------

def _run_one_evaluation_sync(
    tenant_id: int,
    session_factory: Callable[[], Session],
) -> EvaluationSummary:
    """Sync wrapper that opens / closes its own session.

    Called by:    evaluate_for_all_tenants - wrapped in
                  asyncio.to_thread + asyncio.wait_for so each tenant
                  has a hard wall-clock budget.
    Side effects: opens, uses, closes one DB session.
    """
    db = session_factory()
    try:
        return evaluate_for_tenant(tenant_id, db)
    finally:
        db.close()


async def evaluate_for_all_tenants(
    *,
    session_factory: Optional[Callable[[], Session]] = None,
    per_tenant_timeout_s: float = 60.0,
) -> dict:
    """02:00 IST APScheduler entry point. Replaces the original
    promote_for_all_tenants.

    Called by:    app/services/whatsapp_alerts.py
                  start_scheduler() registers this on a CronTrigger
                  (hour=2, minute=0, timezone='Asia/Kolkata') with
                  coalesce=True, max_instances=1.
    Calls into:   _enabled_tenant_ids, asyncio.wait_for,
                  asyncio.to_thread, _run_one_evaluation_sync.
    Side effects: one DB session per tenant; per-tenant log line via
                  evaluate_for_tenant; aggregate INFO line at end.

    Returns:
        Aggregate dict {tenants_processed, confirmed_via_fuzzy,
        ready_for_confirmation, skipped_cap, skipped_no_table,
        skipped_other, already_asked, errors, timeouts}. Returned for
        tests; APScheduler ignores the value.

    Failure semantics:
        Per-tenant timeout / exception caught, logged, next tenant
        runs. Never raises into APScheduler.
    """
    if session_factory is None:
        from app.database import SessionLocal  # late import - cycle guard
        session_factory = SessionLocal

    enabled = sorted(_enabled_tenant_ids())
    aggregate: dict[str, int] = {
        "tenants_processed":      0,
        "confirmed_via_fuzzy":    0,
        "ready_for_confirmation": 0,
        "skipped_cap":            0,
        "skipped_no_table":       0,
        "skipped_other":          0,
        "already_asked":          0,
        "errors":                 0,
        "timeouts":               0,
    }
    if not enabled:
        logger.info(
            "evaluation_run_summary tenants=0 (ENTITY_EXTRACTION_TENANT_IDS empty)",
        )
        return aggregate

    for tenant_id in enabled:
        aggregate["tenants_processed"] += 1
        try:
            summary = await asyncio.wait_for(
                asyncio.to_thread(
                    _run_one_evaluation_sync, tenant_id, session_factory,
                ),
                timeout=per_tenant_timeout_s,
            )
            aggregate["confirmed_via_fuzzy"]    += summary.confirmed_via_fuzzy
            aggregate["ready_for_confirmation"] += summary.ready_for_confirmation
            aggregate["skipped_cap"]            += summary.skipped_cap
            aggregate["skipped_no_table"]       += summary.skipped_no_table
            aggregate["skipped_other"]          += summary.skipped_other
            aggregate["already_asked"]          += summary.already_asked
            aggregate["errors"]                 += len(summary.errors)
        except asyncio.TimeoutError:
            aggregate["timeouts"] += 1
            logger.error(
                "evaluation_timeout tenant=%d after %.1fs",
                tenant_id, per_tenant_timeout_s,
            )
        except Exception:
            aggregate["errors"] += 1
            logger.exception(
                "evaluation_failed tenant=%d", tenant_id,
            )

    logger.info(
        "evaluation_run_summary tenants=%d confirmed_via_fuzzy=%d "
        "ready_for_confirmation=%d skipped_cap=%d skipped_no_table=%d "
        "skipped_other=%d already_asked=%d errors=%d timeouts=%d",
        aggregate["tenants_processed"],
        aggregate["confirmed_via_fuzzy"],
        aggregate["ready_for_confirmation"],
        aggregate["skipped_cap"],
        aggregate["skipped_no_table"],
        aggregate["skipped_other"],
        aggregate["already_asked"],
        aggregate["errors"],
        aggregate["timeouts"],
    )
    return aggregate


def _send_one_tenant_compose_sync(
    tenant_id: int,
    session_factory: Callable[[], Session],
) -> Optional[BatchToSend]:
    """Sync wrapper: timeout sweep + compose+reserve, returns BatchToSend.

    Called by:    send_confirmations_for_all_tenants inside
                  asyncio.to_thread.
    Side effects: opens / closes one DB session. Commits per-candidate
                  in process_timeouts_for_tenant + commits the batch
                  reservation in compose_confirmation_for_tenant.
    """
    db = session_factory()
    try:
        process_timeouts_for_tenant(tenant_id, db)
        return compose_confirmation_for_tenant(tenant_id, db)
    finally:
        db.close()


def _record_sent_sync(
    tenant_id: int,
    session_factory: Callable[[], Session],
    *,
    candidate_ids: list[int],
    message_id: Optional[str],
    recipient_user_id: int,
) -> None:
    """Sync wrapper: write the message_id back + emit requested event.

    Called by:    send_confirmations_for_all_tenants inside
                  asyncio.to_thread, after the WhatsApp send completes.
    """
    db = session_factory()
    try:
        record_confirmation_sent(
            db,
            tenant_id=tenant_id,
            candidate_ids=candidate_ids,
            message_id=message_id,
            recipient_user_id=recipient_user_id,
        )
    finally:
        db.close()


async def send_confirmations_for_all_tenants(
    *,
    session_factory: Optional[Callable[[], Session]] = None,
    per_tenant_timeout_s: float = 60.0,
    sender=None,
) -> dict:
    """19:00 IST APScheduler entry point. Composes + sends + records
    confirmation messages for every enabled tenant.

    Called by:    app/services/whatsapp_alerts.py
                  start_scheduler() registers this on a CronTrigger
                  (hour=PROMOTION_CONFIRMATION_HOUR_IST,
                   minute=PROMOTION_CONFIRMATION_MINUTE_IST,
                   timezone='Asia/Kolkata') with coalesce=True,
                  max_instances=1.
    Calls into:   _enabled_tenant_ids, asyncio.to_thread,
                  _send_one_tenant_compose_sync,
                  _send_whatsapp_message (or `sender` test seam),
                  _record_sent_sync.
    Side effects: per-tenant DB writes (state flips, event row);
                  one outbound WhatsApp message per tenant with
                  eligible candidates.

    Args:
        sender: Optional async test seam with the same signature as
                _send_whatsapp_message (phone, message) -> Optional[str].
                None -> we import the real one.

    Returns:
        Aggregate dict {tenants_processed, batches_sent, candidates_asked,
        skipped_no_top_tier, skipped_no_eligible, send_failures, errors,
        timeouts}.

    Failure semantics:
        Per-tenant timeout / exception caught, logged, next tenant runs.
        Send failures leave the batch 'pending' without a message_id;
        timeout handler re-asks in 7 days.
    """
    if session_factory is None:
        from app.database import SessionLocal
        session_factory = SessionLocal

    if sender is None:
        from app.services.whatsapp_send import _send_whatsapp_message
        sender = _send_whatsapp_message

    enabled = sorted(_enabled_tenant_ids())
    aggregate: dict[str, int] = {
        "tenants_processed":   0,
        "batches_sent":        0,
        "candidates_asked":    0,
        "skipped_no_top_tier": 0,
        "skipped_no_eligible": 0,
        "send_failures":       0,
        "errors":              0,
        "timeouts":            0,
    }
    if not enabled:
        logger.info(
            "confirmation_run_summary tenants=0 (ENTITY_EXTRACTION_TENANT_IDS empty)",
        )
        return aggregate

    for tenant_id in enabled:
        aggregate["tenants_processed"] += 1
        try:
            batch: Optional[BatchToSend] = await asyncio.wait_for(
                asyncio.to_thread(
                    _send_one_tenant_compose_sync,
                    tenant_id, session_factory,
                ),
                timeout=per_tenant_timeout_s,
            )
            if batch is None:
                # Either no top-tier phone (Q9 hard-fail logged inside
                # compose_confirmation_for_tenant) or no eligible
                # candidates. Distinguish in the aggregate by
                # re-checking the reason cheaply.
                # Cheapest approach: read PhoneTenantMap once more.
                check_db = session_factory()
                try:
                    rec = _resolve_recipient_phone_mapping(
                        check_db, tenant_id,
                    )
                finally:
                    check_db.close()
                if rec is None:
                    aggregate["skipped_no_top_tier"] += 1
                else:
                    aggregate["skipped_no_eligible"] += 1
                continue

            wamid = await sender(batch.recipient_phone, batch.message_text)
            if wamid is None:
                aggregate["send_failures"] += 1
                logger.error(
                    "confirmation_send_failed tenant=%d - WhatsApp "
                    "send returned None; %d candidates remain pending "
                    "without message_id and will be re-asked after the "
                    "timeout window.",
                    tenant_id, len(batch.candidate_ids),
                )
                # Still record the requested event so audit trail shows
                # the attempt; message_id=None.
                await asyncio.to_thread(
                    _record_sent_sync,
                    tenant_id, session_factory,
                    candidate_ids=batch.candidate_ids,
                    message_id=None,
                    recipient_user_id=batch.recipient_user_id,
                )
                continue

            await asyncio.to_thread(
                _record_sent_sync,
                tenant_id, session_factory,
                candidate_ids=batch.candidate_ids,
                message_id=wamid,
                recipient_user_id=batch.recipient_user_id,
            )
            aggregate["batches_sent"]    += 1
            aggregate["candidates_asked"] += len(batch.candidate_ids)

        except asyncio.TimeoutError:
            aggregate["timeouts"] += 1
            logger.error(
                "confirmation_timeout tenant=%d after %.1fs",
                tenant_id, per_tenant_timeout_s,
            )
        except Exception:
            aggregate["errors"] += 1
            logger.exception(
                "confirmation_failed tenant=%d", tenant_id,
            )

    logger.info(
        "confirmation_run_summary tenants=%d batches_sent=%d "
        "candidates_asked=%d skipped_no_top_tier=%d "
        "skipped_no_eligible=%d send_failures=%d errors=%d timeouts=%d",
        aggregate["tenants_processed"],
        aggregate["batches_sent"],
        aggregate["candidates_asked"],
        aggregate["skipped_no_top_tier"],
        aggregate["skipped_no_eligible"],
        aggregate["send_failures"],
        aggregate["errors"],
        aggregate["timeouts"],
    )
    return aggregate
