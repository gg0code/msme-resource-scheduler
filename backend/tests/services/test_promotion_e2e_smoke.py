# tests/services/test_promotion_e2e_smoke.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# End-to-end smoke test for v6.3.15 (revised) - exercises the full
# pipeline through the real wiring:
#
#   Stage 1: 02:00 IST evaluate_for_all_tenants - assert ZERO inserts
#            into employees/machines, assert ready_for_confirmation > 0.
#   Stage 2: 19:00 IST send_confirmations_for_all_tenants with a captured
#            sender stub - assert one batch sent, the message text
#            contains the candidate names, the candidates flip to state
#            'pending', the wamid is recorded on each, and an
#            extraction.confirmation_requested event is written.
#   Stage 3: Simulated inbound HAAN reply through the REAL router
#            (_process_inbound_message) - assert Step 2.5 fires,
#            apply_confirmation_decisions inserts both an Employee and
#            a Machine, candidates flip to state 'confirmed', the
#            promoted events carry confirmation_message_id +
#            decided_by_user_id, and an aggregate
#            extraction.confirmation_received event is written.
#
# This is the integration test the user asked for as the "smoke" that
# proves all of the v6.3.15-revised pieces work TOGETHER, not just in
# isolation. Earlier files (test_confirmation_composer.py,
# test_reply_parser.py, test_timeout_handler.py,
# test_promotion_promoter.py) cover the unit boundaries; this file
# covers the boundary between them.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.routers.whatsapp._process_inbound_message - real router path,
#                                                   monkeypatched
#                                                   SessionLocal so the
#                                                   in-flight batch
#                                                   query hits the test DB.
#   app.services.promotion.{evaluate_for_all_tenants,
#                           send_confirmations_for_all_tenants}
#   app.services.whatsapp_actions._mock_sessions - cleared between
#                                                  stages so the v5.12
#                                                  Redis-pending-action
#                                                  state machine starts
#                                                  empty.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.auth import User
from app.models.employee import Employee
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate
from app.models.machine import Machine
from app.models.whatsapp import PhoneTenantMap
from app.routers import whatsapp as whatsapp_router
from app.services.extraction import feature_flag as ff
from app.services.promotion import (
    EVENT_CONFIRMATION_RECEIVED,
    EVENT_CONFIRMATION_REQUESTED,
    EVENT_PROMOTED,
    evaluate_for_all_tenants,
    send_confirmations_for_all_tenants,
)
from app.services.whatsapp_session import _mock_sessions

from tests.services.conftest import make_tenant


PHONE = "+919876543210"


def _build_tenant_with_top_tier_phone(db, *, industry_type="printing"):
    """Create a tenant + a top-tier user + an active linked phone."""
    tenant = make_tenant(db, industry_type=industry_type)
    user = User(
        tenant_id=tenant.id,
        email=f"smoke-{tenant.id}@x.com",
        hashed_password="x",
        role="owner",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    pmap = PhoneTenantMap(
        phone_number=PHONE,
        tenant_id=tenant.id,
        user_id=user.id,
        is_active=True,
        industry_type=industry_type,
        consent_given=True,
        consent_at=datetime.now(timezone.utc),
        phone_role="owner",
        last_seen_at=datetime.now(timezone.utc),
        linked_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    db.add(pmap)
    db.flush()
    return tenant, user, pmap


def _stage_candidate(db, *, tenant_id, entity_type, raw_value, mention_count):
    """Stage one qualifying candidate."""
    seen = datetime.now(timezone.utc) - timedelta(days=1)
    c = ExtractionCandidate(
        tenant_id=tenant_id,
        entity_type=entity_type,
        raw_value=raw_value,
        normalized_value=raw_value.strip().lower(),
        confidence=0.95,
        mention_count=mention_count,
        first_seen=seen,
        last_seen=seen,
        source_type="whatsapp",
        confirmation_state="none",
    )
    db.add(c)
    db.flush()
    return c


@pytest.mark.asyncio
async def test_e2e_full_flow_evaluate_send_reply_insert(db, monkeypatch):
    """The whole v6.3.15-revised pipeline, end to end."""
    from tests.conftest import TestingSessionLocal

    # ----- Setup --------------------------------------------------------
    tenant, user, pmap = _build_tenant_with_top_tier_phone(db)
    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS",
        str(tenant.id), raising=False,
    )
    ff._reset_cache()
    # Make Step 2.5's `inflight_db = SessionLocal()` hit the test DB.
    monkeypatch.setattr(
        whatsapp_router, "SessionLocal", TestingSessionLocal,
    )
    # Clear any v5.12 pending-action state from prior tests; we want
    # Step 3 (Redis pending-action) to be empty so Step 2.5 wins.
    _mock_sessions.clear()

    c_emp = _stage_candidate(
        db, tenant_id=tenant.id, entity_type="employee",
        raw_value="Suresh", mention_count=6,
    )
    c_mach = _stage_candidate(
        db, tenant_id=tenant.id, entity_type="machine",
        raw_value="Heidelberg", mention_count=8,
    )
    db.commit()

    # ----- Stage 1: 02:00 IST evaluate ----------------------------------
    eval_agg = await evaluate_for_all_tenants(
        session_factory=TestingSessionLocal,
    )
    assert eval_agg["tenants_processed"] == 1
    assert eval_agg["ready_for_confirmation"] == 2
    assert eval_agg["confirmed_via_fuzzy"] == 0
    # CRITICAL: nothing inserted on the 02:00 tick.
    assert (
        db.query(Employee).filter(Employee.tenant_id == tenant.id).count()
        == 0
    )
    assert (
        db.query(Machine).filter(Machine.tenant_id == tenant.id).count()
        == 0
    )
    # Both candidates remain state='none' so the 19:00 cron can ask.
    db.expire_all()
    assert db.query(ExtractionCandidate).get(c_emp.id).confirmation_state == "none"
    assert db.query(ExtractionCandidate).get(c_mach.id).confirmation_state == "none"

    # ----- Stage 2: 19:00 IST confirmation send -------------------------
    sent: list[tuple[str, str]] = []

    async def fake_sender(phone, message):
        sent.append((phone, message))
        return f"wamid.smoke.{len(sent)}"

    send_agg = await send_confirmations_for_all_tenants(
        session_factory=TestingSessionLocal,
        sender=fake_sender,
    )
    assert send_agg["batches_sent"] == 1
    assert send_agg["candidates_asked"] == 2
    assert len(sent) == 1
    sent_phone, sent_text = sent[0]
    assert sent_phone == PHONE
    assert "Suresh" in sent_text
    assert "Heidelberg" in sent_text
    # Per Q6 wording check.
    assert "Pichhle kuch dino mein" in sent_text
    # The composed message includes both vertical singulars
    # (printing -> 'employee', 'press').
    assert "(employee?)" in sent_text
    assert "(press?)" in sent_text

    # State + wamid recorded on both candidates.
    db.expire_all()
    c_emp_p = db.query(ExtractionCandidate).get(c_emp.id)
    c_mach_p = db.query(ExtractionCandidate).get(c_mach.id)
    assert c_emp_p.confirmation_state == "pending"
    assert c_mach_p.confirmation_state == "pending"
    assert c_emp_p.confirmation_message_id == "wamid.smoke.1"
    assert c_mach_p.confirmation_message_id == "wamid.smoke.1"
    assert c_emp_p.confirmation_asked_at is not None

    # confirmation_requested audit event written.
    requested = (
        db.query(Event)
        .filter(
            Event.tenant_id == tenant.id,
            Event.event_type == EVENT_CONFIRMATION_REQUESTED,
        )
        .all()
    )
    assert len(requested) == 1
    assert requested[0].payload["message_id"] == "wamid.smoke.1"
    assert sorted(requested[0].payload["candidate_ids"]) == sorted([c_emp.id, c_mach.id])
    assert requested[0].payload["recipient_user_id"] == user.id

    # ----- Stage 3: simulated inbound HAAN reply ------------------------
    # Goes through the REAL router function, which:
    #   - calls resolve_identity (reads PhoneTenantMap)
    #   - skips Step 2 (consent_given=True)
    #   - hits Step 2.5 (find_inflight returns 2 candidates)
    #   - parses 'haan kar do' as all-confirmed via the heuristic prong
    #   - apply_confirmation_decisions inserts Employee + Machine,
    #     emits candidate_promoted (x2) + aggregate
    #     confirmation_received (x1)
    #   - returns the all-added ack text
    ack = await whatsapp_router._process_inbound_message(
        phone_number=PHONE,
        message_text="haan kar do",
        message_type="text",
        db=db,
    )

    # The ack mentions both names so the owner sees what landed.
    assert ack is not None
    assert "Suresh" in ack
    assert "Heidelberg" in ack

    # ----- Final assertions: real-table inserts -------------------------
    db.expire_all()
    emps = (
        db.query(Employee).filter(Employee.tenant_id == tenant.id).all()
    )
    machines = (
        db.query(Machine).filter(Machine.tenant_id == tenant.id).all()
    )
    assert len(emps) == 1
    assert emps[0].full_name == "Suresh"
    assert emps[0].source == "whatsapp_inferred"
    assert emps[0].worker_type == "permanent"
    assert len(machines) == 1
    assert machines[0].name == "Heidelberg"
    assert machines[0].source == "whatsapp_inferred"
    assert machines[0].machine_type is None  # Q6 - left null for owner correction.

    # State flipped to confirmed on both candidates.
    assert db.query(ExtractionCandidate).get(c_emp.id).confirmation_state == "confirmed"
    assert db.query(ExtractionCandidate).get(c_mach.id).confirmation_state == "confirmed"

    # Audit chain - one promoted event per inserted entity, both
    # carrying the wamid + decided_by_user_id (Q10 augmentation).
    promoted = (
        db.query(Event)
        .filter(
            Event.tenant_id == tenant.id,
            Event.event_type == EVENT_PROMOTED,
        )
        .all()
    )
    assert len(promoted) == 2
    for ev in promoted:
        assert ev.payload["confirmation_message_id"] == "wamid.smoke.1"
        assert ev.payload["decided_by_user_id"] == user.id
        assert ev.payload["source_value_used"] == "whatsapp_inferred"
        assert ev.actor_user_id == user.id

    # One aggregate confirmation_received event.
    received = (
        db.query(Event)
        .filter(
            Event.tenant_id == tenant.id,
            Event.event_type == EVENT_CONFIRMATION_RECEIVED,
        )
        .all()
    )
    assert len(received) == 1
    assert received[0].payload["message_id"] == "wamid.smoke.1"
    assert received[0].payload["parse_strategy"] == "heuristic"
    assert received[0].payload["reply_text"] == "haan kar do"
    decisions = received[0].payload["decisions"]
    assert decisions[str(c_emp.id)] == "confirmed"
    assert decisions[str(c_mach.id)] == "confirmed"


@pytest.mark.asyncio
async def test_e2e_nahi_reply_does_not_insert(db, monkeypatch):
    """Owner says NAHI - candidates flip to rejected, NO insertions."""
    from tests.conftest import TestingSessionLocal

    tenant, user, _ = _build_tenant_with_top_tier_phone(db)
    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS",
        str(tenant.id), raising=False,
    )
    ff._reset_cache()
    monkeypatch.setattr(
        whatsapp_router, "SessionLocal", TestingSessionLocal,
    )
    _mock_sessions.clear()

    c = _stage_candidate(
        db, tenant_id=tenant.id, entity_type="employee",
        raw_value="NotMyEmployee", mention_count=5,
    )
    db.commit()

    await evaluate_for_all_tenants(session_factory=TestingSessionLocal)

    async def fake_sender(phone, message):
        return "wamid.nahi.1"

    await send_confirmations_for_all_tenants(
        session_factory=TestingSessionLocal,
        sender=fake_sender,
    )

    ack = await whatsapp_router._process_inbound_message(
        phone_number=PHONE,
        message_text="nahi",
        message_type="text",
        db=db,
    )

    assert ack is not None
    db.expire_all()
    # NO Employee inserted.
    assert (
        db.query(Employee).filter(Employee.tenant_id == tenant.id).count()
        == 0
    )
    # Candidate flipped to 'rejected'.
    assert db.query(ExtractionCandidate).get(c.id).confirmation_state == "rejected"


@pytest.mark.asyncio
async def test_e2e_q9_no_top_tier_phone_skips_send(db, monkeypatch):
    """Tenant with no top-tier phone: 19:00 cron skips, NO message sent."""
    from tests.conftest import TestingSessionLocal

    tenant = make_tenant(db)
    # Stage a NON-top-tier (manager) phone instead.
    user = User(
        tenant_id=tenant.id,
        email=f"mgr-{tenant.id}@x.com",
        hashed_password="x",
        role="manager",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    pmap = PhoneTenantMap(
        phone_number=PHONE,
        tenant_id=tenant.id,
        user_id=user.id,
        is_active=True,
        consent_given=True,
        phone_role="manager",  # NOT top-tier
        last_seen_at=datetime.now(timezone.utc),
        linked_at=datetime.now(timezone.utc),
    )
    db.add(pmap)
    db.flush()

    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS",
        str(tenant.id), raising=False,
    )
    ff._reset_cache()

    _stage_candidate(
        db, tenant_id=tenant.id, entity_type="employee",
        raw_value="Stranded", mention_count=5,
    )
    db.commit()

    sent: list = []
    async def fake_sender(phone, message):
        sent.append((phone, message))
        return "wamid.x"

    send_agg = await send_confirmations_for_all_tenants(
        session_factory=TestingSessionLocal,
        sender=fake_sender,
    )

    # No batch sent - tenant skipped on Q9 hard-fail.
    assert send_agg["batches_sent"] == 0
    assert send_agg["skipped_no_top_tier"] == 1
    assert sent == []
