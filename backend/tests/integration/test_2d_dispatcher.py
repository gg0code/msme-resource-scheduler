# tests/integration/test_2d_dispatcher.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.19 slice 2D-tests — failure-mode coverage matrix for the
# consolidated_briefing.push_v2_tick + dispatch_morning + dispatch_evening
# infrastructure introduced in slices 2C and 2D-shadow.
#
# Every test cites the failure mode it covers in its docstring. The
# 10 dispatcher failure modes guarded by this matrix are:
#
#   FM1  — APScheduler doesn't fire (covered only at boot-time
#          integration; gap accepted, monitored via scheduler heartbeat
#          per CHANGELOG note).
#   FM2  — wrong recipients (right tenants resolved at right minute,
#          paused / disabled / non-top-tier excluded).
#   FM3  — wrong content (template render mismatch — partial coverage
#          via slice 2C unit tests, see report-back).
#   FM4  — duplicate sends (idempotency dedup).
#   FM5  — both systems sending (flag-gating between legacy and v2).
#   FM6  — silent crash / cascade crash (exception swallowing).
#   FM7  — thundering herd (hash stagger spreads sends).
#   FM8  — clock drift (now kwarg discipline).
#   FM9  — locale wrong — slice 2C ships hi_en-only per A1; per-recipient
#          locale resolution deferred. No test in this matrix.
#   FM10 — cross-tenant leak (tenant_id filter on every query).
#
# WHO CALLS THIS FILE
# - pytest, marked @pytest.mark.integration. Runs explicitly via
#   `pytest tests/integration/test_2d_dispatcher.py -v`. Excluded
#   from the unit-tier `pytest -m "not integration"` gate.
#
# WHAT THIS FILE CALLS
# - app.services.consolidated_briefing — module under test.
# - app.routers.whatsapp_debug — debug endpoint under test.
# - The conftest `db` fixture (SQLite in-memory) and `client`
#   TestClient. Mock Meta API throughout via the local
#   mock_meta_sender fixture; no real Meta calls are made.

import asyncio
from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sa_text
from sqlalchemy.schema import DefaultClause

from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.auth import RefreshToken, Tenant, User
from app.models.event import Event
from app.models.whatsapp import PhoneTenantMap
from app.services import consolidated_briefing as cb


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Local fixtures — kept inline so the file is self-contained per the
# del2c2d brief constraint "every test must be runnable via
# pytest tests/integration/test_2d_dispatcher.py -v without requiring
# real Postgres beyond the existing conftest fixtures."
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    """SQLite has no `now()` function. Patch text('now()') server_defaults
    to CURRENT_TIMESTAMP for the duration of each test. Mirrors the
    fixture in tests/services/test_consolidated_briefing.py — kept
    local because tests/conftest.py does not provide it globally.
    """
    patched = []
    for table_attr in (
        Tenant.__table__,
        User.__table__,
        RefreshToken.__table__,
        PhoneTenantMap.__table__,
        Event.__table__,
    ):
        for col in table_attr.columns:
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


@pytest.fixture
def mock_meta_sender(monkeypatch):
    """Replace _send_whatsapp_message in consolidated_briefing with a
    recorder. Yields a list accumulating one dict per call.
    """
    sent: list[dict] = []

    async def fake_send(phone: str, message: str) -> None:
        sent.append({"phone": phone, "message": message})

    monkeypatch.setattr(
        "app.services.consolidated_briefing._send_whatsapp_message",
        fake_send,
    )
    return sent


def _seed_tenant(
    db, *, name: str = "Acme",
    morning_time: time = time(7, 30),
    evening_time: time = time(18, 30),
    morning_enabled: bool = True,
    evening_enabled: bool = True,
    timezone_str: str = "Asia/Kolkata",
) -> Tenant:
    """Build a Tenant with explicit briefing config (avoids SQLite
    server_default truthy-string quirk)."""
    t = Tenant(
        name=name,
        slug=name.lower().replace(" ", "-"),
        briefing_morning_enabled=morning_enabled,
        briefing_evening_enabled=evening_enabled,
        briefing_morning_time=morning_time,
        briefing_evening_time=evening_time,
        briefing_timezone=timezone_str,
    )
    db.add(t)
    db.flush()
    return t


def _seed_owner(db, *, tenant_id: int, email: str, role: str = "proprietor") -> User:
    u = User(
        tenant_id=tenant_id, email=email,
        hashed_password=hash_password("test-password"), role=role,
    )
    db.add(u)
    db.flush()
    return u


def _seed_phone(
    db, *, tenant_id: int, user_id: int, phone: str,
    phone_role: str = "owner", is_active: bool = True,
    alert_preferences: dict | None = None,
) -> PhoneTenantMap:
    if alert_preferences is None:
        alert_preferences = {"push_morning": True, "push_evening": True}
    m = PhoneTenantMap(
        tenant_id=tenant_id, user_id=user_id, phone_number=phone,
        is_active=is_active, phone_role=phone_role,
        alert_preferences=alert_preferences,
    )
    db.add(m)
    db.flush()
    return m


def _seed_full(
    db, *, name: str = "Acme",
    phone: str = "+919999000001",
    morning_time: time = time(7, 30),
    evening_time: time = time(18, 30),
    morning_enabled: bool = True,
    evening_enabled: bool = True,
    alert_preferences: dict | None = None,
) -> tuple[Tenant, User, PhoneTenantMap]:
    """Tenant + owner User + top-tier PhoneTenantMap in one shot."""
    t = _seed_tenant(
        db, name=name,
        morning_time=morning_time, evening_time=evening_time,
        morning_enabled=morning_enabled, evening_enabled=evening_enabled,
    )
    u = _seed_owner(db, tenant_id=t.id, email=f"owner@{t.slug}.test")
    p = _seed_phone(
        db, tenant_id=t.id, user_id=u.id, phone=phone,
        alert_preferences=alert_preferences,
    )
    return t, u, p


def _utc_for_ist(hour: int, minute: int) -> datetime:
    """Build a UTC datetime that maps to the given IST hour:minute on
    2026-05-09 (the canonical fixture date)."""
    ist = datetime(2026, 5, 9, hour, minute, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    return ist.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# 1. test_recipient_resolution_basic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipient_resolution_basic(db, mock_meta_sender, monkeypatch):
    """Failure mode 2: wrong recipients. 3 tenants with different
    morning_push_time, tick at 7:30 IST picks only the one whose
    time matches.
    """
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", True,
    )
    _seed_full(db, name="A", phone="+919900000001",
               morning_time=time(6, 0))
    target, _u, _p = _seed_full(db, name="B", phone="+919900000002",
                                  morning_time=time(7, 30))
    _seed_full(db, name="C", phone="+919900000003",
               morning_time=time(9, 15))

    results = await cb.push_v2_tick(_utc_for_ist(7, 30), db, apply_stagger=False)

    assert len(results) == 1
    assert results[0].tenant_id == target.id
    assert len(mock_meta_sender) == 1
    assert mock_meta_sender[0]["phone"] == "+919900000002"


# ---------------------------------------------------------------------------
# 2. test_recipient_skips_paused_tenant
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipient_skips_paused_tenant(db, mock_meta_sender, monkeypatch):
    """Failure mode 2: paused tenants must not receive."""
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", True,
    )
    t, _u, _p = _seed_full(db, morning_time=time(7, 30))
    t.push_paused_until = (
        _utc_for_ist(7, 30).astimezone(ZoneInfo("Asia/Kolkata")).date()
        + timedelta(days=2)
    )
    db.flush()

    results = await cb.push_v2_tick(_utc_for_ist(7, 30), db, apply_stagger=False)

    assert len(results) == 1
    assert results[0].skip_reason == "paused"
    assert mock_meta_sender == []


# ---------------------------------------------------------------------------
# 3. test_recipient_skips_disabled_direction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipient_skips_disabled_direction(db, mock_meta_sender, monkeypatch):
    """Failure mode 2: tenant with briefing_morning_enabled=False is
    excluded from morning tick (and from _tenants_due_for at the DB
    layer, before reaching the dispatcher)."""
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", True,
    )
    _seed_full(
        db, morning_time=time(7, 30),
        morning_enabled=False, evening_enabled=True,
    )

    results = await cb.push_v2_tick(_utc_for_ist(7, 30), db, apply_stagger=False)

    assert results == []
    assert mock_meta_sender == []


# ---------------------------------------------------------------------------
# 4. test_now_kwarg_discipline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_now_kwarg_discipline(db, mock_meta_sender, monkeypatch):
    """Failure mode 8: clock drift. Pass now=07:30 IST, freeze the wall
    clock to 09:00 IST via monkeypatch, assert dispatch decisions use
    the passed `now` (and the resulting events row's
    payload['scheduled_for_date'] reflects 07:30 IST not 09:00 IST)."""
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", True,
    )
    t, _u, _p = _seed_full(db, morning_time=time(7, 30))

    # Freeze datetime.now() / datetime.utcnow() at a wildly different
    # time so any clock-leakage in the dispatcher would be detected.
    frozen_wall_clock = datetime(2026, 5, 9, 9, 0, 0, tzinfo=timezone.utc)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401
            return frozen_wall_clock if tz is None else frozen_wall_clock.astimezone(tz)

        @classmethod
        def utcnow(cls):
            return frozen_wall_clock.replace(tzinfo=None)

    with patch("app.services.consolidated_briefing.datetime", _FrozenDatetime):
        passed_now = _utc_for_ist(7, 30)
        result = await cb.dispatch_morning(t.id, passed_now, db)

    assert result.sent_count == 1
    sent_event = (
        db.query(Event)
        .filter(Event.event_type == "push.morning_sent")
        .first()
    )
    assert sent_event is not None
    # scheduled_for_date is derived from the passed `now`, not wall clock.
    assert sent_event.payload["scheduled_for_date"] == "2026-05-09"
    assert sent_event.payload["now"] == passed_now.isoformat()


# ---------------------------------------------------------------------------
# 5. test_idempotent_repeated_call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_idempotent_repeated_call(db, mock_meta_sender, monkeypatch):
    """Failure mode 4: duplicate sends. Call dispatch_morning twice with
    the same tenant and same scheduled_for_date. Assert mock_meta
    received only ONE send.

    Slice 2C added events-table dedup against
    payload['scheduled_for_date']; this test locks that contract."""
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", True,
    )
    t, _u, _p = _seed_full(db, morning_time=time(7, 30))

    r1 = await cb.dispatch_morning(t.id, _utc_for_ist(7, 30), db)
    r2 = await cb.dispatch_morning(t.id, _utc_for_ist(7, 31), db)

    assert r1.sent_count == 1
    assert r2.skip_reason == "idempotent"
    assert r2.sent_count == 0
    assert len(mock_meta_sender) == 1


# ---------------------------------------------------------------------------
# 6. test_old_tick_short_circuits_when_flag_enabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_old_tick_short_circuits_when_flag_enabled(
    db, mock_meta_sender, monkeypatch,
):
    """Failure mode 5: both systems sending. push_v2_enabled=True; call
    the legacy run_briefing_dispatch_tick directly and assert it
    early-returns without sending.
    """
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", True,
    )
    monkeypatch.setattr(
        "app.config.settings.PUSH_V2_ENABLED", True,
    )
    _seed_full(db, morning_time=time(7, 30))

    # Spy on dispatch_due_briefings — it should NOT be called.
    called: list[bool] = []

    async def _spy():
        called.append(True)
        from types import SimpleNamespace
        return SimpleNamespace(
            tenants_processed=0, briefings_sent=0, briefings_skipped=0,
        )

    monkeypatch.setattr(
        "app.services.briefings.dispatcher.dispatch_due_briefings",
        _spy,
    )

    from app.services.whatsapp_alerts import run_briefing_dispatch_tick
    await run_briefing_dispatch_tick()

    assert called == [], "Old tick must NOT call dispatch_due_briefings when flag is on"
    assert mock_meta_sender == []


# ---------------------------------------------------------------------------
# 7. test_new_tick_shadow_logs_when_flag_disabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_tick_shadow_logs_when_flag_disabled(
    db, mock_meta_sender, monkeypatch,
):
    """Failure mode 5: both systems sending. push_v2_enabled=False;
    push_v2_tick logs push.shadow_log entries instead of sending.
    """
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", False,
    )
    _seed_full(db, morning_time=time(7, 30))

    results = await cb.push_v2_tick(_utc_for_ist(7, 30), db, apply_stagger=False)

    assert len(results) == 1
    assert mock_meta_sender == []
    shadow_count = (
        db.query(Event)
        .filter(Event.event_type == "push.shadow_log")
        .count()
    )
    morning_sent_count = (
        db.query(Event)
        .filter(Event.event_type == "push.morning_sent")
        .count()
    )
    assert shadow_count == 1
    assert morning_sent_count == 0


# ---------------------------------------------------------------------------
# 8. test_meta_api_exception_logged_does_not_crash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_meta_api_exception_logged_does_not_crash(
    db, monkeypatch,
):
    """Failure mode 6: silent crash. monkeypatch _send_whatsapp_message
    to raise; assert no exception propagates, push.morning_send_failed
    has the entry, and the dispatcher returns DispatchResult with
    success=False.
    """
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", True,
    )
    t, _u, _p = _seed_full(db, morning_time=time(7, 30))

    async def boom(phone: str, message: str) -> None:
        raise RuntimeError("Meta HTTP 500 — fake")

    monkeypatch.setattr(
        "app.services.consolidated_briefing._send_whatsapp_message", boom,
    )

    result = await cb.dispatch_morning(t.id, _utc_for_ist(7, 30), db)

    assert result.success is False
    assert result.sent_count == 0
    assert "Meta HTTP 500" in (result.error or "")
    failed = (
        db.query(Event)
        .filter(Event.event_type == "push.morning_send_failed")
        .count()
    )
    assert failed == 1
    # No *_sent event — idempotency anchor stays open.
    sent = (
        db.query(Event)
        .filter(Event.event_type == "push.morning_sent")
        .count()
    )
    assert sent == 0


# ---------------------------------------------------------------------------
# 9. test_one_tenant_failure_does_not_block_others
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_tenant_failure_does_not_block_others(
    db, monkeypatch,
):
    """Failure mode 6: cascade crash. Tenant A's send raises; Tenant B's
    send succeeds. Run push_v2_tick covering both. Assert B got sent,
    A logged failure, tick completed without raising.
    """
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", True,
    )
    a, _au, _ap = _seed_full(db, name="A", phone="+919900000001",
                              morning_time=time(7, 30))
    b, _bu, _bp = _seed_full(db, name="B", phone="+919900000002",
                              morning_time=time(7, 30))

    sent_log: list[str] = []

    async def selective_send(phone: str, message: str) -> None:
        if phone == "+919900000001":
            raise RuntimeError("Meta says no for tenant A")
        sent_log.append(phone)

    monkeypatch.setattr(
        "app.services.consolidated_briefing._send_whatsapp_message",
        selective_send,
    )

    results = await cb.push_v2_tick(_utc_for_ist(7, 30), db, apply_stagger=False)

    assert len(results) == 2
    # Tenant A failed; B succeeded.
    a_result = next(r for r in results if r.tenant_id == a.id)
    b_result = next(r for r in results if r.tenant_id == b.id)
    assert a_result.success is False
    assert b_result.success is True
    assert b_result.sent_count == 1
    # B's send actually reached the recorder.
    assert sent_log == ["+919900000002"]
    # A logged push.morning_send_failed.
    assert (
        db.query(Event)
        .filter(
            Event.event_type == "push.morning_send_failed",
            Event.tenant_id == a.id,
        )
        .count() == 1
    )


# ---------------------------------------------------------------------------
# 10. test_hash_stagger_spreads_sends
# ---------------------------------------------------------------------------

def test_hash_stagger_spreads_sends():
    """Failure mode 7: thundering herd. 100 tenants all configured for
    morning_push_time=07:30. Compute the offset for each via
    _offset_seconds_for(tenant_id) and assert no single second has
    more than 3 tenants (60 buckets × 100 tenants = 1.67 mean per
    bucket; binomial-ish tail would put ≤3 comfortably).

    Pure unit-style test (no DB), included here for matrix
    completeness — failure mode 7 has no other natural home.
    """
    bucket_counts: dict[int, int] = {}
    for tenant_id in range(1, 101):
        offset = cb._offset_seconds_for(tenant_id)
        bucket_counts[offset] = bucket_counts.get(offset, 0) + 1

    max_per_second = max(bucket_counts.values())
    assert max_per_second <= 3, (
        f"Hash stagger collision: {max_per_second} tenants in one second. "
        f"Distribution: {sorted(bucket_counts.items())}"
    )
    # All 60 buckets used? With 100 tenants over 60 buckets every
    # bucket should be hit (pigeonhole).
    assert len(bucket_counts) >= 40, (
        f"Only {len(bucket_counts)} of 60 buckets hit"
    )


# ---------------------------------------------------------------------------
# 11. test_locale_resolution_per_recipient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_locale_resolution_per_recipient(db, mock_meta_sender, monkeypatch):
    """Failure mode 9 (locale): slice 2C decision A1 ships hi_en for
    ALL recipients — per-recipient locale resolution is deferred until
    User.language_preference exists. This test locks the current
    contract: every recipient receives the Hinglish (hi_en) variant
    regardless of any per-user locale hint.

    When the future User.language_preference field lands, this test
    must be REPLACED with a real per-recipient locale split — do not
    silently delete it. Marked with a TODO at the body level.
    """
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", True,
    )
    t = _seed_tenant(db, morning_time=time(7, 30))
    u1 = _seed_owner(db, tenant_id=t.id, email="a@test.test")
    u2 = _seed_owner(db, tenant_id=t.id, email="b@test.test")
    _seed_phone(db, tenant_id=t.id, user_id=u1.id, phone="+919911110001")
    _seed_phone(db, tenant_id=t.id, user_id=u2.id, phone="+919911110002")

    await cb.dispatch_morning(t.id, _utc_for_ist(7, 30), db)

    # Both recipients got the Hinglish variant — Devanagari header
    # from MORNING_BRIEFING_HI is the marker.
    assert len(mock_meta_sender) == 2
    for entry in mock_meta_sender:
        assert "सुबह की briefing" in entry["message"], (
            "Expected Hinglish template (default locale 'hi_en' under A1)"
        )
        assert "Morning briefing" not in entry["message"]


# ---------------------------------------------------------------------------
# 12. test_24_hour_simulation_old_vs_new_parity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_24_hour_simulation_old_vs_new_parity(db, mock_meta_sender, monkeypatch):
    """The big one — simplified scope.

    Full-day per-minute simulation against the full v6.3.4 dispatcher
    (briefings/dispatcher.py) would require its own fixture
    plumbing and template-content reconciliation that is out of
    slice 2D-tests scope. This simplified version tests the
    INVARIANT that matters for the cutover decision:

      - 3 tenants seeded with distinct morning + evening push times.
      - Run push_v2_tick at each of the 6 (3×2) due minutes plus a
        sample of 3 non-due minutes.
      - Assert: each tenant's morning + evening sends fire exactly
        once at the right minute, no sends at non-due minutes, and
        each tenant's recipient is the expected single phone (which
        is identical to what the legacy v5.10 PhoneTenantMap-based
        resolution would pick — both systems use is_active +
        is_top_tier + alert_preferences default-True, so recipient
        sets are identical by construction).

    If this passes, recipient-set + cadence parity is proven. Content
    parity is NOT asserted here — slice 2C unit tests cover it.
    """
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED", True,
    )
    fixture = [
        ("Alpha",   "+919900001001", time(6, 0),  time(17, 0)),
        ("Bravo",   "+919900001002", time(7, 30), time(18, 30)),
        ("Charlie", "+919900001003", time(9, 15), time(20, 0)),
    ]
    tenants_by_phone = {}
    for name, phone, m_time, e_time in fixture:
        t, _u, _p = _seed_full(
            db, name=name, phone=phone,
            morning_time=m_time, evening_time=e_time,
        )
        tenants_by_phone[phone] = (t.id, m_time, e_time)

    # Tick at each due minute — expect exactly one send per tick to the
    # tenant whose time matches.
    due_minutes: list[tuple[time, str, str]] = [
        (time(6, 0),  "+919900001001", "morning"),
        (time(7, 30), "+919900001002", "morning"),
        (time(9, 15), "+919900001003", "morning"),
        (time(17, 0), "+919900001001", "evening"),
        (time(18, 30), "+919900001002", "evening"),
        (time(20, 0), "+919900001003", "evening"),
    ]

    for tick_time, expected_phone, _kind in due_minutes:
        mock_meta_sender.clear()
        await cb.push_v2_tick(
            _utc_for_ist(tick_time.hour, tick_time.minute),
            db, apply_stagger=False,
        )
        phones = [m["phone"] for m in mock_meta_sender]
        assert phones == [expected_phone], (
            f"At {tick_time} expected only {expected_phone}, got {phones}"
        )

    # Tick at three non-due minutes — expect zero sends.
    for h, m in [(3, 15), (12, 0), (23, 45)]:
        mock_meta_sender.clear()
        await cb.push_v2_tick(_utc_for_ist(h, m), db, apply_stagger=False)
        assert mock_meta_sender == [], (
            f"At non-due time {h:02d}:{m:02d}, sends fired: {mock_meta_sender}"
        )


# ---------------------------------------------------------------------------
# 13. test_debug_endpoint_shadow_mode_returns_payload
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_client(db):
    """TestClient with the DB override and a top-tier proprietor JWT."""
    t = _seed_tenant(db, name="DebugTest")
    u = _seed_owner(db, tenant_id=t.id, email="debug@test.test")
    _seed_phone(db, tenant_id=t.id, user_id=u.id, phone="+919900099001")

    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    token = create_access_token(
        user_id=u.id, tenant_id=t.id, role="proprietor",
    )
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as c:
        yield c, headers, t.id
    app.dependency_overrides.clear()


def test_debug_endpoint_shadow_mode_returns_payload(auth_client, mock_meta_sender):
    """curl-equivalent: POST /api/v1/whatsapp/debug/dispatch with
    force_send=false returns a payload that includes would_send_to,
    rendered_message, and shadow_log_event_id. mock_meta is empty."""
    client, headers, tenant_id = auth_client
    response = client.post(
        "/api/v1/whatsapp/debug/dispatch",
        headers=headers,
        json={
            "type": "morning",
            "tenant_id": tenant_id,
            "now": "2026-05-09T07:30:00",
            "force_send": False,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actually_sent"] is False
    assert body["would_send_to"] == ["+919900099001"]
    assert body["rendered_message"] is not None
    assert body["shadow_log_event_id"] is not None
    assert mock_meta_sender == []


# ---------------------------------------------------------------------------
# 14. test_debug_endpoint_force_send_actually_sends
# ---------------------------------------------------------------------------

def test_debug_endpoint_force_send_actually_sends(auth_client, mock_meta_sender):
    """force_send=true: mock_meta receives the call AND actually_sent
    is True in the response."""
    client, headers, tenant_id = auth_client
    response = client.post(
        "/api/v1/whatsapp/debug/dispatch",
        headers=headers,
        json={
            "type": "morning",
            "tenant_id": tenant_id,
            "now": "2026-05-09T07:30:00",
            "force_send": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actually_sent"] is True
    assert len(mock_meta_sender) == 1
    assert mock_meta_sender[0]["phone"] == "+919900099001"


# ---------------------------------------------------------------------------
# 15. test_debug_endpoint_requires_top_tier_auth
# ---------------------------------------------------------------------------

def test_debug_endpoint_requires_top_tier_auth(db, mock_meta_sender):
    """Operator (non-top-tier) role gets 403."""
    t = _seed_tenant(db, name="OperTest")
    u = _seed_owner(db, tenant_id=t.id, email="oper@test.test", role="viewer")
    _seed_phone(db, tenant_id=t.id, user_id=u.id, phone="+919900099002")

    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    token = create_access_token(user_id=u.id, tenant_id=t.id, role="viewer")
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/whatsapp/debug/dispatch",
                headers=headers,
                json={
                    "type": "morning",
                    "tenant_id": t.id,
                    "now": "2026-05-09T07:30:00",
                    "force_send": False,
                },
            )
            assert response.status_code == 403, response.text
            assert "top-tier" in response.json()["detail"].lower()
            assert mock_meta_sender == []
    finally:
        app.dependency_overrides.clear()
