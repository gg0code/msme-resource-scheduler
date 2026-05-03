# test_whatsapp_send_meta_v6_3_7.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for the four-branch send precedence in
# app/services/whatsapp_send.py::_send_whatsapp_message after v6.3.7.
# Precedence under test:
#   1. WHATSAPP_MOCK_MODE=True              -> log only, no HTTP
#   2. INTERAKT_API_KEY set                 -> POST to api.interakt.ai
#   3. WHATSAPP_ACCESS_TOKEN
#      + WHATSAPP_PHONE_NUMBER_ID set       -> POST to graph.facebook.com (Meta)
#   4. otherwise                            -> log error, no HTTP
#
# httpx.AsyncClient is replaced with _FakeAsyncClient that records every POST.
# All async calls run via asyncio.run() to avoid pytest-asyncio config.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/services/whatsapp_send.py - _send_whatsapp_message
#   app/routers/whatsapp.py       - re-exports _send_whatsapp_message; tests
#                                    still hit it via the router namespace
#                                    to prove import-path stability.
#   app/config.settings           - WHATSAPP_* and INTERAKT_API_KEY (monkeypatched)

import asyncio

import pytest

from app.config import settings
from app.routers import whatsapp as whatsapp_router
from app.services import whatsapp_send


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeAsyncClient:
    """Drop-in for httpx.AsyncClient. Records every POST in `calls`."""

    calls: list = []
    next_response: _FakeResponse = _FakeResponse(200, '{"ok": true}')

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None, timeout=None):
        type(self).calls.append({
            "url": url,
            "headers": headers or {},
            "json": json or {},
            "timeout": timeout,
        })
        return type(self).next_response


@pytest.fixture(autouse=True)
def _patch_httpx_and_reset(monkeypatch):
    """
    Replace httpx.AsyncClient inside the router module and reset capture
    state between tests. Default settings: mock off, no providers configured —
    each test opts in to the providers it needs.
    """
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.next_response = _FakeResponse(200, '{"ok": true}')
    monkeypatch.setattr(whatsapp_send.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", False)
    monkeypatch.setattr(settings, "INTERAKT_API_KEY", None)
    monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", None)
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
    yield


# ---------------------------------------------------------------------------
# Branch 3: Meta direct
# ---------------------------------------------------------------------------

class TestMetaDirectBranch:

    def test_send_whatsapp_message_uses_meta_when_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "test-token-fake")
        monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "111122223333444")

        asyncio.run(whatsapp_router._send_whatsapp_message(
            phone_number="+919876543210",
            message="aaj ka schedule",
        ))

        assert len(_FakeAsyncClient.calls) == 1
        call = _FakeAsyncClient.calls[0]
        assert call["url"] == (
            "https://graph.facebook.com/v21.0/111122223333444/messages"
        )
        assert call["headers"]["Authorization"] == "Bearer test-token-fake"
        assert call["json"]["messaging_product"] == "whatsapp"
        assert call["json"]["to"] == "919876543210"  # leading + stripped
        assert call["json"]["type"] == "text"
        assert call["json"]["text"]["body"] == "aaj ka schedule"

    def test_meta_non_2xx_response_logs_error_and_does_not_raise(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "test-token-fake")
        monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "111122223333444")
        _FakeAsyncClient.next_response = _FakeResponse(
            status_code=400,
            text='{"error":{"message":"(#10) recipient not in allowlist"}}',
        )

        with caplog.at_level("ERROR"):
            asyncio.run(whatsapp_router._send_whatsapp_message(
                phone_number="+919876543210",
                message="hi",
            ))

        assert len(_FakeAsyncClient.calls) == 1  # POST attempted
        assert any("Meta error 400" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Precedence: Interakt wins over Meta when both configured
# ---------------------------------------------------------------------------

class TestProviderPrecedence:

    def test_send_whatsapp_message_prefers_interakt_when_both_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "INTERAKT_API_KEY", "interakt-key-fake")
        monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "test-token-fake")
        monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "111122223333444")

        asyncio.run(whatsapp_router._send_whatsapp_message(
            phone_number="+919876543210",
            message="hi",
        ))

        assert len(_FakeAsyncClient.calls) == 1
        call = _FakeAsyncClient.calls[0]
        assert "api.interakt.ai" in call["url"]
        assert "graph.facebook.com" not in call["url"]
        assert call["headers"]["Authorization"].startswith("Basic ")


# ---------------------------------------------------------------------------
# Branch 4: Unconfigured -> error log, no HTTP
# ---------------------------------------------------------------------------

class TestUnconfiguredBranch:

    def test_send_whatsapp_message_logs_error_when_unconfigured(self, caplog):
        with caplog.at_level("ERROR"):
            asyncio.run(whatsapp_router._send_whatsapp_message(
                phone_number="+919876543210",
                message="hi",
            ))

        assert len(_FakeAsyncClient.calls) == 0
        assert any(
            "WhatsApp send unconfigured" in r.message for r in caplog.records
        )

    def test_meta_phone_id_alone_is_insufficient(self, monkeypatch, caplog):
        # Only one of the two Meta vars set -> falls through to error branch.
        monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "111122223333444")

        with caplog.at_level("ERROR"):
            asyncio.run(whatsapp_router._send_whatsapp_message(
                phone_number="+919876543210",
                message="hi",
            ))

        assert len(_FakeAsyncClient.calls) == 0
        assert any(
            "WhatsApp send unconfigured" in r.message for r in caplog.records
        )


# ---------------------------------------------------------------------------
# Branch 1: Mock mode short-circuits all real-API attempts
# ---------------------------------------------------------------------------

class TestMockModeShortCircuits:

    def test_send_whatsapp_message_mock_mode_short_circuits(self, monkeypatch, caplog):
        # Mock on AND every real provider configured -> mock still wins.
        monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
        monkeypatch.setattr(settings, "INTERAKT_API_KEY", "interakt-key-fake")
        monkeypatch.setattr(settings, "WHATSAPP_ACCESS_TOKEN", "test-token-fake")
        monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "111122223333444")

        with caplog.at_level("INFO"):
            asyncio.run(whatsapp_router._send_whatsapp_message(
                phone_number="+919876543210",
                message="hi",
            ))

        assert len(_FakeAsyncClient.calls) == 0  # NO HTTP call made
        assert any("[MOCK SEND]" in r.message for r in caplog.records)
