# test_role_limiting.py - Version 1.0
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for the role gate added to detect_write_intent() in v5.12.
# Covers: owner always passes, manager blocked on financial/create/delete,
# operator blocked on write keywords, unknown role treated as operator.
# All tests are pure - no DB, no HTTP. DB session is mocked because the
# role gate fires before any DB query in all blocked cases.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/services/whatsapp_intent.py    - detect_write_intent()
#   app/services/whatsapp_responses.py - get_response()

from unittest.mock import MagicMock

import pytest

from app.services.whatsapp_intent import (
    ROLE_MANAGER,
    ROLE_OPERATOR,
    ROLE_OWNER,
    detect_write_intent,
)
from app.services.whatsapp_responses import get_response


@pytest.fixture
def mock_db() -> MagicMock:
    """
    Provides a mock SQLAlchemy Session.

    Called by:   all test methods in this file via pytest fixture injection.
    Calls:       MagicMock() - no real DB connection.
    Returns:     MagicMock instance that accepts any attribute access.
    Side effects: None.
    """
    return MagicMock()


class TestOwnerAlwaysPasses:
    """Owner has no restrictions - role gate never fires for any message."""

    def test_owner_passes_financial_query(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "salary kitna hai", tenant_id=1, db=mock_db,
            phone_role=ROLE_OWNER, language="hinglish",
        )
        assert blocked is False
        assert reply is None

    def test_owner_passes_delete_query(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "delete this job", tenant_id=1, db=mock_db,
            phone_role=ROLE_OWNER, language="english",
        )
        assert blocked is False
        assert reply is None

    def test_owner_passes_create_query(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "create new order", tenant_id=1, db=mock_db,
            phone_role=ROLE_OWNER, language="english",
        )
        assert blocked is False
        assert reply is None

    def test_owner_passes_empty_message(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "", tenant_id=1, db=mock_db,
            phone_role=ROLE_OWNER, language="english",
        )
        assert blocked is False
        assert reply is None


class TestManagerBlocking:
    """Manager blocked from financial, create, delete. Attendance/view passes."""

    def test_manager_blocked_on_cost(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "what is the cost of this job", tenant_id=1, db=mock_db,
            phone_role=ROLE_MANAGER, language="english",
        )
        assert blocked is True
        assert reply == get_response("role_blocked", "english")

    def test_manager_blocked_on_salary_hinglish(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "salary report dikhao", tenant_id=1, db=mock_db,
            phone_role=ROLE_MANAGER, language="hinglish",
        )
        assert blocked is True
        assert reply == get_response("role_blocked", "hinglish")

    def test_manager_blocked_on_revenue(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "revenue kitna hua", tenant_id=1, db=mock_db,
            phone_role=ROLE_MANAGER, language="hinglish",
        )
        assert blocked is True
        assert reply is not None

    def test_manager_blocked_on_create(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "create a new job for client", tenant_id=1, db=mock_db,
            phone_role=ROLE_MANAGER, language="english",
        )
        assert blocked is True

    def test_manager_blocked_on_delete(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "delete this order", tenant_id=1, db=mock_db,
            phone_role=ROLE_MANAGER, language="english",
        )
        assert blocked is True

    def test_manager_blocked_on_hatao(self, mock_db: MagicMock) -> None:
        blocked, _, _, _ = detect_write_intent(
            "ye job hatao", tenant_id=1, db=mock_db,
            phone_role=ROLE_MANAGER, language="hinglish",
        )
        assert blocked is True

    def test_manager_blocked_reply_localised_hindi(self, mock_db: MagicMock) -> None:
        """Blocked reply must be in Hindi when language='hindi'."""
        blocked, reply, _, _ = detect_write_intent(
            "salary dikhao", tenant_id=1, db=mock_db,
            phone_role=ROLE_MANAGER, language="hindi",
        )
        assert blocked is True
        assert reply == get_response("role_blocked", "hindi")

    def test_manager_allowed_on_schedule_view(self, mock_db: MagicMock) -> None:
        """Manager asking what work is on today - no blocked keywords."""
        blocked, reply, _, _ = detect_write_intent(
            "aaj ka kaam kya hai", tenant_id=1, db=mock_db,
            phone_role=ROLE_MANAGER, language="hinglish",
        )
        assert blocked is False
        assert reply is None

    def test_manager_allowed_general_query(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "aaj kaun kaun aaya", tenant_id=1, db=mock_db,
            phone_role=ROLE_MANAGER, language="hinglish",
        )
        assert blocked is False
        assert reply is None


class TestOperatorBlocking:
    """Operator blocked from all write/financial. Own-query passes."""

    def test_operator_blocked_on_schedule(self, mock_db: MagicMock) -> None:
        blocked, _, _, _ = detect_write_intent(
            "schedule dikhao", tenant_id=1, db=mock_db,
            phone_role=ROLE_OPERATOR, language="hinglish",
        )
        assert blocked is True

    def test_operator_blocked_on_assign(self, mock_db: MagicMock) -> None:
        blocked, _, _, _ = detect_write_intent(
            "assign Raju to machine", tenant_id=1, db=mock_db,
            phone_role=ROLE_OPERATOR, language="english",
        )
        assert blocked is True

    def test_operator_blocked_on_financial(self, mock_db: MagicMock) -> None:
        blocked, _, _, _ = detect_write_intent(
            "mera wage kitna hai", tenant_id=1, db=mock_db,
            phone_role=ROLE_OPERATOR, language="hinglish",
        )
        assert blocked is True

    def test_operator_blocked_on_all_query(self, mock_db: MagicMock) -> None:
        blocked, _, _, _ = detect_write_intent(
            "sab ka kaam dikhao", tenant_id=1, db=mock_db,
            phone_role=ROLE_OPERATOR, language="hinglish",
        )
        assert blocked is True

    def test_operator_allowed_own_work_english(self, mock_db: MagicMock) -> None:
        """Operator asking about own work - no blocked keywords."""
        blocked, reply, _, _ = detect_write_intent(
            "what is my work today", tenant_id=1, db=mock_db,
            phone_role=ROLE_OPERATOR, language="english",
        )
        assert blocked is False
        assert reply is None

    def test_operator_allowed_mera_kaam(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "mera kaam kya hai", tenant_id=1, db=mock_db,
            phone_role=ROLE_OPERATOR, language="hinglish",
        )
        assert blocked is False
        assert reply is None


class TestUnknownRole:
    """Unknown roles default to operator restrictions (most restrictive)."""

    def test_unknown_role_blocked_on_schedule(self, mock_db: MagicMock) -> None:
        blocked, _, _, _ = detect_write_intent(
            "schedule all jobs", tenant_id=1, db=mock_db,
            phone_role="supervisor",
            language="english",
        )
        assert blocked is True

    def test_unknown_role_allowed_own_query(self, mock_db: MagicMock) -> None:
        blocked, reply, _, _ = detect_write_intent(
            "what is my work today", tenant_id=1, db=mock_db,
            phone_role="unknown_role",
            language="english",
        )
        assert blocked is False
        assert reply is None


class TestReturnTupleContract:
    """Verify the 4-tuple return contract is correct in all cases."""

    def test_blocked_case_tuple_shape(self, mock_db: MagicMock) -> None:
        """When blocked: (True, str, None, None)."""
        blocked, block_reply, action_type, action_params = detect_write_intent(
            "salary dikhao", tenant_id=1, db=mock_db,
            phone_role=ROLE_MANAGER, language="hinglish",
        )
        assert blocked is True
        assert isinstance(block_reply, str)
        assert len(block_reply) > 0
        assert action_type is None
        assert action_params is None

    def test_read_query_tuple_shape(self, mock_db: MagicMock) -> None:
        """When not blocked and no write intent: (False, None, None, None)."""
        blocked, block_reply, action_type, action_params = detect_write_intent(
            "aaj ka kaam kya hai", tenant_id=1, db=mock_db,
            phone_role=ROLE_OWNER, language="hinglish",
        )
        assert blocked is False
        assert block_reply is None
