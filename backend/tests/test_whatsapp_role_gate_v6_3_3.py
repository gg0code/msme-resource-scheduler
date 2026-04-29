# tests/test_whatsapp_role_gate_v6_3_3.py
#
# FILE PURPOSE
# v6.3.3 regression + extension tests for the role gate in
# detect_write_intent() (app/services/whatsapp_intent.py). The v5.12
# behaviour (3 roles: owner / manager / operator) is covered by
# tests/test_role_limiting.py - this file adds the v6.3.3 extensions:
#   - top-tier roles other than 'owner' (proprietor / factory_manager /
#     co_owner) all pass the gate unconditionally
#   - 'scheduler' (legacy synonym for 'manager') gets manager-level gating
#   - operator / viewer still receive most-restrictive gating
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.whatsapp_intent.detect_write_intent
#   app.services.whatsapp_intent.{PHONE_TOP_TIER_ROLES, PHONE_MID_TIER_ROLES}
#
# DESIGN NOTES
# - DB session is mocked because the role gate fires before any DB query
#   in all blocked cases. Same pattern as test_role_limiting.py.

from unittest.mock import MagicMock

import pytest

from app.services.whatsapp_intent import (
    PHONE_MID_TIER_ROLES, PHONE_TOP_TIER_ROLES, detect_write_intent,
)


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# v6.3.3 top-tier extension - new top-tier roles get owner treatment
# ---------------------------------------------------------------------------

class TestTopTierPassesUnconditionally:

    @pytest.mark.parametrize("role", sorted(PHONE_TOP_TIER_ROLES))
    def test_role_passes_financial_query(self, mock_db, role):
        blocked, reply, _, _ = detect_write_intent(
            "salary kitna hai", tenant_id=1, db=mock_db,
            phone_role=role, language="hinglish",
        )
        assert blocked is False
        assert reply is None

    @pytest.mark.parametrize("role", sorted(PHONE_TOP_TIER_ROLES))
    def test_role_passes_create_query(self, mock_db, role):
        blocked, reply, _, _ = detect_write_intent(
            "create new order", tenant_id=1, db=mock_db,
            phone_role=role, language="english",
        )
        assert blocked is False
        assert reply is None

    @pytest.mark.parametrize("role", sorted(PHONE_TOP_TIER_ROLES))
    def test_role_passes_delete_query(self, mock_db, role):
        blocked, reply, _, _ = detect_write_intent(
            "delete this job", tenant_id=1, db=mock_db,
            phone_role=role, language="english",
        )
        assert blocked is False
        assert reply is None


# ---------------------------------------------------------------------------
# v6.3.3 mid-tier extension - 'scheduler' synonym for 'manager'
# ---------------------------------------------------------------------------

class TestMidTierGatesAsManager:

    @pytest.mark.parametrize("role", sorted(PHONE_MID_TIER_ROLES))
    def test_mid_tier_blocked_on_financial(self, mock_db, role):
        blocked, reply, _, _ = detect_write_intent(
            "kitna salary hai", tenant_id=1, db=mock_db,
            phone_role=role, language="hinglish",
        )
        assert blocked is True
        assert reply is not None

    @pytest.mark.parametrize("role", sorted(PHONE_MID_TIER_ROLES))
    def test_mid_tier_blocked_on_delete(self, mock_db, role):
        blocked, reply, _, _ = detect_write_intent(
            "delete this job", tenant_id=1, db=mock_db,
            phone_role=role, language="english",
        )
        assert blocked is True
        assert reply is not None

    @pytest.mark.parametrize("role", sorted(PHONE_MID_TIER_ROLES))
    def test_mid_tier_passes_attendance_query(self, mock_db, role):
        # Attendance-style messages have no financial / create / delete
        # tokens, so manager AND scheduler both pass.
        blocked, reply, _, _ = detect_write_intent(
            "Rajan nahi aaya aaj", tenant_id=1, db=mock_db,
            phone_role=role, language="hinglish",
        )
        assert blocked is False
        assert reply is None


# ---------------------------------------------------------------------------
# Unknown role - safety fallback
# ---------------------------------------------------------------------------

class TestUnknownRoleSafety:

    def test_unknown_role_treated_as_operator(self, mock_db):
        # 'guest' is not in any tier set. Should be most-restrictive.
        blocked, reply, _, _ = detect_write_intent(
            "delete this job", tenant_id=1, db=mock_db,
            phone_role="guest", language="english",
        )
        assert blocked is True
        assert reply is not None

    def test_unknown_role_passes_innocuous_query(self, mock_db):
        # No write/financial keywords - even unknown role passes.
        blocked, reply, _, _ = detect_write_intent(
            "hello", tenant_id=1, db=mock_db,
            phone_role="guest", language="english",
        )
        assert blocked is False
        assert reply is None
