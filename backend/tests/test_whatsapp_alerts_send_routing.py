# test_whatsapp_alerts_send_routing.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Verify that whatsapp_alerts._send_alert routes through the shared
# _send_whatsapp_message helper rather than doing its own outbound HTTP.
# Every alert send goes through one helper that owns mock>meta>error
# precedence.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/services/whatsapp_alerts.py - send_morning_briefings,
#                                     send_manager_checkin, _send_alert
#   app/services/whatsapp_send.py   - _send_whatsapp_message (mocked)

import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.services import whatsapp_alerts


@pytest.fixture(autouse=True)
def _enable_mock_mode(monkeypatch):
    """Force WHATSAPP_MOCK_MODE=True so no real provider lookup happens."""
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
    yield


@pytest.fixture()
def fake_send(monkeypatch):
    """
    Replace _send_whatsapp_message in the whatsapp_alerts namespace.

    The function was imported at module load via
    `from app.services.whatsapp_send import _send_whatsapp_message`,
    so we patch the binding inside whatsapp_alerts — that's what
    _send_alert actually calls.
    """
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(whatsapp_alerts, "_send_whatsapp_message", mock)
    return mock


# ---------------------------------------------------------------------------
# _send_alert — direct routing contract
# ---------------------------------------------------------------------------

class TestSendAlertRouting:
    """_send_alert must always delegate transport to _send_whatsapp_message."""

    def test_send_alert_in_mock_mode_logs_and_delegates(self, fake_send, caplog):
        with caplog.at_level(logging.INFO):
            asyncio.run(whatsapp_alerts._send_alert(
                phone_number="+919876543210",
                message="hello world",
                alert_type="morning_briefing",
            ))

        # Mock-mode breadcrumb preserved for alert-type debugging
        assert any("[MOCK ALERT]" in r.message for r in caplog.records)
        assert any("morning_briefing" in r.message for r in caplog.records)

        # AND the helper was still called — mock branching now lives there
        fake_send.assert_awaited_once_with("+919876543210", "hello world")

    def test_send_alert_in_real_mode_logs_dispatch_and_delegates(
        self, fake_send, caplog, monkeypatch
    ):
        monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", False)

        with caplog.at_level(logging.INFO):
            asyncio.run(whatsapp_alerts._send_alert(
                phone_number="+919999999999",
                message="conflict alert",
                alert_type="conflict",
            ))

        assert any("Dispatching alert" in r.message for r in caplog.records)
        assert not any("[MOCK ALERT]" in r.message for r in caplog.records)
        fake_send.assert_awaited_once_with("+919999999999", "conflict alert")


# ---------------------------------------------------------------------------
# Morning briefing — full path through _send_alert
# ---------------------------------------------------------------------------

class TestMorningBriefingRoutesThroughSendHelper:

    def test_morning_briefing_calls_send_helper_with_recipient_and_body(
        self, fake_send, monkeypatch
    ):
        async def fake_phones(alert_type, tenant_id_filter=None):
            return [{
                "phone_number": "+919876543210",
                "tenant_id": 12,
                "industry_type": "printing",
            }]

        async def fake_briefing(tenant_id, industry_type):
            return "Good morning! ZetaOps daily briefing"

        monkeypatch.setattr(
            whatsapp_alerts, "_get_active_phone_mappings", fake_phones,
        )
        monkeypatch.setattr(
            whatsapp_alerts, "_build_morning_briefing", fake_briefing,
        )

        asyncio.run(whatsapp_alerts.send_morning_briefings())

        fake_send.assert_awaited_once_with(
            "+919876543210", "Good morning! ZetaOps daily briefing",
        )


# ---------------------------------------------------------------------------
# Manager check-in — full path through _send_alert
# ---------------------------------------------------------------------------

class TestManagerCheckinRoutesThroughSendHelper:

    def test_manager_checkin_calls_send_helper_with_recipient_and_prompt(
        self, fake_send, monkeypatch
    ):
        async def fake_managers():
            return [{
                "phone_number": "+919876500001",
                "tenant_id": 12,
                "industry_type": "printing",
            }]

        monkeypatch.setattr(
            whatsapp_alerts, "_get_manager_phone_mappings", fake_managers,
        )

        # Patch the late-imported build_checkin_prompt at its source so the
        # function send_manager_checkin imports inside its body picks it up.
        from app.services import whatsapp_checkin
        monkeypatch.setattr(
            whatsapp_checkin, "build_checkin_prompt",
            lambda lang: "Good morning! ZetaOps check-in",
        )

        asyncio.run(whatsapp_alerts.send_manager_checkin())

        fake_send.assert_awaited_once_with(
            "+919876500001", "Good morning! ZetaOps check-in",
        )
