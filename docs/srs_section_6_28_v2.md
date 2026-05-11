# SRS Section 6.28 v2 — Consolidated Push Cadence

> **v6.3.19.1 update.** The shadow-mode pattern documented below
> (PUSH_V2_ENABLED flag, push.shadow_log events, 5-box cutover gate)
> was abandoned in v6.3.19.1: the flag was removed and the new push
> system became the sole code path. Sections **6.28.v2.6 Shadow mode**
> and **6.28.v2.7.2 Flip CLI** are retained for historical reference
> only. The push_v2_tick now sends authoritatively on every run; the
> legacy `run_briefing_dispatch_tick` + `check_delayed_jobs` +
> `check_scheduling_conflicts` functions were deleted in v6.3.19.1.
> dispatch_delay_alert and dispatch_conflict_alert also shipped in
> v6.3.19.1 (originally deferred per the D4 scope reduction); see
> CHANGELOG `[v6.3.19.1]` for the full migration.


**Status:** Markdown supplement. The canonical SRS lives in
`docs/ZetaOps_SRS_v6_6.docx` (and its v6.7+ successors). This file
captures the v6.3.19 push-dispatcher rewrite as plain Markdown so
engineering can reference it without round-tripping through Word.
**The .docx requires manual paste from this file** when the
documentation team next refreshes the canonical source — same
pattern v6.3.18 used for `docs/srs_section_23_voice_tone.md`.

**Document version on first paste:** Document v6.7 → Document v6.8.

**Branch:** v5-whatsapp.
**Release:** v6.3.19 (2026-05-10).
**Cross-references:** SRS §6.28 v1 (current cadence spec, pre-v6.3.19),
SRS §23 (Voice, Tone, and Formatting Standards — v6.3.18),
`docs/v6_3_19_smoke_tests.md` (operator verification checklist),
CHANGELOG `[v6.3.19]`.

---

## 6.28.v2.1 Why this exists

v6.3.19 retires the v5.10 era of four hardcoded WhatsApp ticks (5-min
briefing dispatcher + 8:00 delayed-jobs check + 8:30 conflict check
+ 7:03 AI-down ping) in favour of two **per-tenant-configurable**
ticks — one morning, one evening. The two ticks share one dispatcher
(`app/services/consolidated_briefing.py`) that wires through the
v6.3.18 Meta-bound templates and the v6.3.11 pattern-aware briefing
intelligence.

v6.3.19 ships the infrastructure in **shadow mode**: the new tick
runs every minute, computes due tenants, renders messages, but does
NOT send. The legacy 5-minute briefing tick continues to send
authoritatively. The cutover is deferred to v6.3.19.1 once shadow-
log verification is clean. This document specifies both the new tick's
behaviour and the shadow-mode safety pattern.

Per slice 2D scope reduction (D4), v6.3.19 migrates **only the
morning + evening cadence**. The 8:00 delayed-jobs tick and 8:30
conflict tick remain on the v5.10 inline path, ungated by the
cutover flag. v6.3.19.1 ships dispatch_delay_alert /
dispatch_conflict_alert and gates those legacy ticks too.

---

## 6.28.v2.2 Per-tenant push config

Three sources of truth, resolved by `app/services/push_config.resolve_push_config(tenant)`:

1. **Tenant override** — columns on the `tenants` row.
2. **System fallback** — `backend/config/push_defaults.yaml`.

(There is no industry-tier or per-vertical layer. The v6.3.19 brief
originally proposed an `industry_push_config` table; ops decision
during the slice 2A audit killed that table — "simpler, honest, no
fake structure" — and condensed it into the flat YAML.)

### 6.28.v2.2.1 Bridged briefing_* columns (migration 027, v6.3.1)

These five columns already existed at v6.3.1. v6.3.19 reuses them
verbatim rather than introducing parallel `push_*` columns. The
resolver maps them into PushConfig field names matching the v6.3.19
brief vocabulary:

| Tenant column (migration 027)   | PushConfig field      |
|---------------------------------|-----------------------|
| `briefing_morning_time` (TIME)  | `morning_push_time`   |
| `briefing_evening_time` (TIME)  | `evening_push_time`   |
| `briefing_timezone` (VARCHAR)   | `push_timezone`       |
| `briefing_morning_enabled` (BOOL) | `morning_enabled`   |
| `briefing_evening_enabled` (BOOL) | `evening_enabled`   |

A future slice 2A-rename may unify the namespace by renaming
`briefing_*` → `push_*` in a single breaking migration. v6.3.19
deliberately defers that work — the cost of touching ~5–10 caller
sites for naming-cleanliness alone outweighs the immediate benefit.

### 6.28.v2.2.2 New columns (migration 033, v6.3.19)

| Column                 | Type    | Default | Meaning                                   |
|------------------------|---------|---------|-------------------------------------------|
| `morning_sections`     | JSONB   | NULL    | Ordered section keys for the morning body |
| `evening_sections`     | JSONB   | NULL    | Ordered section keys for the evening body |
| `push_paused_until`    | DATE    | NULL    | Both pushes silently skip while ≥ today   |

NULL semantics: `morning_sections` / `evening_sections` fall through
to the YAML default. `push_paused_until=NULL` means "not paused".

### 6.28.v2.2.3 System fallback YAML

`backend/config/push_defaults.yaml`:

```yaml
morning_push_time: "07:30"
evening_push_time: "18:30"
push_timezone: "Asia/Kolkata"
morning_enabled: true
evening_enabled: true
morning_sections:
  - plan
  - flag
  - next_step
evening_sections:
  - completed
  - hours_logged
  - tomorrow_preview
```

The `morning_push_time` / `evening_push_time` / `push_timezone` /
`morning_enabled` / `evening_enabled` entries are operationally inert
today (the briefing_* columns are NOT NULL with their own server
defaults from migration 027) — they document design intent and serve
as a defensive fallback if any column is ever NULL'd manually.

The `morning_sections` / `evening_sections` entries DO fire
operationally, since migration 033 added those columns nullable with
no server default.

---

## 6.28.v2.3 The new ticks

### 6.28.v2.3.1 push_v2_tick

Registered in `app/services/whatsapp_alerts.start_scheduler` as
APScheduler cron job `push_v2_tick_job`:

```python
scheduler.add_job(
    func=run_push_v2_tick,
    trigger=CronTrigger(second=0, timezone="Asia/Kolkata"),
    id="push_v2_tick_job",
    coalesce=True,
    max_instances=1,
)
```

Every minute on the 0-second mark, the wrapper opens a sync session
and calls `app.services.consolidated_briefing.push_v2_tick(now, db)`.

The dispatcher iterates tenants whose `briefing_morning_enabled=True`
(or `briefing_evening_enabled=True` for the evening pass), resolves
PushConfig per tenant, and picks the ones whose
`morning_push_time.hour:minute` (or `evening_push_time.hour:minute`)
matches `now` converted to the tenant's timezone.

### 6.28.v2.3.2 Hash stagger

Per-tenant offset is `tenant_id % 60`. The dispatcher calls
`asyncio.sleep(offset)` before invoking `dispatch_morning` /
`dispatch_evening`:

| `tenant_id` | `offset_seconds` |
|-------------|------------------|
| 1           | 1                |
| 12          | 12               |
| 60          | 0                |
| 120         | 0                |
| 31          | 31               |
| 59          | 59               |

Tenant 60 and tenant 120 collide on offset 0 — a natural mod-60
artefact. With 3000 tenants spread across 60 buckets, each second
holds ~50 sends — comfortably below Meta API rate limits.

The stagger is deterministic so an owner sees the same arrival
second day after day.

`apply_stagger=False` kwarg lets tests bypass the asyncio.sleep
entirely.

### 6.28.v2.3.3 Idempotency

Every successful dispatch writes a `push.morning_sent` /
`push.evening_sent` event whose payload carries
`scheduled_for_date` (calendar date in tenant timezone).

Each subsequent dispatch checks for an existing `*_sent` event for
the same `(tenant_id, event_type, scheduled_for_date)` triple
before sending; if present, it returns
`DispatchResult(skip_reason='idempotent')` and does NOT re-render
or re-send.

The full-failure path (all recipients raised) does NOT write the
`*_sent` anchor — so the next tick can retry. Migration 034 added
the composite btree index `ix_events_tenant_type_dedup` on
`events(tenant_id, event_type)` to support this query at scale.

---

## 6.28.v2.4 Recipient resolution

Per slice 2C decision B1, recipients come from `PhoneTenantMap`
(matching the v5.10 dispatcher convention), not from `User`. The
filter:

```sql
SELECT * FROM phone_tenant_map
WHERE tenant_id = :tid
  AND is_active = TRUE
  AND phone_role IN ('owner', 'proprietor', 'factory_manager', 'co_owner')
  AND (alert_preferences ->> :alert_key) <> 'false'
ORDER BY id ASC;
```

`alert_key` is `push_morning` for morning dispatches, `push_evening`
for evening. **Default-True semantics** — when a tenant's
`alert_preferences` JSONB does not carry the key, the resolver
treats it as enabled. Same convention as the legacy
`whatsapp_alerts._get_active_phone_mappings`. Tenants who have
never explicitly opted out continue to receive the new push without
any alert_preferences migration.

Locale defaults to `'hi_en'` (Hinglish) for all recipients in
v6.3.19. Per-recipient locale resolution is deferred until a future
slice adds `User.language_preference` (the v6.3.19 brief assumed
that field existed; an audit found it does not).

---

## 6.28.v2.5 Hybrid flag rendering

The Meta-bound `MORNING_BRIEFING_EN` / `MORNING_BRIEFING_HI`
templates from v6.3.18 carry hard `{flag}` and `{next_step}`
placeholders. When the v6.3.11 pattern-briefing detector pipeline
returns no blocker-class signal, the dispatcher falls back to
benign placeholder text:

| Locale | flag                          | next_step                       |
|--------|-------------------------------|---------------------------------|
| hi_en  | "Aaj sab routine hai."        | "Koi action nahi chahiye."      |
| en     | "All systems normal today."   | "No action needed."             |

Tone follows SRS §23: calm, neutral, no exclamation.

**The placeholder is an explicit §23 tone exception.** §23 dispreferred
ambient acknowledgement-only messages on calm days — but the v6.3.18
template's hard placeholders cannot collapse to empty without a Meta
v2 conditional-section template re-submission. The v2 submission is
ops/business workflow; until it lands, the placeholder is the
honest stop-gap.

**Closing condition:** Meta approves a v2 template using
`{flag_section}` / `{next_step_section}` that collapse cleanly when
empty. At that point, the dispatcher render path switches via the
template registry, the placeholder lookup is removed, and §23 tone
purity is fully restored. CHANGELOG `[v6.3.19]` "Deferred"
subsection tracks this.

---

## 6.28.v2.6 Shadow mode (the safety pattern)

The new infrastructure ships behind `settings.PUSH_V2_ENABLED`,
defaulting **False**. While the flag is False:

- `push_v2_tick` runs every minute, computes due tenants, resolves
  recipients, renders messages — but does **NOT** send.
- Each dispatch logs a single `push.shadow_log` event consolidating
  skip + send paths under one `event_type`. Payload carries
  `kind` (`'morning'` or `'evening'`), `stage` (`'skipped_disabled'`
  / `'skipped_paused'` / `'skipped_no_recipients'` / `'sent'` /
  `'send_failed'`), and `would_send=False`.
- Idempotency dedup is **skipped** in shadow mode so every tick logs
  for verification.
- The legacy `whatsapp_alerts.run_briefing_dispatch_tick` continues
  to send authoritatively.

When `PUSH_V2_ENABLED=True` (post-v6.3.19.1 cutover):

- `push_v2_tick` becomes authoritative. Each dispatch logs
  `push.{kind}_sent` (or `push.{kind}_skipped_*` / `push.{kind}_send_failed`)
  per the existing event vocabulary.
- The legacy `run_briefing_dispatch_tick` early-returns with
  "skipped — PUSH_V2_ENABLED=true" log line.

The cutover is operator-driven via `python scripts/push_v2_flip.py
--enable`, run only after the 5-box gate criteria in
`docs/v6_3_19_smoke_tests.md` are all green.

Per D4: only the legacy 5-min briefing tick is gated by the flag in
v6.3.19. The 8:00 delay tick and 8:30 conflict tick remain
authoritative regardless until v6.3.19.1.

---

## 6.28.v2.7 Operator surface

### 6.28.v2.7.1 Debug endpoint

`POST /api/v1/whatsapp/debug/dispatch`. Top-tier auth required.
Gated behind `settings.DEBUG_DISPATCH_ENABLED` (defaults True in
dev/staging; production deployments must set False in `.env`).

Body:

```json
{
  "type": "morning" | "evening",
  "tenant_id": 12,
  "now": "2026-05-10T07:30:00",
  "force_send": false
}
```

`type` of `'delay_alert'` or `'conflict_alert'` returns 400 — those
dispatchers are scoped to v6.3.19.1 and not yet implemented.

Response:

```json
{
  "actually_sent": false,
  "skip_reason": null,
  "would_send_to": ["+919876543210"],
  "rendered_message": "...",
  "sent_count": 1,
  "success": true,
  "shadow_log_event_id": 4178
}
```

### 6.28.v2.7.2 Flip CLI

`backend/scripts/push_v2_flip.py`:

- `--enable` / `--disable` rewrites `PUSH_V2_ENABLED` in
  `backend/.env` via atomic write (`tempfile.mkstemp` +
  `os.replace`).
- `--status` prints the current value plus a count of
  `push.shadow_log` events in the last 24h. Sanity-check before
  flipping.
- `--env-file` lets ops target a non-default path.

Backend restart is required for the new value to take effect — the
script logs a "Restart backend to apply" reminder.

---

## 6.28.v2.8 Acceptance criteria

`6.28.v2-AC1` — A tenant with `briefing_morning_enabled=True` and
`briefing_morning_time=07:30` (in tenant timezone), no
`push_paused_until`, and at least one top-tier active
`PhoneTenantMap` row, receives exactly one morning push at 07:30
+ `(tenant_id % 60)` seconds (in tenant timezone) per calendar day.

`6.28.v2-AC2` — Same tenant, configured for evening at 18:30, also
receives exactly one evening push per day. Morning and evening
dedup independently (sending morning does not block evening).

`6.28.v2-AC3` — A tenant with `push_paused_until ≥ today` (tenant
timezone) receives neither push that day. Dispatcher logs
`push.{kind}_skipped_paused`.

`6.28.v2-AC4` — A tenant with `briefing_morning_enabled=False` is
filtered out of the morning tick at the DB level. Dispatcher does
NOT log `push.morning_skipped_disabled` — the tenant is invisible
to the morning tick (it remains visible to the evening tick when
`briefing_evening_enabled=True`).

`6.28.v2-AC5` — When the v6.3.11 pattern-briefing detector pipeline
returns no blocker-class signal, the rendered message contains the
hi_en placeholder text "Aaj sab routine hai." and "Koi action nahi
chahiye." (§23 tone exception, closes when Meta v2 lands).

`6.28.v2-AC6` — When a Meta send raises, the dispatcher catches
the exception, writes one `push.{kind}_send_failed` row with the
exception message, and continues to the next recipient. The
`*_sent` anchor is NOT written (next tick can retry).

`6.28.v2-AC7` — Calling `push_v2_tick` while
`settings.PUSH_V2_ENABLED=False` writes `push.shadow_log` events
and does NOT call `_send_whatsapp_message`. The legacy
`run_briefing_dispatch_tick` continues to send.

`6.28.v2-AC8` — Calling `push_v2_tick` while
`settings.PUSH_V2_ENABLED=True` writes `push.{kind}_sent` events
and DOES call `_send_whatsapp_message`. The legacy
`run_briefing_dispatch_tick` early-returns.

`6.28.v2-AC9` — All ten dispatcher failure modes (FM1–FM10) listed
in `tests/integration/test_2d_dispatcher.py` either have a passing
test in the matrix OR are explicitly documented as accepted gaps
(FM1 = APScheduler-not-firing, monitored at boot only).

`6.28.v2-AC10` — Migration `034_add_events_dedup_index` keeps the
idempotency dedup query bounded as the events table grows. Without
this index, a long-lived production database would full-scan
events on every tick.

Test coverage matrix: see `tests/integration/test_2d_dispatcher.py`
for FM1–FM10 mapping; see `tests/services/test_consolidated_briefing.py`
for unit-tier coverage of select_flag_and_next_step, PushConfig
resolution, field computers, dispatch_morning/dispatch_evening
behaviour, and shadow-mode smoke.

---

## 6.28.v2.9 Deferred to v6.3.19.1

- **`dispatch_delay_alert` / `dispatch_conflict_alert`** —
  template field shapes diverge from morning (DELAY_ALERT_EN
  expects `{job_name, customer, time_remaining, progress, next_job}`;
  CONFLICT_ALERT_EN expects `{job_a, job_b, resource, window,
  next_step}`). v6.3.19 ships morning + evening only; the legacy
  8:00 + 8:30 ticks survive ungated.
- **The cutover flip itself** — `PUSH_V2_ENABLED=true` is set in
  production only after the 5-box gate in
  `docs/v6_3_19_smoke_tests.md` is all green.
- **Detector test date-anchoring infrastructure fix** — 13 tests
  xfailed in v6.3.19 for date drift (CHANGELOG note 92). v6.3.19.1
  rewrites the 13 with consistent `TODAY` / `NOW` anchoring.
- **Legacy 5-min briefing tick removal** — code is gated, not
  deleted, in v6.3.19. v6.3.20 removes the legacy code path once
  shadow verification clears.
- **`User.language_preference` + per-recipient locale routing** —
  out of scope for v6.3.19; placeholder for the future slice that
  adds the column.
- **Meta v2 conditional-section template re-submission** — ops
  workflow. Closes the §23 tone exception when approved.
- **`industry_push_config` table** — killed during slice 2A audit.
  The flat YAML is the system fallback; per-industry tiering is a
  v7.x design concern if it ever materialises.

---

## 6.28.v2.10 Glossary additions

- **Shadow mode** — `PUSH_V2_ENABLED=False`. New tick computes
  what would have been sent and logs `push.shadow_log` rows. No
  Meta traffic.
- **Real mode** — `PUSH_V2_ENABLED=True`. Post-cutover. New tick
  is authoritative; legacy tick early-returns.
- **Cutover gate** — the 5-box checklist in
  `docs/v6_3_19_smoke_tests.md` that must all be green before ops
  flips `PUSH_V2_ENABLED=true` in production.
- **Hash stagger** — per-tenant deterministic offset in seconds,
  computed as `tenant_id % 60`. Spreads sends across the 60-second
  tick window so 3000 tenants don't all fire at the same instant.
