# test_whatsapp_checkin_attendance_events.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.11-prereq tests: verify save_checkin_state() also persists an
# attendance.recorded Event row alongside the existing Redis SETEX, so
# the v6.3.11 attendance signals can read 7+ days of history.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/services/whatsapp_checkin.py  - save_checkin_state, get_checkin_state
#   app/models/event.py               - Event ORM
#
# KEY DESIGN DECISIONS
#   1. SQLite in-memory + StaticPool — same tier-1 pattern as
#      test_whatsapp_checkin.py and test_signup_v6_4.py.
#   2. patch_now_defaults_for_sqlite mirrors test_signup_v6_4.py /
#      test_team_management.py / test_team_invite_v6_3_5.py — the autouse
#      fixture swaps text("now()") server defaults to CURRENT_TIMESTAMP so
#      Event.created_at can be inserted under SQLite.
#   3. Redis side is exercised in mock mode (_mock_sessions dict) — no
#      Upstash needed.

import logging
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text as sa_text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.schema import DefaultClause

from app.database import Base
from app.models.event import Event


# ---------------------------------------------------------------------------
# SQLite engine — column types (JSONB → JSON) are patched at conftest import
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite:///:memory:"


def _make_engine():
    return create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    """Swap text("now()") server defaults to CURRENT_TIMESTAMP for SQLite.

    Same pattern as tests/test_signup_v6_4.py and tests/test_team_management.py
    — kept local so this file is self-contained.
    """
    patched = []
    for col in Event.__table__.columns:
        if col.server_default is None:
            continue
        arg = getattr(col.server_default, "arg", None)
        text_value = str(arg) if arg is not None else ""
        if "now()" in text_value.lower():
            patched.append((col, col.server_default))
            col.server_default = DefaultClause(sa_text("CURRENT_TIMESTAMP"))
    yield
    for col, original in patched:
        col.server_default = original


@pytest.fixture()
def db_session():
    """In-memory SQLite session with all tables created. Rolled back per-test."""
    engine = _make_engine()
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.rollback()
    db.close()
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clear_mock_sessions():
    """Clear Redis mock dict between tests — no state bleed across cases."""
    from app.services.whatsapp_session import _mock_sessions
    _mock_sessions.clear()
    yield
    _mock_sessions.clear()


# ---------------------------------------------------------------------------
# TEST CLASS — attendance.recorded event persistence
# ---------------------------------------------------------------------------

class TestSaveCheckinStateAttendanceEvent:
    """v6.3.11-prereq: save_checkin_state() must append an attendance.recorded
    Event row whenever a db session is supplied."""

    def test_save_checkin_state_writes_attendance_event(self, db_session):
        from app.services.whatsapp_checkin import save_checkin_state

        today = date.today()
        save_checkin_state(
            tenant_id=12,
            absent_ids=[1, 2],
            down_machine_ids=[5],
            for_date=today,
            db=db_session,
            manager_user_id=42,
        )

        events = (
            db_session.query(Event)
            .filter(Event.event_type == "attendance.recorded")
            .all()
        )
        assert len(events) == 1
        ev = events[0]
        assert ev.tenant_id == 12
        assert ev.entity_type == "checkin"
        assert ev.entity_id is None
        assert ev.actor_user_id == 42
        assert ev.source == "whatsapp"
        assert ev.payload["for_date"] == today.isoformat()
        assert ev.payload["absent_employee_ids"] == [1, 2]
        assert ev.payload["down_machine_ids"] == [5]

    def test_save_checkin_state_with_no_absences(self, db_session):
        """A check-in with all-present is still meaningful attendance data —
        the Event row must be written with empty arrays in the payload."""
        from app.services.whatsapp_checkin import save_checkin_state

        today = date.today()
        save_checkin_state(
            tenant_id=12,
            absent_ids=[],
            down_machine_ids=[],
            for_date=today,
            db=db_session,
            manager_user_id=42,
        )

        events = (
            db_session.query(Event)
            .filter(Event.event_type == "attendance.recorded")
            .all()
        )
        assert len(events) == 1
        ev = events[0]
        assert ev.payload["absent_employee_ids"] == []
        assert ev.payload["down_machine_ids"] == []

    def test_save_checkin_state_redis_succeeds_when_event_write_fails(
        self, caplog
    ):
        """Redis is the source of truth for the live check-in flow; an
        event-write failure must be logged but never raised."""
        from app.services.whatsapp_checkin import (
            save_checkin_state,
            get_checkin_state,
        )

        today = date.today()
        broken_db = MagicMock()
        broken_db.commit.side_effect = RuntimeError("simulated DB failure")

        with caplog.at_level(
            logging.ERROR, logger="app.services.whatsapp_checkin"
        ):
            # Must not raise
            save_checkin_state(
                tenant_id=12,
                absent_ids=[7],
                down_machine_ids=[],
                for_date=today,
                db=broken_db,
                manager_user_id=99,
            )

        # Redis write still happened — independent of the event-write failure
        state = get_checkin_state(tenant_id=12, for_date=today)
        assert state["absent_ids"] == [7]

        # An error was logged for the event-write failure
        assert "attendance.recorded" in caplog.text
        # Rollback was attempted on the broken session
        broken_db.rollback.assert_called()

    def test_save_checkin_state_idempotency(self, db_session):
        """Two check-ins on the same date for the same tenant must produce
        two Event rows. Deduplication happens at signal-evaluation time,
        not at write time — every check-in is recorded."""
        from app.services.whatsapp_checkin import save_checkin_state

        today = date.today()
        save_checkin_state(
            tenant_id=12,
            absent_ids=[1],
            down_machine_ids=[],
            for_date=today,
            db=db_session,
            manager_user_id=42,
        )
        save_checkin_state(
            tenant_id=12,
            absent_ids=[1],
            down_machine_ids=[],
            for_date=today,
            db=db_session,
            manager_user_id=42,
        )

        events = (
            db_session.query(Event)
            .filter(
                Event.event_type == "attendance.recorded",
                Event.tenant_id == 12,
            )
            .all()
        )
        assert len(events) == 2
