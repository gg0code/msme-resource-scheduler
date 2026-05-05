# tests/services/test_entity_extractor.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/extraction/entity_extractor.py (v6.3.14).
# Covers prompt assembly, JSON parsing, normalisation, confidence
# clamping, upsert (SQLite path), provenance fields, multi-tenant
# isolation, failure handling, schedule short-circuit, per-industry
# happy path.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.extraction.entity_extractor — extract_entities,
#                                              schedule_extraction,
#                                              ENTITY_TYPES.
#   app.services.extraction.feature_flag — _reset_cache after
#                                          monkeypatching settings.
#   tests/services/conftest.py — make_tenant builder.
#
# DESIGN NOTES
#   - The Groq client is mocked end-to-end. No tests reach the real
#     LLM; we inject a stub via the `groq_client=` kwarg.
#   - SQLite FKs are not enforced by the parent conftest engine, but
#     we still call make_tenant so the Tenant row exists for any
#     relationship-backed assertions.
#   - The `extract_entities` synchronous surface is what we test.
#     `schedule_extraction` is exercised separately for its flag and
#     event-loop behaviour.

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.models.extraction_candidate import ExtractionCandidate
from app.services.extraction import entity_extractor as ee
from app.services.extraction import feature_flag as ff

from tests.services.conftest import make_tenant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_payload() -> dict:
    return {k: [] for k in ee.ENTITY_TYPES}


def _mock_response(payload: dict) -> MagicMock:
    """Build a Groq-shaped response object whose
    `.choices[0].message.content` is the JSON string of `payload`.
    """
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


def _mock_response_raw(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


def _stub_client(response_or_exc) -> MagicMock:
    client = MagicMock()
    if isinstance(response_or_exc, Exception):
        client.chat.completions.create.side_effect = response_or_exc
    else:
        client.chat.completions.create.return_value = response_or_exc
    return client


# ---------------------------------------------------------------------------
# Tests — extract_entities (sync, mockable)
# ---------------------------------------------------------------------------


class TestExtractEntities:

    def test_returns_zero_when_no_entities(self, db):
        tenant = make_tenant(db)
        client = _stub_client(_mock_response(_empty_payload()))

        n = ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="ok", source_message_id=None, groq_client=client,
        )

        assert n == 0
        assert db.query(ExtractionCandidate).count() == 0

    def test_returns_one_employee_with_confidence(self, db):
        tenant = make_tenant(db)
        payload = _empty_payload()
        payload["employee"] = [
            {"raw_value": "Ramesh", "normalized_value": "ramesh", "confidence": 0.92}
        ]
        client = _stub_client(_mock_response(payload))

        n = ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="Ramesh aa gaya", source_message_id="m1",
            groq_client=client,
        )

        assert n == 1
        rows = db.query(ExtractionCandidate).all()
        assert len(rows) == 1
        assert rows[0].entity_type == "employee"
        assert rows[0].raw_value == "Ramesh"
        assert rows[0].normalized_value == "ramesh"
        assert rows[0].confidence == pytest.approx(0.92)
        assert rows[0].mention_count == 1

    def test_returns_multiple_categories_in_one_message(self, db):
        tenant = make_tenant(db)
        payload = _empty_payload()
        payload["employee"] = [{"raw_value": "Ramesh", "normalized_value": "ramesh", "confidence": 0.9}]
        payload["machine"]  = [{"raw_value": "Heidelberg", "normalized_value": "heidelberg", "confidence": 0.85}]
        payload["customer"] = [{"raw_value": "Coca Cola", "normalized_value": "coca cola", "confidence": 0.88}]
        client = _stub_client(_mock_response(payload))

        n = ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="Heidelberg pe Ramesh ne Coca Cola ka label print kar diya",
            source_message_id=None, groq_client=client,
        )

        assert n == 3
        types = {r.entity_type for r in db.query(ExtractionCandidate).all()}
        assert types == {"employee", "machine", "customer"}

    def test_normalizes_capitalization_consistently(self, db):
        tenant = make_tenant(db)
        # The model returns a normalized_value with mixed case + extra
        # whitespace; the service must always lowercase and collapse
        # whitespace before storing, regardless of model output.
        payload = _empty_payload()
        payload["employee"] = [
            {"raw_value": "Ramesh Kumar",
             "normalized_value": "  Ramesh   Kumar ",
             "confidence": 0.9}
        ]
        client = _stub_client(_mock_response(payload))

        ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="Ramesh Kumar present", source_message_id=None,
            groq_client=client,
        )

        row = db.query(ExtractionCandidate).one()
        assert row.normalized_value == "ramesh kumar"

    def test_handles_invalid_json_gracefully(self, db, caplog):
        tenant = make_tenant(db)
        client = _stub_client(_mock_response_raw("not json at all"))

        n = ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="anything", source_message_id=None,
            groq_client=client,
        )

        assert n == 0
        assert db.query(ExtractionCandidate).count() == 0
        assert any(
            "entity_extraction_failed" in rec.message
            for rec in caplog.records
        )

    def test_handles_groq_timeout_gracefully(self, db, caplog):
        tenant = make_tenant(db)
        client = _stub_client(TimeoutError("LLM took too long"))

        n = ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="hello", source_message_id=None,
            groq_client=client,
        )

        assert n == 0
        assert any(
            "entity_extraction_failed" in rec.message
            for rec in caplog.records
        )

    def test_handles_groq_4xx_gracefully(self, db, caplog):
        tenant = make_tenant(db)
        # We don't import groq.BadRequestError here — any subclass of
        # Exception triggers the same failure branch.
        client = _stub_client(RuntimeError("400 bad request"))

        n = ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="hello", source_message_id=None,
            groq_client=client,
        )

        assert n == 0
        assert any(
            "entity_extraction_failed" in rec.message
            for rec in caplog.records
        )

    def test_uses_industry_vocabulary_for_disambiguation(self, db):
        tenant = make_tenant(db, industry_type="fabrication")
        client = _stub_client(_mock_response(_empty_payload()))

        ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="fabrication",
            message_text="anything", source_message_id=None,
            groq_client=client,
        )

        # Inspect what was actually sent to the LLM.
        sent_messages = client.chat.completions.create.call_args.kwargs["messages"]
        system_prompt = sent_messages[0]["content"]

        # Fabrication vocab must appear; printing vocab must not.
        assert "Plasma Cutter" in system_prompt
        assert "MIG Welder"    in system_prompt
        assert "Welding"       in system_prompt
        assert "Flexo Printer" not in system_prompt

    def test_writes_to_extraction_candidates_via_upsert(self, db):
        tenant = make_tenant(db)
        payload = _empty_payload()
        payload["machine"] = [{"raw_value": "Heidelberg", "normalized_value": "heidelberg", "confidence": 0.9}]
        client = _stub_client(_mock_response(payload))

        ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="Heidelberg ready", source_message_id="msg-1",
            groq_client=client,
        )

        row = db.query(ExtractionCandidate).one()
        assert row.tenant_id        == tenant.id
        assert row.entity_type      == "machine"
        assert row.normalized_value == "heidelberg"
        assert row.mention_count    == 1
        assert row.first_seen is not None
        assert row.last_seen  is not None

    def test_increments_mention_count_on_repeat(self, db):
        tenant = make_tenant(db)
        payload = _empty_payload()
        payload["employee"] = [{"raw_value": "Ramesh", "normalized_value": "ramesh", "confidence": 0.9}]
        client = _stub_client(_mock_response(payload))

        ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="Ramesh aa gaya", source_message_id="m1",
            groq_client=client,
        )
        # Second mention.
        ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="Ramesh ne kaam khatam kiya", source_message_id="m2",
            groq_client=client,
        )

        rows = db.query(ExtractionCandidate).all()
        assert len(rows) == 1
        assert rows[0].mention_count == 2
        assert rows[0].source_message_id == "m2"

    def test_logs_failure_when_groq_raises(self, db, caplog):
        tenant = make_tenant(db)
        client = _stub_client(Exception("boom"))

        with caplog.at_level("ERROR", logger="app.services.extraction.entity_extractor"):
            n = ee.extract_entities(
                db=db, tenant_id=tenant.id, industry_type="printing",
                message_text="hello", source_message_id=None,
                groq_client=client,
            )

        assert n == 0
        assert any(
            "entity_extraction_failed" in rec.message and rec.levelname == "ERROR"
            for rec in caplog.records
        )

    def test_writes_correct_provenance_fields(self, db):
        tenant = make_tenant(db)
        payload = _empty_payload()
        payload["customer"] = [{"raw_value": "ACME Co", "normalized_value": "acme co", "confidence": 0.8}]
        client = _stub_client(_mock_response(payload))

        ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="ACME ka order", source_message_id="meta-abc-123",
            groq_client=client,
        )

        row = db.query(ExtractionCandidate).one()
        assert row.source_type       == "whatsapp"
        assert row.source_message_id == "meta-abc-123"

    def test_clamps_confidence_to_zero_one_range(self, db):
        tenant = make_tenant(db)
        payload = _empty_payload()
        payload["employee"] = [
            {"raw_value": "A", "normalized_value": "a", "confidence": 1.7},
            {"raw_value": "B", "normalized_value": "b", "confidence": -0.3},
            {"raw_value": "C", "normalized_value": "c", "confidence": "not a number"},
        ]
        client = _stub_client(_mock_response(payload))

        ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="A B C", source_message_id=None,
            groq_client=client,
        )

        rows = {r.normalized_value: r for r in db.query(ExtractionCandidate).all()}
        assert rows["a"].confidence == 1.0
        assert rows["b"].confidence == 0.0
        assert rows["c"].confidence == 0.0

    def test_skips_entities_with_empty_normalized_value(self, db):
        tenant = make_tenant(db)
        payload = _empty_payload()
        payload["employee"] = [
            {"raw_value": "  ", "normalized_value": "  ", "confidence": 0.9},
            {"raw_value": "Ramesh", "normalized_value": "ramesh", "confidence": 0.9},
        ]
        client = _stub_client(_mock_response(payload))

        n = ee.extract_entities(
            db=db, tenant_id=tenant.id, industry_type="printing",
            message_text="Ramesh", source_message_id=None,
            groq_client=client,
        )

        assert n == 1
        row = db.query(ExtractionCandidate).one()
        assert row.normalized_value == "ramesh"

    def test_uses_correct_tenant_id_in_inserts(self, db):
        t1 = make_tenant(db)
        t2 = make_tenant(db)
        payload = _empty_payload()
        payload["employee"] = [{"raw_value": "Ramesh", "normalized_value": "ramesh", "confidence": 0.9}]
        client = _stub_client(_mock_response(payload))

        ee.extract_entities(
            db=db, tenant_id=t1.id, industry_type="printing",
            message_text="Ramesh", source_message_id=None,
            groq_client=client,
        )
        ee.extract_entities(
            db=db, tenant_id=t2.id, industry_type="printing",
            message_text="Ramesh", source_message_id=None,
            groq_client=client,
        )

        rows = db.query(ExtractionCandidate).all()
        assert len(rows) == 2
        assert {r.tenant_id for r in rows} == {t1.id, t2.id}
        # Each tenant has its own first-mention row, mention_count=1.
        assert all(r.mention_count == 1 for r in rows)


# ---------------------------------------------------------------------------
# Tests — per-industry happy path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("industry,expected_machine_in_prompt", [
    ("printing",      "Flexo Printer"),
    ("fabrication",   "Plasma Cutter"),
    ("manufacturing", "CNC Lathe"),
    ("chemical",      "Reactor"),
    ("field_service", "Service Van"),
])
def test_per_industry_happy_path(db, industry, expected_machine_in_prompt):
    """For each vertical the prompt carries the right machine vocab and
    the upsert path still writes a row.
    """
    tenant = make_tenant(db, industry_type=industry)
    payload = _empty_payload()
    payload["employee"] = [{"raw_value": "Ramesh", "normalized_value": "ramesh", "confidence": 0.9}]

    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response(payload)

    n = ee.extract_entities(
        db=db, tenant_id=tenant.id, industry_type=industry,
        message_text="Ramesh aa gaya", source_message_id=None,
        groq_client=client,
    )

    assert n == 1
    sent_messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert expected_machine_in_prompt in sent_messages[0]["content"]


# ---------------------------------------------------------------------------
# Tests — schedule_extraction flag short-circuit
# ---------------------------------------------------------------------------


class TestScheduleExtraction:

    def test_skipped_when_feature_flag_off(self, db, monkeypatch):
        # Default settings.ENTITY_EXTRACTION_TENANT_IDS is "" — flag off.
        monkeypatch.setattr(
            "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS", "", raising=False,
        )
        ff._reset_cache()

        task = ee.schedule_extraction(
            tenant_id=999, industry_type="printing",
            message_text="hello", source_message_id=None,
        )
        assert task is None

    def test_skipped_when_message_blank(self, db, monkeypatch):
        # Flag on for tenant 1 — but blank text should still short-circuit.
        monkeypatch.setattr(
            "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS", "1", raising=False,
        )
        ff._reset_cache()

        task = ee.schedule_extraction(
            tenant_id=1, industry_type="printing",
            message_text="   ", source_message_id=None,
        )
        assert task is None


@pytest.mark.asyncio
async def test_schedule_creates_task_when_flag_on(monkeypatch):
    """When the flag is on, schedule_extraction returns an asyncio.Task
    that the caller does not have to await.

    The task itself will try to call SessionLocal() and the real Groq
    client — we patch both to no-ops so the scheduled coroutine
    completes cleanly without external side effects.
    """
    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS", "42", raising=False,
    )
    ff._reset_cache()

    # Replace the inner sync extractor with a no-op so the scheduled
    # task does not need SessionLocal or a Groq client.
    monkeypatch.setattr(ee, "extract_entities", lambda **kwargs: 0)

    # SessionLocal is called inside the task; replace with a dummy so
    # we don't open a real DB session here.
    class _DummySession:
        def close(self): pass

    monkeypatch.setattr(ee, "SessionLocal", lambda: _DummySession())

    task = ee.schedule_extraction(
        tenant_id=42, industry_type="printing",
        message_text="Ramesh aa gaya", source_message_id=None,
    )
    assert task is not None
    assert isinstance(task, asyncio.Task)

    await task  # Drain the task so the test does not leak it.
    assert task.done()
    assert task.exception() is None
