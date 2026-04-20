# test_whatsapp_phase4.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for the Phase 4 confirmation state machine.
# Original tests referenced _send_confirmation from the old whatsapp_pipeline.py.
# That function is now split into:
#   - build_confirmation_prompt()  in app/services/whatsapp_actions.py
#   - store_pending_action()       in app/services/whatsapp_actions.py
# Phase 4 also covers is_confirmation / is_cancellation detection and the
# full Redis pending-action lifecycle (store -> get -> clear).
#
# All tests use mock Redis (_mock_sessions in-memory dict) — no Upstash needed.
# Async functions are executed via asyncio.run() to avoid pytest-asyncio config.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/services/whatsapp_actions.py  - all public confirmation functions + ActionType
#   app/services/whatsapp_session.py  - _mock_sessions (cleared between tests)

import asyncio
import pytest

from app.services.whatsapp_actions import (
    ActionType,
    CONFIRMATION_WORDS,
    CANCELLATION_WORDS,
    is_confirmation,
    is_cancellation,
    build_confirmation_prompt,
    store_pending_action,
    get_pending_action,
    clear_pending_action,
)
from app.services.whatsapp_session import _mock_sessions


PHONE = "+919876543210"


@pytest.fixture(autouse=True)
def clear_sessions():
    """Wipe the in-memory mock session store before and after every test."""
    _mock_sessions.clear()
    yield
    _mock_sessions.clear()


# ---------------------------------------------------------------------------
# is_confirmation
# ---------------------------------------------------------------------------

class TestIsConfirmation:

    def test_haan_is_confirmation(self):
        assert is_confirmation("haan") is True

    def test_yes_is_confirmation(self):
        assert is_confirmation("yes") is True

    def test_ok_is_confirmation(self):
        assert is_confirmation("ok") is True

    def test_confirm_is_confirmation(self):
        assert is_confirmation("confirm") is True

    def test_bilkul_is_confirmation(self):
        assert is_confirmation("bilkul") is True

    def test_nahi_not_confirmation(self):
        assert is_confirmation("nahi") is False

    def test_random_text_not_confirmation(self):
        assert is_confirmation("schedule kya hai") is False

    def test_empty_string_not_confirmation(self):
        assert is_confirmation("") is False

    def test_case_insensitive_haan(self):
        assert is_confirmation("HAAN") is True

    def test_case_insensitive_yes(self):
        assert is_confirmation("YES") is True

    def test_prefix_match_haan_kar_do(self):
        # "haan kar do" starts with a confirmation word
        assert is_confirmation("haan kar do") is True

    def test_prefix_match_yes_please(self):
        assert is_confirmation("yes please") is True

    def test_all_confirmation_words_return_true(self):
        for word in CONFIRMATION_WORDS:
            assert is_confirmation(word) is True, f"Expected True for '{word}'"


# ---------------------------------------------------------------------------
# is_cancellation
# ---------------------------------------------------------------------------

class TestIsCancellation:

    def test_nahi_is_cancellation(self):
        assert is_cancellation("nahi") is True

    def test_no_is_cancellation(self):
        assert is_cancellation("no") is True

    def test_cancel_is_cancellation(self):
        assert is_cancellation("cancel") is True

    def test_ruko_is_cancellation(self):
        assert is_cancellation("ruko") is True

    def test_haan_not_cancellation(self):
        assert is_cancellation("haan") is False

    def test_random_text_not_cancellation(self):
        assert is_cancellation("schedule dekhao") is False

    def test_empty_string_not_cancellation(self):
        assert is_cancellation("") is False

    def test_case_insensitive_nahi(self):
        assert is_cancellation("NAHI") is True

    def test_case_insensitive_no(self):
        assert is_cancellation("NO") is True

    def test_all_cancellation_words_return_true(self):
        for word in CANCELLATION_WORDS:
            assert is_cancellation(word) is True, f"Expected True for '{word}'"

    def test_confirmation_and_cancellation_do_not_overlap(self):
        # No word should match both
        overlap = CONFIRMATION_WORDS & CANCELLATION_WORDS
        assert len(overlap) == 0, f"Overlap found: {overlap}"


# ---------------------------------------------------------------------------
# build_confirmation_prompt  (was _send_confirmation)
# ---------------------------------------------------------------------------

class TestBuildConfirmationPrompt:

    def test_absent_prompt_contains_employee_name(self):
        prompt = build_confirmation_prompt(
            action_type=ActionType.MARK_ABSENT,
            action_params={"employee_name": "Rajan", "date": "2026-04-20"},
        )
        assert "Rajan" in prompt

    def test_absent_prompt_contains_date(self):
        prompt = build_confirmation_prompt(
            action_type=ActionType.MARK_ABSENT,
            action_params={"employee_name": "Rajan", "date": "2026-04-20"},
        )
        assert "2026-04-20" in prompt

    def test_maintenance_prompt_contains_machine_name(self):
        prompt = build_confirmation_prompt(
            action_type=ActionType.MARK_MAINTENANCE,
            action_params={"machine_name": "Heidelberg"},
        )
        assert "Heidelberg" in prompt

    def test_job_status_prompt_contains_job_name(self):
        prompt = build_confirmation_prompt(
            action_type=ActionType.UPDATE_JOB_STATUS,
            action_params={"job_name": "Print Order 5", "new_status": "completed"},
        )
        assert "Print Order 5" in prompt

    def test_reschedule_prompt_contains_job_name(self):
        prompt = build_confirmation_prompt(
            action_type=ActionType.RESCHEDULE_JOB,
            action_params={"job_name": "Job #12", "new_start_date": "2026-05-01"},
        )
        assert "Job #12" in prompt

    def test_create_job_prompt_contains_job_name(self):
        prompt = build_confirmation_prompt(
            action_type=ActionType.CREATE_JOB,
            action_params={"job_name": "New Print Run"},
        )
        assert "New Print Run" in prompt

    def test_prompt_instructs_haan_to_confirm(self):
        # Owner must know to reply HAAN to confirm
        prompt = build_confirmation_prompt(
            action_type=ActionType.MARK_ABSENT,
            action_params={"employee_name": "Rajan", "date": "2026-04-20"},
        )
        assert "HAAN" in prompt

    def test_prompt_instructs_nahi_to_cancel(self):
        # Owner must know to reply NAHI to cancel
        prompt = build_confirmation_prompt(
            action_type=ActionType.MARK_ABSENT,
            action_params={"employee_name": "Rajan", "date": "2026-04-20"},
        )
        assert "NAHI" in prompt

    def test_prompt_is_non_empty_string(self):
        prompt = build_confirmation_prompt(
            action_type=ActionType.MARK_ABSENT,
            action_params={},
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_empty_params_do_not_raise(self):
        # Missing params should fall back gracefully, not raise
        for action in ActionType:
            prompt = build_confirmation_prompt(action_type=action, action_params={})
            assert isinstance(prompt, str)


# ---------------------------------------------------------------------------
# Pending action state machine  (async, uses mock Redis via _mock_sessions)
# ---------------------------------------------------------------------------

class TestPendingActionStorage:

    def test_store_and_retrieve_pending_action(self):
        async def _run():
            stored = await store_pending_action(
                phone_number=PHONE,
                action_type=ActionType.MARK_ABSENT,
                action_params={"employee_name": "Rajan", "date": "2026-04-20"},
            )
            assert stored is True
            retrieved = await get_pending_action(phone_number=PHONE)
            assert retrieved is not None
            assert retrieved["action_type"] == ActionType.MARK_ABSENT.value
            assert retrieved["action_params"]["employee_name"] == "Rajan"
        asyncio.run(_run())

    def test_no_pending_action_returns_none(self):
        async def _run():
            result = await get_pending_action(phone_number="+910000000000")
            assert result is None
        asyncio.run(_run())

    def test_clear_removes_pending_action(self):
        async def _run():
            await store_pending_action(
                phone_number=PHONE,
                action_type=ActionType.MARK_MAINTENANCE,
                action_params={"machine_id": 5, "machine_name": "Heidelberg"},
            )
            cleared = await clear_pending_action(phone_number=PHONE)
            assert cleared is True
            retrieved = await get_pending_action(phone_number=PHONE)
            assert retrieved is None
        asyncio.run(_run())

    def test_pending_action_has_required_fields(self):
        async def _run():
            await store_pending_action(
                phone_number=PHONE,
                action_type=ActionType.UPDATE_JOB_STATUS,
                action_params={"job_id": 1, "new_status": "completed"},
            )
            retrieved = await get_pending_action(phone_number=PHONE)
            assert "action_type" in retrieved
            assert "action_params" in retrieved
            assert "phone_number" in retrieved
            assert "proposed_at" in retrieved
        asyncio.run(_run())

    def test_action_type_stored_as_string(self):
        # Enum must be serialised to its .value string for JSON storage
        async def _run():
            await store_pending_action(
                phone_number=PHONE,
                action_type=ActionType.MARK_ABSENT,
                action_params={"employee_name": "Rajan"},
            )
            retrieved = await get_pending_action(phone_number=PHONE)
            assert isinstance(retrieved["action_type"], str)
            assert retrieved["action_type"] == "mark_absent"
        asyncio.run(_run())

    def test_different_phones_have_separate_state(self):
        async def _run():
            phone_a = "+919000000001"
            phone_b = "+919000000002"
            await store_pending_action(
                phone_number=phone_a,
                action_type=ActionType.MARK_ABSENT,
                action_params={"employee_name": "Rajan"},
            )
            result_b = await get_pending_action(phone_number=phone_b)
            assert result_b is None
        asyncio.run(_run())

    def test_overwrite_replaces_existing_action(self):
        async def _run():
            await store_pending_action(
                phone_number=PHONE,
                action_type=ActionType.MARK_ABSENT,
                action_params={"employee_name": "Rajan"},
            )
            await store_pending_action(
                phone_number=PHONE,
                action_type=ActionType.UPDATE_JOB_STATUS,
                action_params={"job_id": 3},
            )
            retrieved = await get_pending_action(phone_number=PHONE)
            assert retrieved["action_type"] == "update_job_status"
        asyncio.run(_run())

    def test_clear_nonexistent_action_returns_true(self):
        # Clearing when nothing is stored should not raise, should return True
        async def _run():
            result = await clear_pending_action(phone_number="+910000000000")
            assert result is True
        asyncio.run(_run())
