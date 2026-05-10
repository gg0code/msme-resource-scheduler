# v6.3.19 shadow-mode smoke tests

Manual checklist for the operator running the v6.3.19 slice 2D-shadow
verification. Run all five steps end-to-end before the v6.3.19 tag,
and again before flipping `PUSH_V2_ENABLED=true` in v6.3.19.1.

## Prerequisites

- Backend running locally with `WHATSAPP_MOCK_MODE=True` and
  `DEBUG_DISPATCH_ENABLED=True` (the `.env` defaults are correct).
- A top-tier user JWT for the test tenant. The `what@what.what /
  qazx1234 / tenant_id=12` test tenant from CLAUDE.md works.
- Test tenant has at least one active top-tier `PhoneTenantMap`
  row (the seed scripts handle this).
- `$TOKEN` in your shell holds a valid Authorization Bearer token
  (e.g. `export TOKEN=eyJ...`).

## 1. Trigger morning shadow dispatch for tenant 12 at simulated 07:30 IST

```bash
curl -X POST http://localhost:8000/api/v1/whatsapp/debug/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"type":"morning","tenant_id":12,"now":"2026-05-09T07:30:00","force_send":false}'
```

**Expected:** `200 OK`. JSON body has `shadow_log_event_id` (integer),
`actually_sent: false`, and `would_send_to` is a non-empty array of
phone numbers. `rendered_message` is the full Hinglish briefing text.

## 2. Inspect the shadow log row

```bash
curl "http://localhost:8000/api/v1/events?tenant_id=12&event_type=push.shadow_log" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected:** the response includes at least one entry from step 1.
The payload carries `kind: 'morning'`, `stage: 'sent'`,
`would_send: false`, `recipients: [...]`, and `rendered_message`. The
event row id should match `shadow_log_event_id` from step 1.

(If this endpoint does not exist yet — `/api/v1/events` is on the
v6.4 backlog — fall back to a direct DB query against the `events`
table for the same row.)

## 3. Trigger force-send in mock mode

```bash
curl -X POST http://localhost:8000/api/v1/whatsapp/debug/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"type":"morning","tenant_id":12,"now":"2026-05-09T07:31:00","force_send":true}'
```

**Expected:** `200 OK`, `actually_sent: true`. Backend stdout shows a
`[MOCK ALERT] Type=...` line for each recipient (via
`whatsapp_send._send_whatsapp_message` mock-mode logging). The
`events` table now has a `push.morning_sent` row in addition to the
shadow row from step 1.

Note the different `now` (07:31 instead of 07:30) — same calendar
date, so the dedup check in step 4 will trip on the next call.

## 4. Verify idempotency dedup

```bash
curl -X POST http://localhost:8000/api/v1/whatsapp/debug/dispatch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"type":"morning","tenant_id":12,"now":"2026-05-09T07:32:00","force_send":true}'
```

**Expected:** `200 OK`, `actually_sent: false`,
`skip_reason: "idempotent"`. The `events` table now also has a
`push.morning_skipped_idempotent` row. `mock_meta` (visible via
backend stdout) shows NO new `[MOCK ALERT]` line.

## 5. Verify legacy 5-min tick is gated by the flag

Set the env var and restart the backend:

```bash
PUSH_V2_ENABLED=true uvicorn app.main:app --reload
```

Watch stdout over a 6-minute briefing window (or trigger the legacy
tick manually via `/api/v1/whatsapp/trigger-dev-alerts` if available).

**Expected:** the legacy `briefing_dispatch_job tick` log line reads
`skipped — PUSH_V2_ENABLED=true; consolidated_briefing.push_v2_tick
is authoritative.` No `[MOCK ALERT]` lines from the legacy path.

Reset to default before further testing:

```bash
PUSH_V2_ENABLED=false uvicorn app.main:app --reload
```

## 6. Verify new tick fires (PUSH_V2_ENABLED=false default)

With the backend running normally, watch stdout at the configured
morning push time (`briefing_morning_time` for tenant 12 — default
07:30 IST).

**Expected:** `push_v2_tick: results=N sent=0 skipped=N failed=0
shadow=true` log line. `events` table accumulates one `push.shadow_log`
row per due tenant per day. No real Meta sends.

---

## Cutover gate criteria (v6.3.19.1 ship gate)

Do NOT flip `PUSH_V2_ENABLED=true` in production until ALL of the
following are true:

- [ ] At least 7 consecutive days of `push.shadow_log` rows in
      production with no `push.tick_failed` rows.
- [ ] Every shadow_log row carries a non-empty `recipients` list and
      a `rendered_message` longer than 200 characters.
- [ ] Manual spot check: 3 random shadow_log rows have
      `payload['scheduled_for_date']` matching the tenant's
      configured morning_push_time when converted to the tenant
      timezone.
- [ ] The 13 detector tests xfailed for date drift (CHANGELOG note 92)
      have been rewritten and re-passed in v6.3.19.1.
- [ ] Meta v2 conditional template re-submission has landed (or the
      release accepts the v1 template + placeholder hybrid).

When all five boxes are checked, run `python scripts/push_v2_flip.py
--enable` (slice 2D-flip) and restart the backend. Watch the next
two morning ticks for `push.morning_sent` rows.
