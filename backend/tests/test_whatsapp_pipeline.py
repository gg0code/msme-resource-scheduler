# test_whatsapp_pipeline.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for intent detection pipeline functions.
# Original tests referenced detect_write_intent and parse_employee_name from
# the old app/services/whatsapp_pipeline.py. That file was refactored:
#   - detect_write_intent  -> app/services/whatsapp_intent.py (same name, v5.12 4-tuple return)
#   - parse_employee_name  -> _extract_employee_name in whatsapp_intent.py
#   - _resolve_date        -> _resolve_date in whatsapp_intent.py (unchanged)
# All tests use MagicMock for DB — no PostgreSQL required.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/services/whatsapp_intent.py  - detect_write_intent, _extract_employee_name, _resolve_date
#   app/services/whatsapp_actions.py - ActionType enum

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from app.services.whatsapp_intent import (
    detect_write_intent,
    _extract_employee_name,
    _resolve_date,
    ROLE_OWNER,
    ROLE_MANAGER,
    ROLE_OPERATOR,
)
from app.services.whatsapp_actions import ActionType


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_db(employee_return=None):
    """Build a mock SQLAlchemy Session. query().filter().first() returns employee_return."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = employee_return
    return mock_db


# ---------------------------------------------------------------------------
# _extract_employee_name  (was parse_employee_name)
# ---------------------------------------------------------------------------

class TestExtractEmployeeName:

    def test_extracts_capitalised_name(self):
        # Capitalised word that is not a keyword should be returned
        result = _extract_employee_name("Rajan nahi aaya aaj")
        assert result == "Rajan"

    def test_returns_none_for_only_keywords(self):
        # Message of only skip-words has no extractable name
        result = _extract_employee_name("nahi aaya absent hai")
        assert result is None

    def test_empty_message_returns_none(self):
        result = _extract_employee_name("")
        assert result is None

    def test_extracts_first_capitalised_non_keyword(self):
        result = _extract_employee_name("Suresh nahi aaya kal")
        assert result == "Suresh"

    def test_fallback_capitalises_first_non_keyword_word(self):
        # No capitalised words -> fallback capitalises first eligible word
        result = _extract_employee_name("ramesh absent hai")
        assert result == "Ramesh"

    def test_skips_words_shorter_than_3_chars(self):
        # Short words like "he", "is", "to" should not be returned as names
        result = _extract_employee_name("he is on leave")
        # "leave" is not in SKIP_WORDS and length > 2 -> capitalised fallback
        assert result == "Leave"

    def test_multi_name_returns_first(self):
        result = _extract_employee_name("Suresh aur Mahesh dono absent")
        assert result == "Suresh"


# ---------------------------------------------------------------------------
# _resolve_date
# ---------------------------------------------------------------------------

class TestResolveDate:

    def test_no_date_keyword_returns_today(self):
        result = _resolve_date("employee absent")
        assert result == str(date.today())

    def test_aaj_returns_today(self):
        result = _resolve_date("Rajan aaj absent hai")
        assert result == str(date.today())

    def test_today_keyword_returns_today(self):
        result = _resolve_date("absent today")
        assert result == str(date.today())

    def test_kal_returns_tomorrow(self):
        result = _resolve_date("Rajan kal nahi aayega")
        assert result == str(date.today() + timedelta(days=1))

    def test_tomorrow_keyword_returns_tomorrow(self):
        result = _resolve_date("absent tomorrow")
        assert result == str(date.today() + timedelta(days=1))

    def test_result_is_yyyy_mm_dd_format(self):
        result = _resolve_date("absent")
        parts = result.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4


# ---------------------------------------------------------------------------
# detect_write_intent
# ---------------------------------------------------------------------------

class TestDetectWriteIntent:

    def test_returns_4_tuple(self):
        db = _make_db()
        result = detect_write_intent(
            user_message="hello kya haal hai",
            tenant_id=1,
            db=db,
        )
        assert len(result) == 4

    def test_no_intent_returns_pass_through(self):
        # Plain query message: no role block, no write action
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="aaj ka schedule kya hai",
            tenant_id=1,
            db=db,
            phone_role=ROLE_OWNER,
        )
        assert blocked is False
        assert reply is None
        assert action is None
        assert params is None

    def test_absent_intent_employee_not_in_db(self):
        # "Rajan nahi aaya" -> MARK_ABSENT with employee_id=None when DB has no match
        db = _make_db(employee_return=None)
        blocked, reply, action, params = detect_write_intent(
            user_message="Rajan nahi aaya",
            tenant_id=1,
            db=db,
            phone_role=ROLE_OWNER,
        )
        assert blocked is False
        assert action == ActionType.MARK_ABSENT
        assert params is not None
        assert params["employee_name"] == "Rajan"
        assert params["employee_id"] is None

    def test_absent_intent_employee_found_in_db(self):
        # When DB returns an employee, employee_id is populated
        mock_emp = MagicMock()
        mock_emp.id = 42
        mock_emp.full_name = "Rajan Mehta"
        db = _make_db(employee_return=mock_emp)
        blocked, reply, action, params = detect_write_intent(
            user_message="Rajan nahi aaya",
            tenant_id=1,
            db=db,
            phone_role=ROLE_OWNER,
        )
        assert blocked is False
        assert action == ActionType.MARK_ABSENT
        assert params["employee_id"] == 42
        assert params["employee_name"] == "Rajan Mehta"

    def test_absent_params_contain_date(self):
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="Rajan nahi aaya",
            tenant_id=1,
            db=db,
            phone_role=ROLE_OWNER,
        )
        assert action == ActionType.MARK_ABSENT
        assert "date" in params
        assert params["date"] == str(date.today())

    def test_maintenance_intent_detected(self):
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="machine maintenance pe hai",
            tenant_id=1,
            db=db,
            phone_role=ROLE_OWNER,
        )
        assert blocked is False
        assert action == ActionType.MARK_MAINTENANCE
        assert params is not None

    def test_job_status_intent_detected(self):
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="job complete kar do",
            tenant_id=1,
            db=db,
            phone_role=ROLE_OWNER,
        )
        assert blocked is False
        assert action == ActionType.UPDATE_JOB_STATUS

    def test_operator_blocked_on_schedule_keyword(self):
        # Operator role: "schedule" is in OPERATOR_BLOCKED_KEYWORDS
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="schedule dekhao",
            tenant_id=1,
            db=db,
            phone_role=ROLE_OPERATOR,
        )
        assert blocked is True
        assert reply is not None
        assert len(reply) > 0
        assert action is None
        assert params is None

    def test_operator_blocked_on_financial_keyword(self):
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="salary kitna hai",
            tenant_id=1,
            db=db,
            phone_role=ROLE_OPERATOR,
        )
        assert blocked is True

    def test_manager_blocked_on_financial(self):
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="salary kitna hai",
            tenant_id=1,
            db=db,
            phone_role=ROLE_MANAGER,
        )
        assert blocked is True
        assert reply is not None

    def test_manager_blocked_on_create_keywords(self):
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="naya job banao",
            tenant_id=1,
            db=db,
            phone_role=ROLE_MANAGER,
        )
        assert blocked is True

    def test_manager_blocked_on_delete_keywords(self):
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="job delete karo",
            tenant_id=1,
            db=db,
            phone_role=ROLE_MANAGER,
        )
        assert blocked is True

    def test_owner_always_passes_role_gate(self):
        # Owner bypasses all role checks regardless of keywords
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="salary kitna hai sab ka",
            tenant_id=1,
            db=db,
            phone_role=ROLE_OWNER,
        )
        assert blocked is False

    def test_unknown_role_treated_as_operator(self):
        # Unrecognised role defaults to most restrictive (operator)
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="schedule dekhao",
            tenant_id=1,
            db=db,
            phone_role="unknown_role",
        )
        assert blocked is True

    def test_manager_allowed_on_attendance(self):
        # Manager can mark absent — not in blocked keyword sets
        db = _make_db(employee_return=None)
        blocked, reply, action, params = detect_write_intent(
            user_message="Rajan nahi aaya",
            tenant_id=1,
            db=db,
            phone_role=ROLE_MANAGER,
        )
        assert blocked is False
        assert action == ActionType.MARK_ABSENT

    def test_blocked_reply_is_string(self):
        # Block reply must be a non-empty string ready to send
        db = _make_db()
        blocked, reply, action, params = detect_write_intent(
            user_message="salary kitna hai",
            tenant_id=1,
            db=db,
            phone_role=ROLE_MANAGER,
        )
        assert blocked is True
        assert isinstance(reply, str)
        assert len(reply) > 0
