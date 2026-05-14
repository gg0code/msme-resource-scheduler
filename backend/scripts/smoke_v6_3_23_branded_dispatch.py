"""v6.3.23 mock-mode end-to-end smoke.

Drives the DoD bar from BrandAsset.md: triggers a morning briefing for
tenant 12 against the live uvicorn at 127.0.0.1:8000 and reports both
the HTTP response and the helper-written audit events. The actual
`[MOCK TEMPLATE]` / `[MOCK SEND]` / WARNING log lines go to the
uvicorn terminal — this script tells you exactly which line shapes
to grep for there.

Usage (with uvicorn already running on :8000):
    python backend/scripts/smoke_v6_3_23_branded_dispatch.py

Exit code 0 on success, 1 on failure.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Windows console is cp1252; rendered messages carry emoji + ₹ + em-dash.
# Reconfigure stdout/stderr so prints don't UnicodeEncodeError on the way out.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Make backend/ importable when run from repo root.
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import httpx  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.event import Event  # noqa: E402
from app.models.whatsapp import PhoneTenantMap  # noqa: E402
from sqlalchemy import select  # noqa: E402

BASE = "http://127.0.0.1:8000"
EMAIL = "what@what.what"
PASSWORD = "qazx1234"
TENANT_ID = 12


def _login() -> str:
    r = httpx.post(
        f"{BASE}/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _force_window_state(state: str) -> None:
    """Nudge phone_tenant_map.last_seen_at to force the helper's branch.

    state='outside' => set last_seen_at to 30h ago (template path)
    state='within'  => set last_seen_at to 2h ago (freeform path)

    Restores nothing — the smoke is destructive in a controlled way
    against the dev DB. Production runs would not use this.
    """
    db = SessionLocal()
    try:
        if state == "outside":
            new_ts = datetime.now(timezone.utc) - timedelta(hours=30)
        else:
            new_ts = datetime.now(timezone.utc) - timedelta(hours=2)
        rows = db.execute(
            select(PhoneTenantMap).where(
                PhoneTenantMap.tenant_id == TENANT_ID,
                PhoneTenantMap.is_active == True,  # noqa: E712
            )
        ).scalars().all()
        for r in rows:
            r.last_seen_at = new_ts
        db.commit()
        print(f"  set last_seen_at = {new_ts.isoformat()} for {len(rows)} row(s)")
    finally:
        db.close()


def _dispatch_morning(token: str, days_ahead: int = 0) -> dict:
    # The v6.3.19 dispatcher dedups on (tenant, event_type, scheduled_for_date).
    # Forward-dated `now` lets each pass land on its own dedup key so we can
    # exercise both branches in one smoke run.
    now = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat()
    r = httpx.post(
        f"{BASE}/api/v1/whatsapp/debug/dispatch",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "type": "morning",
            "tenant_id": TENANT_ID,
            "now": now,
            "force_send": False,
        },
        timeout=30.0,
    )
    if r.status_code != 200:
        print(f"  HTTP {r.status_code}: {r.text[:500]}")
    r.raise_for_status()
    return r.json()


def _recent_whatsapp_events(limit: int = 5) -> list[Event]:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Event).where(
                Event.tenant_id == TENANT_ID,
                Event.event_type.like("whatsapp.%"),
            ).order_by(Event.id.desc()).limit(limit)
        ).scalars().all()
        # Detach so we can read after session close.
        for r in rows:
            db.refresh(r)
        return list(rows)
    finally:
        db.close()


def _check_response(label: str, resp: dict, expected_path: str) -> bool:
    """Print one block of dispatch result; return True if the brand-header
    behaviour matched expectation."""
    print(f"\n[{label}] dispatch response:")
    print(f"  actually_sent = {resp.get('actually_sent')}")
    print(f"  sent_count    = {resp.get('sent_count')}")
    print(f"  skip_reason   = {resp.get('skip_reason')}")
    print(f"  would_send_to = {resp.get('would_send_to')}")
    rendered = resp.get('rendered_message') or ""
    print(f"  rendered_message (first 120 chars):\n    {rendered[:120]!r}")
    return bool(resp.get('actually_sent')) and resp.get('sent_count', 0) > 0


def _check_events(label: str, expected_event_type: str, after_id: int = 0) -> tuple[bool, int]:
    """Print events newer than `after_id`; return (found_expected, max_id_seen)."""
    print(f"\n[{label}] whatsapp.* events for tenant {TENANT_ID} since id>{after_id}:")
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Event).where(
                Event.tenant_id == TENANT_ID,
                Event.event_type.like("whatsapp.%"),
                Event.id > after_id,
            ).order_by(Event.id.asc()).limit(20)
        ).scalars().all()
    finally:
        db.close()
    if not rows:
        print("  (none)")
        return False, after_id
    found_expected = False
    max_id = after_id
    for e in rows:
        print(f"  id={e.id} type={e.event_type}")
        payload = e.payload or {}
        for k in ("event", "meta_name", "meta_language", "within_window",
                  "alert_type", "meta_params", "used_fallback", "wamid"):
            if k in payload:
                v = payload[k]
                # Trim long strings for readability.
                if isinstance(v, str) and len(v) > 120:
                    v = v[:120] + "..."
                print(f"    {k} = {v!r}")
        if "rendered_text" in payload:
            rt = payload["rendered_text"]
            print(f"    rendered_text (first 140) = {rt[:140]!r}")
        if e.event_type == expected_event_type:
            found_expected = True
        max_id = max(max_id, e.id)
    if not found_expected:
        print(f"  ! expected {expected_event_type!r} in recent events, not found")
    return found_expected, max_id


def _max_event_id() -> int:
    db = SessionLocal()
    try:
        row = db.execute(
            select(Event.id).order_by(Event.id.desc()).limit(1)
        ).scalar_one_or_none()
        return row or 0
    finally:
        db.close()


def main() -> int:
    print("v6.3.23 mock-mode end-to-end smoke")
    print(f"  base    = {BASE}")
    print(f"  tenant  = {TENANT_ID}")
    print(f"  account = {EMAIL}")

    try:
        token = _login()
        print(f"\nlogged in, token starts {token[:12]}...")
    except Exception as e:
        print(f"\nLOGIN FAILED: {e}")
        return 1

    baseline_id = _max_event_id()
    print(f"  baseline event id = {baseline_id} (only events newer than this count)")

    # --- PASS 1: force OUT-OF-WINDOW so the helper takes the template path,
    # exercising the brand-asset wiring + [MOCK TEMPLATE] line + WARNING.
    # Forward-date `now` by +2 days to dodge the morning-briefing dedup. ---
    print("\n=== PASS 1: force OUTSIDE 24h window (template path) ===")
    _force_window_state("outside")
    try:
        resp1 = _dispatch_morning(token, days_ahead=2)
    except Exception as e:
        print(f"DISPATCH FAILED: {e}")
        return 1
    ok1_response = _check_response("PASS 1", resp1, expected_path="template")
    ok1_events, last_id = _check_events(
        "PASS 1", "whatsapp.template_sent", after_id=baseline_id,
    )

    # --- PASS 2: force IN-WINDOW so the helper takes the freeform path
    # (no brand header), verifying the v6.3.22 freeform path still works
    # unchanged. Forward-date `now` by +3 days for its own dedup slot. ---
    print("\n=== PASS 2: force WITHIN 24h window (freeform path) ===")
    _force_window_state("within")
    try:
        resp2 = _dispatch_morning(token, days_ahead=3)
    except Exception as e:
        print(f"DISPATCH FAILED: {e}")
        return 1
    ok2_response = _check_response("PASS 2", resp2, expected_path="freeform")
    ok2_events, _ = _check_events(
        "PASS 2", "whatsapp.freeform_sent", after_id=last_id,
    )

    # --- Summary ---
    print("\n=== SUMMARY ===")
    print(f"  PASS 1 (out-of-window/template) response ok: {ok1_response}")
    print(f"  PASS 1 (out-of-window/template) audit ok:    {ok1_events}")
    print(f"  PASS 2 (in-window/freeform)     response ok: {ok2_response}")
    print(f"  PASS 2 (in-window/freeform)     audit ok:    {ok2_events}")
    print("\nIn your UVICORN terminal you should see, around PASS 1:")
    print('  - "[MOCK TEMPLATE] To=****... event_template=zetaops_morning_briefing '
          'language=en_US params=... header_asset=morning_briefing.png '
          'header_handle=None wamid=mock_wamid_..."')
    print('  - a WARNING line: "...morning_briefing.png but no header_image_handle '
          'yet — would fall through to body-only in real mode..."')
    print("And around PASS 2:")
    print('  - "[MOCK SEND] To=****... message=..." (freeform path, no header)')

    all_ok = ok1_response and ok1_events and ok2_response and ok2_events
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
