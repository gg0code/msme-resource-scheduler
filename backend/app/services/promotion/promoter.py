# app/services/promotion/promoter.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.15 candidate-promotion service. Reads from extraction_candidates
# (written by the v6.3.14 entity extractor) and materialises high-
# confidence, frequently-mentioned candidates into the canonical
# employees / machines tables. Runs nightly at 02:00 IST via the
# existing AsyncIOScheduler in app/services/whatsapp_alerts.py.
#
# CUSTOMER PROMOTION IS OUT OF SCOPE AT v6.3.15
# There is no `customers` table in the v6.3.x schema (only the free-text
# Job.customer label column). Candidates with entity_type='customer'
# are NOT inserted anywhere; instead, the promoter writes one
# `extraction.candidate_skipped` audit event per qualifying customer
# candidate with reason="customer_table_not_yet_implemented" so a
# log-grep across the events table will surface the deferred backlog
# when a customers table eventually lands. Per-candidate dedupe is
# applied so we don't emit the same skipped event every nightly run.
#
# WHO CALLS THIS FILE
# - app/services/whatsapp_alerts.py — start_scheduler() registers
#   `promote_for_all_tenants` on the existing AsyncIOScheduler at
#   02:00 IST nightly (Job 7).
# - app/services/promotion/__init__.py — re-exports the public surface.
# - backend/inspect_extractions.py — uses the EVENT_* constants when
#   rendering --show-promotions output.
# - backend/tests/services/test_promotion_promoter.py — direct unit
#   tests against promote_for_tenant with stub data.
#
# WHAT THIS FILE CALLS
# - app/services/extraction/feature_flag.is_entity_extraction_enabled
#   and ._enabled_tenant_ids — Q4 reuses extractor's tenant scope so a
#   parallel parser cannot drift. The private import is the single
#   carefully-documented breach of the underscore convention.
# - app/services/promotion/fuzzy_match.fuzzy_best_match — string-
#   similarity helper that powers idempotency (Q9).
# - app/models.{employee.Employee, machine.Machine,
#   extraction_candidate.ExtractionCandidate, event.Event}.
# - app/database.SessionLocal — promote_for_all_tenants opens its own
#   short-lived session per tenant; promote_for_tenant takes one in.
# - app/config.settings — PROMOTION_* thresholds + cap.
#
# DESIGN NOTES (Q1–Q10 from the discovery doc)
# - Q1 / fuzzy strategy: hybrid via fuzzy_match.fuzzy_best_match.
# - Q2 / on-match: write candidate_confirmed event + bump candidate
#   last_seen=now. NEVER mutate the matched canonical entity row.
# - Q3 / thresholds: read from settings, defaults in code.
# - Q4 / tenant scope: reuse ENTITY_EXTRACTION_TENANT_IDS (no
#   separate flag).
# - Q5 / per-tenant daily cap: top-N by (mention_count desc,
#   confidence desc, id asc) — deterministic.
# - Q6 / insert shape: source='whatsapp_inferred' (Conflict-1, accepted
#   resolution b — VALID_SOURCE_VALUES extended), worker_type='permanent'
#   default for employees, machine_type left NULL.
# - Q6b / customer skipped: see "CUSTOMER PROMOTION IS OUT OF SCOPE"
#   block above.
# - Q7 / event payloads: see EVENT_* constants and emit_* helpers.
# - Q8 / scheduling: 02:00 IST, coalesce, max_instances=1, 60s timeout
#   per tenant via asyncio.wait_for + asyncio.to_thread.
# - Q9 / idempotency: NO new column. The fuzzy match against existing
#   entities catches the just-inserted row on the second run and writes
#   a `confirmed` event instead of inserting a duplicate.
#   KNOWN EDGE CASE: if the owner renames the just-inserted entity by
#   more than the fuzzy threshold tolerates within 24h (e.g.
#   "Suresh" → "S. Kumar"), the next nightly run treats the candidate
#   as new and inserts a duplicate. Acceptable risk per Q9; daily cap
#   bounds the blast radius.
# - Q10 / observability: structured INFO `promotion_summary` log line
#   per (tenant, run); --show-promotions flag on inspect_extractions.py.
#
# FAILURE SEMANTICS
# - Per-candidate failure (insert/event commit blows up): rolled back
#   for that candidate, logged with structured context, summary.errors
#   gets one entry, the loop continues with the next candidate.
# - Per-tenant failure (timeout / unexpected exception): caught in
#   promote_for_all_tenants, logged with tenant_id, the next tenant
#   still runs.
# - The promoter NEVER raises into APScheduler. The scheduler tick
#   may complete with summary.errors populated; that is a normal
#   degraded outcome, not a crash.

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.employee import Employee
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate
from app.models.machine import Machine
from app.services.extraction.feature_flag import (  # type: ignore[reportPrivateUsage]
    _enabled_tenant_ids,
    is_entity_extraction_enabled,
)
from app.services.promotion.fuzzy_match import fuzzy_best_match

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit-event vocabulary — all `extraction.*` to match the v6.3.4
# `briefing.*` precedent (one dotted namespace per subsystem).
# ---------------------------------------------------------------------------

EVENT_PROMOTED:  str = "extraction.candidate_promoted"
EVENT_CONFIRMED: str = "extraction.candidate_confirmed"
EVENT_SKIPPED:   str = "extraction.candidate_skipped"

# Polymorphic entity_type written into Event rows. Always paired with
# entity_id = candidate.id so audit records dereference back to the
# staging row.
_EVENT_ENTITY_TYPE: str = "extraction_candidate"

# Skip reasons — written into Event.payload['reason'] and used by the
# inspection script to bucket counts.
REASON_DAILY_CAP: str = "daily_cap_reached"
REASON_NO_TABLE:  str = "customer_table_not_yet_implemented"

# Entity types we promote into real tables at v6.3.15.
_PROMOTABLE_ENTITY_TYPES: frozenset[str] = frozenset({"employee", "machine"})

# Source value stamped on inserted rows (Conflict-1 / Q6a resolution b).
_INFERRED_SOURCE: str = "whatsapp_inferred"

# Default for employee.worker_type on inserted rows (Q6c).
_DEFAULT_WORKER_TYPE: str = "permanent"


# ---------------------------------------------------------------------------
# Telemetry shape
# ---------------------------------------------------------------------------

@dataclass
class PromotionSummary:
    """Per-(tenant, run) outcome.

    Used by:    promote_for_tenant return; promote_for_all_tenants
                aggregates these into a dict.
    Logged at:  INFO level as the `promotion_summary` line per Q10.
    Fields:
        tenant_id:        Tenant the run targeted.
        qualified:        Total candidates above (mention, confidence)
                          thresholds, regardless of entity_type.
        promoted:         New canonical rows inserted (employee+machine).
        confirmed:        Fuzzy-matched against an existing entity.
        skipped_cap:      Promotable candidates beyond the daily cap.
        skipped_no_table: Customer candidates skipped (Q6b).
        skipped_other:    Qualifying candidates whose entity_type is
                          neither promotable nor explicitly skipped
                          (e.g. 'skill', 'material', 'job', 'issue' at
                          v6.3.15). No event written for these — they
                          remain in the staging table for future
                          versions to consume.
        duration_ms:      Wall-clock for the run.
        errors:           Per-candidate error strings; not raised.
    """
    tenant_id:        int
    qualified:        int = 0
    promoted:         int = 0
    confirmed:        int = 0
    skipped_cap:      int = 0
    skipped_no_table: int = 0
    skipped_other:    int = 0
    duration_ms:      int = 0
    errors:           list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers — small, side-effect-free (or single-side-effect) functions.
# ---------------------------------------------------------------------------

def _qualifying_candidates(
    db: Session, tenant_id: int,
) -> list[ExtractionCandidate]:
    """Threshold-filtered + ranked candidates for one tenant.

    Called by:    promote_for_tenant.
    Calls into:   db.query.
    Side effects: read-only.
    Returns:      Candidates with mention_count >= threshold AND
                  confidence >= threshold, ordered by mention_count
                  desc, confidence desc, id asc (deterministic).
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
    """Tenant's current employees as (id, full_name) pairs.

    Called by:    _promote_or_confirm_employee.
    Calls into:   db.query.
    Side effects: read-only.
    """
    rows = (
        db.query(Employee.id, Employee.full_name)
        .filter(Employee.tenant_id == tenant_id)
        .all()
    )
    return [(int(r[0]), str(r[1] or "")) for r in rows]


def _existing_machines(
    db: Session, tenant_id: int,
) -> list[tuple[int, str]]:
    """Tenant's current machines as (id, name) pairs.

    Called by:    _promote_or_confirm_machine.
    Calls into:   db.query.
    Side effects: read-only.
    """
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

    Called by:    _skip_customer (dedupe).
    Calls into:   db.query.
    Side effects: read-only.

    Why: customer candidates persist in the staging table run-over-run
    while there is no customers table. Without dedupe, the events
    table would gain a duplicate row every night for every qualifying
    customer. Dedupe by (tenant_id, event_type, entity_id).
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


def _emit_event(
    db: Session,
    *,
    tenant_id: int,
    event_type: str,
    entity_id: int,
    payload: dict,
) -> None:
    """Stage one Event row. Caller commits.

    Called by:    every promote/confirm/skip helper below.
    Calls into:   db.add.
    Side effects: stages an INSERT on events. No flush, no commit.

    Convention matches v6.3.4 dispatcher:
      - entity_type = 'extraction_candidate'
      - entity_id   = candidate.id
      - source      = 'system'
      - actor_user_id = None (cron-triggered).
    """
    db.add(Event(
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type=_EVENT_ENTITY_TYPE,
        entity_id=entity_id,
        actor_user_id=None,
        source="system",
        payload=payload,
    ))


# ---------------------------------------------------------------------------
# Per-candidate dispatchers
# ---------------------------------------------------------------------------

def _promote_or_confirm_employee(
    candidate: ExtractionCandidate,
    db: Session,
    *,
    now: datetime,
    summary: PromotionSummary,
) -> None:
    """Insert or confirm a single employee candidate.

    Called by:    promote_for_tenant for each promotable employee.
    Calls into:   _existing_employees, fuzzy_best_match, _emit_event.
    Side effects: stages an INSERT on employees + events; mutates
                  candidate.last_seen. Caller commits.
    """
    existing = _existing_employees(db, candidate.tenant_id)
    match = fuzzy_best_match(candidate.normalized_value, existing)
    if match is not None:
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
            },
        )
        candidate.last_seen = now
        summary.confirmed += 1
        return

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
        payload={
            "candidate_id":      candidate.id,
            "entity_type":       "employee",
            "raw_value":         candidate.raw_value,
            "normalized_value":  candidate.normalized_value,
            "mention_count":     candidate.mention_count,
            "confidence":        candidate.confidence,
            "promoted_to_table": "employees",
            "promoted_to_id":    new_emp.id,
            "source_value_used": _INFERRED_SOURCE,
        },
    )
    candidate.last_seen = now
    summary.promoted += 1


def _promote_or_confirm_machine(
    candidate: ExtractionCandidate,
    db: Session,
    *,
    now: datetime,
    summary: PromotionSummary,
) -> None:
    """Insert or confirm a single machine candidate.

    Called by:    promote_for_tenant for each promotable machine.
    Calls into:   _existing_machines, fuzzy_best_match, _emit_event.
    Side effects: stages an INSERT on machines + events; mutates
                  candidate.last_seen. Caller commits.
    """
    existing = _existing_machines(db, candidate.tenant_id)
    match = fuzzy_best_match(candidate.normalized_value, existing)
    if match is not None:
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
            },
        )
        candidate.last_seen = now
        summary.confirmed += 1
        return

    new_mach = Machine(
        tenant_id=candidate.tenant_id,
        name=candidate.raw_value,
        source=_INFERRED_SOURCE,
        # machine_type is nullable; left NULL for owner correction (Q6).
    )
    db.add(new_mach)
    db.flush()
    _emit_event(
        db,
        tenant_id=candidate.tenant_id,
        event_type=EVENT_PROMOTED,
        entity_id=candidate.id,
        payload={
            "candidate_id":      candidate.id,
            "entity_type":       "machine",
            "raw_value":         candidate.raw_value,
            "normalized_value":  candidate.normalized_value,
            "mention_count":     candidate.mention_count,
            "confidence":        candidate.confidence,
            "promoted_to_table": "machines",
            "promoted_to_id":    new_mach.id,
            "source_value_used": _INFERRED_SOURCE,
        },
    )
    candidate.last_seen = now
    summary.promoted += 1


def _skip_customer(
    candidate: ExtractionCandidate,
    db: Session,
    *,
    summary: PromotionSummary,
) -> None:
    """Emit one candidate_skipped event for a customer candidate, deduped.

    Called by:    promote_for_tenant for each qualifying customer.
    Calls into:   _customer_already_skipped, _emit_event.
    Side effects: may stage an INSERT on events. Caller commits.

    Per Q6b: the customer candidate stays in the staging table; no
    canonical insert. The skipped event makes the deferred backlog
    grep-able when a customers table eventually lands.
    """
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
    summary: PromotionSummary,
) -> None:
    """Emit one candidate_skipped event for an over-cap candidate.

    Called by:    promote_for_tenant when the per-tenant daily cap is
                  exhausted. Tomorrow's run will re-evaluate the same
                  candidate with the same counts and may promote it.
    Calls into:   _emit_event.
    Side effects: stages an INSERT on events. Caller commits.

    No dedupe: the cap log entry is per-run and per-candidate is fine
    because the cap rarely engages once steady state is reached.
    """
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


# ---------------------------------------------------------------------------
# Public entry — per tenant
# ---------------------------------------------------------------------------

def promote_for_tenant(
    tenant_id: int,
    db: Session,
    *,
    now: Optional[datetime] = None,
) -> PromotionSummary:
    """Run the candidate-promotion pipeline for a single tenant.

    Called by:    promote_for_all_tenants (cron path) and direct
                  invocation from tests / smoke scripts.
    Calls into:   is_entity_extraction_enabled, _qualifying_candidates,
                  _promote_or_confirm_employee, _promote_or_confirm_machine,
                  _skip_customer, _skip_over_cap.
    Side effects:
        - Reads extraction_candidates, employees, machines, events.
        - Stages and COMMITS rows on `db` (one commit per candidate so
          a single bad row cannot poison the rest of the run).
        - Mutates candidate.last_seen on every successful promote/confirm.
        - Logs one INFO `promotion_summary` line at end.

    Args:
        tenant_id: Tenant to run for.
        db:        Sync SQLAlchemy session. THIS function commits per
                   candidate; callers should not nest a transaction.
        now:       UTC anchor for last_seen bumps. Tests inject a
                   fixed value for deterministic assertions. Defaults
                   to datetime.now(timezone.utc).

    Returns:
        PromotionSummary with telemetry. Never raises — every failure
        is caught, logged, and recorded in summary.errors.

    Idempotency:
        Two consecutive runs against the same data produce the same
        final state: the second run fuzzy-matches the freshly-inserted
        entity from the first run and writes a `confirmed` event
        rather than inserting a duplicate. Documented edge case: if
        the owner renames a just-inserted entity by more than the
        fuzzy threshold tolerates within 24h, the next run will
        treat the candidate as new and insert a duplicate.

    Cap behaviour:
        Promotable candidates beyond settings.PROMOTION_DAILY_CAP_PER_TENANT
        are NOT promoted on this run. Each writes a `candidate_skipped`
        event with reason='daily_cap_reached'. The candidates remain
        in extraction_candidates with their counts intact, so they
        will qualify and likely promote on the next nightly run.
    """
    summary = PromotionSummary(tenant_id=tenant_id)
    started = monotonic()
    if now is None:
        now = datetime.now(timezone.utc)

    if not is_entity_extraction_enabled(tenant_id):
        # Q4: extractor-off implies promoter-off. Zero work, zero log
        # (matches the v6.3.4 'disabled' precedent — silent skip to
        # avoid flooding logs across many disabled tenants).
        summary.duration_ms = int((monotonic() - started) * 1000)
        return summary

    qualifying = _qualifying_candidates(db, tenant_id)
    summary.qualified = len(qualifying)
    if not qualifying:
        summary.duration_ms = int((monotonic() - started) * 1000)
        logger.info(
            "promotion_summary tenant=%d qualified=0 promoted=0 "
            "confirmed=0 skipped_cap=0 skipped_no_table=0 "
            "skipped_other=0 errors=0 duration_ms=%d",
            tenant_id, summary.duration_ms,
        )
        return summary

    # Bucket by entity_type. Customer is a separate skipped path; only
    # 'employee' and 'machine' are subject to the per-tenant cap (Q5).
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

    # Customer skips first — cheap, deduped, no commit churn if all
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
            if c.entity_type == "employee":
                _promote_or_confirm_employee(
                    c, db, now=now, summary=summary,
                )
            elif c.entity_type == "machine":
                _promote_or_confirm_machine(
                    c, db, now=now, summary=summary,
                )
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            msg = (
                f"promote_failed tenant={tenant_id} candidate={c.id} "
                f"entity_type={c.entity_type} err={exc!r}"
            )
            logger.error(msg)
            summary.errors.append(msg)

    summary.duration_ms = int((monotonic() - started) * 1000)
    logger.info(
        "promotion_summary tenant=%d qualified=%d promoted=%d "
        "confirmed=%d skipped_cap=%d skipped_no_table=%d "
        "skipped_other=%d errors=%d duration_ms=%d",
        tenant_id,
        summary.qualified,
        summary.promoted,
        summary.confirmed,
        summary.skipped_cap,
        summary.skipped_no_table,
        summary.skipped_other,
        len(summary.errors),
        summary.duration_ms,
    )
    return summary


# ---------------------------------------------------------------------------
# Public entry — APScheduler tick
# ---------------------------------------------------------------------------

def _run_one_tenant_sync(
    tenant_id: int,
    session_factory: Callable[[], Session],
) -> PromotionSummary:
    """Sync wrapper that opens / closes its own session.

    Called by:    promote_for_all_tenants — wrapped in
                  asyncio.to_thread + asyncio.wait_for so each tenant
                  has a hard 60s wall-clock budget.
    Calls into:   session_factory, promote_for_tenant.
    Side effects: opens, uses, closes one DB session.
    """
    db = session_factory()
    try:
        return promote_for_tenant(tenant_id, db)
    finally:
        db.close()


async def promote_for_all_tenants(
    *,
    session_factory: Optional[Callable[[], Session]] = None,
    per_tenant_timeout_s: float = 60.0,
) -> dict:
    """APScheduler entry point — fan out across enabled tenants.

    Called by:    app/services/whatsapp_alerts.py
                  start_scheduler() registers this on a CronTrigger
                  (hour=2, minute=0, timezone='Asia/Kolkata') with
                  coalesce=True, max_instances=1.
    Calls into:   _enabled_tenant_ids, asyncio.wait_for,
                  asyncio.to_thread, _run_one_tenant_sync.
    Side effects: one DB session per tenant; emits per-tenant log line
                  via promote_for_tenant; emits an aggregate INFO line
                  at the end.

    Args:
        session_factory:      Optional zero-arg callable returning a
                              Session. Defaults to app.database.SessionLocal
                              (late-imported to avoid an import cycle
                              with app.main at module load).
        per_tenant_timeout_s: Hard wall-clock budget per tenant. The
                              sync body runs in a worker thread via
                              asyncio.to_thread so the timeout actually
                              fires (an in-loop sync call would block
                              the cancellation).

    Returns:
        Aggregate dict {tenants_processed, promoted, confirmed,
        skipped_cap, skipped_no_table, errors, timeouts}. Returned for
        tests; APScheduler ignores the value.

    Failure semantics:
        Per-tenant timeout → log error, continue with next tenant.
        Per-tenant exception → log error with traceback, continue.
        Never raises into APScheduler.
    """
    if session_factory is None:
        from app.database import SessionLocal  # late import — cycle guard
        session_factory = SessionLocal

    enabled = sorted(_enabled_tenant_ids())
    aggregate: dict[str, int] = {
        "tenants_processed": 0,
        "promoted":          0,
        "confirmed":         0,
        "skipped_cap":       0,
        "skipped_no_table":  0,
        "skipped_other":     0,
        "errors":            0,
        "timeouts":          0,
    }
    if not enabled:
        logger.info(
            "promotion_run_summary tenants=0 (ENTITY_EXTRACTION_TENANT_IDS empty)",
        )
        return aggregate

    for tenant_id in enabled:
        aggregate["tenants_processed"] += 1
        try:
            summary = await asyncio.wait_for(
                asyncio.to_thread(
                    _run_one_tenant_sync, tenant_id, session_factory,
                ),
                timeout=per_tenant_timeout_s,
            )
            aggregate["promoted"]         += summary.promoted
            aggregate["confirmed"]        += summary.confirmed
            aggregate["skipped_cap"]      += summary.skipped_cap
            aggregate["skipped_no_table"] += summary.skipped_no_table
            aggregate["skipped_other"]    += summary.skipped_other
            aggregate["errors"]           += len(summary.errors)
        except asyncio.TimeoutError:
            aggregate["timeouts"] += 1
            logger.error(
                "promotion_timeout tenant=%d after %.1fs",
                tenant_id, per_tenant_timeout_s,
            )
        except Exception:
            aggregate["errors"] += 1
            logger.exception(
                "promotion_failed tenant=%d", tenant_id,
            )

    logger.info(
        "promotion_run_summary tenants=%d promoted=%d confirmed=%d "
        "skipped_cap=%d skipped_no_table=%d skipped_other=%d "
        "errors=%d timeouts=%d",
        aggregate["tenants_processed"],
        aggregate["promoted"],
        aggregate["confirmed"],
        aggregate["skipped_cap"],
        aggregate["skipped_no_table"],
        aggregate["skipped_other"],
        aggregate["errors"],
        aggregate["timeouts"],
    )
    return aggregate
