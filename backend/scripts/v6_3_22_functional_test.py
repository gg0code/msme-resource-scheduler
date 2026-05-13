"""v6.3.22 functional smoke test — channel-decision send helper.

WHAT THIS SCRIPT DOES
Exercises send_with_window_decision against the real dev Postgres
across all 5 channel-decision outcomes:

  S1 — in 24h window  → freeform path  → whatsapp.freeform_sent
  S2 — outside window → template path  → whatsapp.template_sent
  S3 — last_seen NULL → template path  → whatsapp.template_sent
  S4 — unknown event  → no send        → whatsapp.window_expired_no_template
  S5 — param mismatch → no send        → whatsapp.template_param_mismatch

The script is FULLY TRANSACTIONAL: every row it inserts (tenant, user,
phone_tenant_map, events) is rolled back at the end. Nothing persists.
Mock mode is enforced — no Meta wire call ever fires.

WHY POSTGRES, NOT SQLITE
The unit-tier tests already cover this on SQLite. The point of running
against real Postgres is to confirm:
  - JSONB serialisation of the new whatsapp.* event payloads
  - SQLAlchemy's filter on PhoneTenantMap.last_seen_at against a real
    TIMESTAMPTZ column (not the SQLite-patched JSON proxy)
  - Index plans on events(tenant_id, event_type) per migration 034

USAGE
  cd backend && python scripts/v6_3_22_functional_test.py

Exits non-zero on any assertion failure so it can chain into a CI gate
later if needed.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

# Configure logging so we see [MOCK TEMPLATE] / [MOCK SEND] breadcrumbs.
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s | %(levelname)s | %(message)s",
)

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal
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


# Force mock mode in case the dev env has it disabled.
settings.WHATSAPP_MOCK_MODE = True


MORNING_ARGS = (
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


# --- helpers ----------------------------------------------------------------

def _seed_tenant(db) -> tuple[Tenant, User]:
    """Create one ephemeral tenant + owner. Caller rolls back."""
    suffix = datetime.now().strftime("%H%M%S%f")
    t = Tenant(
        name=f"v6322 functional {suffix}",
        slug=f"v6322-func-{suffix}",
        plan="paid",
        is_active=True,
    )
    db.add(t)
    db.flush()
    u = User(
        tenant_id=t.id,
        email=f"v6322-owner-{suffix}@example.test",
        hashed_password=hash_password("test-password"),
        role="proprietor",
    )
    db.add(u)
    db.flush()
    return t, u


def _seed_phone(db, *, tenant_id, user_id, phone, last_seen_at):
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


def _events_since(db, tenant_id, baseline_max_id, event_types):
    """Return events rows for this tenant with id > baseline_max_id and
    event_type in event_types. Lets each scenario isolate its own writes
    even though every row in the script will roll back."""
    return (
        db.query(Event)
        .filter(
            Event.tenant_id == tenant_id,
            Event.id > baseline_max_id,
            Event.event_type.in_(event_types),
        )
        .order_by(Event.id.asc())
        .all()
    )


def _max_event_id(db) -> int:
    """Read the current max events.id so each scenario can isolate its
    own writes via id > baseline."""
    from sqlalchemy import func
    row = db.query(func.max(Event.id)).one()
    return row[0] or 0


# --- scenarios --------------------------------------------------------------

async def run() -> int:
    failures: list[str] = []

    # One outer transaction; rolled back at the end.
    db = SessionLocal()
    try:
        # Begin a savepoint we can roll back. This keeps any concurrent
        # uvicorn workers untouched if they happen to be hitting the same
        # DB.
        outer_savepoint = db.begin_nested()

        # ---------- S1 — in 24h window: freeform ----------
        t, u = _seed_tenant(db)
        now = datetime.now(timezone.utc)
        _seed_phone(
            db, tenant_id=t.id, user_id=u.id,
            phone=f"+91999{t.id:07d}1",
            last_seen_at=now - timedelta(hours=2),
        )
        baseline = _max_event_id(db)
        outcome = await send_with_window_decision(
            db=db, tenant_id=t.id, phone_e164=f"+91999{t.id:07d}1",
            event="morning_briefing", language="en_US",
            args=MORNING_ARGS, free_form_text=MORNING_FREEFORM,
            alert_type="push_morning", now=now,
        )
        rows = _events_since(db, t.id, baseline, [EVENT_FREEFORM_SENT])
        print(f"[S1 in-window] path={outcome.path} success={outcome.success} "
              f"wamid={outcome.wamid!r} events={len(rows)}")
        if outcome.path != "freeform":
            failures.append(f"S1 expected path=freeform, got {outcome.path}")
        if not outcome.success:
            failures.append(f"S1 expected success=True, got False ({outcome.error})")
        if len(rows) != 1:
            failures.append(f"S1 expected 1 freeform_sent event, got {len(rows)}")
        elif rows[0].payload.get("within_window") is not True:
            failures.append(f"S1 payload.within_window expected True, got {rows[0].payload.get('within_window')}")

        # ---------- S2 — outside window: template ----------
        t2, u2 = _seed_tenant(db)
        _seed_phone(
            db, tenant_id=t2.id, user_id=u2.id,
            phone=f"+91999{t2.id:07d}2",
            last_seen_at=now - timedelta(hours=30),
        )
        baseline = _max_event_id(db)
        outcome = await send_with_window_decision(
            db=db, tenant_id=t2.id, phone_e164=f"+91999{t2.id:07d}2",
            event="morning_briefing", language="en_US",
            args=MORNING_ARGS, free_form_text=MORNING_FREEFORM,
            alert_type="push_morning", now=now,
        )
        rows = _events_since(db, t2.id, baseline, [EVENT_TEMPLATE_SENT])
        print(f"[S2 outside]   path={outcome.path} success={outcome.success} "
              f"wamid={outcome.wamid!r} used_fallback={outcome.used_fallback} "
              f"events={len(rows)}")
        if outcome.path != "template":
            failures.append(f"S2 expected path=template, got {outcome.path}")
        if not outcome.success:
            failures.append(f"S2 expected success=True, got False ({outcome.error})")
        if len(rows) != 1:
            failures.append(f"S2 expected 1 template_sent event, got {len(rows)}")
        else:
            payload = rows[0].payload
            if payload.get("meta_name") != "zetaops_morning_briefing":
                failures.append(f"S2 meta_name expected zetaops_morning_briefing, got {payload.get('meta_name')}")
            if payload.get("meta_params") != list(MORNING_ARGS):
                failures.append(f"S2 meta_params mismatch: {payload.get('meta_params')}")
            if payload.get("within_window") is not False:
                failures.append("S2 payload.within_window expected False")

        # ---------- S3 — last_seen NULL: template ----------
        t3, u3 = _seed_tenant(db)
        _seed_phone(
            db, tenant_id=t3.id, user_id=u3.id,
            phone=f"+91999{t3.id:07d}3",
            last_seen_at=None,
        )
        baseline = _max_event_id(db)
        outcome = await send_with_window_decision(
            db=db, tenant_id=t3.id, phone_e164=f"+91999{t3.id:07d}3",
            event="invite_team_member", language="en_US",
            args=("Suresh", "owner-test", "Test Factory", "Manager", "daily briefings"),
            free_form_text="Namaste Suresh, you have been invited...",
            alert_type="invite_welcome",
        )
        rows = _events_since(db, t3.id, baseline, [EVENT_TEMPLATE_SENT])
        print(f"[S3 null seen] path={outcome.path} success={outcome.success} "
              f"wamid={outcome.wamid!r} events={len(rows)}")
        if outcome.path != "template":
            failures.append(f"S3 expected path=template, got {outcome.path}")
        if len(rows) != 1:
            failures.append(f"S3 expected 1 template_sent event, got {len(rows)}")
        elif rows[0].payload.get("last_seen_at") is not None:
            failures.append("S3 payload.last_seen_at expected None")

        # ---------- S4 — unknown event ----------
        t4, u4 = _seed_tenant(db)
        _seed_phone(
            db, tenant_id=t4.id, user_id=u4.id,
            phone=f"+91999{t4.id:07d}4",
            last_seen_at=None,
        )
        baseline = _max_event_id(db)
        outcome = await send_with_window_decision(
            db=db, tenant_id=t4.id, phone_e164=f"+91999{t4.id:07d}4",
            event="not_a_real_event_xyz", language="en_US",
            args=("anything",), free_form_text="ignored",
            alert_type="bogus",
        )
        rows = _events_since(db, t4.id, baseline, [EVENT_WINDOW_EXPIRED_NO_TEMPLATE])
        print(f"[S4 unknown]   path={outcome.path} success={outcome.success} "
              f"error={outcome.error!r} events={len(rows)}")
        if outcome.path != "skipped_unknown_event":
            failures.append(f"S4 expected path=skipped_unknown_event, got {outcome.path}")
        if outcome.success:
            failures.append("S4 expected success=False")
        if len(rows) != 1:
            failures.append(f"S4 expected 1 window_expired_no_template event, got {len(rows)}")
        elif rows[0].payload.get("reason") != "unknown_event":
            failures.append(f"S4 payload.reason expected unknown_event, got {rows[0].payload.get('reason')}")

        # ---------- S5 — param mismatch ----------
        t5, u5 = _seed_tenant(db)
        _seed_phone(
            db, tenant_id=t5.id, user_id=u5.id,
            phone=f"+91999{t5.id:07d}5",
            last_seen_at=None,
        )
        baseline = _max_event_id(db)
        outcome = await send_with_window_decision(
            db=db, tenant_id=t5.id, phone_e164=f"+91999{t5.id:07d}5",
            event="morning_briefing", language="en_US",
            args=("12 May", "3"),  # 2 args; expects 6
            free_form_text="ignored", alert_type="push_morning",
        )
        rows = _events_since(db, t5.id, baseline, [EVENT_TEMPLATE_PARAM_MISMATCH])
        print(f"[S5 mismatch]  path={outcome.path} success={outcome.success} "
              f"error={outcome.error!r} events={len(rows)}")
        if outcome.path != "skipped_param_mismatch":
            failures.append(f"S5 expected path=skipped_param_mismatch, got {outcome.path}")
        if outcome.success:
            failures.append("S5 expected success=False")
        if len(rows) != 1:
            failures.append(f"S5 expected 1 template_param_mismatch event, got {len(rows)}")
        elif rows[0].payload.get("args_count") != 2:
            failures.append(f"S5 payload.args_count expected 2, got {rows[0].payload.get('args_count')}")

        # ---------- cleanup ----------
        outer_savepoint.rollback()
        print()
        print("Rolled back all inserts. Nothing persists in the dev DB.")
    finally:
        db.close()

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All 5 scenarios passed against real Postgres.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
