# tests/services/test_timeout_handler.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/promotion/timeout_handler.py (v6.3.15
# revised). Covers the 7-day re-ask / 21-day auto-reject cycle:
#   - 7d pending -> re-ask (state='none', retry_count+1, asked_at=None)
#   - retry-count cap hit -> auto-reject (state='rejected')
#   - confirmed before timeout -> no-op
#   - rejected before timeout -> no-op
#   - within window -> not_yet_due, no state change
#   - missing asked_at -> treated as due (defensive)
#   - emits one extraction.confirmation_timeout event per transition
#   - per-candidate failure isolation

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.event import Event
from app.models.extraction_candidate import ExtractionCandidate
from app.services.promotion import timeout_handler as TH

from tests.services.conftest import make_tenant


FIXED_NOW = datetime(2026, 5, 15, 19, 0, 0, tzinfo=timezone.utc)


def _make_pending_candidate(
    db,
    *,
    tenant_id: int,
    asked_days_ago: float | None = 8.0,
    retry_count: int = 0,
    raw_value: str = "Suresh",
    state: str = "pending",
) -> ExtractionCandidate:
    """Stage one pending ExtractionCandidate."""
    asked_at = (
        FIXED_NOW - timedelta(days=asked_days_ago)
        if asked_days_ago is not None else None
    )
    c = ExtractionCandidate(
        tenant_id=tenant_id,
        entity_type="employee",
        raw_value=raw_value,
        normalized_value=raw_value.lower(),
        confidence=0.9,
        mention_count=5,
        first_seen=FIXED_NOW - timedelta(days=10),
        last_seen=FIXED_NOW - timedelta(days=10),
        source_type="whatsapp",
        confirmation_state=state,
        confirmation_asked_at=asked_at,
        confirmation_message_id=("mock_wamid_existing" if state == "pending" else None),
        confirmation_retry_count=retry_count,
    )
    db.add(c)
    db.flush()
    return c


# ---------------------------------------------------------------------------
# Re-ask path
# ---------------------------------------------------------------------------

class TestReAskPath:

    def test_pending_8_days_old_gets_re_asked(self, db):
        tenant = make_tenant(db)
        c = _make_pending_candidate(
            db, tenant_id=tenant.id, asked_days_ago=8.0, retry_count=0,
        )
        db.commit()

        summary = TH.process_timeouts_for_tenant(
            tenant.id, db, now=FIXED_NOW,
        )

        assert summary.scanned == 1
        assert summary.re_asked == 1
        assert summary.auto_rejected == 0
        db.refresh(c)
        assert c.confirmation_state == "none"
        assert c.confirmation_retry_count == 1
        assert c.confirmation_asked_at is None
        assert c.confirmation_message_id is None

    def test_pending_within_window_is_not_yet_due(self, db):
        tenant = make_tenant(db)
        c = _make_pending_candidate(
            db, tenant_id=tenant.id, asked_days_ago=2.0, retry_count=0,
        )
        db.commit()

        summary = TH.process_timeouts_for_tenant(
            tenant.id, db, now=FIXED_NOW,
        )

        assert summary.scanned == 1
        assert summary.not_yet_due == 1
        assert summary.re_asked == 0
        db.refresh(c)
        assert c.confirmation_state == "pending"
        assert c.confirmation_retry_count == 0

    def test_re_ask_emits_timeout_event_with_re_asked_action(self, db):
        tenant = make_tenant(db)
        c = _make_pending_candidate(
            db, tenant_id=tenant.id, asked_days_ago=8.0, retry_count=0,
        )
        db.commit()

        TH.process_timeouts_for_tenant(tenant.id, db, now=FIXED_NOW)

        ev = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == TH.EVENT_CONFIRMATION_TIMEOUT,
            )
            .one()
        )
        assert ev.entity_id == c.id
        assert ev.payload["action"] == TH.ACTION_RE_ASKED
        assert ev.payload["retry_count"] == 1


# ---------------------------------------------------------------------------
# Auto-reject path
# ---------------------------------------------------------------------------

class TestAutoRejectPath:

    def test_third_strike_auto_rejects(self, db, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.PROMOTION_CONFIRMATION_MAX_RETRIES", 3,
            raising=False,
        )
        tenant = make_tenant(db)
        c = _make_pending_candidate(
            db, tenant_id=tenant.id, asked_days_ago=8.0, retry_count=2,
        )
        db.commit()

        summary = TH.process_timeouts_for_tenant(
            tenant.id, db, now=FIXED_NOW,
        )

        # retry_count goes 2 -> 3, hits cap -> auto-reject.
        assert summary.scanned == 1
        assert summary.auto_rejected == 1
        assert summary.re_asked == 0
        db.refresh(c)
        assert c.confirmation_state == "rejected"
        assert c.confirmation_retry_count == 3

    def test_auto_reject_emits_event_with_auto_rejected_action(self, db, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.PROMOTION_CONFIRMATION_MAX_RETRIES", 3,
            raising=False,
        )
        tenant = make_tenant(db)
        c = _make_pending_candidate(
            db, tenant_id=tenant.id, asked_days_ago=8.0, retry_count=2,
        )
        db.commit()

        TH.process_timeouts_for_tenant(tenant.id, db, now=FIXED_NOW)

        ev = (
            db.query(Event)
            .filter(
                Event.tenant_id == tenant.id,
                Event.event_type == TH.EVENT_CONFIRMATION_TIMEOUT,
            )
            .one()
        )
        assert ev.entity_id == c.id
        assert ev.payload["action"] == TH.ACTION_AUTO_REJECTED
        assert ev.payload["retry_count"] == 3


# ---------------------------------------------------------------------------
# Already-decided candidates - no-op
# ---------------------------------------------------------------------------

class TestNoOpStates:

    def test_confirmed_candidate_not_touched(self, db):
        tenant = make_tenant(db)
        c = _make_pending_candidate(
            db, tenant_id=tenant.id,
            asked_days_ago=30.0,  # very old
            retry_count=0,
            state="confirmed",
        )
        db.commit()

        summary = TH.process_timeouts_for_tenant(
            tenant.id, db, now=FIXED_NOW,
        )

        # 'confirmed' is not in the pending filter -> 0 scanned.
        assert summary.scanned == 0
        db.refresh(c)
        assert c.confirmation_state == "confirmed"

    def test_rejected_candidate_not_touched(self, db):
        tenant = make_tenant(db)
        c = _make_pending_candidate(
            db, tenant_id=tenant.id,
            asked_days_ago=30.0,
            retry_count=0,
            state="rejected",
        )
        db.commit()

        summary = TH.process_timeouts_for_tenant(
            tenant.id, db, now=FIXED_NOW,
        )

        assert summary.scanned == 0
        db.refresh(c)
        assert c.confirmation_state == "rejected"

    def test_no_pending_candidates_at_all(self, db):
        tenant = make_tenant(db)
        db.commit()

        summary = TH.process_timeouts_for_tenant(
            tenant.id, db, now=FIXED_NOW,
        )

        assert summary.scanned == 0
        assert summary.re_asked == 0
        assert summary.auto_rejected == 0


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------

class TestDefensivePaths:

    def test_missing_asked_at_treated_as_due(self, db):
        """A pending row with NULL asked_at should be re-asked, not leaked."""
        tenant = make_tenant(db)
        c = _make_pending_candidate(
            db, tenant_id=tenant.id, asked_days_ago=None,  # NULL asked_at
            retry_count=0,
        )
        db.commit()

        summary = TH.process_timeouts_for_tenant(
            tenant.id, db, now=FIXED_NOW,
        )

        assert summary.scanned == 1
        assert summary.re_asked == 1
        db.refresh(c)
        assert c.confirmation_state == "none"

    def test_per_candidate_failure_does_not_block_others(self, db, monkeypatch):
        tenant = make_tenant(db)
        c_good = _make_pending_candidate(
            db, tenant_id=tenant.id, asked_days_ago=8.0,
            raw_value="Good", retry_count=0,
        )
        c_bad = _make_pending_candidate(
            db, tenant_id=tenant.id, asked_days_ago=8.0,
            raw_value="Bad", retry_count=0,
        )
        db.commit()

        # Force the second emit to raise.
        original_emit = TH._emit_timeout_event
        seen: list[int] = []

        def flaky_emit(db_, *, tenant_id, candidate_id, **kw):
            seen.append(candidate_id)
            if candidate_id == c_bad.id:
                raise RuntimeError("synthetic event-emit failure")
            original_emit(
                db_, tenant_id=tenant_id, candidate_id=candidate_id, **kw,
            )

        monkeypatch.setattr(TH, "_emit_timeout_event", flaky_emit)

        summary = TH.process_timeouts_for_tenant(
            tenant.id, db, now=FIXED_NOW,
        )

        # Good candidate processed; bad candidate failure recorded.
        assert summary.scanned == 2
        assert summary.re_asked == 1
        assert len(summary.errors) == 1
        # Both attempted.
        assert c_good.id in seen
        assert c_bad.id in seen
        db.refresh(c_good)
        assert c_good.confirmation_state == "none"
