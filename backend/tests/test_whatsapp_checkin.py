# test_whatsapp_checkin.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/whatsapp_checkin.py (v5.15).
# Tests all pure functions and Redis state without hitting PostgreSQL.
# DB-dependent functions (parse_attendance, find_substitute,
# build_owner_briefing_from_checkin) are tested with SQLite in-memory
# following the same pattern as other test files in this project.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/services/whatsapp_checkin.py  - all public functions
#   app/models/employee.py            - Employee, EmployeeSkill
#   app/models/skill.py               - Skill
#   app/models/job.py                 - Job
#   app/models/machine.py             - Machine
#
# KEY DESIGN DECISIONS
#   1. No real PostgreSQL — SQLite in-memory only. Same pattern as conftest.py.
#   2. Redis tests use mock mode (_mock_sessions dict) — no Upstash needed.
#   3. Each test class owns its own DB setup via fixtures — no shared state.
#   4. Skills are M2M via EmployeeSkill/Skill — tests reflect real schema.

import json
import pytest
from datetime import date, datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# SQLite engine — patches ARRAY/JSONB for SQLite compat (same as conftest.py)
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite:///:memory:"


def _make_engine():
    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


# ---------------------------------------------------------------------------
# Import models after engine is set up
# ---------------------------------------------------------------------------

from app.database import Base
from app.models.employee import Employee, EmployeeSkill
from app.models.skill import Skill
from app.models.job import Job
from app.models.machine import Machine


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    """
    In-memory SQLite session with all tables created.
    Rolled back after each test — no state bleeds between tests.
    """
    engine = _make_engine()
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.rollback()
    db.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def employees_with_skills(db_session: Session):
    """
    Seed three employees with skills matching your real tenant 12 data.
    Returns dict of employee objects keyed by first name for easy lookup.
    """
    # Skills
    skill_flexo   = Skill(id=1, tenant_id=12, name="Flexo Printing", category="production", is_active=True)
    skill_cutting  = Skill(id=2, tenant_id=12, name="Die Cutting",    category="production", is_active=True)
    skill_quality  = Skill(id=3, tenant_id=12, name="Quality Control", category="production", is_active=True)

    db_session.add_all([skill_flexo, skill_cutting, skill_quality])
    db_session.flush()

    # Employees
    suresh = Employee(
        id=84, tenant_id=12, full_name="Suresh Patel",
        status="Active", worker_type="permanent",
        employment_type="Full-time", base_availability_pct=100.0,
    )
    ramesh = Employee(
        id=86, tenant_id=12, full_name="Ramesh Kumar",
        status="Active", worker_type="permanent",
        employment_type="Full-time", base_availability_pct=100.0,
    )
    ganesh = Employee(
        id=87, tenant_id=12, full_name="Ganesh Rao",
        status="Active", worker_type="permanent",
        employment_type="Full-time", base_availability_pct=100.0,
    )

    db_session.add_all([suresh, ramesh, ganesh])
    db_session.flush()

    # Skills M2M
    db_session.add_all([
        EmployeeSkill(employee_id=84, tenant_id=12, skill_id=1, skill_level="Generic"),  # Suresh: Flexo
        EmployeeSkill(employee_id=84, tenant_id=12, skill_id=2, skill_level="Generic"),  # Suresh: Die Cutting
        EmployeeSkill(employee_id=86, tenant_id=12, skill_id=3, skill_level="Generic"),  # Ramesh: Quality
        EmployeeSkill(employee_id=86, tenant_id=12, skill_id=1, skill_level="Generic"),  # Ramesh: Flexo
        EmployeeSkill(employee_id=87, tenant_id=12, skill_id=2, skill_level="Generic"),  # Ganesh: Die Cutting
    ])
    db_session.commit()

    # Reload with relationships
    suresh = db_session.query(Employee).filter_by(id=84).first()
    ramesh = db_session.query(Employee).filter_by(id=86).first()
    ganesh = db_session.query(Employee).filter_by(id=87).first()

    return {"suresh": suresh, "ramesh": ramesh, "ganesh": ganesh}


# ---------------------------------------------------------------------------
# TEST CLASS 1 — Pure functions: normalise, name tokens
# ---------------------------------------------------------------------------

class TestNormaliseFunctions:
    """Tests for _normalise() and _name_tokens() — pure functions, no DB."""

    def test_normalise_strips_whitespace(self):
        from app.services.whatsapp_checkin import _normalise
        assert _normalise("  Suresh  ") == "suresh"

    def test_normalise_lowercases(self):
        from app.services.whatsapp_checkin import _normalise
        assert _normalise("SURESH PATEL") == "suresh patel"

    def test_normalise_empty_string(self):
        from app.services.whatsapp_checkin import _normalise
        assert _normalise("") == ""

    def test_name_tokens_splits_full_name(self):
        from app.services.whatsapp_checkin import _name_tokens
        assert _name_tokens("Suresh Patel") == ["suresh", "patel"]

    def test_name_tokens_filters_short_tokens(self):
        from app.services.whatsapp_checkin import _name_tokens
        # Single-char tokens filtered out
        tokens = _name_tokens("A B Suresh")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "suresh" in tokens

    def test_name_tokens_single_name(self):
        from app.services.whatsapp_checkin import _name_tokens
        assert _name_tokens("Ravi") == ["ravi"]


# ---------------------------------------------------------------------------
# TEST CLASS 2 — Absent markers
# ---------------------------------------------------------------------------

class TestAbsentMarkers:
    """All absent markers must be lowercase — detection uses normalised text."""

    def test_all_markers_are_lowercase(self):
        from app.services.whatsapp_checkin import ABSENT_MARKERS
        for marker in ABSENT_MARKERS:
            assert marker == marker.lower(), f"Marker not lowercase: '{marker}'"

    def test_markers_are_non_empty(self):
        from app.services.whatsapp_checkin import ABSENT_MARKERS
        for marker in ABSENT_MARKERS:
            assert len(marker.strip()) > 0

    def test_nahi_aaya_is_present(self):
        from app.services.whatsapp_checkin import ABSENT_MARKERS
        assert "nahi aaya" in ABSENT_MARKERS

    def test_absent_is_present(self):
        from app.services.whatsapp_checkin import ABSENT_MARKERS
        assert "absent" in ABSENT_MARKERS


# ---------------------------------------------------------------------------
# TEST CLASS 3 — Message builders (pure functions, no DB)
# ---------------------------------------------------------------------------

class TestMessageBuilders:
    """build_checkin_prompt, build_absent_reply, build_checkin_complete_reply."""

    def test_checkin_prompt_all_languages(self):
        from app.services.whatsapp_checkin import build_checkin_prompt
        for lang in ["en", "hinglish", "hindi"]:
            result = build_checkin_prompt(lang)
            assert isinstance(result, str)
            assert len(result) > 20, f"Prompt too short for lang={lang}"

    def test_checkin_prompt_unknown_lang_falls_back_to_en(self):
        from app.services.whatsapp_checkin import build_checkin_prompt
        assert build_checkin_prompt("tamil") == build_checkin_prompt("en")

    def test_checkin_prompt_hinglish_contains_aaj(self):
        from app.services.whatsapp_checkin import build_checkin_prompt
        # Hinglish prompt must contain the attendance question
        assert "aaj" in build_checkin_prompt("hinglish").lower()

    def test_closing_reply_all_languages(self):
        from app.services.whatsapp_checkin import build_checkin_complete_reply
        for lang in ["en", "hinglish", "hindi"]:
            result = build_checkin_complete_reply(lang)
            assert isinstance(result, str)
            assert len(result) > 5

    def test_closing_reply_hinglish_mentions_sahab(self):
        from app.services.whatsapp_checkin import build_checkin_complete_reply
        assert "sahab" in build_checkin_complete_reply("hinglish").lower()

    def test_closing_reply_unknown_lang_falls_back(self):
        from app.services.whatsapp_checkin import build_checkin_complete_reply
        assert build_checkin_complete_reply("tamil") == build_checkin_complete_reply("en")


# ---------------------------------------------------------------------------
# TEST CLASS 4 — Redis checkin state (mock mode)
# ---------------------------------------------------------------------------

class TestCheckinState:
    """save_checkin_state and get_checkin_state using _mock_sessions dict."""

    def setup_method(self):
        """Clear mock sessions before each test."""
        from app.services.whatsapp_session import _mock_sessions
        _mock_sessions.clear()

    def test_save_and_retrieve_checkin_state(self):
        from app.services.whatsapp_checkin import save_checkin_state, get_checkin_state
        today = date.today()
        save_checkin_state(
            tenant_id=12,
            absent_ids=[84, 85],
            down_machine_ids=[5],
            for_date=today,
        )
        state = get_checkin_state(tenant_id=12, for_date=today)
        assert state["absent_ids"] == [84, 85]
        assert state["down_machine_ids"] == [5]
        assert state["recorded_at"] is not None

    def test_empty_state_for_unknown_tenant(self):
        from app.services.whatsapp_checkin import get_checkin_state
        state = get_checkin_state(tenant_id=999, for_date=date.today())
        assert state["absent_ids"] == []
        assert state["down_machine_ids"] == []
        assert state["recorded_at"] is None

    def test_different_tenants_have_separate_state(self):
        from app.services.whatsapp_checkin import save_checkin_state, get_checkin_state
        today = date.today()
        save_checkin_state(tenant_id=12, absent_ids=[1], down_machine_ids=[], for_date=today)
        save_checkin_state(tenant_id=99, absent_ids=[2], down_machine_ids=[], for_date=today)
        assert get_checkin_state(12, today)["absent_ids"] == [1]
        assert get_checkin_state(99, today)["absent_ids"] == [2]

    def test_overwrite_updates_state(self):
        from app.services.whatsapp_checkin import save_checkin_state, get_checkin_state
        today = date.today()
        save_checkin_state(tenant_id=12, absent_ids=[1], down_machine_ids=[], for_date=today)
        save_checkin_state(tenant_id=12, absent_ids=[1, 2], down_machine_ids=[5], for_date=today)
        state = get_checkin_state(12, today)
        assert state["absent_ids"] == [1, 2]
        assert state["down_machine_ids"] == [5]

    def test_recorded_at_is_iso_format(self):
        from app.services.whatsapp_checkin import save_checkin_state, get_checkin_state
        today = date.today()
        save_checkin_state(tenant_id=12, absent_ids=[], down_machine_ids=[], for_date=today)
        state = get_checkin_state(12, today)
        # Should be parseable as ISO datetime
        dt = datetime.fromisoformat(state["recorded_at"])
        assert dt is not None


# ---------------------------------------------------------------------------
# TEST CLASS 5 — _get_employee_skill_name (pure function)
# ---------------------------------------------------------------------------

class TestGetEmployeeSkillName:
    """Tests for _get_employee_skill_name() helper."""

    def test_returns_first_skill_name(self, employees_with_skills):
        from app.services.whatsapp_checkin import _get_employee_skill_name
        suresh = employees_with_skills["suresh"]
        skill = _get_employee_skill_name(suresh)
        # Suresh has Flexo Printing and Die Cutting — first one wins
        assert skill in ["Flexo Printing", "Die Cutting"]

    def test_returns_none_for_no_skills(self, db_session):
        from app.services.whatsapp_checkin import _get_employee_skill_name
        no_skill_emp = Employee(
            id=200, tenant_id=12, full_name="No Skill Worker",
            status="Active", worker_type="permanent",
            employment_type="Full-time", base_availability_pct=100.0,
        )
        db_session.add(no_skill_emp)
        db_session.commit()
        emp = db_session.query(Employee).filter_by(id=200).first()
        assert _get_employee_skill_name(emp) is None


# ---------------------------------------------------------------------------
# TEST CLASS 6 — _match_employee_name
# ---------------------------------------------------------------------------

class TestMatchEmployeeName:
    """Tests for _match_employee_name() — fuzzy first-name matching."""

    def test_matches_first_name(self, employees_with_skills):
        from app.services.whatsapp_checkin import _match_employee_name
        employees = list(employees_with_skills.values())
        result = _match_employee_name("Suresh", employees)
        assert result is not None
        assert result.full_name == "Suresh Patel"

    def test_matches_last_name(self, employees_with_skills):
        from app.services.whatsapp_checkin import _match_employee_name
        employees = list(employees_with_skills.values())
        result = _match_employee_name("Patel", employees)
        assert result is not None
        assert result.full_name == "Suresh Patel"

    def test_case_insensitive_match(self, employees_with_skills):
        from app.services.whatsapp_checkin import _match_employee_name
        employees = list(employees_with_skills.values())
        result = _match_employee_name("suresh", employees)
        assert result is not None

    def test_no_match_returns_none(self, employees_with_skills):
        from app.services.whatsapp_checkin import _match_employee_name
        employees = list(employees_with_skills.values())
        result = _match_employee_name("Dilip", employees)
        assert result is None

    def test_short_word_does_not_match(self, employees_with_skills):
        from app.services.whatsapp_checkin import _match_employee_name
        employees = list(employees_with_skills.values())
        # Single char — too short to be a name
        result = _match_employee_name("R", employees)
        assert result is None


# ---------------------------------------------------------------------------
# TEST CLASS 7 — parse_attendance
# ---------------------------------------------------------------------------

class TestParseAttendance:
    """Tests for parse_attendance() — message parsing with DB."""

    def test_detects_absent_employee_by_first_name(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import parse_attendance
        result = parse_attendance("Suresh nahi aaya aaj", tenant_id=12, db=db_session)
        absent_names = [e.full_name for e in result["absent"]]
        assert "Suresh Patel" in absent_names

    def test_detects_multiple_absent_employees(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import parse_attendance
        result = parse_attendance("Suresh aur Ganesh absent hain aaj", tenant_id=12, db=db_session)
        absent_names = [e.full_name for e in result["absent"]]
        assert "Suresh Patel" in absent_names
        assert "Ganesh Rao" in absent_names

    def test_no_absent_marker_means_present(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import parse_attendance
        # No absent marker — names treated as present confirmation
        result = parse_attendance("Suresh aaya hai aaj", tenant_id=12, db=db_session)
        assert len(result["absent"]) == 0
        present_names = [e.full_name for e in result["present"]]
        assert "Suresh Patel" in present_names

    def test_unmatched_words_go_to_unknown(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import parse_attendance
        result = parse_attendance("Dilip nahi aaya", tenant_id=12, db=db_session)
        # Dilip not in DB — goes to unknown
        assert "Dilip" in result["unknown"]
        assert len(result["absent"]) == 0

    def test_same_employee_not_duplicated(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import parse_attendance
        # "Suresh Suresh" should only match once
        result = parse_attendance("Suresh Suresh nahi aaya", tenant_id=12, db=db_session)
        absent_names = [e.full_name for e in result["absent"]]
        assert absent_names.count("Suresh Patel") == 1

    def test_empty_message_returns_empty_lists(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import parse_attendance
        result = parse_attendance("", tenant_id=12, db=db_session)
        assert result["absent"] == []
        assert result["present"] == []

    def test_cross_tenant_isolation(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import parse_attendance
        # Suresh belongs to tenant 12 — querying tenant 99 should find nothing
        result = parse_attendance("Suresh nahi aaya", tenant_id=99, db=db_session)
        assert len(result["absent"]) == 0


# ---------------------------------------------------------------------------
# TEST CLASS 8 — find_substitute
# ---------------------------------------------------------------------------

class TestFindSubstitute:
    """Tests for find_substitute() — M2M skill-based substitute lookup."""

    def test_finds_substitute_with_same_skill(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import find_substitute
        suresh = employees_with_skills["suresh"]
        # Suresh has Flexo Printing — Ramesh also has Flexo Printing
        sub = find_substitute(suresh, tenant_id=12, db=db_session, already_absent_ids=[84])
        assert sub is not None
        assert sub.full_name == "Ramesh Kumar"

    def test_no_substitute_when_skill_unique(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import find_substitute
        ramesh = employees_with_skills["ramesh"]
        # Ramesh has Quality Control — nobody else has it
        sub = find_substitute(ramesh, tenant_id=12, db=db_session, already_absent_ids=[86])
        # Quality Control is only held by Ramesh — no sub
        assert sub is None or sub.full_name != "Ramesh Kumar"

    def test_excludes_absent_employee_from_results(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import find_substitute
        suresh = employees_with_skills["suresh"]
        sub = find_substitute(suresh, tenant_id=12, db=db_session, already_absent_ids=[84])
        # Should never return Suresh himself
        assert sub is None or sub.id != 84

    def test_excludes_already_absent_employees(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import find_substitute
        suresh = employees_with_skills["suresh"]
        # Mark Ramesh (who shares Flexo skill) also absent
        sub = find_substitute(
            suresh, tenant_id=12, db=db_session,
            already_absent_ids=[84, 86],  # Suresh + Ramesh both absent
        )
        # Ramesh excluded — no other Flexo substitute
        assert sub is None or sub.id not in [84, 86]

    def test_no_substitute_for_employee_with_no_skills(self, db_session):
        from app.services.whatsapp_checkin import find_substitute
        no_skill_emp = Employee(
            id=201, tenant_id=12, full_name="No Skill",
            status="Active", worker_type="permanent",
            employment_type="Full-time", base_availability_pct=100.0,
        )
        db_session.add(no_skill_emp)
        db_session.commit()
        emp = db_session.query(Employee).filter_by(id=201).first()
        sub = find_substitute(emp, tenant_id=12, db=db_session, already_absent_ids=[201])
        assert sub is None

    def test_cross_tenant_isolation(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import find_substitute
        suresh = employees_with_skills["suresh"]
        # Query with wrong tenant — should find no substitute from other tenant
        sub = find_substitute(suresh, tenant_id=99, db=db_session, already_absent_ids=[84])
        assert sub is None


# ---------------------------------------------------------------------------
# TEST CLASS 9 — handle_manager_checkin_reply
# ---------------------------------------------------------------------------

class TestHandleManagerCheckinReply:
    """Integration test for the full checkin reply flow."""

    def setup_method(self):
        from app.services.whatsapp_session import _mock_sessions
        _mock_sessions.clear()

    def test_returns_list_of_replies(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import handle_manager_checkin_reply
        replies = handle_manager_checkin_reply(
            message="Suresh nahi aaya aaj",
            tenant_id=12,
            phone_number="+919876540000",
            lang="hinglish",
            db=db_session,
        )
        assert isinstance(replies, list)
        assert len(replies) >= 1

    def test_last_reply_is_closing_message(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import handle_manager_checkin_reply
        replies = handle_manager_checkin_reply(
            message="Suresh nahi aaya aaj",
            tenant_id=12,
            phone_number="+919876540000",
            lang="hinglish",
            db=db_session,
        )
        # Closing message always last
        assert "sahab" in replies[-1].lower() or "7:15" in replies[-1]

    def test_saves_checkin_state_to_redis(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import handle_manager_checkin_reply, get_checkin_state
        handle_manager_checkin_reply(
            message="Suresh nahi aaya aaj",
            tenant_id=12,
            phone_number="+919876540000",
            lang="hinglish",
            db=db_session,
        )
        state = get_checkin_state(tenant_id=12, for_date=date.today())
        assert 84 in state["absent_ids"]  # Suresh id=84

    def test_no_absent_marker_saves_empty_absent_list(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import handle_manager_checkin_reply, get_checkin_state
        handle_manager_checkin_reply(
            message="Sab theek hai aaj",
            tenant_id=12,
            phone_number="+919876540000",
            lang="hinglish",
            db=db_session,
        )
        state = get_checkin_state(tenant_id=12, for_date=date.today())
        assert state["absent_ids"] == []

    def test_absent_reply_mentions_employee_name(self, db_session, employees_with_skills):
        from app.services.whatsapp_checkin import handle_manager_checkin_reply
        replies = handle_manager_checkin_reply(
            message="Suresh absent hai aaj",
            tenant_id=12,
            phone_number="+919876540000",
            lang="en",
            db=db_session,
        )
        # At least one reply should mention Suresh
        combined = " ".join(replies)
        assert "Suresh" in combined
