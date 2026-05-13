# ZetaOps Copilot — Delivery Ledger

**Purpose.** This file is the source of truth for *what is actually built* — as
distinct from the SRS, which describes *what the product should be*. When the
two disagree, this file wins for "is it shipped"; the SRS wins for "what is the
spec." Both must be reconciled in any release that closes the gap.

**Update rule.** Any commit that changes the status of a feature updates the
matching row in the same commit. Treat this like a file-header version number —
not optional, not deferred to a cleanup pass.

**Last updated:** 2026-05-13 — **v6.3.20 release-blocker fixed: briefing classifier disambiguation.** `whatsapp_intent.detect_briefing_request_intent` was intercepting settings-change phrases like `"morning briefing 8 baje karo"` and routing them to `manual_trigger_briefing` instead of the AI's `update_push_setting` tool. New `_SETTINGS_TIME_CUE_RE` regex + `_SETTINGS_STRONG_VERBS` frozenset suppress dispatch when a briefing keyword co-occurs with a settings signal. Tests: 13 new negative cases + 10 new positive regression cases in `tests/test_briefings.py::TestBriefingIntent`. Test counts: **1108 unit-tier passing** (+23 from part 2's 1085). Migration head unchanged at 034. **Walkthrough still pending** — operator should re-run `docs/v6_3_20_manual_walkthrough.md` step 1 first to confirm the original bug is closed before proceeding.

**Last updated:** 2026-05-12 — **v6.3.20 part 2 landed (untagged, walkthrough pending).** Bridge plumbing for the v6.3.20 NL push-settings updater. `actor_user_id` + `phone_number` now flow from `IdentityResult` (set by `resolve_identity` in `whatsapp_identity.py`) through `app/routers/whatsapp.py:1075` → `whatsapp_bridge.AIChannelBridge.process_message` (Protocol + `GroqDirectBridge` impl) → `ai_service.run_ai_chat` → `execute_tool`. All four signatures gain optional kwargs defaulting to None so the web-UI `ai_chat` caller continues working unchanged. With this commit the three v6.3.20 tools become callable end-to-end from WhatsApp: writes stage in Redis under `whatsapp:pending_action:<phone>` and the existing v5.6 confirmation flow at `whatsapp.py:831` resolves HAAN/NAHI into the actual write via `whatsapp_actions.execute_action`. New test file `tests/test_v6_3_20_plumbing.py` (7 cases) covers both legs of the security boundary: `run_ai_chat` carries the kwargs through when given, defaults to None on the web-UI path, and the v6.3.20 write tools refuse with `tool_requires_whatsapp_channel` when either kwarg is missing (incl. partial-kwarg variants). Test counts: **1085 unit-tier passing** (+7 from part 1's 1078). Migration head unchanged at 034. **Remaining v6.3.20 acceptance:** the manual WhatsApp mock-mode walkthrough at `docs/v6_3_20_manual_walkthrough.md` (9 steps, must be run before tagging v6.3.20).

**Last updated:** 2026-05-11 — **v6.3.20 part 1 landed (untagged, in progress).** Backend foundations for the WhatsApp NL push-settings updater. New service module `app/services/push_settings_service.py` (~520 lines): `EDITABLE_FIELDS` whitelist (9 scalar columns; `morning_sections`/`evening_sections` deliberately excluded with typed `field_not_editable_via_whatsapp` redirect), four validators (bool / HH:MM / IANA tz / ISO weekday CSV), trilingual (English / Hinglish / Hindi) error templates, three service functions (`update_push_setting`, `pause_push`, `get_push_settings`). `pause_push` computes `today + (days - 1)` in tenant timezone with `[1, 30]` bounds, replaces (not adds to) any existing pause. Every successful write inserts one `events` row with `event_type='tenant.push_setting_changed'` and `source='whatsapp'`. Confirmation flow extended via existing v5.6 machinery in `whatsapp_actions.py`: new `UPDATE_PUSH_SETTING` + `PAUSE_PUSH` ActionTypes, sync `store_pending_action_sync` helper (uses new sync `sync_redis_client` in `whatsapp_session.py` + existing `_mock_sessions` fallback), `_execute_update_push_setting` + `_execute_pause_push` executors that delegate to the service module after user replies HAAN. Three Groq tools registered in `ai_service.TOOLS`; `execute_tool` extended with optional `actor_user_id` / `phone_number` kwargs (write tools refuse with `tool_requires_whatsapp_channel` when missing). System prompt addendum in `_SYSTEM_PROMPT_BASE` covers routing rules, sections-desktop-only redirect, confirmation-flow rule, top-tier permission rule. Test coverage: 26 cases in new `tests/services/test_push_settings_service.py` covering happy paths, all 4 validator rejection types, top-tier gate, owner-vs-self user-override rule, audit row shape, tenant isolation, full executor integration. Test counts: **1078 unit-tier passing** (+26 new from baseline 1052 + zero regressions). Migration head unchanged at 034. **v6.3.20 part 2 deferred:** plumbing `actor_user_id`/`phone_number` from `app/routers/whatsapp.py:1075` → `whatsapp_bridge.process_message` → `run_ai_chat` → `execute_tool`, plus the manual WhatsApp mock-mode walkthrough required by the v6.3.20 acceptance criteria. Steps 1 (schema_context) and 7 (dispatcher pause check) from the v6.3.20 prompt were already shipped in v6.3.19 — no work this commit.

**Last updated:** 2026-05-11 — **v6.3.19.1 shipped (cutover release).** Both slice 3A and slice 3B landed in this release. The shadow-mode pattern v6.3.19 introduced was abandoned: `PUSH_V2_ENABLED` flag removed entirely from `app/config.py`, the legacy v5.10-era push functions (`run_briefing_dispatch_tick`, `check_delayed_jobs`, `check_scheduling_conflicts`) and their orphaned helpers (~232 lines) deleted from `whatsapp_alerts.py`, scheduler registrations cleaned up. `consolidated_briefing.dispatch_delay_alert` and `dispatch_conflict_alert` shipped — async, per-job/per-conflict, rendering the Meta-bound `DELAY_ALERT_EN` / `CONFLICT_ALERT_EN` templates. `push_v2_tick` extended to fire delay alerts at 8/10/12/14/16/18/20 IST and conflict alerts at 8:30/12:30/16:30/20:30 IST (legacy parity, no dedup). New alert keys `push_delay` / `push_conflict` + event vocabulary `push.delay_*` / `push.conflict_*`. Debug endpoint extended for `type='delay_alert'` / `'conflict_alert'`. Slice 3A: `freezegun==1.5.5`, autouse anchor fixture, all 13 detector xfails stripped, 26-case 90-day verification harness. `tests/integration/test_push_v2_flip.py` deleted (CLI obsolete; script retained with OBSOLETE header). Two retired tests in `test_2d_dispatcher.py`. Tests: 1052 unit + 31 integration passing, 0 xfailed (was 13), 0 failed. Migration head unchanged at 034.

**Last updated:** 2026-05-11 — v6.3.19.1 slice 3A landed: detector test date-anchoring fix. `freezegun==1.5.5` added to requirements; autouse `freeze_clock_at_detector_today` fixture in `tests/services/conftest.py` pins `datetime.now()` to `date(2026, 5, 4)` matching the detector tests' hardcoded TODAY. All 13 `xfail` markers stripped (3 from `test_detect_idle_machine.py` + 2 from `test_detect_low_utilization.py` + 2 from `test_detect_manager_silence.py` + 2 from `test_detect_new_employee_no_show.py` + 3 from `test_detect_no_progress.py` + 1 from `test_detect_status_change_alert.py`). Dead `import pytest` lines also stripped. New 26-case 90-day verification harness in `tests/services/test_detector_date_anchoring.py` proves anchor-invariance: `detect_delayed_jobs` fires identically across 13 frozen-`now()` anchors spanning Jan–Jul 2026, in both positive and negative cases. Production behaviour unaffected — test-infrastructure change only. Test counts: 1054 unit passing (+39: 13 xfails became passing + 26 new harness cases), 0 xfailed (was 13). Migration head unchanged at 034. Slice 3B (dispatch_delay_alert + dispatch_conflict_alert) next.

**Last updated:** 2026-05-10 — **v6.3.19 shipped (shadow mode).** All five planned slices landed: slice 1 (flag/next_step selector), slice 2A (migration 033 + push_config + yaml + tests), slice 2B (field computation helpers), slice 2C (async dispatch_morning + dispatch_evening + migration 034), slice 2D-shadow (push_v2_tick + PUSH_V2_ENABLED flag + debug endpoint), slice 2D-tests (15 integration tests in `tests/integration/test_2d_dispatcher.py`), slice 2D-flip (`scripts/push_v2_flip.py` admin CLI + 7 integration tests), slice 2E (release wrap — `docs/srs_section_6_28_v2.md` markdown supplement, CLAUDE.md current-state refresh, ledger row flipped to `shipped (shadow mode)`, CHANGELOG `[Unreleased]` → `[v6.3.19]`). Migration head 034. Tests: 1015 unit-tier passing + 22 integration passing + 13 xfailed (detector test date drift — v6.3.19.1 fix scoped per CHANGELOG note 92). **Cutover from shadow to real-send is deferred to v6.3.19.1** — ops runs `python scripts/push_v2_flip.py --enable` after the 5-box verification gate in `docs/v6_3_19_smoke_tests.md` is green. Legacy 5-min briefing tick stays authoritative until then. Legacy 8:00 + 8:30 ticks survive ungated until v6.3.19.1 ships dispatch_delay_alert / dispatch_conflict_alert (D4 scope reduction).

**Last updated:** 2026-05-10 — v6.3.19 slice 2D-flip landed: `backend/scripts/push_v2_flip.py` ships the admin CLI for the `PUSH_V2_ENABLED` cutover gate (`--enable` / `--disable` / `--status`). Atomic write via `tempfile.mkstemp` + `os.replace`. **Flag NOT flipped in this session** — default stays `PUSH_V2_ENABLED=false`; flip is a v6.3.19.1 follow-up after shadow-log verification (5-box gate criteria in `docs/v6_3_19_smoke_tests.md`). Live `--status` against the dev DB confirms: `PUSH_V2_ENABLED` not present in `.env` (implicit default false), 0 `push.shadow_log` events in the last 24h — gap noted: dev hasn't yet run uvicorn through a 7:30 IST tick after slice 2D-shadow shipped, so no shadow rows have accumulated. 7 integration tests for the script in `tests/integration/test_push_v2_flip.py` (22 integration cases total now: 15 dispatcher + 7 flip), all green.

**Last updated:** 2026-05-10 — v6.3.19 slice 2D-tests landed: `tests/integration/test_2d_dispatcher.py` ships 15 failure-mode tests covering all 10 dispatcher failure modes from the v6.3.19 brief (FM1 APScheduler-not-firing intentionally uncovered — gap accepted, monitored via scheduler heartbeat; FM3 wrong-content has partial coverage via slice 2C unit tests; FM9 locale locks the A1 default-hi_en contract until per-recipient resolution lands). All 15 green via `pytest tests/integration/test_2d_dispatcher.py -v`. Marked `@pytest.mark.integration` so they are excluded from the unit-tier gate and run on demand. `docs/v6_3_19_smoke_tests.md` ships the operator curl checklist and the 5-box v6.3.19.1 cutover gate criteria. Test count: 1015 passed (unit), 15 passed (integration, on demand), 13 xfailed unchanged.

**Last updated:** 2026-05-10 — v6.3.19 slice 2D-shadow landed: new APScheduler cron job `push_v2_tick_job` runs every minute on the 0-second mark (cron not interval to avoid drift). Iterates tenants whose `briefing_morning_time` / `briefing_evening_time` matches `now` in their timezone, applies `tenant_id % 60` hash stagger, and calls `dispatch_morning` / `dispatch_evening`. New `settings.PUSH_V2_ENABLED` flag (default False) gates whether the new tick sends or shadow-logs; when False the dispatchers run with `shadow=True` and write a single `push.shadow_log` event consolidating skip + send paths under one event_type with `would_send=False`. New operator endpoint `POST /api/v1/whatsapp/debug/dispatch` exposes shadow / force-send testing for ops. Per slice 2D scope reduction (D4), only the legacy 5-min briefing tick is gated by the flag; the 8:00 delay tick and 8:30 conflict tick survive ungated until v6.3.19.1 wires up dispatch_delay_alert / dispatch_conflict_alert. CHANGELOG note 92 expanded — 13 detector tests now xfailed for the same date-drift root cause (test infrastructure only, production behaviour unaffected); v6.3.19.1 will rewrite all 13 with consistent `TODAY` / `NOW` anchoring (new ledger row added below). Migration head unchanged at 034. Test count: 1015 passed, 13 xfailed (was 5), 0 failed.

**Last updated:** 2026-05-09 — v6.3.19 slice 2C landed: `dispatch_morning` and `dispatch_evening` async functions in `consolidated_briefing.py` wire `PushConfig` (slice 2A) + field computers (slice 2B) + `select_flag_and_next_step` (slice 1) + Meta-bound `MORNING_BRIEFING_EN/HI` template + the existing `_send_whatsapp_message` transport. Argument order `(tenant_id, now, db)` matches slice 2B; zero `datetime.utcnow()` / `datetime.now()` calls in the module (verified by grep). `DispatchResult` frozen dataclass returned. Idempotency via events-table dedup keyed on `(tenant_id, event_type, payload['scheduled_for_date'])`; migration `034_add_events_dedup_index` adds the supporting `ix_events_tenant_type_dedup` composite btree index. Recipients resolved via `PhoneTenantMap` (B1 — matches v5.10 pattern) with new alert keys `push_morning` / `push_evening` and top-tier role gate. Locale defaults to `'hi_en'` (A1 — per-recipient deferred). Hybrid flag rendering uses benign placeholder until Meta v2 conditional-section template approves. Slice 2C ships morning + evening only; delay/conflict dispatchers deferred to v6.3.19.1 (D4). 14 new dispatcher tests in `tests/services/test_consolidated_briefing.py`, all green. 1017 passed total (+15 from session start), xfail count unchanged at 5. Migration head 033 → 034.

**Last updated:** 2026-05-09 — v6.3.19 slice 2B landed: three pure-SQL field computation helpers appended to `app/services/consolidated_briefing.py` (`_compute_jobs_starting`, `_compute_continuing`, `_compute_crew_expected`). Helpers are pure reads, no clock access, no scheduling; every query filters by `tenant_id` per CLAUDE.md rule 1. `_compute_continuing` uses `is_locked DESC, start_date ASC, id ASC` ordering — locked jobs lead the line as explicit owner commitments. `_compute_crew_expected` excludes contractors from the math (per-day contractor check-in is the future feature that closes the gap) and surfaces a gap-disclosure line when `contractor_count >= permanent_count`. 18 new unit tests in `tests/services/test_consolidated_briefing.py` (29 cases total in that file with slice 1's 11). xfail count unchanged at 5; alembic head still 033.

**Last updated:** 2026-05-09 — v6.3.19 slice 2A part 2 landed: `app/services/push_config.py` ships `resolve_push_config(tenant) -> PushConfig` with a two-layer cascade (tenant override → `backend/config/push_defaults.yaml`). PushConfig is a frozen dataclass with split `morning_enabled` / `evening_enabled` (independent per direction). The resolver bridges briefing_* columns (migration 027) into PushConfig field names that match the v6.3.19 brief; migration 033 columns flow through with active YAML fallback for the two sections fields. 10 unit tests in `tests/services/test_push_config.py` — all green; xfail count unchanged at 5; alembic head still 033. No caller wired yet — slice 2C will consume PushConfig from the dispatcher.

**Last updated:** 2026-05-09 — v6.3.19 slice 2A part 1 landed: migration `033_add_push_columns_to_tenants` adds three nullable columns to `tenants` (`morning_sections JSONB`, `evening_sections JSONB`, `push_paused_until DATE`). Tenant ORM in `app/models/auth.py` and `app/knowledge_graph/schema_context.py` updated in the same commit. Migrations 027 columns (`briefing_morning_time`, `briefing_evening_time`, `briefing_timezone`, `briefing_morning_enabled`, `briefing_evening_enabled`) are deliberately reused — see CHANGELOG `[Unreleased]` "Naming bridge in resolve_push_config" for the slice 2A scope decision and the deferred `slice 2A-rename` follow-up. Migration head advances 032 → 033; xfail count unchanged at 5; alembic chain verified single-head.

**Last updated:** 2026-05-09 — v6.3.19 morning-briefing flag/next_step selector landed as a lookup-table-only slice. New row added below for "Morning-briefing flag/next_step rendering" — status `in progress`. `backend/app/services/consolidated_briefing.py` ships `select_flag_and_next_step` (pure function over a pre-sorted `SignalResult` list) plus `_BLOCKER_CLASS_SIGNALS` (8 ids) and `_NEXT_STEP_TEMPLATES` (16 strings: hi_en + en for each id). 7 unit tests in `tests/services/test_consolidated_briefing.py` (11 cases incl. parametrised invalid-locale cases) — all green; xfail count unchanged at 5; migration head unchanged at 032. The dispatcher rewrite, cascade resolver, migrations 033/034, template registry wiring, and Meta v2 hybrid-template handoff are deferred to follow-up prompts in the v6.3.19 release window.

**Last updated:** 2026-05-08 — v6.3.18 WhatsApp message styling pass shipped: centralised emoji vocabulary (`message_emoji.py`), entity formatters + 5 Meta-bound template constants (`message_formatters.py`), Meta HSM template registry (`whatsapp_meta_templates.py` + `.json`, 35 entries from `meta/templates_v2.json` plus new Hindi `zetaops_job_conflict_alert` draft), dispatcher-shape templates (`message_templates.py`) wired into `whatsapp_alerts.py` (`_build_morning_briefing`, `_build_delay_alert`, `_build_conflict_alert`, `send_machine_down_alert`) and the WhatsApp AI reply path (`routers/whatsapp.py:1089` via `render_ai_reply()`). New SRS Section 23 (Voice, Tone, and Formatting Standards), AC IDs 23-AC1–AC8 all verified by 75 new passing tests (51 in `test_message_formatters.py` + `test_message_templates.py`, 24 in `tests/services/test_message_dispatcher_templates.py`). Migration head stays 032; no schema. Old `whatsapp_formatter.py` reduced to a backwards-compat re-export shim. Meta-bound `_EN`/`_HI` constants stay as infrastructure for v6.4 when the morning briefing data shape catches up — see CHANGELOG `[v6.3.18]` "Deferred" subsection for details.

**Last updated:** 2026-05-08 — version-number gap policy documented; v5.11 / v5.13 / v5.14 retired from "blocked" list (work shipped under v6.3.7+v6.3.8, v5.2-voice-notes, v6.3.5 respectively).

**Last updated:** 2026-05-07 — v6.3.16 Day-7 First-Insight Gate and v6.3.17 WhatsApp owner-bypass entity writes shipped and tagged on dev. Both verified end-to-end against real Postgres tenant 12 in mock-mode. CHANGELOG entries written in the same pass that updated this ledger.

Prior update (2026-05-06 → 2026-05-07): v6.3.15 (revised) Owner-Confirmed Candidate Promotion landed (silent insertion retracted; nightly job now batches qualifying candidates per tenant and sends a single WhatsApp confirmation requesting explicit HAAN/NAHI; only on HAAN does insertion happen; reply-parser is hybrid heuristic+LLM; migration `030` added the four `confirmation_*` columns to `extraction_candidates`).

Prior update (2026-05-05): v6.3.13 + v6.3.14 CHANGELOG entries backfilled (the prerequisite versions for the v6.3.15 Candidate Promotion Job that shipped earlier the same day).

**Current migration head:** `034` (per `alembic heads`). Chain through the v6.3.x
window: `028` events audit table (v6.3.3); `029` `extraction_candidates`
staging table (v6.3.13); `030` `confirmation_*` columns on
`extraction_candidates` (v6.3.15 revised); `031` `first_briefing_sent_at`
+ `engagement_ladder_state` columns on `tenants` (v6.3.16); `032` `source`
column on `skills` (v6.3.17); `033` `morning_sections` + `evening_sections`
+ `push_paused_until` columns on `tenants` (v6.3.19 slice 2A); `034`
`ix_events_tenant_type_dedup` composite index on `events` (v6.3.19
slice 2C). Next migration must use revision ID `035` and chain
`down\_revision = "034"`.

\---

## Status vocabulary

Tight values only. No fuzzy words.

|Status|Meaning|
|-|-|
|`not started`|Spec exists, no code yet.|
|`in progress`|Code being written, tests not yet passing, no tag.|
|`partial`|Tag exists, some acceptance criteria pass, others deferred.|
|`shipped`|Tag exists, all acceptance criteria pass, feature flag default decided.|
|`blocked`|External dependency holding it back (Meta review, third-party API).|

The "Acceptance N/M" column reads: M criteria specified in SRS, N currently
passing. Deferred column names the specific AC IDs (e.g. `6.28-AC10`) still
open.

\---

## Active features

### V4 era (multi-industry foundation) — shipped baseline

|Feature|SRS §|Spec'd in|Status|Shipped in|Flag|Migration|Acceptance|Deferred|
|-|-|-|-|-|-|-|-|-|
|Multi-industry config layer|4|v4.0|shipped|v4.0.3|(always on)|016|n/a|none|
|Industry-aware AI Copilot|6.13|v4.0.8|shipped|v4.0.8|ai\_copilot=True|—|n/a|none|
|Demo data seeder|6.14|v4.0.6|shipped|v4.0.6|(always on)|—|n/a|none|
|Getting Started onboarding (8-step)|6.15|v4.1|shipped|v4.1|(always on)|—|n/a|none|
|CSV / Excel import|6.16|v4.0|shipped|v4.0.x|csv\_import=True|—|n/a|none|
|CSS theme engine|4.4|v4.0.7|shipped|v4.0.7|(always on)|—|n/a|none|

### V5 era (WhatsApp-first MSME platform)

|Feature|SRS §|Spec'd in|Status|Shipped in|Flag|Migration|Acceptance|Deferred|
|-|-|-|-|-|-|-|-|-|
|WhatsApp Copilot pipeline (mock)|6.13|v5.0–5.9|shipped|v5.9|whatsapp\_copilot=True|017|n/a|none|
|Proactive alerts (briefing/conflict)|6.13|v5.10|shipped|v5.10|whatsapp\_copilot=True|—|n/a|none|
|WhatsApp production cutover|—|originally v5.11; shipped at v6.3.7 + v6.3.8|blocked on Meta approval (engineering complete)|v6.3.7 + v6.3.8|(env switch: WHATSAPP\_MOCK\_MODE)|—|0/n|Meta Business portfolio review pending; v5.11 number unused — see CLAUDE.md "Version-number gaps are normal"|
|Role limiting (owner/manager/viewer)|6.17|v5.12|shipped|v5.12|(always on)|018|n/a|none|
|3-language support (Hi/Hg/En)|6.18|v5.12|shipped|v5.12|(always on)|—|n/a|none|
|Voice notes (Whisper)|6.13|originally v5.13; shipped at v5.2-voice-notes|shipped (mock); blocked on Meta approval for real audio|v5.2-voice-notes|whatsapp\_copilot=True|—|n/a|v5.13 number unused — implementation landed Mar 30 at v5.2-voice-notes; real inbound audio gated by Meta portfolio review|
|Manager check-in flow (7:00am)|6.20|v5.15|shipped|v5.15|whatsapp\_copilot=True|—|n/a|none|
|Owner briefing (7:15am)|6.21|v5.15|shipped|v5.15|whatsapp\_copilot=True|—|n/a|none|
|Day 1 Simple Table|6.19|v5.16|shipped|v5.16|(always on)|023|n/a|none|

### V6 era (AI-first intelligent platform)

|Feature|SRS §|Spec'd in|Status|Shipped in|Flag|Migration|Acceptance|Deferred|
|-|-|-|-|-|-|-|-|-|
|Schema Context layer|17.2|v6.0|shipped|v6.0|(always on)|—|n/a|none|
|RAG pipeline (flat-file MVP)|6.22|v6.1|shipped|v6.1|(always on)|—|n/a|none|
|Industry-aware dynamic UI labels|6.23|v6.2|shipped|v6.2|(always on)|—|n/a|none|
|RegisterPage auth fix|7.2#23|v6.2|shipped|v6.2|(bug fix)|—|n/a|none|
|Test suite recovery (199 passing)|22|v6.2.2|shipped|v6.2.2-test-recovery|(no flag)|—|n/a|none|
|BUG-6: industry\_type from Tenant ORM|—|v6.3.0|shipped|v6.3.0-whatsapp-industry|(bug fix)|—|n/a|none|
|KPI Baseline + Monthly Savings|6.24|v6.3|in progress|—|kpi\_baseline=True|TBD|?/8|6.24-AC? (verify count)|
|Top-Tier Role Group (Owner/FM/Co-O)|6.28-F2|v6.4|in progress|—|whatsapp\_entry\_gate=True|027 plan|?/13|6.28-AC? (work split across v6.3.1–v6.3.6 — see notes)|
|Entry Mode Configuration|6.28-F1|v6.4|in progress|—|whatsapp\_entry\_gate=True|027 plan|?/13|6.28-AC? (work split across v6.3.1–v6.3.6 — see notes)|
|Daily Push Briefings (AM+PM)|6.28-F3|v6.4|in progress|—|whatsapp\_entry\_gate=True|027 plan|?/13|6.28-AC? (CHANGELOG suggests dispatcher landed at v6.3.4 — verify)|
|UI Consolidation (Invite, /welcome)|6.28.4|v6.3.5 doc|partial|v6.3.5|whatsapp\_entry\_gate=True|(no schema)|?/12|6.28.4-AC? (CHANGELOG v6.3.5 claims 12/12 — verify against tests)|
|Day-1 Onboarding Sequence|? (deferred)|v6.3.12|shipped|v6.3.12|(always on)|—|?/?|locale routing (v6.3.18), field-service grammar (v6.3.18), push\_schedule cascade (v6.3.19), AC IDs (v6.3.7..12 batched pass)|
|Events audit table|9.2|v6.3.3|shipped|v6.3.3|(no flag)|028|n/a|none|
|Extraction candidates staging table|? (deferred)|v6.3.13|shipped|v6.3.13|(no flag — schema only)|029|n/a|none|
|Entity extractor (WhatsApp → candidates)|? (deferred)|v6.3.14|shipped|v6.3.14|ENTITY\_EXTRACTION\_TENANT\_IDS=CSV (default empty=OFF)|—|?/?|AC IDs (batched pass)|
|Candidate Promotion Job (employees + machines)|? (deferred)|v6.3.15|shipped|v6.3.15|ENTITY\_EXTRACTION\_TENANT\_IDS=CSV (reused; default empty=OFF)|—|?/?|customer promotion (no `customers` table yet); per-tenant settings UI (v6.3.19); 30-day fuzzy-threshold review on tenant 12; AC IDs (batched pass)|
|Owner-confirmed candidate promotion (revised)|? (deferred)|v6.3.15 revised|shipped|v6.3.15|ENTITY\_EXTRACTION\_TENANT\_IDS=CSV (reused)|030|?/?|customer promotion (no `customers` table); confirmation timeout / re-ask cadence tuning post-pilot; AC IDs (batched pass)|
|Day-7 First-Insight Gate|? (deferred)|v6.3.16|shipped|v6.3.16|(no flag — fires only when `tenants.first_briefing_sent_at` is set AND ledger key absent)|031|6/6 unit + 3/3 PG smoke|existing `detect_day_7` marker left in place (v6.4.0 owns retiring it); `zetaops_day7_routine_set` Meta template not yet submitted (Cloud API session messages used everywhere); AC IDs (batched pass)|
|WhatsApp owner-bypass entity writes|? (deferred)|v6.3.17|shipped|v6.3.17|(no flag — strict role gate inside `evaluate_and_write` defaults to deny)|032|all 40 unit + 4/4 PG smoke|customer-add (no `customers` table); DELETE / UPDATE / bulk-add intents; reply localisation (v6.3.18); AC IDs (batched pass)|
|WhatsApp message styling pass (Voice/Tone/Formatting standards)|23|v6.3.18|shipped|v6.3.18|(always on — code-only)|—|8/8|runtime wiring of Meta-bound `MORNING_BRIEFING_EN/HI` + `DELAY_ALERT_EN` + `CONFLICT_ALERT_EN` into v6.3.4 push-briefing dispatcher (deferred to v6.4 when data shape matches; v5.10 dispatcher is wired through `message_templates.py` dispatcher-shape templates this release); `AI_REPLY_HEADER` integration in `routers/ai_chat.py` (out of scope per v6.3.18 §6 — WhatsApp router AI path IS wired); `CONFLICT_ALERT_HI` Python binding (when Meta approves the hi entry)|
|Consolidated push cadence (morning + evening + delay + conflict)|6.28 v2|v6.3.19 → v6.3.19.1|shipped|v6.3.19.1|`DEBUG_DISPATCH_ENABLED=True` in dev/staging (debug endpoint gate). `PUSH_V2_ENABLED` flag removed in v6.3.19.1 cutover.|033 + 034|10/10 SRS §6.28.v2-AC1..AC10 (per `docs/srs_section_6_28_v2.md`)|Meta v2 conditional `{flag_section}`/`{next_step_section}` template re-submission (closes the §23 tone exception); dedicated `zetaops_job_delayed` Meta template — current dispatch_delay_alert reuses `zetaops_job_ending_soon` with best-effort field shape; per-recipient locale routing once `User.language_preference` lands; `briefing_*` → `push_*` namespace unification (slice 2A-rename, future); spam-fix dedup for delay/conflict ticks (currently mirrors legacy no-dedup behaviour); `scripts/push_v2_flip.py` deletion in a future cleanup release (currently retained with OBSOLETE header).|
|Detector test date-anchoring infrastructure fix|—|v6.3.19.1|shipped|v6.3.19.1 (slice 3A)|(test-only — no production behaviour change)|—|13/13 xfails removed|none — `freezegun==1.5.5` + autouse `freeze_clock_at_detector_today` fixture in `tests/services/conftest.py` pins `datetime.now()` to the detector tests' hardcoded TODAY. New 26-case verification harness in `tests/services/test_detector_date_anchoring.py` parametrises a 90-day span (Jan–Jul 2026) and asserts identical detector behaviour at every anchor. 1054 unit-tier passing (+39 from v6.3.19), 0 xfailed (was 13).|
|Material Estimator (WhatsApp surface)|6.25|v6.5 plan|not started|—|material\_estimator\_freemium=False|—|0/4|6.25-AC1, 6.25-AC2, 6.25-AC3, 6.25-AC4|
|Compliance Deadline Tracker|6.26|v6.6 plan|not started|—|compliance\_tracker=False|TBD|0/n|all (6.26-AC1..ACn)|
|GST E-Invoicing JSON|6.27|v6.7 plan|not started|—|einvoice\_generator=False|TBD|0/n|all (6.27-AC1..ACn)|
|RAG pgvector migration|21|v6.8 plan|not started|—|(always on)|planned|0/n|all|
|Supervisor Agent|17.4|v6.9 plan|not started|—|(always on)|—|0/n|all|

### V7 era (ERP-connected mid-market) — all not started

|Feature|SRS §|Spec'd in|Status|Shipped in|Flag|Migration|Acceptance|Deferred|
|-|-|-|-|-|-|-|-|-|
|ERP Connector layer (SAP/Tally/Xls)|21|v7.0 plan|not started|—|(per-tenant)|planned|0/n|all|
|Contractor Labour Layer|—|v7.1 plan|not started|—|planned|planned|0/n|all|

\---

## How to fill in the remaining gaps

Pass on 2026-05-02 closed several `?` rows from documentation alone (Events
audit table, UI Consolidation, KPI Baseline status). What remains is
genuinely test-and-tag work that needs the repo, not the docs.

**Open uncertainties:**

1. **The three v6.4 entry-gate rows** (Top-Tier Role Group, Entry Mode
Configuration, Daily Push Briefings) — SRS §1.2 lists v6.4 as "NEXT TO
BUILD" and not shipped, but the CHANGELOG narrates v6.3.x tags
(especially v6.3.4) as if entry-gate work is already landing. Either
the SRS §1.2 paragraph is stale or the CHANGELOG is speculating ahead
of reality. **Resolution:** read `git show v6.3.4` and run
`tests/test\_briefing\_dispatcher.py` (or whatever the dispatcher tests
are named); the truth is in the code, not either doc.
2. **AC pass counts** for KPI Baseline (8 ACs), each entry-gate feature
(13 ACs covering Section 6.28 collectively), and UI Consolidation
(12 ACs in §6.28.4). The AC totals are based on the SRS prose and
should be verified once the SRS annotation pass adds explicit AC IDs.
3. **The `srs-ac-annotation-pass` task is still open** — SRS Section 6
ACs are in prose, not yet prefixed with stable IDs. Until that pass
lands, "AC#?" in the Deferred column means "we haven't numbered them
yet," not "we don't know which are open."

**Recipe per remaining row** (the original five-step process, unchanged):

1. Find the tag where the feature first appeared in working form
(`git log --tags --simplify-by-decoration --pretty="format:%h %d %s"`).
2. Open the SRS section listed in column 2; count the acceptance
criteria. After the AC annotation pass, this is just `grep -c '^\[0-9]\\+\\.\[0-9]\\+-AC' SRS.docx`-equivalent.
3. Run the test file that exercises those criteria; count passing.
Test names mirror AC IDs: `test\_6\_28\_ac1\_\*`, `test\_6\_28\_4\_ac5\_\*`, etc.
4. Fill in `Shipped in`, `Acceptance N/M`, and any `Deferred` AC IDs.
5. Set Status: `partial` if N < M, `shipped` if N == M, `in progress`
if no tag yet, `blocked` if external dependency holds it back.

If SRS §1.2 ("Current State") and the CHANGELOG disagree about whether a
feature shipped, the test suite is the tiebreaker. Then update whichever
doc is wrong in the same commit that updates this ledger.

\---

## How this file relates to other artifacts

|Artifact|Question it answers|Source for "is it shipped?"|
|-|-|-|
|SRS|What should the product be?|No — describes target state|
|`DELIVERY\_LEDGER.md`|What is actually built right now?|**Yes — this file is truth**|
|`CHANGELOG.md`|What changed in version X?|No — narrates per release|
|Git tags|Which commits got released?|Yes — for the bare fact|
|Test suite|Do acceptance criteria pass right now?|Yes — for AC-level truth|

The four "yes" sources should never disagree. When they do, fix the ledger row
immediately and write a one-line note in CHANGELOG explaining the correction.

\---

## Acceptance criterion ID convention (mandatory)

Every numbered acceptance criterion in the SRS gets a stable ID of the form
`{section}-AC{n}`. This is the canonical reference used across the SRS, this
ledger, the test suite, and commit messages. Anything not following the
convention is wrong and must be corrected.

**Examples:**

* `6.24-AC1` — Section 6.24 (KPI Baseline) AC #1: "first 7 days produce baseline rows"
* `6.28-AC1` — Section 6.28 (Entry Gate) AC #1: "whatsapp\_first signup creates Tenant + User + PhoneTenantMap atomically"
* `6.28-AC10` — Section 6.28 AC #10: "migration runs cleanly on copy of production data"
* `6.28.4-AC5` — Section 6.28.4 (UI Consolidation) AC #5: "GET /api/team returns redesigned shape"

**Test naming mirrors the ID** (underscores replace dots and dashes):

```python
def test\_6\_28\_ac1\_whatsapp\_first\_creates\_three\_rows():
    """SRS 6.28-AC1: whatsapp\_first signup creates Tenant + User + PhoneTenantMap atomically."""
    ...

def test\_6\_28\_4\_ac5\_team\_endpoint\_no\_synthesised\_emails():
    """SRS 6.28.4-AC5: GET /api/team returns whatsapp\_status, no invite-XXX leakage."""
    ...
```

**Commit messages reference the ID** when closing or working on an AC:

```
feat: 6.28-AC7 briefing dispatcher fires on working days only
fix:  6.28-AC10 migration backfill idempotency on tenants table
test: 6.28.4-AC5 assert no synthesised email leaks in /api/team response
```

**Grepability is the point.** A search across SRS + ledger + tests for any
AC ID returns three hits: where it is specified, where its status is
tracked, where it is verified. Fewer than three hits means the chain is
broken — fix the missing artifact.

**SRS annotation pass required.** SRS Section 6 lists numbered ACs in prose
(e.g. Section 6.28 has 13 numbered items). The IDs are not yet written into
the SRS document itself. Before this convention has full effect, do a
one-time pass through Section 6 and prefix each AC with its ID:

```
Acceptance criteria.
6.28-AC1: whatsapp\_first signup creates Tenant + User + PhoneTenantMap...
6.28-AC2: desktop\_first signup creates Tenant and User but does not...
6.28-AC3: hybrid signup creates all three with the same industry attribution.
...
```

Mark this as `srs-ac-annotation-pass` in the next SRS update.

