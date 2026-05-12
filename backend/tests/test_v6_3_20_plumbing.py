# tests/test_v6_3_20_plumbing.py
# Branch: v5-whatsapp
# Introduced: v6.3.20 part 2 (bridge + run_ai_chat plumbing)
#
# FILE PURPOSE
# Verifies the actor_user_id + phone_number plumbing from
# whatsapp.py:_process_inbound_message → whatsapp_bridge.process_message →
# ai_service.run_ai_chat → execute_tool. Without this plumbing the three
# v6.3.20 tools (update_push_setting / pause_push / get_push_settings)
# can't tell who the calling user is or where to stage the pending
# action — the write tools refuse with tool_requires_whatsapp_channel.
#
# These tests use MagicMock for the Groq client (mirroring the pattern in
# test_ai_service_tool_use_failed.py) so we don't need a live API key
# and the tool-call dispatch is fast and deterministic.
#
# SCOPE
# - run_ai_chat passes actor_user_id + phone_number to execute_tool
#   when given (WhatsApp path).
# - run_ai_chat defaults both to None when the caller doesn't pass them
#   (web-UI ai_chat path).
# - execute_tool's v6.3.20 write branches refuse with
#   tool_requires_whatsapp_channel when either kwarg is missing.
# - execute_tool's get_push_settings branch works without kwargs
#   (read-only — no staging needed).

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import ai_service


# ---------------------------------------------------------------------------
# Test helpers — minimal fake Groq tool-call response
# ---------------------------------------------------------------------------

def _make_tool_call_response(tool_name: str, args: dict, *, follow_up_text: str = "Done."):
    """Build a fake Groq response that triggers exactly one tool call."""
    tool_call = SimpleNamespace(
        id="call_test_1",
        function=SimpleNamespace(
            name=tool_name,
            arguments=json.dumps(args),
        ),
    )
    first_msg = SimpleNamespace(content=None, tool_calls=[tool_call])
    first_choice = SimpleNamespace(message=first_msg)
    first = SimpleNamespace(choices=[first_choice])

    second_msg = SimpleNamespace(content=follow_up_text, tool_calls=None)
    second_choice = SimpleNamespace(message=second_msg)
    second = SimpleNamespace(choices=[second_choice])
    return first, second


# ===========================================================================
# run_ai_chat plumbing — kwargs reach execute_tool
# ===========================================================================

def test_run_ai_chat_plumbs_actor_and_phone_to_execute_tool():
    """The WhatsApp path: bridge → run_ai_chat with both kwargs set →
    execute_tool sees them on every tool call."""
    fake_client = MagicMock()
    first, second = _make_tool_call_response(
        "get_push_settings", {"include_user_overrides": True},
        follow_up_text="Morning briefing 08:00.",
    )
    fake_client.chat.completions.create.side_effect = [first, second]
    fake_db = MagicMock()

    captured = {}

    def fake_execute_tool(name, args, db, tenant_id, *, actor_user_id=None, phone_number=None):
        captured["name"] = name
        captured["args"] = args
        captured["actor_user_id"] = actor_user_id
        captured["phone_number"] = phone_number
        return {"ok": True}

    with patch.object(ai_service, "get_groq_client", return_value=fake_client), \
         patch.object(ai_service, "_build_system_prompt", return_value="SYS"), \
         patch.object(ai_service, "execute_tool", side_effect=fake_execute_tool):
        ai_service.run_ai_chat(
            messages=[{"role": "user", "content": "morning briefing kab hai?"}],
            db=fake_db,
            tenant_id=12,
            industry_type="printing",
            actor_user_id=42,
            phone_number="+919876543210",
        )

    assert captured["name"] == "get_push_settings"
    assert captured["actor_user_id"] == 42, "actor_user_id did not reach execute_tool"
    assert captured["phone_number"] == "+919876543210", "phone_number did not reach execute_tool"


def test_run_ai_chat_defaults_actor_and_phone_to_none_for_web_ui_path():
    """The web-UI path (ai_chat router): no kwargs passed → execute_tool
    receives None for both. This is the security boundary that keeps the
    v6.3.20 write tools WhatsApp-channel-only."""
    fake_client = MagicMock()
    first, second = _make_tool_call_response(
        "get_delayed_jobs", {},  # any read-only existing tool works here
        follow_up_text="0 delayed.",
    )
    fake_client.chat.completions.create.side_effect = [first, second]
    fake_db = MagicMock()

    captured = {}

    def fake_execute_tool(name, args, db, tenant_id, *, actor_user_id=None, phone_number=None):
        captured["actor_user_id"] = actor_user_id
        captured["phone_number"] = phone_number
        return {"ok": True}

    with patch.object(ai_service, "get_groq_client", return_value=fake_client), \
         patch.object(ai_service, "_build_system_prompt", return_value="SYS"), \
         patch.object(ai_service, "execute_tool", side_effect=fake_execute_tool):
        ai_service.run_ai_chat(
            messages=[{"role": "user", "content": "any delayed jobs?"}],
            db=fake_db,
            tenant_id=12,
            industry_type="printing",
        )

    assert captured["actor_user_id"] is None
    assert captured["phone_number"] is None


# ===========================================================================
# execute_tool v6.3.20 branches — refusal + read-only behavior
# ===========================================================================

def test_execute_tool_update_push_setting_refuses_without_phone():
    """Web-UI-style call (no kwargs) must produce the typed refusal envelope.
    No DB queries, no service-module call, no staging."""
    fake_db = MagicMock()
    result = ai_service.execute_tool(
        "update_push_setting",
        {"field": "briefing_morning_time", "value": "08:00", "source_phrase": "x"},
        fake_db,
        tenant_id=12,
    )
    assert result["error"] == "tool_requires_whatsapp_channel"
    # Must NOT have hit the DB or push_settings_service.
    fake_db.assert_not_called()


def test_execute_tool_update_push_setting_refuses_with_only_actor():
    """Both kwargs are required — actor alone is not enough to identify
    the Redis namespace where the pending action gets staged."""
    fake_db = MagicMock()
    result = ai_service.execute_tool(
        "update_push_setting",
        {"field": "briefing_morning_time", "value": "08:00", "source_phrase": "x"},
        fake_db,
        tenant_id=12,
        actor_user_id=42,
        # phone_number omitted
    )
    assert result["error"] == "tool_requires_whatsapp_channel"


def test_execute_tool_update_push_setting_refuses_with_only_phone():
    """Phone alone isn't enough either — we need the actor to write the
    audit row and to enforce the top-tier role gate."""
    fake_db = MagicMock()
    result = ai_service.execute_tool(
        "update_push_setting",
        {"field": "briefing_morning_time", "value": "08:00", "source_phrase": "x"},
        fake_db,
        tenant_id=12,
        phone_number="+919876543210",
        # actor_user_id omitted
    )
    assert result["error"] == "tool_requires_whatsapp_channel"


def test_execute_tool_pause_push_refuses_without_phone_or_actor():
    fake_db = MagicMock()
    result = ai_service.execute_tool(
        "pause_push",
        {"days": 5, "source_phrase": "agle 5 din"},
        fake_db,
        tenant_id=12,
    )
    assert result["error"] == "tool_requires_whatsapp_channel"


def test_execute_tool_get_push_settings_works_without_phone(db):
    """Read tool is callable from any channel — no Redis staging needed,
    no audit row written. The desktop AI chat would route here for
    'what are my settings' queries.

    Uses the real `db` fixture (not MagicMock) because the read path
    actually hits push_settings_service.get_push_settings which queries
    the tenants table."""
    from datetime import datetime, time, timezone
    from app.models.auth import Tenant

    now = datetime.now(timezone.utc)
    t = Tenant(
        name="WebUI Tenant",
        slug=f"webui-{now.timestamp()}",
        plan="free",
        is_active=True,
        industry_type="printing",
        briefing_morning_enabled=True,
        briefing_morning_time=time(7, 30),
        briefing_evening_enabled=True,
        briefing_evening_time=time(18, 30),
        briefing_timezone="Asia/Kolkata",
        briefing_working_days="1,2,3,4,5,6",
        created_at=now,
        updated_at=now,
    )
    db.add(t)
    db.flush()

    result = ai_service.execute_tool(
        "get_push_settings",
        {"include_user_overrides": False},
        db,
        tenant_id=t.id,
        # actor_user_id and phone_number both None — web-UI path
    )

    assert "error" not in result
    assert result["tenant_id"] == t.id
    assert result["briefing_morning_time"] == "07:30"
    assert result["sections_editable_note"]  # the desktop-redirect hint is set
