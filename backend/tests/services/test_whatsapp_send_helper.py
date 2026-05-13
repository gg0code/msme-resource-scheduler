# tests/services/test_whatsapp_send_helper.py
# Branch: v5-whatsapp
# Iteration: v6.3.22 — channel-decision send helper.
#
# FILE PURPOSE
# Unit-tier coverage for app/services/whatsapp_send_helper.py. Five
# scenarios, one per SRS 6.28.6 acceptance criterion:
#   AC1 — in 24h window: free-form path fires, whatsapp.freeform_sent event.
#   AC2 — outside window: template path fires, whatsapp.template_sent event.
#   AC3 — last_seen_at IS NULL: template path fires (never-messaged-us).
#   AC4 — unknown event: window_expired_no_template event, no send.
#   AC5 — param-count mismatch: template_param_mismatch event, no send.
# Plus a mock-mode log assertion (AC6) and a content-equivalence check (AC7).

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from sqlalchemy.schema import DefaultClause
from sqlalchemy.sql import text as sa_text

from app.config import settings
from app.core.security import hash_password
from app.models.auth import Tenant, User
from app.models.event import Event
from app.models.whatsapp import PhoneTenantMap
from app.services.whatsapp_send_helper import (
    EVENT_FREEFORM_SENT,
    EVENT_TEMPLATE_PARAM_MISMATCH,
    EVENT_TEMPLATE_SENT,
    EVENT_WINDOW_EXPIRED_NO_TEMPLATE,
    send_with_window_decision,
)


# ---------------------------------------------------------------------------
# Local fixture — patch PhoneTenantMap's now() server_default for SQLite.
# services/conftest.py:patch_now_defaults_for_sqlite covers the common
# tables but not PhoneTenantMap. Mirroring its style keeps the override
# minimal and local to this file.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_phone_tenant_map_now_default():
    patched: list[tuple[Any, Any]] = []
    for col in PhoneTenantMap.__table__.columns:
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


# ---------------------------------------------------------------------------
# Row factories
# ---------------------------------------------------------------------------

def _make_tenant(db) -> Tenant:
    t = Tenant(
        name="Test Factory",
        slug=f"test-factory-{id(db)}",
        plan="paid",
        is_active=True,
    )
    db.add(t)
    db.flush()
    return t


def _make_user(db, *, tenant_id: int) -> User:
    u = User(
        tenant_id=tenant_id,
        email=f"owner-{tenant_id}@test.com",
        hashed_password=hash_password("test-password"),
        role="proprietor",
    )
    db.add(u)
    db.flush()
    return u


def _make_phone_map(
    db,
    *,
    tenant_id: int,
    user_id: int,
    phone: str = "+919999900001",
    last_seen_at: datetime | None = None,
) -> PhoneTenantMap:
    m = PhoneTenantMap(
        tenant_id=tenant_id,
        user_id=user_id,
        phone_number=phone,
        is_active=True,
        last_seen_at=last_seen_at,
    )
    db.add(m)
    db.flush()
    return m


# ---------------------------------------------------------------------------
# Common args for happy paths
# ---------------------------------------------------------------------------

# MORNING_BRIEFING expects 6 positional args (date, jobs_starting,
# continuing, crew_expected, flag, next_step).
MORNING_ARGS: tuple = (
    "12 May",
    "3",
    "2 (Job A, Job B)",
    "8 of 10",
    "1 worker absent",
    "Plan a one-on-one with the worker.",
)

MORNING_FREEFORM = (
    "Morning briefing — 12 May\n\n"
    "Today's plan\n- Jobs starting: 3\n- Continuing from yesterday: 2 (Job A, Job B)\n"
    "- Crew expected: 8 of 10\n\nFlag: 1 worker absent\n\nSuggested next step: "
    "Plan a one-on-one with the worker.\n\nReply OK to apply or HELP for options."
)


# ---------------------------------------------------------------------------
# AC1 — in 24h window: free-form path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac1_in_window_uses_freeform_path(db, monkeypatch, caplog):
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
    caplog.set_level(logging.INFO, logger="app.services.whatsapp_send")

    tenant = _make_tenant(db)
    user = _make_user(db, tenant_id=tenant.id)
    now = datetime.now(timezone.utc)
    _make_phone_map(
        db, tenant_id=tenant.id, user_id=user.id,
        last_seen_at=now - timedelta(hours=2),  # well within 24h
    )

    outcome = await send_with_window_decision(
        db=db,
        tenant_id=tenant.id,
        phone_e164="+919999900001",
        event="morning_briefing",
        language="en_US",
        args=MORNING_ARGS,
        free_form_text=MORNING_FREEFORM,
        alert_type="push_morning",
        now=now,
    )

    assert outcome.path == "freeform"
    assert outcome.success is True
    assert outcome.wamid is not None
    assert outcome.wamid.startswith("mock_wamid_")
    assert outcome.error is None

    # [MOCK SEND] line emitted from _send_whatsapp_message.
    assert any("[MOCK SEND]" in r.message for r in caplog.records)

    # whatsapp.freeform_sent event staged.
    events = (
        db.query(Event)
        .filter(Event.event_type == EVENT_FREEFORM_SENT)
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["event"] == "morning_briefing"
    assert payload["within_window"] is True
    assert payload["success"] is True


# ---------------------------------------------------------------------------
# AC2 — outside 24h window: template path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac2_outside_window_uses_template_path(db, monkeypatch, caplog):
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
    caplog.set_level(logging.INFO, logger="app.services.whatsapp_send_helper")

    tenant = _make_tenant(db)
    user = _make_user(db, tenant_id=tenant.id)
    now = datetime.now(timezone.utc)
    _make_phone_map(
        db, tenant_id=tenant.id, user_id=user.id,
        last_seen_at=now - timedelta(hours=30),  # outside 24h
    )

    outcome = await send_with_window_decision(
        db=db,
        tenant_id=tenant.id,
        phone_e164="+919999900001",
        event="morning_briefing",
        language="en_US",
        args=MORNING_ARGS,
        free_form_text=MORNING_FREEFORM,
        alert_type="push_morning",
        now=now,
    )

    assert outcome.path == "template"
    assert outcome.success is True
    assert outcome.wamid is not None
    assert outcome.used_fallback is False
    assert outcome.error is None

    # [MOCK TEMPLATE] line emitted with the Meta template name.
    assert any(
        "[MOCK TEMPLATE]" in r.message
        and "zetaops_morning_briefing" in r.message
        for r in caplog.records
    ), f"missing template breadcrumb; got: {[r.message for r in caplog.records]}"

    # whatsapp.template_sent event staged with meta_params populated.
    events = (
        db.query(Event)
        .filter(Event.event_type == EVENT_TEMPLATE_SENT)
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["meta_name"] == "zetaops_morning_briefing"
    assert payload["meta_language"] == "en_US"
    assert payload["meta_params"] == list(MORNING_ARGS)
    assert payload["within_window"] is False


# ---------------------------------------------------------------------------
# AC3 — last_seen_at IS NULL (never messaged us): template path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac3_never_seen_uses_template_path(db, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
    tenant = _make_tenant(db)
    user = _make_user(db, tenant_id=tenant.id)
    _make_phone_map(
        db, tenant_id=tenant.id, user_id=user.id,
        last_seen_at=None,  # never inbound
    )

    outcome = await send_with_window_decision(
        db=db,
        tenant_id=tenant.id,
        phone_e164="+919999900001",
        event="morning_briefing",
        language="en_US",
        args=MORNING_ARGS,
        free_form_text=MORNING_FREEFORM,
        alert_type="push_morning",
    )

    assert outcome.path == "template"
    assert outcome.success is True

    events = (
        db.query(Event)
        .filter(Event.event_type == EVENT_TEMPLATE_SENT)
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["last_seen_at"] is None
    assert events[0].payload["within_window"] is False


# ---------------------------------------------------------------------------
# AC4 — unknown event: window_expired_no_template, no send
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac4_unknown_event_drops_silently_with_audit(db, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
    tenant = _make_tenant(db)
    user = _make_user(db, tenant_id=tenant.id)
    _make_phone_map(
        db, tenant_id=tenant.id, user_id=user.id,
        last_seen_at=None,
    )

    outcome = await send_with_window_decision(
        db=db,
        tenant_id=tenant.id,
        phone_e164="+919999900001",
        event="not_a_real_event_xyz",
        language="en_US",
        args=("anything",),
        free_form_text="ignored",
        alert_type="bogus",
    )

    assert outcome.path == "skipped_unknown_event"
    assert outcome.success is False
    assert outcome.wamid is None
    assert outcome.error == "unknown_event"

    events = (
        db.query(Event)
        .filter(Event.event_type == EVENT_WINDOW_EXPIRED_NO_TEMPLATE)
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["reason"] == "unknown_event"
    assert events[0].payload["event"] == "not_a_real_event_xyz"

    # No template_sent / freeform_sent event written.
    other = (
        db.query(Event)
        .filter(Event.event_type.in_([EVENT_TEMPLATE_SENT, EVENT_FREEFORM_SENT]))
        .all()
    )
    assert other == []


# ---------------------------------------------------------------------------
# AC5 — param-count mismatch: template_param_mismatch, no send
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac5_param_mismatch_drops_with_audit(db, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
    tenant = _make_tenant(db)
    user = _make_user(db, tenant_id=tenant.id)
    _make_phone_map(
        db, tenant_id=tenant.id, user_id=user.id,
        last_seen_at=None,
    )

    # morning_briefing expects 6 args; pass only 2.
    outcome = await send_with_window_decision(
        db=db,
        tenant_id=tenant.id,
        phone_e164="+919999900001",
        event="morning_briefing",
        language="en_US",
        args=("12 May", "3"),
        free_form_text="ignored",
        alert_type="push_morning",
    )

    assert outcome.path == "skipped_param_mismatch"
    assert outcome.success is False
    assert outcome.wamid is None
    assert outcome.error == "param_mismatch"

    events = (
        db.query(Event)
        .filter(Event.event_type == EVENT_TEMPLATE_PARAM_MISMATCH)
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["args_count"] == 2
    assert events[0].payload["event"] == "morning_briefing"

    # No successful send event.
    assert (
        db.query(Event)
        .filter(Event.event_type == EVENT_TEMPLATE_SENT)
        .count() == 0
    )


# ---------------------------------------------------------------------------
# AC6 — mock-mode log line carries event_template + params
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac6_mock_template_log_format(db, monkeypatch, caplog):
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
    caplog.set_level(logging.INFO, logger="app.services.whatsapp_send_helper")

    tenant = _make_tenant(db)
    user = _make_user(db, tenant_id=tenant.id)
    _make_phone_map(
        db, tenant_id=tenant.id, user_id=user.id,
        last_seen_at=None,
    )

    await send_with_window_decision(
        db=db,
        tenant_id=tenant.id,
        phone_e164="+919999900001",
        event="morning_briefing",
        language="en_US",
        args=MORNING_ARGS,
        free_form_text=MORNING_FREEFORM,
        alert_type="push_morning",
    )

    template_log_lines = [
        r.message for r in caplog.records if "[MOCK TEMPLATE]" in r.message
    ]
    assert len(template_log_lines) == 1
    line = template_log_lines[0]
    assert "event_template=zetaops_morning_briefing" in line
    assert "language=en_US" in line
    assert "To=****0001" in line
    # First positional arg appears verbatim in the params list.
    assert "12 May" in line


# ---------------------------------------------------------------------------
# AC7 — content equivalence: free-form rendered text matches
# resolve_template's rendered_text byte-for-byte (placeholder format
# strings are shared via message_formatters constants).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac7_content_equivalence_freeform_vs_template_render(db, monkeypatch):
    """The free-form text the dispatcher renders for the in-window path
    is the same byte string resolve_template's rendered_text returns
    for the out-of-window path. This guards against drift between the
    two rendering paths."""
    from app.services.whatsapp_templates import resolve_template

    resolved = resolve_template("morning_briefing", "en_US", MORNING_ARGS)
    assert resolved.rendered_text == MORNING_FREEFORM


# ---------------------------------------------------------------------------
# Extra — Hindi fallback path emits used_fallback=True only when the
# language requires it. For morning_briefing both en_US and hi exist,
# so used_fallback must be False.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hindi_language_does_not_fallback_for_morning_briefing(
    db, monkeypatch
):
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
    tenant = _make_tenant(db)
    user = _make_user(db, tenant_id=tenant.id)
    _make_phone_map(
        db, tenant_id=tenant.id, user_id=user.id,
        last_seen_at=None,
    )

    outcome = await send_with_window_decision(
        db=db,
        tenant_id=tenant.id,
        phone_e164="+919999900001",
        event="morning_briefing",
        language="hi",
        args=MORNING_ARGS,
        free_form_text=MORNING_FREEFORM,
        alert_type="push_morning",
    )

    assert outcome.path == "template"
    assert outcome.success is True
    assert outcome.used_fallback is False
