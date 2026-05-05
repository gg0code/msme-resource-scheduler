# app/services/extraction/entity_extractor.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.14 entity-extractor service. Runs a single Groq JSON-mode call
# on every inbound WhatsApp message (when the per-tenant flag is on),
# parses the response into seven entity categories, normalises each
# value, and upserts a row into extraction_candidates per
# (tenant_id, entity_type, normalized_value) — incrementing
# mention_count when the same entity is seen again. Failure is
# silent: nothing in this module ever raises into the caller's reply
# path.
#
# WHO CALLS THIS FILE
# - app/routers/whatsapp.py — `_process_inbound_message` calls
#   `schedule_extraction(...)` after Step 6b (add_message_to_session).
#   That call returns immediately; the actual extraction runs as a
#   detached asyncio task.
# - app/services/extraction/__init__.py — re-exports
#   schedule_extraction.
# - backend/tests/services/test_entity_extractor.py — exercises
#   `extract_entities` (the synchronous, mockable inner function)
#   directly with a stubbed Groq client.
#
# WHAT THIS FILE CALLS
# - app/services/extraction/feature_flag.is_entity_extraction_enabled
# - app/services/extraction/industry_vocabularies.get_industry_vocabulary
# - app/services/ai_service.get_groq_client + ai_service.MODEL — same
#   Groq client + same model name as the chat reply path.
# - app/models/extraction_candidate.ExtractionCandidate — ORM target.
# - app/database.SessionLocal — extractor opens its own session
#   because the request-scoped db from get_db() is closed before the
#   detached task runs.
#
# DESIGN NOTES (Q1-Q9 from the discovery doc)
# - Q1 EXECUTION MODEL: asyncio.create_task — no signature changes
#   to receive_webhook / simulate_message; the LLM call runs in a
#   thread-pool executor wrapped in run_in_executor (the Groq SDK is
#   sync). Tasks held in a module-level set to avoid GC.
# - Q2 MODEL: same `llama-3.3-70b-versatile` as ai_service.MODEL,
#   reused with response_format={"type":"json_object"}. Different
#   client instance — the existing one in ai_service is for chat;
#   keeping ours separate avoids cross-contamination of params.
# - Q3 ENTITY VOCABULARY: ENTITY_TYPES dict below — seven keys
#   matching migration 029's docstring. Application code references
#   this dict, never magic strings.
# - Q4 INDUSTRY VOCABULARY: pulled from
#   app/services/extraction/industry_vocabularies.py.
# - Q5 PROMPT: single inbound message in scope; two few-shot examples
#   per industry (one positive, one empty/uncertain) — 10 total. The
#   "empty/uncertain" example is what teaches the model to return []
#   instead of confidently mis-classifying short / ambiguous text.
# - Q6 UPSERT: PostgreSQL INSERT ... ON CONFLICT DO UPDATE via
#   sqlalchemy.dialects.postgresql.insert. SQLite fallback: a
#   query-then-update / insert branch (see _upsert_candidate). The
#   branching is needed because tests run on SQLite and the unit-tier
#   suite must not require Postgres.
# - Q7 FAILURE HANDLING: every exception is swallowed at module
#   boundary with logger.error(..., exc_info=True). The reply path
#   is sacred — never raise.
# - Q8 FEATURE FLAG: env-CSV ENTITY_EXTRACTION_TENANT_IDS, no
#   migration. See feature_flag.py.
# - Q9 INSPECTION: see backend/inspect_extractions.py.
#
# FORWARD-COMPAT
# - v6.3.15 will read from the table this writes to; do not change
#   the column shape without updating that promotion job.
# - v6.3.16 may want a conversation-window prompt (last 1–3 messages
#   instead of just the current one); the prompt assembly in
#   _build_prompt is the single function to modify.
# - The async task indirection (`schedule_extraction` -> internal
#   coroutine -> `extract_entities`) intentionally separates the
#   fire-and-forget shape from the synchronous testable extractor.
#   Future versions can swap asyncio.create_task for FastAPI
#   BackgroundTasks or a Celery enqueue without touching the
#   extractor body.

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.extraction_candidate import ExtractionCandidate
from app.services.extraction.feature_flag import is_entity_extraction_enabled
from app.services.extraction.industry_vocabularies import (
    get_industry_vocabulary,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public vocabulary — the seven entity_type values we extract.
# ---------------------------------------------------------------------------
# Application code MUST reference this dict, not magic strings, when
# constructing entity_type values. Adding a key here without updating
# migration 029's docstring is fine — entity_type is VARCHAR(50) with
# no CHECK constraint by design.
ENTITY_TYPES: dict[str, str] = {
    "employee": "Worker / employee names",
    "machine":  "Equipment / machine references",
    "customer": "Client / customer names",
    "skill":    "Skill mentions (welder, operator, etc.)",
    "material": "Material / supply mentions",
    "job":      "Job / project / order references",
    "issue":    "Problems / blockers / complaints",
}


# ---------------------------------------------------------------------------
# Groq call parameters (Q2).
# ---------------------------------------------------------------------------
_LLM_MAX_TOKENS  = 400
_LLM_TEMPERATURE = 0.1
_LLM_TIMEOUT_S   = 8.0


# ---------------------------------------------------------------------------
# Background-task strong-ref set (Q1).
# ---------------------------------------------------------------------------
# asyncio.create_task() returns a Task that the event loop holds with
# only a weak reference. Without an external strong ref the task can
# be garbage-collected mid-flight. We add to this set on schedule and
# remove via add_done_callback when the task completes.
_pending_extractions: set[asyncio.Task[None]] = set()


# ---------------------------------------------------------------------------
# Few-shot examples per industry (Q5).
# ---------------------------------------------------------------------------
# Each industry contributes two examples to the prompt:
#   - one positive case (entities present)
#   - one empty/uncertain case (terse / ambiguous → empty arrays)
#
# The empty case is the critical part: it teaches the model that
# returning empty arrays is correct when the message has no clear
# entities, instead of fabricating ones to avoid an empty answer.
_FEW_SHOT_EXAMPLES: dict[str, list[dict[str, Any]]] = {
    "printing": [
        {
            "input": "Heidelberg pe Ramesh ne Coca Cola ka label print kar diya",
            "output": {
                "employee": [{"raw_value": "Ramesh", "normalized_value": "ramesh", "confidence": 0.95}],
                "machine":  [{"raw_value": "Heidelberg", "normalized_value": "heidelberg", "confidence": 0.9}],
                "customer": [{"raw_value": "Coca Cola", "normalized_value": "coca cola", "confidence": 0.9}],
                "skill":    [],
                "material": [],
                "job":      [{"raw_value": "label print", "normalized_value": "label print", "confidence": 0.7}],
                "issue":    [],
            },
        },
        {
            "input": "ok",
            "output": {k: [] for k in ENTITY_TYPES},
        },
    ],
    "fabrication": [
        {
            "input": "MIG Welder pe Suresh weld kar raha hai 50 sariya",
            "output": {
                "employee": [{"raw_value": "Suresh", "normalized_value": "suresh", "confidence": 0.95}],
                "machine":  [{"raw_value": "MIG Welder", "normalized_value": "mig welder", "confidence": 0.95}],
                "customer": [],
                "skill":    [{"raw_value": "weld", "normalized_value": "welding", "confidence": 0.85}],
                "material": [{"raw_value": "sariya", "normalized_value": "sariya", "confidence": 0.7}],
                "job":      [],
                "issue":    [],
            },
        },
        {
            "input": "haan theek hai",
            "output": {k: [] for k in ENTITY_TYPES},
        },
    ],
    "manufacturing": [
        {
            "input": "CNC Lathe band ho gaya, Mahesh ko bulao",
            "output": {
                "employee": [{"raw_value": "Mahesh", "normalized_value": "mahesh", "confidence": 0.9}],
                "machine":  [{"raw_value": "CNC Lathe", "normalized_value": "cnc lathe", "confidence": 0.95}],
                "customer": [],
                "skill":    [],
                "material": [],
                "job":      [],
                "issue":    [{"raw_value": "CNC Lathe band", "normalized_value": "cnc lathe down", "confidence": 0.85}],
            },
        },
        {
            "input": "kya hua",
            "output": {k: [] for k in ENTITY_TYPES},
        },
    ],
    "chemical": [
        {
            "input": "Reactor R-101 mein batch start kar diya, Anil ne",
            "output": {
                "employee": [{"raw_value": "Anil", "normalized_value": "anil", "confidence": 0.9}],
                "machine":  [{"raw_value": "Reactor R-101", "normalized_value": "reactor r-101", "confidence": 0.95}],
                "customer": [],
                "skill":    [],
                "material": [],
                "job":      [{"raw_value": "batch start", "normalized_value": "batch start", "confidence": 0.7}],
                "issue":    [],
            },
        },
        {
            "input": "thoda ruk",
            "output": {k: [] for k in ENTITY_TYPES},
        },
    ],
    "field_service": [
        {
            "input": "Ramesh HVAC site pe gaya, AC service ke liye",
            "output": {
                "employee": [{"raw_value": "Ramesh", "normalized_value": "ramesh", "confidence": 0.9}],
                "machine":  [],
                "customer": [],
                "skill":    [{"raw_value": "HVAC", "normalized_value": "hvac", "confidence": 0.95}],
                "material": [],
                "job":      [{"raw_value": "AC service", "normalized_value": "ac service", "confidence": 0.85}],
                "issue":    [],
            },
        },
        {
            "input": "ji",
            "output": {k: [] for k in ENTITY_TYPES},
        },
    ],
}


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def _build_prompt(message_text: str, industry_type: str | None) -> list[dict[str, str]]:
    """Compose the messages list for the Groq JSON-mode call.

    Called by:    extract_entities (this file).
    Calls into:   get_industry_vocabulary (industry_vocabularies.py).
    Returns:      List of {role, content} dicts in Groq chat format,
                  ready to pass to client.chat.completions.create.
    Side effects: none — pure function.

    Args:
        message_text:  The single inbound user message to extract from.
                       Q5 single-message scope; no conversation window.
        industry_type: The tenant's industry_type. Used to (1) inject
                       vertical-specific vocabulary, (2) pick which
                       few-shot examples to include.

    The system prompt includes:
      - the seven entity-type definitions
      - the tenant's industry skills + machine_types
      - the explicit "if uncertain, return empty arrays" instruction
      - two few-shot examples for that industry (one positive, one
        empty/uncertain)
    """
    vocab = get_industry_vocabulary(industry_type)
    examples = _FEW_SHOT_EXAMPLES.get(industry_type or "", [])

    type_lines = "\n".join(
        f"  - {name}: {desc}" for name, desc in ENTITY_TYPES.items()
    )

    skills_csv  = ", ".join(vocab["skills"])  if vocab["skills"]        else "(none)"
    machine_csv = ", ".join(vocab["machine_types"]) if vocab["machine_types"] else "(none)"

    example_block = ""
    for ex in examples:
        example_block += (
            f"\nExample input: {ex['input']}\n"
            f"Example output: {json.dumps(ex['output'], ensure_ascii=False)}\n"
        )

    system_prompt = (
        "You are an entity extractor for an Indian factory operations "
        "WhatsApp chat. Read the user message and extract entities by "
        "category. Return strict JSON only — no commentary.\n"
        "\n"
        "Categories to extract:\n"
        f"{type_lines}\n"
        "\n"
        f"Industry: {industry_type or 'unknown'}\n"
        f"Industry skills vocabulary: {skills_csv}\n"
        f"Industry machine vocabulary: {machine_csv}\n"
        "\n"
        "Output schema: a single JSON object with one key per category. "
        "Each value is a list of {raw_value, normalized_value, "
        "confidence} objects. confidence is a float in [0.0, 1.0].\n"
        "  - raw_value:        the entity exactly as it appeared\n"
        "  - normalized_value: lowercased, deduplicated canonical form\n"
        "  - confidence:       your self-assessed certainty\n"
        "\n"
        "If you are not certain, do NOT include the entity. Empty "
        "arrays are correct outputs. Short / generic / ambiguous "
        "messages should return all-empty arrays.\n"
        f"{example_block}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": message_text},
    ]


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(value: str) -> str:
    """Canonicalise a raw entity value for upsert deduplication.

    Called by:    _coerce_candidates (this file). Also applied as a
                  safety net to whatever the LLM returned in
                  normalized_value — we never trust the model to
                  produce a stable key.
    Calls into:   nothing.
    Returns:      lowercased, single-space-collapsed, trimmed string.
                  Empty input returns empty string.
    Side effects: none.

    The LLM is asked to produce normalized_value, but we re-apply this
    function unconditionally so the upsert key is stable regardless of
    model variance run-to-run.
    """
    if not value:
        return ""
    cleaned = _WHITESPACE_RE.sub(" ", value).strip().lower()
    return cleaned


def _clamp_confidence(value: Any) -> float:
    """Coerce a model-reported confidence into [0.0, 1.0].

    Called by:    _coerce_candidates (this file).
    Calls into:   nothing.
    Returns:      float in [0.0, 1.0]. Non-numeric input → 0.0.
    Side effects: none.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


# ---------------------------------------------------------------------------
# LLM-response coercion
# ---------------------------------------------------------------------------

def _coerce_candidates(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the LLM JSON into a list of candidate dicts.

    Called by:    extract_entities (this file).
    Calls into:   _normalize, _clamp_confidence (this file).
    Returns:      list of dicts, each with keys {entity_type,
                  raw_value, normalized_value, confidence}. Skips any
                  candidate whose normalized_value is empty after
                  cleanup.
    Side effects: none.

    Tolerant: any unrecognised top-level key is ignored, any
    malformed list element is skipped silently. The extractor is
    best-effort — a single bad row should not prevent the rest of the
    batch from landing.
    """
    out: list[dict[str, Any]] = []

    if not isinstance(parsed, dict):
        return out

    for entity_type in ENTITY_TYPES:
        candidates = parsed.get(entity_type)
        if not isinstance(candidates, list):
            continue
        for c in candidates:
            if not isinstance(c, dict):
                continue
            raw = c.get("raw_value")
            if not isinstance(raw, str) or not raw.strip():
                continue
            normalized_in = c.get("normalized_value")
            normalized = _normalize(normalized_in if isinstance(normalized_in, str) else raw)
            if not normalized:
                continue
            confidence = _clamp_confidence(c.get("confidence"))
            out.append({
                "entity_type":      entity_type,
                "raw_value":        raw.strip(),
                "normalized_value": normalized,
                "confidence":       confidence,
            })
    return out


# ---------------------------------------------------------------------------
# Upsert helpers (Q6)
# ---------------------------------------------------------------------------

def _upsert_candidate(
    db: Session,
    *,
    tenant_id: int,
    entity_type: str,
    raw_value: str,
    normalized_value: str,
    confidence: float,
    source_message_id: Optional[str],
    now: datetime,
) -> None:
    """Upsert one candidate row.

    Called by:    extract_entities (this file).
    Calls into:   sqlalchemy.dialects.postgresql.insert on Postgres,
                  ORM query/update/insert on SQLite. ExtractionCandidate
                  ORM model.
    Returns:      None.
    Side effects: One DB write — INSERT or UPDATE on
                  extraction_candidates. Caller commits.

    On Postgres we use INSERT ... ON CONFLICT DO UPDATE against the
    uq_extraction_candidates_tenant_type_value constraint that
    migration 029 created. On SQLite (unit tests) we run a SELECT
    first and then UPDATE-or-INSERT — the dialect-specific `insert`
    helper expects Postgres-style EXCLUDED rows.

    Dialect detection is deferred to call time because tests inject
    a SQLite session at runtime; the same module is imported by
    Postgres and SQLite consumers.
    """
    dialect_name = db.bind.dialect.name if db.bind is not None else ""

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(ExtractionCandidate).values(
            tenant_id=tenant_id,
            entity_type=entity_type,
            raw_value=raw_value,
            normalized_value=normalized_value,
            confidence=confidence,
            mention_count=1,
            first_seen=now,
            last_seen=now,
            source_type="whatsapp",
            source_message_id=source_message_id,
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_extraction_candidates_tenant_type_value",
            set_={
                "mention_count": ExtractionCandidate.__table__.c.mention_count + 1,
                "last_seen":     now,
                "raw_value":     stmt.excluded.raw_value,
                "confidence":    stmt.excluded.confidence,
                "source_message_id": stmt.excluded.source_message_id,
                "updated_at":    now,
            },
        )
        db.execute(stmt)
        return

    # SQLite fallback (unit tests). Non-atomic by design — the test
    # suite runs single-threaded so the read/write race is fine.
    existing = (
        db.query(ExtractionCandidate)
        .filter(
            ExtractionCandidate.tenant_id        == tenant_id,
            ExtractionCandidate.entity_type      == entity_type,
            ExtractionCandidate.normalized_value == normalized_value,
        )
        .one_or_none()
    )
    if existing is not None:
        existing.mention_count    = (existing.mention_count or 0) + 1
        existing.last_seen        = now
        existing.raw_value        = raw_value
        existing.confidence       = confidence
        existing.source_message_id = source_message_id
        existing.updated_at       = now
        return

    db.add(ExtractionCandidate(
        tenant_id=tenant_id,
        entity_type=entity_type,
        raw_value=raw_value,
        normalized_value=normalized_value,
        confidence=confidence,
        mention_count=1,
        first_seen=now,
        last_seen=now,
        source_type="whatsapp",
        source_message_id=source_message_id,
        created_at=now,
        updated_at=now,
    ))


# ---------------------------------------------------------------------------
# Synchronous extractor (testable surface)
# ---------------------------------------------------------------------------

def extract_entities(
    *,
    db: Session,
    tenant_id: int,
    industry_type: str | None,
    message_text: str,
    source_message_id: Optional[str],
    groq_client: Any = None,
) -> int:
    """Run one extraction pass: LLM call -> parse -> upsert.

    Called by:    _run_extraction_task (this file). Tests call this
                  directly with a stubbed groq_client so the LLM
                  doesn't need to be reachable.
    Calls into:   _build_prompt, _coerce_candidates, _upsert_candidate
                  (this file). app.services.ai_service.get_groq_client
                  + ai_service.MODEL.
    Returns:      number of candidate rows successfully upserted.
                  Returns 0 on any failure (parse error, empty result,
                  etc.).
    Side effects: One Groq HTTP call. One commit on `db`. logger.error
                  on failure (with exc_info), logger.info on success.
                  NEVER raises — every exception is caught and turned
                  into a 0 return.

    Args:
        db:                Session opened by the caller; this function
                           commits and lets the caller close.
        tenant_id:         Tenant scope for the upsert (multi-tenant
                           isolation enforced in WHERE clauses).
        industry_type:     Tenant.industry_type — drives prompt vocab.
        message_text:      The raw inbound user message.
        source_message_id: Optional Meta message id for provenance.
                           Stored in source_message_id column.
        groq_client:       Test seam. None in production -> we call
                           ai_service.get_groq_client(). Tests inject
                           a stub with a chat.completions.create that
                           returns a canned response object.
    """
    try:
        if not message_text or not message_text.strip():
            return 0

        if groq_client is None:
            from app.services.ai_service import get_groq_client
            groq_client = get_groq_client()

        from app.services.ai_service import MODEL

        messages = _build_prompt(message_text, industry_type)

        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=_LLM_MAX_TOKENS,
            temperature=_LLM_TEMPERATURE,
            response_format={"type": "json_object"},
            timeout=_LLM_TIMEOUT_S,
        )

        # Groq SDK 1.0 — message.content is the raw JSON string.
        content = response.choices[0].message.content or ""
        if not content.strip():
            logger.info(
                "entity_extraction_empty: tenant=%s — model returned "
                "empty content.",
                tenant_id,
            )
            return 0

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.error(
                "entity_extraction_failed: tenant=%s — invalid JSON "
                "from model. content_preview=%r",
                tenant_id,
                content[:200],
                exc_info=True,
            )
            return 0

        candidates = _coerce_candidates(parsed)
        if not candidates:
            return 0

        now = datetime.now(timezone.utc)
        for cand in candidates:
            _upsert_candidate(
                db,
                tenant_id=tenant_id,
                entity_type=cand["entity_type"],
                raw_value=cand["raw_value"],
                normalized_value=cand["normalized_value"],
                confidence=cand["confidence"],
                source_message_id=source_message_id,
                now=now,
            )

        db.commit()
        logger.info(
            "entity_extraction_ok: tenant=%s candidates=%d "
            "industry=%s",
            tenant_id, len(candidates), industry_type,
        )
        return len(candidates)

    except Exception:
        # Q7 — never raise into the caller's reply path. Every
        # failure is a structured log line plus a 0 return.
        logger.error(
            "entity_extraction_failed: tenant=%s industry=%s",
            tenant_id, industry_type,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return 0


# ---------------------------------------------------------------------------
# Async fire-and-forget wrapper (Q1)
# ---------------------------------------------------------------------------

async def _run_extraction_task(
    *,
    tenant_id: int,
    industry_type: str | None,
    message_text: str,
    source_message_id: Optional[str],
) -> None:
    """Background coroutine — opens its own Session and runs extract.

    Called by:    schedule_extraction (this file). Wrapped in
                  asyncio.create_task so the caller's reply path is
                  not blocked on the LLM round-trip.
    Calls into:   asyncio.get_event_loop().run_in_executor (offload
                  the sync Groq SDK call to a thread-pool slot).
                  extract_entities (this file).
    Returns:      None.
    Side effects: opens + closes one SessionLocal session. May call
                  Groq, may write to extraction_candidates. NEVER
                  raises — extract_entities swallows all exceptions.

    A fresh session is opened because the request-scoped `db` from
    FastAPI's get_db dependency is closed before this task runs.
    """
    loop = asyncio.get_event_loop()
    db = SessionLocal()
    try:
        await loop.run_in_executor(
            None,
            lambda: extract_entities(
                db=db,
                tenant_id=tenant_id,
                industry_type=industry_type,
                message_text=message_text,
                source_message_id=source_message_id,
            ),
        )
    finally:
        try:
            db.close()
        except Exception:
            logger.debug(
                "entity_extraction: session close failed silently.",
                exc_info=True,
            )


def schedule_extraction(
    *,
    tenant_id: int,
    industry_type: str | None,
    message_text: str,
    source_message_id: Optional[str] = None,
) -> Optional[asyncio.Task[None]]:
    """Schedule a background extraction for one inbound message.

    Called by:    app/routers/whatsapp.py — _process_inbound_message
                  after Step 6b (add_message_to_session).
    Calls into:   is_entity_extraction_enabled (feature_flag.py),
                  asyncio.create_task -> _run_extraction_task.
    Returns:      The asyncio.Task when scheduled, else None when the
                  feature flag is off or scheduling was skipped. The
                  router does not await the returned task — the
                  return is for testability.
    Side effects: When the flag is on, schedules a detached task on
                  the running event loop. Adds it to
                  _pending_extractions to prevent GC, removes via
                  done-callback on completion. NEVER raises into the
                  caller.

    The single-line short-circuit on is_entity_extraction_enabled is
    what guarantees zero behaviour change for tenants who have not
    been opted in via ENTITY_EXTRACTION_TENANT_IDS.
    """
    try:
        if not is_entity_extraction_enabled(tenant_id):
            return None
        if not message_text or not message_text.strip():
            return None

        task = asyncio.create_task(
            _run_extraction_task(
                tenant_id=tenant_id,
                industry_type=industry_type,
                message_text=message_text,
                source_message_id=source_message_id,
            )
        )
        _pending_extractions.add(task)
        task.add_done_callback(_pending_extractions.discard)
        return task

    except Exception:
        logger.error(
            "entity_extraction_schedule_failed: tenant=%s",
            tenant_id,
            exc_info=True,
        )
        return None
