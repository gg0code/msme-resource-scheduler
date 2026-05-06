# tests/services/test_promotion_promoter.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/promotion/promoter.py (v6.3.15 revised).
#
# Behavioural shift from v6.3.15-original (covered here):
#   - The 02:00 IST evaluate_for_tenant tick NEVER inserts into
#     employees / machines. It only writes candidate_confirmed events
#     for fuzzy-matched candidates and leaves non-matching qualifying
#     candidates with state='none' for the 19:00 IST cron.
#   - The 19:00 IST compose_confirmation_for_tenant flips state to
#     'pending' AND returns a BatchToSend; the caller does the
#     WhatsApp send + record_confirmation_sent.
#   - Real insertion only happens in apply_confirmation_decisions
#     after an explicit owner HAAN reply.
#   - Q9 hard-fail: tenants with no top-tier phone are SKIPPED with
#     logger.critical; never fall back to a delegated manager phone.
#
# Covers:
#   - evaluate_for_tenant: threshold gating, tenant scoping, fuzzy
#     short-circuit, customer skip, over-cap skip, others count,
#     already-asked filter, idempotency, failure isolation, per-
#     industry, multi-tenant isolation, fan-out, DB error handling.
#   - compose_confirmation_for_tenant: top-N picking, state flip to
#     pending, recipient resolution, Q9 hard-fail, no-eligible.
#   - record_confirmation_sent: message_id update + event emission.
#   - apply_confirmation_decisions: insert on confirmed, flip on
#     rejected, no-op on deferred, aggregate received event.
#   - find_inflight_batch_for_tenant: returns most recent batch only.
#   - send_confirmations_for_all_tenants async wrapper.

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.auth import User
from app.models.employee import Employee
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate
from app.models.machine import Machine
from app.models.whatsapp import PhoneTenantMap
from app.services.extraction import feature_flag as ff
from app.services.promotion import promoter as P

from tests.services.conftest import make_employee, make_machine, make_tenant


FIXED_NOW = datetime(2026, 5, 15, 2, 0, 0, tzinfo=timezone.utc)
EVENING_NOW = datetime(2026, 5, 15, 13, 30, 0, tzinfo=timezone.utc)  # 19:00 IST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _opt_in(monkeypatch, tenant_ids: str) -> None:
    """Set ENTITY_EXTRACTION_TENANT_IDS and bust the lru_cache."""
    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS",
        tenant_ids, raising=False,
    )
    ff._reset_cache()


def _make_candidate(
    db,
    *,
    tenant_id: int,
    entity_type: str,
    raw_value: str,
    normalized_value: str | None = None,
    mention_count: int = 5,
    confidence: float = 0.9,
    seen_days_ago: int = 1,
    confirmation_state: str = "none",
    confirmation_asked_at: datetime | None = None,
    confirmation_retry_count: int = 0,
) -> ExtractionCandidate:
    """Stage one ExtractionCandidate row and flush."""
    if normalized_value is None:
        normalized_value = raw_value.strip().lower()
    seen = FIXED_NOW - timedelta(days=seen_days_ago)
    c = ExtractionCandidate(
        tenant_id=tenant_id,
        entity_type=entity_type,
        raw_value=raw_value,
        normalized_value=normalized_value,
        confidence=confidence,
        mention_count=mention_count,
        first_seen=seen,
        last_seen=seen,
        source_type="whatsapp",
        confirmation_state=confirmation_state,
        confirmation_asked_at=confirmation_asked_at,
        confirmation_retry_count=confirmation_retry_count,
    )
    db.add(c)
    db.flush()
    return c


_USER_COUNTER = {"n": 0}


def _make_user_and_top_tier_phone(
    db,
    *,
    tenant,
    phone_number: str = "+919876543210",
    phone_role: str = "owner",
    last_seen_minutes_ago: int = 5,
) -> tuple[User, PhoneTenantMap]:
    """Stage a User + active PhoneTenantMap with top-tier role.

    The user email is monotonically unique across the test session so
    one tenant can host multiple linked phones (used by
    test_picks_most_recent_top_tier_phone).
    """
    _USER_COUNTER["n"] += 1
    n = _USER_COUNTER["n"]
    user = User(
        tenant_id=tenant.id,
        email=f"u{n}-{phone_role}@x.com",
        hashed_password="x",
        role=phone_role,
        is_active=True,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    db.add(user)
    db.flush()
    pmap = PhoneTenantMap(
        phone_number=phone_number,
        tenant_id=tenant.id,
        user_id=user.id,
        is_active=True,
        industry_type=tenant.industry_type,
        consent_given=True,
        phone_role=phone_role,
        last_seen_at=EVENING_NOW - timedelta(minutes=last_seen_minutes_ago),
        linked_at=FIXED_NOW - timedelta(days=30),
    )
    db.add(pmap)
    db.flush()
    return user, pmap


# ---------------------------------------------------------------------------
# evaluate_for_tenant - happy path: fuzzy-match short-circuit
# ---------------------------------------------------------------------------

class TestEvaluateFuzzyConfirm:

    def test_fuzzy_match_employee_flips_state_to_confirmed_no_insert(
        self, db, monkeypatch,
    ):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        make_employee(db, tenant=tenant, full_name="Suresh Kumar")
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Suresh Kumar", normalized_value="suresh kumar",
            mention_count=4, confidence=0.9,
        )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.confirmed_via_fuzzy == 1
        assert summary.ready_for_confirmation == 0
        # Critical: NO new Employee inserted.
        emps = db.query(Employee).filter(Employee.tenant_id == tenant.id).all()
        assert len(emps) == 1
        assert emps[0].full_name == "Suresh Kumar"  # the existing one
        # State flipped on the candidate.
        db.refresh(c)
        assert c.confirmation_state == "confirmed"

    def test_fuzzy_match_machine_flips_state_no_insert(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        make_machine(db, tenant=tenant, name="Heidelberg")
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="machine",
            raw_value="Heidelberg", mention_count=4, confidence=0.9,
        )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.confirmed_via_fuzzy == 1
        machines = db.query(Machine).filter(Machine.tenant_id == tenant.id).all()
        assert len(machines) == 1  # only the existing one
        db.refresh(c)
        assert c.confirmation_state == "confirmed"

    def test_no_fuzzy_match_leaves_state_none_for_evening_cron(
        self, db, monkeypatch,
    ):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Suresh", mention_count=5, confidence=0.9,
        )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.confirmed_via_fuzzy == 0
        assert summary.ready_for_confirmation == 1
        # Critical: state stays 'none' so the evening cron picks it up.
        db.refresh(c)
        assert c.confirmation_state == "none"
        # Also critical: NO Employee inserted on the 02:00 tick.
        assert (
            db.query(Employee)
            .filter(Employee.tenant_id == tenant.id)
            .count()
            == 0
        )

    def test_evaluate_idempotent_across_runs(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        make_employee(db, tenant=tenant, full_name="Vikram")
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Vikram", mention_count=5, confidence=0.9,
        )
        db.commit()

        first  = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)
        second = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        # First run fuzzy-matches and flips to 'confirmed'.
        assert first.confirmed_via_fuzzy == 1
        # Second run sees state='confirmed' and counts as already_asked.
        assert second.already_asked == 1
        assert second.confirmed_via_fuzzy == 0


# ---------------------------------------------------------------------------
# evaluate_for_tenant - threshold + tenant scoping
# ---------------------------------------------------------------------------

class TestThresholdGating:

    def test_below_mention_threshold_not_qualifying(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Ravi", mention_count=2, confidence=0.95,
        )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.qualified == 0
        assert summary.ready_for_confirmation == 0

    def test_below_confidence_threshold_not_qualifying(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Mohan", mention_count=10, confidence=0.5,
        )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.qualified == 0
        assert summary.ready_for_confirmation == 0


class TestTenantScoping:

    def test_skips_when_tenant_not_in_extraction_flag(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, "")  # nobody opted in
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="ShouldSkip", mention_count=5, confidence=0.9,
        )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.qualified == 0
        assert summary.ready_for_confirmation == 0


# ---------------------------------------------------------------------------
# evaluate_for_tenant - skip paths preserved from original v6.3.15
# ---------------------------------------------------------------------------

class TestDailyCap:

    def test_respects_per_tenant_daily_cap(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        monkeypatch.setattr(
            "app.config.settings.PROMOTION_DAILY_CAP_PER_TENANT", 3,
            raising=False,
        )
        for i in range(5):
            _make_candidate(
                db, tenant_id=tenant.id, entity_type="employee",
                raw_value=f"Worker{i}", normalized_value=f"worker{i}",
                mention_count=5, confidence=0.9,
            )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.qualified == 5
        # 3 ready (no fuzzy match against empty employees), 2 skipped over cap.
        assert summary.ready_for_confirmation == 3
        assert summary.skipped_cap == 2
        # Cap-skipped candidates emit one event each.
        skipped = db.query(Event).filter(
            Event.tenant_id == tenant.id,
            Event.event_type == P.EVENT_SKIPPED,
        ).all()
        assert len(skipped) == 2
        for ev in skipped:
            assert ev.payload["reason"] == P.REASON_DAILY_CAP


class TestCustomerSkip:

    def test_customer_emits_skipped_event_with_reason(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="customer",
            raw_value="Coca Cola", mention_count=8, confidence=0.95,
        )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.skipped_no_table == 1
        assert summary.confirmed_via_fuzzy == 0
        ev = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == P.EVENT_SKIPPED,
            )
            .one()
        )
        assert ev.entity_id == c.id
        assert ev.payload["reason"] == P.REASON_NO_TABLE

    def test_customer_skip_dedupes_across_runs(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="customer",
            raw_value="ACME", mention_count=4, confidence=0.85,
        )
        db.commit()

        P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)
        P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)
        P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        n = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == P.EVENT_SKIPPED,
            )
            .count()
        )
        assert n == 1


class TestOtherEntityTypes:

    def test_skill_material_job_issue_count_as_skipped_other(
        self, db, monkeypatch,
    ):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        for et in ("skill", "material", "job", "issue"):
            _make_candidate(
                db, tenant_id=tenant.id, entity_type=et,
                raw_value=f"{et}-val", normalized_value=f"{et}-val",
                mention_count=5, confidence=0.9,
            )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.qualified == 4
        assert summary.skipped_other == 4
        assert summary.confirmed_via_fuzzy == 0
        # No events for these.
        assert db.query(Event).filter(Event.tenant_id == tenant.id).count() == 0


class TestAlreadyAskedFilter:

    def test_pending_state_skipped_from_evaluation(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Already", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=FIXED_NOW - timedelta(hours=4),
        )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        # Pending candidate is counted but not re-evaluated.
        assert summary.already_asked == 1
        assert summary.confirmed_via_fuzzy == 0
        assert summary.ready_for_confirmation == 0
        db.refresh(c)
        assert c.confirmation_state == "pending"  # unchanged

    def test_confirmed_state_skipped_from_evaluation(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Decided", mention_count=5, confidence=0.9,
            confirmation_state="confirmed",
        )
        db.commit()

        summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

        assert summary.already_asked == 1


# ---------------------------------------------------------------------------
# compose_confirmation_for_tenant - the 19:00 IST per-tenant body
# ---------------------------------------------------------------------------

class TestComposeConfirmation:

    def test_composes_batch_and_flips_state_to_pending(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_user_and_top_tier_phone(db, tenant=tenant)
        c1 = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Suresh", mention_count=10, confidence=0.95,
        )
        c2 = _make_candidate(
            db, tenant_id=tenant.id, entity_type="machine",
            raw_value="Heidelberg", mention_count=8, confidence=0.9,
        )
        db.commit()

        batch = P.compose_confirmation_for_tenant(
            tenant.id, db, now=EVENING_NOW,
        )

        assert batch is not None
        assert batch.tenant_id == tenant.id
        assert batch.recipient_phone == "+919876543210"
        assert batch.candidate_ids == [c1.id, c2.id]
        assert "Suresh" in batch.message_text
        assert "Heidelberg" in batch.message_text
        # State flipped on both.
        db.refresh(c1)
        db.refresh(c2)
        assert c1.confirmation_state == "pending"
        assert c2.confirmation_state == "pending"
        # asked_at populated.
        assert c1.confirmation_asked_at is not None
        assert c2.confirmation_asked_at is not None

    def test_respects_batch_size_cap(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_user_and_top_tier_phone(db, tenant=tenant)
        monkeypatch.setattr(
            "app.config.settings.PROMOTION_CONFIRMATION_BATCH_SIZE", 2,
            raising=False,
        )
        # Three eligible.
        for i, name in enumerate(("A", "B", "C")):
            _make_candidate(
                db, tenant_id=tenant.id, entity_type="employee",
                raw_value=name, mention_count=10 - i, confidence=0.9,
            )
        db.commit()

        batch = P.compose_confirmation_for_tenant(
            tenant.id, db, now=EVENING_NOW,
        )

        assert batch is not None
        assert len(batch.candidate_ids) == 2
        # Top-N by mention_count desc - A and B win.
        assert "A" in batch.message_text
        assert "B" in batch.message_text
        assert "C" not in batch.message_text
        # C stays state='none' for tomorrow.
        c_obj = (
            db.query(ExtractionCandidate)
            .filter(ExtractionCandidate.raw_value == "C")
            .one()
        )
        assert c_obj.confirmation_state == "none"

    def test_q9_no_top_tier_phone_returns_none_with_critical_log(
        self, db, monkeypatch, caplog,
    ):
        import logging
        caplog.set_level(logging.CRITICAL, logger="app.services.promotion.promoter")
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        # Linked phone but role is 'manager' - NOT top-tier.
        _make_user_and_top_tier_phone(
            db, tenant=tenant, phone_role="manager",
        )
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Stranded", mention_count=5, confidence=0.9,
        )
        db.commit()

        batch = P.compose_confirmation_for_tenant(
            tenant.id, db, now=EVENING_NOW,
        )

        assert batch is None
        assert any(
            "no_top_tier" in r.message and r.levelname == "CRITICAL"
            for r in caplog.records
        )
        # Critically: candidate state UNCHANGED. Q9 hard-fail must not
        # leave the candidate hanging in 'pending'.
        db.refresh(c)
        assert c.confirmation_state == "none"

    def test_no_eligible_returns_none(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        _make_user_and_top_tier_phone(db, tenant=tenant)
        # No qualifying candidates.
        db.commit()

        batch = P.compose_confirmation_for_tenant(
            tenant.id, db, now=EVENING_NOW,
        )

        assert batch is None

    def test_picks_most_recent_top_tier_phone(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        # Two top-tier phones with different last_seen_at.
        _make_user_and_top_tier_phone(
            db, tenant=tenant, phone_number="+919000000001",
            last_seen_minutes_ago=100,
        )
        _make_user_and_top_tier_phone(
            db, tenant=tenant, phone_number="+919000000002",
            last_seen_minutes_ago=10,
        )
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Pick", mention_count=5, confidence=0.9,
        )
        db.commit()

        batch = P.compose_confirmation_for_tenant(
            tenant.id, db, now=EVENING_NOW,
        )

        assert batch is not None
        # The more-recent one wins.
        assert batch.recipient_phone == "+919000000002"


# ---------------------------------------------------------------------------
# record_confirmation_sent - message_id update + event
# ---------------------------------------------------------------------------

class TestRecordConfirmationSent:

    def test_writes_message_id_and_emits_requested_event(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Pending", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW,
        )
        db.commit()

        P.record_confirmation_sent(
            db,
            tenant_id=tenant.id,
            candidate_ids=[c.id],
            message_id="wamid.HBg123",
            recipient_user_id=42,
        )

        db.refresh(c)
        assert c.confirmation_message_id == "wamid.HBg123"
        ev = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == P.EVENT_CONFIRMATION_REQUESTED,
            )
            .one()
        )
        assert ev.payload["message_id"] == "wamid.HBg123"
        assert ev.payload["candidate_ids"] == [c.id]
        assert ev.payload["recipient_user_id"] == 42

    def test_no_message_id_still_emits_event(self, db, monkeypatch):
        """Send failure -> message_id=None; event still recorded for audit."""
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Pending", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW,
        )
        db.commit()

        P.record_confirmation_sent(
            db,
            tenant_id=tenant.id,
            candidate_ids=[c.id],
            message_id=None,
            recipient_user_id=42,
        )

        db.refresh(c)
        assert c.confirmation_message_id is None
        ev = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == P.EVENT_CONFIRMATION_REQUESTED,
            )
            .one()
        )
        assert ev.payload["message_id"] is None


# ---------------------------------------------------------------------------
# apply_confirmation_decisions - the actual insertion path
# ---------------------------------------------------------------------------

class TestApplyConfirmationDecisions:

    def test_confirmed_inserts_employee_with_full_payload(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Suresh", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW,
        )
        db.commit()

        summary = P.apply_confirmation_decisions(
            tenant.id, db,
            decisions={c.id: "confirmed"},
            message_id="wamid.HBg123",
            decided_by_user_id=42,
            parse_strategy="heuristic",
            raw_reply="haan",
        )

        assert summary.confirmed_inserted == 1
        # Real Employee row exists.
        emp = (
            db.query(Employee)
            .filter(Employee.tenant_id == tenant.id)
            .one()
        )
        assert emp.full_name == "Suresh"
        assert emp.source == "whatsapp_inferred"
        assert emp.worker_type == "permanent"
        # State flipped.
        db.refresh(c)
        assert c.confirmation_state == "confirmed"
        # Promoted event payload includes Q10 augmentations.
        ev = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == P.EVENT_PROMOTED,
            )
            .one()
        )
        assert ev.payload["confirmation_message_id"] == "wamid.HBg123"
        assert ev.payload["decided_by_user_id"] == 42
        assert ev.payload["promoted_to_id"] == emp.id

    def test_confirmed_inserts_machine(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="machine",
            raw_value="Heidelberg", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW,
        )
        db.commit()

        P.apply_confirmation_decisions(
            tenant.id, db,
            decisions={c.id: "confirmed"},
            message_id="wamid.X",
            decided_by_user_id=42,
            parse_strategy="heuristic",
            raw_reply="haan",
        )

        m = db.query(Machine).filter(Machine.tenant_id == tenant.id).one()
        assert m.name == "Heidelberg"
        assert m.source == "whatsapp_inferred"

    def test_rejected_flips_state_no_insert(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Nope", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW,
        )
        db.commit()

        summary = P.apply_confirmation_decisions(
            tenant.id, db,
            decisions={c.id: "rejected"},
            message_id="wamid.X",
            decided_by_user_id=42,
            parse_strategy="heuristic",
            raw_reply="nahi",
        )

        assert summary.rejected == 1
        assert summary.confirmed_inserted == 0
        db.refresh(c)
        assert c.confirmation_state == "rejected"
        assert (
            db.query(Employee)
            .filter(Employee.tenant_id == tenant.id)
            .count()
            == 0
        )

    def test_deferred_leaves_state_pending(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Maybe", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW,
        )
        db.commit()

        summary = P.apply_confirmation_decisions(
            tenant.id, db,
            decisions={c.id: "deferred"},
            message_id="wamid.X",
            decided_by_user_id=42,
            parse_strategy="fallback",
            raw_reply="kuch samajh nahi aaya",
        )

        assert summary.deferred == 1
        db.refresh(c)
        assert c.confirmation_state == "pending"

    def test_aggregate_received_event_emitted(self, db, monkeypatch):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c1 = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="A", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW,
        )
        c2 = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="B", mention_count=4, confidence=0.85,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW,
        )
        db.commit()

        P.apply_confirmation_decisions(
            tenant.id, db,
            decisions={c1.id: "confirmed", c2.id: "rejected"},
            message_id="wamid.X",
            decided_by_user_id=42,
            parse_strategy="heuristic",
            raw_reply="a haan, b nahi",
        )

        ev = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == P.EVENT_CONFIRMATION_RECEIVED,
            )
            .one()
        )
        assert ev.payload["message_id"] == "wamid.X"
        assert ev.payload["parse_strategy"] == "heuristic"
        assert ev.payload["reply_text"] == "a haan, b nahi"
        assert ev.payload["decisions"] == {
            str(c1.id): "confirmed",
            str(c2.id): "rejected",
        }

    def test_already_decided_candidate_counted_as_not_found(
        self, db, monkeypatch,
    ):
        """A late reply for a candidate already moved out of pending."""
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Stale", mention_count=5, confidence=0.9,
            confirmation_state="confirmed",  # already done
        )
        db.commit()

        summary = P.apply_confirmation_decisions(
            tenant.id, db,
            decisions={c.id: "confirmed"},
            message_id="wamid.X",
            decided_by_user_id=42,
            parse_strategy="heuristic",
            raw_reply="haan",
        )

        assert summary.confirmed_inserted == 0
        assert summary.not_found == 1


# ---------------------------------------------------------------------------
# find_inflight_batch_for_tenant - reply routing pre-flight
# ---------------------------------------------------------------------------

class TestFindInflightBatch:

    def test_returns_pending_within_48h(self, db, monkeypatch):
        tenant = make_tenant(db)
        c = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Recent", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW - timedelta(hours=4),
        )
        db.commit()

        batch = P.find_inflight_batch_for_tenant(db, tenant.id, now=EVENING_NOW)
        ids = [int(c.id) for c in batch]
        assert c.id in ids

    def test_excludes_pending_older_than_window(self, db, monkeypatch):
        tenant = make_tenant(db)
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Old", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW - timedelta(hours=72),
        )
        db.commit()

        batch = P.find_inflight_batch_for_tenant(db, tenant.id, now=EVENING_NOW)
        assert batch == []

    def test_only_returns_most_recent_message_id_group(self, db, monkeypatch):
        tenant = make_tenant(db)
        # Older batch (10h ago, msg id wamid.OLD).
        c_old = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="OldBatch", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW - timedelta(hours=10),
        )
        c_old.confirmation_message_id = "wamid.OLD"
        # Newer batch (1h ago, msg id wamid.NEW).
        c_new = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="NewBatch", mention_count=4, confidence=0.85,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW - timedelta(hours=1),
        )
        c_new.confirmation_message_id = "wamid.NEW"
        db.commit()

        batch = P.find_inflight_batch_for_tenant(db, tenant.id, now=EVENING_NOW)
        ids = [int(c.id) for c in batch]
        assert c_new.id in ids
        assert c_old.id not in ids


# ---------------------------------------------------------------------------
# send_confirmations_for_all_tenants - async fan-out
# ---------------------------------------------------------------------------

class TestSendConfirmationsAsync:

    @pytest.mark.asyncio
    async def test_fan_out_sends_one_message_per_eligible_tenant(
        self, db, monkeypatch,
    ):
        from tests.conftest import TestingSessionLocal

        tenant_a = make_tenant(db)
        tenant_b = make_tenant(db)
        _opt_in(monkeypatch, f"{tenant_a.id},{tenant_b.id}")
        _make_user_and_top_tier_phone(
            db, tenant=tenant_a, phone_number="+919000000010",
        )
        _make_user_and_top_tier_phone(
            db, tenant=tenant_b, phone_number="+919000000020",
        )
        _make_candidate(
            db, tenant_id=tenant_a.id, entity_type="employee",
            raw_value="WorkerA", mention_count=5, confidence=0.9,
        )
        _make_candidate(
            db, tenant_id=tenant_b.id, entity_type="employee",
            raw_value="WorkerB", mention_count=5, confidence=0.9,
        )
        db.commit()

        sent: list[tuple[str, str]] = []

        async def fake_sender(phone, message):
            sent.append((phone, message))
            return f"wamid.fake.{len(sent)}"

        aggregate = await P.send_confirmations_for_all_tenants(
            session_factory=TestingSessionLocal,
            per_tenant_timeout_s=10.0,
            sender=fake_sender,
        )

        # Both tenants got one message each.
        assert aggregate["batches_sent"] == 2
        assert aggregate["candidates_asked"] == 2
        assert len(sent) == 2
        phones_sent = {p for p, _ in sent}
        assert phones_sent == {"+919000000010", "+919000000020"}

        # Each tenant has one CONFIRMATION_REQUESTED event.
        for t in (tenant_a, tenant_b):
            n = (
                db.query(Event)
                .filter(
                    Event.tenant_id == t.id,
                    Event.event_type == P.EVENT_CONFIRMATION_REQUESTED,
                )
                .count()
            )
            assert n == 1

    @pytest.mark.asyncio
    async def test_q9_no_top_tier_phone_skips_tenant(self, db, monkeypatch):
        from tests.conftest import TestingSessionLocal

        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        # No phone linked at all.
        _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Stranded", mention_count=5, confidence=0.9,
        )
        db.commit()

        sent: list = []
        async def fake_sender(phone, message):
            sent.append((phone, message))
            return "wamid.fake"

        aggregate = await P.send_confirmations_for_all_tenants(
            session_factory=TestingSessionLocal,
            per_tenant_timeout_s=10.0,
            sender=fake_sender,
        )

        assert aggregate["batches_sent"] == 0
        assert aggregate["skipped_no_top_tier"] == 1
        assert len(sent) == 0


# ---------------------------------------------------------------------------
# Multi-tenant isolation (carry-over from original)
# ---------------------------------------------------------------------------

class TestTenantIsolation:

    def test_evaluate_only_touches_target_tenant(self, db, monkeypatch):
        tenant_a = make_tenant(db)
        tenant_b = make_tenant(db)
        _opt_in(monkeypatch, f"{tenant_a.id},{tenant_b.id}")
        ca = _make_candidate(
            db, tenant_id=tenant_a.id, entity_type="employee",
            raw_value="AOnly", mention_count=5, confidence=0.9,
        )
        cb = _make_candidate(
            db, tenant_id=tenant_b.id, entity_type="employee",
            raw_value="BOnly", mention_count=5, confidence=0.9,
        )
        db.commit()

        P.evaluate_for_tenant(tenant_a.id, db, now=FIXED_NOW)

        # Tenant B's candidate untouched.
        db.refresh(cb)
        assert cb.confirmation_state == "none"


# ---------------------------------------------------------------------------
# Failure isolation - DB / per-candidate / fan-out
# ---------------------------------------------------------------------------

class TestFailureIsolation:

    def test_apply_per_candidate_failure_does_not_block_others(
        self, db, monkeypatch,
    ):
        tenant = make_tenant(db)
        _opt_in(monkeypatch, str(tenant.id))
        good = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Good", mention_count=5, confidence=0.9,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW,
        )
        bad = _make_candidate(
            db, tenant_id=tenant.id, entity_type="employee",
            raw_value="Bad", mention_count=4, confidence=0.85,
            confirmation_state="pending",
            confirmation_asked_at=EVENING_NOW,
        )
        db.commit()

        original = P._insert_confirmed_employee
        seen: list[str] = []

        def flaky(candidate, db_, *, now, message_id, decided_by_user_id):
            seen.append(candidate.raw_value)
            if candidate.raw_value == "Bad":
                raise RuntimeError("synthetic failure")
            original(
                candidate, db_,
                now=now, message_id=message_id,
                decided_by_user_id=decided_by_user_id,
            )

        monkeypatch.setattr(P, "_insert_confirmed_employee", flaky)

        summary = P.apply_confirmation_decisions(
            tenant.id, db,
            decisions={good.id: "confirmed", bad.id: "confirmed"},
            message_id="wamid.X",
            decided_by_user_id=42,
            parse_strategy="heuristic",
            raw_reply="haan",
        )

        assert summary.confirmed_inserted == 1
        assert len(summary.errors) == 1
        assert "Good" in seen
        assert "Bad" in seen


# ---------------------------------------------------------------------------
# Per-industry happy path - sanity over the 5 verticals (carry-over)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("industry", [
    "printing", "manufacturing", "fabrication", "chemical", "field_service",
])
def test_evaluate_works_per_industry(db, monkeypatch, industry):
    tenant = make_tenant(db, industry_type=industry)
    _opt_in(monkeypatch, str(tenant.id))
    _make_candidate(
        db, tenant_id=tenant.id, entity_type="employee",
        raw_value=f"{industry}-worker", mention_count=5, confidence=0.9,
    )
    db.commit()

    summary = P.evaluate_for_tenant(tenant.id, db, now=FIXED_NOW)

    assert summary.ready_for_confirmation == 1


# ---------------------------------------------------------------------------
# Fan-out failure isolation across tenants
# ---------------------------------------------------------------------------

class TestFanOutFailureIsolation:

    @pytest.mark.asyncio
    async def test_evaluation_per_tenant_failure_does_not_block_others(
        self, db, monkeypatch,
    ):
        from tests.conftest import TestingSessionLocal

        tenant_a = make_tenant(db)
        tenant_b = make_tenant(db)
        _opt_in(monkeypatch, f"{tenant_a.id},{tenant_b.id}")
        _make_candidate(
            db, tenant_id=tenant_a.id, entity_type="employee",
            raw_value="ATenant", mention_count=5, confidence=0.9,
        )
        _make_candidate(
            db, tenant_id=tenant_b.id, entity_type="employee",
            raw_value="BTenant", mention_count=5, confidence=0.9,
        )
        db.commit()

        real_run = P._run_one_evaluation_sync
        call_log: list[int] = []

        def flaky(tenant_id, session_factory):
            call_log.append(tenant_id)
            if tenant_id == tenant_a.id:
                raise RuntimeError("synthetic failure")
            return real_run(tenant_id, session_factory)

        monkeypatch.setattr(P, "_run_one_evaluation_sync", flaky)

        aggregate = await P.evaluate_for_all_tenants(
            session_factory=TestingSessionLocal,
            per_tenant_timeout_s=10.0,
        )

        assert aggregate["tenants_processed"] == 2
        assert aggregate["errors"] >= 1
        # Tenant B still produced a ready_for_confirmation count.
        assert aggregate["ready_for_confirmation"] == 1
        assert tenant_a.id in call_log
        assert tenant_b.id in call_log
