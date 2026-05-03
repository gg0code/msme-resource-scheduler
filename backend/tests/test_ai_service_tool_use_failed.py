# test_ai_service_tool_use_failed.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for the v6.3.9 tool_use_failed retry path in
# app/services/ai_service.py::run_ai_chat.
#
# Background: Llama 3.3 70B on Groq sometimes emits XML-style
# `<function=name>{json}</function>` markup in the content channel. Groq's
# wrapper detects malformed markup and rejects with HTTP 400
# code='tool_use_failed'. v6.3.9 catches this, retries without tools, and
# returns the retry response so the user gets a real answer (no live data,
# but no error either).
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/services/ai_service.py - run_ai_chat,
#                                _is_tool_use_failed,
#                                _extract_failed_generation

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from groq import BadRequestError

from app.services import ai_service


def _make_bad_request(body: dict) -> BadRequestError:
    """Build a Groq BadRequestError with the given body, plus a stub httpx Response."""
    fake_response = httpx.Response(status_code=400, request=httpx.Request("POST", "http://x"))
    return BadRequestError(message="Error code: 400", response=fake_response, body=body)


def _make_chat_completion(content: str, tool_calls=None):
    """Build a minimal Groq ChatCompletion-like response object."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


# ---------------------------------------------------------------------------
# Helper coverage — _is_tool_use_failed and _extract_failed_generation
# ---------------------------------------------------------------------------

def test_is_tool_use_failed_top_level_code():
    err = _make_bad_request({"code": "tool_use_failed", "failed_generation": "<function=x>"})
    assert ai_service._is_tool_use_failed(err) is True


def test_is_tool_use_failed_nested_under_error():
    err = _make_bad_request({"error": {"code": "tool_use_failed", "failed_generation": "<function=x>"}})
    assert ai_service._is_tool_use_failed(err) is True


def test_is_tool_use_failed_other_code_returns_false():
    err = _make_bad_request({"code": "rate_limit_exceeded"})
    assert ai_service._is_tool_use_failed(err) is False


def test_is_tool_use_failed_no_body_returns_false():
    err = _make_bad_request({})
    assert ai_service._is_tool_use_failed(err) is False


def test_extract_failed_generation_top_level():
    err = _make_bad_request({"code": "tool_use_failed", "failed_generation": "<function=foo>{}</function>"})
    assert ai_service._extract_failed_generation(err) == "<function=foo>{}</function>"


def test_extract_failed_generation_nested():
    err = _make_bad_request({"error": {"failed_generation": "<function=bar>"}})
    assert ai_service._extract_failed_generation(err) == "<function=bar>"


def test_extract_failed_generation_truncates_long_payload():
    huge = "x" * 1000
    err = _make_bad_request({"failed_generation": huge})
    assert len(ai_service._extract_failed_generation(err)) == 500


# ---------------------------------------------------------------------------
# run_ai_chat retry path — the actual v6.3.9 fix
# ---------------------------------------------------------------------------

def test_run_ai_chat_retries_without_tools_on_tool_use_failed():
    """When Groq raises tool_use_failed on the first call, run_ai_chat should
    retry without tools and return the retry response's content."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _make_bad_request({"code": "tool_use_failed", "failed_generation": "<function=oops>"}),
        _make_chat_completion("Sorry, I can't fetch live data right now."),
    ]
    fake_db = MagicMock()

    with patch.object(ai_service, "get_groq_client", return_value=fake_client), \
         patch.object(ai_service, "_build_system_prompt", return_value="SYS"):
        result = ai_service.run_ai_chat(
            messages=[{"role": "user", "content": "Next job kab schedule kar sakta hoon"}],
            db=fake_db,
            tenant_id=12,
            industry_type="printing",
        )

    assert result == "Sorry, I can't fetch live data right now."
    # First call should pass tools=, retry should not.
    assert fake_client.chat.completions.create.call_count == 2
    first_kwargs = fake_client.chat.completions.create.call_args_list[0].kwargs
    retry_kwargs = fake_client.chat.completions.create.call_args_list[1].kwargs
    assert "tools" in first_kwargs
    assert "tools" not in retry_kwargs


def test_run_ai_chat_retry_returns_fallback_when_retry_content_is_empty():
    """If the retry call returns empty content too, return a graceful fallback string
    rather than None (which would crash the WhatsApp formatter)."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _make_bad_request({"code": "tool_use_failed"}),
        _make_chat_completion(None),
    ]
    fake_db = MagicMock()

    with patch.object(ai_service, "get_groq_client", return_value=fake_client), \
         patch.object(ai_service, "_build_system_prompt", return_value="SYS"):
        result = ai_service.run_ai_chat(
            messages=[{"role": "user", "content": "hi"}],
            db=fake_db,
            tenant_id=12,
            industry_type="printing",
        )

    assert isinstance(result, str)
    assert result  # non-empty fallback


def test_run_ai_chat_other_bad_request_errors_still_bubble_up():
    """Non-tool_use_failed BadRequestErrors should propagate so the caller
    handles them (e.g. rate limits, auth failures)."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = _make_bad_request(
        {"code": "rate_limit_exceeded"}
    )
    fake_db = MagicMock()

    with patch.object(ai_service, "get_groq_client", return_value=fake_client), \
         patch.object(ai_service, "_build_system_prompt", return_value="SYS"):
        with pytest.raises(BadRequestError):
            ai_service.run_ai_chat(
                messages=[{"role": "user", "content": "hi"}],
                db=fake_db,
                tenant_id=12,
                industry_type="printing",
            )
