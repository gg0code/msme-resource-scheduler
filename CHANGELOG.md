# Changelog

All notable changes to ZetaOps Copilot are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a custom version scheme described in SRS Section 1.1
(Product Version: vMAJOR.MINOR.PATCH where MAJOR is the product era — V5
WhatsApp-first, V6 AI-first, V7 ERP-connected).

This file narrates **what changed per release**. For "what is actually shipped
and working right now," see [`DELIVERY_LEDGER.md`](./DELIVERY_LEDGER.md). For
"what the product is supposed to be," see the SRS.

Hotfix sub-versions (e.g. v6.3.2.1 → v6.3.2.4) are kept granular here for
audit purposes; in the SRS they collapse into the parent version's entry.

---

> **Doc-trinity reconciliation pass — 2026-05-02.** A pass against SRS v6.5
> + DELIVERY_LEDGER closed several `?` rows in the ledger from
> documentation alone, but the v6.3.1, v6.3.2.x hotfix chain, v6.3.4, and
> v6.3.6 entries below are still stubs because they require `git show` /
> `git log` / `pytest` output that wasn't available in that pass. Each
> stub now lists the exact commands needed to close it. The v6.3.5 entry
> is fully documented from SRS §6.28.4. The v6.3.3 entry is documented
> from SRS §9.2 (migration 028) but may have additional non-migration
> commits not yet captured. SRS §1.2 ("Current State") and these stubs
> disagree about whether v6.4 has shipped — when reconciling, the test
> suite is the tiebreaker; update whichever doc is wrong in the same
> commit that closes the stub.

> **Dual-tag reconciliation — 2026-05-08.** `v5.10`/`v5.12` and `v6.0`/`v6.1`
> are dual-tagged single commits, not separate releases. CHANGELOG entries
> below combine each pair into one section with both tag names. Closes
> Findings #7 and #8 in `SRS_RECONCILIATION_FINDINGS.md`. Git tags
> unchanged; only documentation updated.

---

## [Unreleased]

### Added
- **v6.3.21 part 2 — Runtime lookup helper + Day-7 / give-up-nudge wiring.**
  Two pieces folded into the v6.3.21 scope:
  1. **Runtime lookup helper.** New module
     `backend/app/services/whatsapp_templates.py` ships `resolve_template`,
     `ResolvedTemplate`, `UnknownEventError`, `ArgCountMismatchError`,
     `known_events`, and the `EVENT_ROUTING` dict (single source of
     "internal event name" → "Meta template name"). The helper centralises
     what previously would have been ad-hoc plumbing in seven dispatcher
     files: language fallback (`hi` → `en_US` with logged warning),
     placeholder-count validation against the Meta `{{n}}` count, and a
     `ResolvedTemplate` dataclass carrying both the rendered Python
     string (mock-mode logs + audit trail) and the str-coerced
     `meta_params` list (production-mode Interakt POST). New test file
     `backend/tests/test_whatsapp_templates.py` adds a 25-event coverage
     invariant + 12 unit tests for happy paths, fallback, error paths,
     and str-coercion.
  2. **4 newly-submitted Meta templates wired** (`zetaops_owner_day7_insight`
     en_US + hi for v6.3.16 First-Insight Gate;
     `zetaops_engagement_give_up_nudge` en_US + hi for v6.4.0 engagement
     ladder fallback). 4 constants added to a new Section 5 in
     `message_formatters.py`; 4 rows added to `PYTHON_CONSTANT_BINDINGS`;
     4 entries appended to `whatsapp_meta_templates.json` with
     `"status": "pending_meta_approval"` until Meta review completes;
     2 rows added to `EVENT_ROUTING`. New utility script
     `backend/scripts/merge_approved_templates.py` clears
     `draft_pending_meta_submission` + `pending_meta_approval` status
     flags on any registry entry that carries them (idempotent, runs
     post-approval).

  Counts after this iteration: 40 `META_TEMPLATES` entries, 40 bound
  Python constants, 25 events in `EVENT_ROUTING`, AC 23-AC7 audit
  parametrises across 40 entries. Full unit-tier suite: **1181 passed,
  3 skipped, 0 failed** (+41 from the pre-v6.3.21-part-2 baseline of
  1140: 4 new AC 23-AC7 cases + 25 coverage invariant + 12 lookup-helper
  unit tests). No Meta API submissions in this iteration. No new feature
  flag. No dispatcher wiring of the new 4 (separate iteration when
  caller data shapes catch up). Migration head unchanged at 034.

- **v6.3.22a — Normalised the 4 v6.3.18 constants to positional placeholders.**
  `MORNING_BRIEFING_EN`, `MORNING_BRIEFING_HI`, `CONFLICT_ALERT_EN`,
  `DELAY_ALERT_EN` in `app/services/message_formatters.py` converted from
  named (`{date}`, `{job_a}`, ...) to positional (`{0}`, `{1}`, ...) so
  the entire file uses one consistent style across all 36 constants.
  Slot order matches the v6.3.18 named-kwarg order; inline comments at
  every callsite preserve the old key names for review readability.
  Reconciled one latent v6.3.18 drift surfaced in the review:
  `CONFLICT_ALERT_EN` now includes the Meta HEADER prefix (`Schedule
  conflict — action needed`) that the Python constant had silently
  dropped — mock-mode renders + audit logs now match what Meta actually
  sends. Updated 3 production callsites in
  `app/services/consolidated_briefing.py` (morning EN/HI shared call +
  delay-alert + conflict-alert dispatchers), 4 callsites in
  `scripts/preview_v6_3_18_templates.py`, and the test scaffolding in
  `tests/test_message_templates.py` (4 sample dicts → tuples; 7
  `format(**sample)` → `format(*sample)` rewrites; `_SNAP_CONFLICT_EN`
  snapshot updated to include the new HEADER prefix). Full unit-tier
  suite: 1140 passed, 0 failed, 0 regressions. Migration head unchanged
  at 034. Unblocks the v6.3.22 lookup helper's
  `template_string.format(*args)` rendering strategy.

- **v6.3.21 — Meta template constants wiring (full inventory).** 32 new
  template constants appended to `app/services/message_formatters.py` in
  a new Section 4 (onboarding & consent, evening briefing, manager
  check-in, operational alerts, order intake, compliance reminders,
  team invite, manager engagement ladder, performance & finance).
  `PYTHON_CONSTANT_BINDINGS` in `app/services/whatsapp_meta_templates.py`
  extended from 4 → 36 entries — full coverage of the Meta WhatsApp
  inventory in `whatsapp_meta_templates.json`. AC 23-AC7
  placeholder-parity audit now parametrises across all 36 entries (was
  4); 58/58 cases pass in `tests/test_message_templates.py`. New
  constants use positional `{0}, {1}, ...` slots (HEADER `{{1}}..{{H}}`
  → `{0}..{H-1}`; BODY `{{1}}..{{B}}` → `{H}..{H+B-1}`), distinct from
  the v6.3.18 named-kwarg style of the four already-wired constants
  (kept unchanged per spec). Hindi / Hinglish strings preserved
  byte-for-byte. No Meta API submissions, no dispatcher wiring, no new
  feature flag — code-side wiring only. Migration head unchanged at 034.

### Changed
-

### Fixed
-

### Migration
-

### Notes
-

---

## [v6.3.20] — 2026-05-13
**Branch:** v5-whatsapp
**Spec:** SRS Section 6.28 (Daily Push Briefings) — NL extension

WhatsApp natural-language pathway for top-tier owners to change
push-briefing settings without leaving the chat. Three new AI tools
(`update_push_setting` / `pause_push` / `get_push_settings`) backed
by a strict server-side whitelist + validators, wired through the
existing v5.6 confirmation flow. Schema columns added in v6.3.19
slice 2A (migration 033) finally drive end-to-end behaviour from
NL → write. Shipped across four commits on `v5-whatsapp` since the
v6.3.19.1 cutover: backend foundations (part 1, `6aea025`), manual
walkthrough runbook (`d45f9d3`), bridge plumbing (part 2, `93b900f`),
release-blocker bug fix for the briefing-classifier intercept
(`83d9d8c`).

### Added
- **v6.3.20 part 2 — bridge plumbing (actor_user_id + phone_number).**
  Plumbs the calling user's identity from
  `app/routers/whatsapp.py:_process_inbound_message` (which has it on
  `IdentityResult` from `resolve_identity`) through
  `whatsapp_bridge.AIChannelBridge.process_message` (Protocol +
  `GroqDirectBridge`) → `ai_service.run_ai_chat` →
  `execute_tool`. Optional kwargs default to None so the web-UI
  `ai_chat` caller continues working unchanged. With this commit
  the three v6.3.20 tools become callable end-to-end from WhatsApp:
  `update_push_setting` and `pause_push` stage the pending change in
  Redis under `whatsapp:pending_action:<phone>` and the existing
  v5.6 confirmation flow at `whatsapp.py:831` resolves HAAN/NAHI
  into the actual write. `get_push_settings` returns the per-user
  override section when called with the user's id.
- **`tests/test_v6_3_20_plumbing.py`** (new) — 7 cases covering both
  legs of the security boundary: (a) `run_ai_chat` carries
  `actor_user_id` + `phone_number` through to `execute_tool` when
  given; (b) the web-UI path defaults both to None; (c) the two
  v6.3.20 write tools refuse with `tool_requires_whatsapp_channel`
  when either kwarg is missing (incl. partial-kwarg variants); (d)
  `get_push_settings` works without either kwarg (read-only).
- **v6.3.20 part 1 — WhatsApp NL push-settings updater (backend foundations).**
  New service module `app/services/push_settings_service.py` ships the
  whitelist (`EDITABLE_FIELDS`, 9 scalar columns split tenant-scoped vs
  user-scoped), trilingual error templates (English / Hinglish / Hindi),
  four validators (`_validate_bool`, `_validate_time_hhmm`,
  `_validate_iana_timezone`, `_validate_weekday_csv`), and three
  service functions (`update_push_setting`, `pause_push`,
  `get_push_settings`). `morning_sections` / `evening_sections` are
  deliberately excluded from the whitelist (desktop-only) and produce
  a typed `field_not_editable_via_whatsapp` error redirecting the
  owner to the desktop UI. `pause_push` computes
  `today + (days - 1)` in the tenant's timezone with `[1, 30]` bounds
  and replaces (not adds to) any existing pause. Every successful
  write inserts one `events` row with
  `event_type='tenant.push_setting_changed'`, `source='whatsapp'`,
  `actor_user_id`, and a payload carrying `field` / `old_value` /
  `new_value` / `source_phrase`.
- **Confirmation flow extension via existing v5.6 machinery.**
  `whatsapp_actions.ActionType` gains `UPDATE_PUSH_SETTING` and
  `PAUSE_PUSH`. New sync `store_pending_action_sync` helper (mirrors
  the async `store_pending_action` but uses a sync Redis client +
  `_mock_sessions` fallback so `ai_service.execute_tool` — which is
  sync — can stage pending state). New sync executors
  `_execute_update_push_setting` and `_execute_pause_push` delegate
  to `push_settings_service` after the user confirms with HAAN/YES.
  `build_confirmation_prompt` extended to render the proposed
  setting change or pause range; the pause confirmation MUST restate
  the date range so day-counting mistakes surface before commit.
  `whatsapp_session.py` gains a sync `sync_redis_client` companion
  to `redis_client`.
- **Three Groq AI tools registered in `ai_service.TOOLS` (v6.3.20):**
  `update_push_setting` (field enum excludes
  morning_sections/evening_sections), `pause_push` (days 1-30),
  `get_push_settings` (read-only). `execute_tool` gains optional
  `actor_user_id` / `phone_number` kwargs. The two write tools
  refuse with `tool_requires_whatsapp_channel` when either is
  missing — they are WhatsApp-only by design and the bridge
  plumbing that fills these in lives in part 2 (see Notes).
  Writes return a `confirmation_required` envelope that stages the
  change in Redis and instructs the LLM to surface the
  confirmation prompt verbatim instead of calling another tool.
- **System prompt addendum (in `_SYSTEM_PROMPT_BASE`).** Adds the
  v6.3.20 routing table (Hinglish + English examples for time
  changes, enable/disable, working days, timezone, pause), the
  desktop-only redirect rule for `morning_sections`/`evening_sections`,
  the confirmation-flow rule (do NOT call any tool until user replies
  with confirmation word), and the top-tier permission rule.
- **Test coverage in `tests/services/test_push_settings_service.py`**:
  26 cases covering happy paths (morning_time, weekday_csv normalised,
  owner-edits-other-user-override), rejections (unknown_field,
  morning_sections, evening_sections, invalid_time_format ×7
  variants, non-top-tier, co-owner cannot edit other override,
  proprietor-as-owner-synonym), pause arithmetic (today + (days - 1)
  on Mon 2026-05-04 anchor, days=1 = today only, replaces existing),
  range bounds (zero/negative/>30/bool-not-int), get_push_settings
  (sections returned readable, no audit row, is_currently_paused
  inclusive boundary), tenant isolation (cross-tenant actor lookup
  returns `actor_not_found`), validator unit coverage (Hindi
  bool synonyms, IANA tz reject), and full executor integration
  (`_execute_update_push_setting` / `_execute_pause_push` happy paths
  + rollback on validation error).

### Changed
- **`app/services/whatsapp_session.py`** now imports `redis` (sync) in
  addition to `redis.asyncio` and exposes both `redis_client`
  (existing async) and `sync_redis_client` (new). Production behaviour
  unchanged — both clients use the same `UPSTASH_REDIS_URL`.

### Fixed
- **v6.3.20 release-blocker — briefing-request classifier intercepted
  settings-change phrases.** `whatsapp_intent.detect_briefing_request_intent`
  was a pure substring match on `BRIEFING_MORNING_KEYWORDS` /
  `BRIEFING_EVENING_KEYWORDS`. Phrases like `"morning briefing 8 baje karo"`
  matched `"morning briefing"`, were routed to `manual_trigger_briefing`,
  and `update_push_setting` was never offered to the LLM. The user saw
  `"Aaj koi tickets schedule mein nahi hai"` instead of a confirmation
  prompt. New module-level `_SETTINGS_TIME_CUE_RE` regex (HH:MM /
  N am-pm / `baje` / `ke jagah` / `instead of`) and
  `_SETTINGS_STRONG_VERBS` frozenset (on/off:
  band/bandh/chalu/off/on/disable/enable/stop/start; pause:
  pause/chuti/chutti/holiday/roko/rok/break; change:
  change/shift/set/modify/update/move/reschedule). When either signal
  co-occurs with a briefing keyword the classifier returns None and the
  message falls through to the AI. Bias is toward suppressing on
  ambiguity: a false positive costs one slower AI hop, a false negative
  is the original bug. Logs `Briefing keyword present but
  settings-change signal co-occurs — falling through to AI` so the
  routing decision is debuggable. Tests in
  `tests/test_briefings.py::TestBriefingIntent`: 13 negative cases
  (must fall through) + 11 positive cases (display intents must still
  dispatch, including benign verbs `share`/`kar`/`do`/`dikhao` that
  are deliberately excluded from the strong-verb set). Test counts:
  **1108 unit-tier passing** (+23 from part 2's 1085: 13 negative + 10
  positive new cases).

### Migration
- None. Reuses columns added in migration 033 (v6.3.19 slice 2A —
  `tenants.morning_sections` / `evening_sections` / `push_paused_until`).
  Migration head stays 034.

### Notes
- **All four v6.3.20 commits are tagged in this single release.**
  Part 1 (backend foundations, `6aea025`) shipped the service module
  + tools as a self-contained slice with the bridge plumbing
  intentionally deferred. Part 2 (`93b900f`) wired the optional
  `actor_user_id` + `phone_number` kwargs all the way from the
  WhatsApp router through the bridge → `run_ai_chat` → `execute_tool`,
  closing the security boundary so the v6.3.20 write tools stay
  WhatsApp-channel-only (they refuse with
  `tool_requires_whatsapp_channel` from the web-UI `ai_chat`
  caller). Manual walkthrough doc (`d45f9d3`) covers nine acceptance
  scenarios; live walkthrough on `WHATSAPP_MOCK_MODE=True` against
  the test tenant signed off all nine before this tag. Bug fix
  (`83d9d8c`) closed the briefing-classifier intercept that was
  silently swallowing `"morning briefing 8 baje karo"` and routing
  it to the v6.3.4 dispatcher instead of the new
  `update_push_setting` tool.
- **Steps 1 and 7 from the v6.3.20 prompt were already shipped in
  v6.3.19** (schema_context.py documents the three v6.3.19 columns
  at lines 107-116; `consolidated_briefing._dispatch_one:846-864`
  has the inclusive-boundary pause check emitting
  `push.{kind}_skipped_paused`). The v6.3.20 prompt's pre-flight
  reconciliation commit was likewise pre-empted by the v6.3.19.1
  doc-trinity sync that landed under the amended v6.3.19.1 tag.
- **Test count at tag:** 1108 unit-tier passing (+56 from v6.3.19.1's
  1052 baseline: 26 service-module + 7 plumbing + 23 disambiguation).
  Migration head unchanged at 034 (no schema this release).
- **Deferred to v6.4.0 / future:** any system-prompt tightening for
  the soft-fail path on step 6's `"8pm karo"` variant (LLM should
  normalise "8pm" → "20:00"; if it passes raw, the validator catches
  it but the user gets a re-ask instead of a confirmation prompt).
  Not a blocker — the validator is the safety net.

---

## [v6.3.19.1] — 2026-05-11
**Branch:** v5-whatsapp

Cutover release. The shadow-mode pattern v6.3.19 introduced (`PUSH_V2_ENABLED` flag, `push.shadow_log` events, 5-box verification gate) was abandoned: the safety benefit was theoretical (v5.11 production cutover blocked on Meta review; no real customer traffic) and the cognitive cost was real every session. v6.3.19.1 removes the flag entirely, deletes the legacy v5.10-era push functions, and ships the remaining v6.3.19.1-scope work (slice 3A detector-test anchoring fix + slice 3B delay/conflict dispatchers) as the new push system becomes the sole code path.

**Slices landed:** 3A (freezegun + xfail strip + 90-day anchor-invariance harness) and 3B (dispatch_delay_alert + dispatch_conflict_alert + legacy push-function deletion + flag removal).

### Added (slice 3A — detector test date-anchoring fix)
- **`freezegun==1.5.5`** added to `backend/requirements.txt`. Used by the new autouse fixture in `tests/services/conftest.py` to pin `datetime.now()` to `date(2026, 5, 4)` — the same value every `tests/services/test_detect_*.py` file hardcodes as `TODAY`. This aligns fixture-builder timestamps with the detector's `today` argument. **Production behaviour unaffected** — real attendance.recorded events carry true `now()` `created_at` and dispatchers pass live tenant-local today, so the two anchors stay in sync at runtime regardless of this test-side autouse.
- **`tests/services/conftest.py` `freeze_clock_at_detector_today` autouse fixture.**
- **`tests/services/test_detector_date_anchoring.py`** (new) — 26-case parametrised verification harness. Runs `detect_delayed_jobs` at 13 frozen-`now()` anchors spanning Jan–Jul 2026 for both the positive and negative cases. Anchor-invariance proven.

### Added (slice 3B — delay + conflict dispatchers)
- **`consolidated_briefing.dispatch_delay_alert(tenant_id, now, db, *, job_id) -> DispatchResult`** — async, per-job. Renders the Meta-bound `DELAY_ALERT_EN` template (`zetaops_job_ending_soon` shape) with five fields computed from the Job (`job_name`, `customer`, `time_remaining`, `progress`, `next_job`). No dedup — consecutive ticks for the same job both fire `push.delay_sent`, mirroring legacy `check_delayed_jobs` behaviour. Spam-fix tracked as a future release.
- **`consolidated_briefing.dispatch_conflict_alert(tenant_id, now, db, *, conflict_payload) -> DispatchResult`** — async, per-conflict. Renders Meta-bound `CONFLICT_ALERT_EN` (`zetaops_job_conflict_alert`) with `job_a`/`job_b`/`resource`/`window`/`next_step`. Caller-computed payload; `_compute_conflict_alert_fields` is passthrough + decoration.
- **`consolidated_briefing._compute_delay_alert_fields(job, now, db)` + `_compute_conflict_alert_fields(payload)`** — best-effort field computation. `time_remaining` renders as `"overdue by N days"` for delays (template's "ending soon" shape adapted); `resource` and `next_step` for conflicts are placeholders pending v6.4 scheduler-conflict rewrite that exposes contended resources.
- **`consolidated_briefing._get_delayed_jobs_for_dispatch` + `_get_conflicts_for_dispatch`** — sync helpers mirroring legacy `_get_delayed_jobs` / `_get_conflicts` semantics (which were deleted in this release) but taking an external `db` session. Conflict pairing collapses single-job allocation-gap conflicts into paired `(job_a, job_b)` slots; lone conflicts render `job_b='—'`.
- **`consolidated_briefing._is_delay_tick` / `_is_conflict_tick`** — IST minute-mark detectors. Delay: 8/10/12/14/16/18/20 :00 IST (7 ticks daily). Conflict: 8:30 / 12:30 / 16:30 / 20:30 IST (4 ticks daily). Mirrors legacy `check_delayed_jobs` + `check_scheduling_conflicts` cadence.
- **`push_v2_tick` extended** to fire delay + conflict dispatches at the IST tick marks (in addition to morning/evening per-tenant time match). One dispatch task per delayed-job per tick; one per conflict per tick.
- **`consolidated_briefing._tenants_for_alert_pref(alert_pref_key, db)`** — returns distinct tenant_ids with at least one active top-tier phone opted in to a given alert preference key. Used by `push_v2_tick` to scope the delay/conflict tick to opted-in tenants only.
- **New alert-preference keys:** `push_delay`, `push_conflict` (default-True for missing-key tenants, same convention as `push_morning` / `push_evening`).
- **New event vocabulary:** `push.delay_sent` / `push.delay_skipped_paused` / `push.delay_skipped_no_recipients` / `push.delay_send_failed`. Mirror set for `push.conflict_*`.
- **`whatsapp_debug.py` extended** — POST `/api/v1/whatsapp/debug/dispatch` now accepts `type='delay_alert'` (requires `job_id`) and `type='conflict_alert'` (requires `conflict_payload`). Returns 400 with explanatory message when the required extra field is absent.
- **Slice 3B tests** (in `tests/integration/test_2d_dispatcher.py`): 12 dispatcher cases (6 delay + 6 conflict — happy / tenant-filter / no-recipients / paused / Meta-failure / template-render), 2 tick-window cases (8:00 fires delay / 8:30 conflict; off-window does not), cadence iteration (full 7-tick delay schedule produces 7 events), parity-with-legacy no-dedup assertion (consecutive ticks both emit `push.delay_sent`), 2 debug-endpoint routing cases. 31 integration tests total, all green.

### Removed
- **`PUSH_V2_ENABLED` config setting** in `app/config.py` — gone. The new push system is now the sole code path.
- **`app/services/whatsapp_alerts.run_briefing_dispatch_tick`** — the v6.3.4 5-minute briefing dispatcher. Replaced by `consolidated_briefing.push_v2_tick`.
- **`app/services/whatsapp_alerts.check_delayed_jobs`** + **`check_scheduling_conflicts`** — the v5.10 every-2-hour / every-4-hour ticks. Replaced by `dispatch_delay_alert` + `dispatch_conflict_alert` running at the legacy IST tick marks.
- **Legacy helper functions** `_get_delayed_jobs`, `_get_conflicts`, `_build_delay_alert`, `_build_conflict_alert` (in `whatsapp_alerts.py`) — orphaned by the function deletions above; ~232 lines stripped.
- **Legacy scheduler registrations** for `briefing_dispatch_job`, `job_delay_check`, and `conflict_check`. `set_dev_schedule` updated accordingly.
- **Legacy constants** `JOB_DELAY_CHECK_HOURS`, `JOB_DELAY_CHECK_EVERY`, `CONFLICT_CHECK_EVERY`, `ALERT_TYPE_JOB_DELAY`, `ALERT_TYPE_CONFLICT`, `BRIEFING_DISPATCH_INTERVAL_MINUTES` — consumed only by the deleted functions.
- **Shadow-mode infrastructure** — `shadow=True` kwarg on `dispatch_morning` / `dispatch_evening` / `_dispatch_one`, the `push.shadow_log` event_type, the consolidated-emit logic that funneled all stages under one event. Replaced by direct per-stage event writes.
- **`tests/integration/test_push_v2_flip.py`** — tests for the obsolete CLI deleted. The script `scripts/push_v2_flip.py` itself is retained with an "OBSOLETE as of v6.3.19.1" header so v6.3.19-era operator runbooks don't 404, but the tests for it are dead-code coverage.
- **Two retired tests in `tests/integration/test_2d_dispatcher.py`**: `test_old_tick_short_circuits_when_flag_enabled` (validated the early-return on the deleted legacy tick) and `test_new_tick_shadow_logs_when_flag_disabled` (validated shadow-mode log writes). Replaced with `test_push_v2_tick_sends_for_morning_match` in `tests/services/test_consolidated_briefing.py`.

### Changed
- **`tests/integration/test_2d_dispatcher.py::test_debug_endpoint_shadow_mode_returns_payload`** renamed to `test_debug_endpoint_returns_payload`. Assertions updated to reflect the cutover: dispatcher always sends; `actually_sent: True`; mock_meta receives one call.
- **`DispatchResponse.shadow_log_event_id`** field name retained in the response schema for v6.3.19 backward compatibility, but now carries the `push.{kind}_sent` (or skip) row id, not a `push.shadow_log` id. Documented in the field's docstring.
- **`force_send`** in the debug-endpoint request body retained as a no-op for backward compatibility with v6.3.19 operator scripts. The dispatcher always sends post-cutover.
- **CLAUDE.md current-state paragraph** rewritten through v6.3.19.1.

### Migration
- (none — code-only release)

### Notes
- **`docs/v6_3_19_smoke_tests.md`** marked OBSOLETE at the top with a note explaining the cutover. 5-box gate retired.
- **`docs/srs_section_6_28_v2.md`** marked with a v6.3.19.1 update banner. Sections 6.28.v2.6 (Shadow mode) and 6.28.v2.7.2 (Flip CLI) retained for historical reference.
- **`scripts/push_v2_flip.py`** retained with OBSOLETE header. CLI writes to `.env` produce an unused environment variable post-v6.3.19.1; the script is preserved so v6.3.19-era operator runbooks don't 404. Future cleanup release can delete.
- **No-dedup parity choice** — `dispatch_delay_alert` and `dispatch_conflict_alert` mirror legacy `check_delayed_jobs` / `check_scheduling_conflicts` exactly: consecutive ticks for the same job/conflict both fire. Per slice 3B test `test_push_v2_tick_consecutive_ticks_no_dedup` this is explicit and intentional. Spam fix is tracked as a future release with its own version number (no v6.3.19.2 dedicated to this — the future release will roll up spam dedup + any other small follow-ups).
- **Field shape divergence** — `DELAY_ALERT_EN` (`zetaops_job_ending_soon`) is a "job ending soon" Meta template; v6.3.19.1 wires it for "delayed" semantics with best-effort field computation (`time_remaining = "overdue by N days"`). The Meta template was approved for the "ending soon" use case; reusing it for "delayed" is honest about the field-shape mismatch in the dispatcher docstring. A dedicated `zetaops_job_delayed` Meta template is on the v6.4 backlog.

---

## [v6.3.19] — 2026-05-10
**Branch:** v5-whatsapp

Consolidated push dispatcher in shadow mode. v6.3.19 retires the v5.10 era of four hardcoded WhatsApp ticks (5-min briefing dispatcher + 8:00 delayed-jobs check + 8:30 conflict check + 7:03 AI-down ping) in favour of two **per-tenant-configurable** ticks — one morning, one evening — sharing one async dispatcher (`app/services/consolidated_briefing.py`) that wires through the v6.3.18 Meta-bound templates and the v6.3.11 pattern-aware briefing intelligence. New infrastructure ships behind `settings.PUSH_V2_ENABLED` defaulting **False**: the new tick runs every minute computing due tenants, rendering messages, but does NOT send — every dispatch logs a single `push.shadow_log` event capturing what would have been sent. The legacy 5-minute briefing tick continues to send authoritatively in this mode. Cutover to real-send is deferred to v6.3.19.1 once the 5-box gate criteria in `docs/v6_3_19_smoke_tests.md` are all green; ops flips via `python scripts/push_v2_flip.py --enable`.

**Per slice 2D scope reduction (D4),** v6.3.19 ships morning + evening only. The legacy 8:00 delay tick and 8:30 conflict tick remain authoritative regardless of `PUSH_V2_ENABLED` until v6.3.19.1 ships `dispatch_delay_alert` / `dispatch_conflict_alert`.

**Slices landed in this release:** 1 (selector + lookup), 2A pt1 (migration 033 + Tenant ORM + schema_context), 2A pt2 (push_config + yaml), 2B (field computation helpers), 2C (async dispatch_morning + dispatch_evening + migration 034 events dedup index), 2D-shadow (push_v2_tick + flag + debug endpoint), 2D-tests (15-case failure-mode matrix), 2D-flip (admin CLI), 2E (release wrap).

**SRS supplement:** new `docs/srs_section_6_28_v2.md` Markdown supplement specifies the consolidated cadence, hash stagger, shadow-mode pattern, and hybrid flag rendering. Canonical `docs/ZetaOps_SRS_v6_6.docx` requires manual paste — same pattern v6.3.18 used for `docs/srs_section_23_voice_tone.md`. Document version pointer advances v6.7 → v6.8 on first paste. AC IDs `6.28.v2-AC1` through `6.28.v2-AC10`.

### Added (slice 1 — flag/next_step selector)
- **`backend/app/services/consolidated_briefing.py`** (new, lookup-table-only slice of v6.3.19) — `select_flag_and_next_step(signals, locale) -> tuple[str | None, str | None]`. Pure function picks the top blocker-class signal from a pre-sorted `SignalResult` list and returns the (flag_text, next_step_text) pair the v6.3.18 Meta-bound `MORNING_BRIEFING_EN/HI` templates expect. Carries `_BLOCKER_CLASS_SIGNALS` (frozenset of 8 ids: `delayed_jobs_count`, `no_progress`, `idle_machine`, `low_utilization`, `status_change_alert`, `consecutive_absence`, `attendance_ratio_concern`, `new_employee_no_show`) and `_NEXT_STEP_TEMPLATES` (16 strings, 2 locales × 8 ids). Module-level assertion fails loud at import if the two diverge.
- **`backend/tests/services/test_consolidated_briefing.py`** — 7 tests (11 cases incl. parametrised invalid-locale cases) covering blocker selection, informational-signal skip, empty-list handling, iteration-order preservation, hi_en/en locale routing, ValueError on bad locale, and the module-level assertion's catch-condition.
- **Migration 033 (v6.3.19 slice 2A)** — three nullable columns on `tenants`: `morning_sections JSONB`, `evening_sections JSONB`, `push_paused_until DATE`. All NULL by default; `resolve_push_config()` (slice 2A part 2) interprets NULL as "use system default from `backend/config/push_defaults.yaml`". No backfill, no server_default. Reversible.
- **`app/models/auth.py` Tenant** — three column attrs added to mirror migration 033, with comment explaining the briefing_* / push_* naming bridge.
- **`app/knowledge_graph/schema_context.py`** — three new column entries in the tenants block; "Current migration head" comment advanced from 027 to 033 with explicit acknowledgement that 028–032 column additions remain undocumented in the AI-facing schema (see "schema_context backfill" note below).
- **`backend/app/services/push_config.py`** (new, slice 2A part 2) — `resolve_push_config(tenant: Tenant) -> PushConfig`. Pure function over a Tenant ORM row (no DB queries). Two-layer cascade: tenant column override → `backend/config/push_defaults.yaml`. Bridges briefing_* columns from migration 027 (`briefing_morning_time`, `briefing_evening_time`, `briefing_timezone`, `briefing_morning_enabled`, `briefing_evening_enabled`) into PushConfig field names that match the v6.3.19 brief (`morning_push_time`, `evening_push_time`, `push_timezone`, `morning_enabled`, `evening_enabled`). Migration 033 columns (`morning_sections`, `evening_sections`, `push_paused_until`) flow through with active YAML fallback for the two sections fields. `morning_enabled`/`evening_enabled` are split per direction (independent), not AND-ed — dispatcher decides which to honour per tick.
- **`backend/app/services/push_config.PushConfig`** — frozen dataclass. Sections fields are tuples (immutable, hashable). Dispatcher cannot mutate a resolved config between morning and evening ticks.
- **`backend/config/push_defaults.yaml`** (new) — flat system fallback. No industry keying, no tenant scoping. Documents that morning_push_time / evening_push_time / push_timezone / morning_enabled / evening_enabled are inert today (briefing_* columns are NOT NULL with their own defaults from migration 027) and operative only for morning_sections / evening_sections via migration 033.
- **`backend/tests/services/test_push_config.py`** — 10 tests covering YAML fallback path, tenant override path, sections tuple shape, push_paused_until pass-through, split per-direction enabled flags, frozen-dataclass guarantee, defensive YAML fallback for nulled briefing_* (manual DB edit / future schema change scenario), and the no-DB-queries contract. All 10 green; xfail count unchanged.
- **`backend/app/services/consolidated_briefing.py`** (extended, slice 2B) — three pure-SQL field computation helpers: `_compute_jobs_starting(tenant_id, today, db) -> int` (count of jobs whose `start_date == today` minus terminal statuses), `_compute_continuing(tenant_id, today, db) -> str` (in-progress jobs spanning today, ordered `is_locked DESC, start_date ASC, id ASC` — locked jobs are explicit owner commitments and lead the line so the briefing matches the owner's mental model), and `_compute_crew_expected(tenant_id, today, db) -> str` (`"{expected} of {roster} permanent"` with optional contractor gap-disclosure when contractor_count >= roster). All three filter by `tenant_id` per CLAUDE.md rule 1; all three are pure reads (no writes, no clock reads, no scheduling concerns) — caller passes the tenant-local `today` date.
- **`backend/tests/services/test_consolidated_briefing.py`** (extended) — 18 new tests across the three field helpers: jobs-starting count + terminal-status exclusion + per-tenant filter + empty-tenant; continuing format branches (0 / 1 / 2-3 / 4+) + locked-leads-unlocked ordering + case-insensitive status; crew-expected math + on-leave subtraction + inactive exclusion + contractor-minority silent + contractor-majority gap-disclosure + threshold-equality + zero-roster + per-tenant filter. Total file: 29 cases (11 from slice 1 + 18 new). All green; xfail unchanged.

### Notes (slice 2B scope decisions)
- **Contractor scoping in `_compute_crew_expected`.** Contractors (`worker_type='contractor'`) are deliberately excluded from both numerator (expected) and denominator (roster) of the crew-expected calculation. Reason: per-day contractor check-in does not exist as a feature today (no confirmed-presence table), so the briefing cannot honestly count contractors as either expected or absent. Counting them as expected would inflate the number; counting them as absent would inflate the gap. Excluding them keeps the math honest. **Gap-disclosure rule:** when `contractor_count >= roster` AND `contractor_count > 0`, the output appends `" ({N} contractors not yet tracked)"` so contractor-majority tenants (common in fabrication and manufacturing) see the staffing-gap explicitly rather than reading "2 of 2 permanent" and feeling reassured. The future feature that closes the gap is per-day contractor check-in (no design yet — this CHANGELOG note is the placeholder until that work is scoped).
- **`_compute_continuing` ordering: `is_locked DESC, start_date ASC, id ASC`.** Overrides the v6.3.19 brief's `priority DESC` because `Job.priority` is a free-text string (`"High"`/`"Medium"`/`"Low"`/etc.) and not all rows carry a sortable value. Locked jobs represent explicit owner commitments — they lead the line so the briefing matches the owner's mental model of what matters most. `start_date ASC` then surfaces older work first (more time-pressured); `id ASC` is the stable tiebreak.

### Added (slice 2E — release wrap)
- **`docs/srs_section_6_28_v2.md`** (new) — Markdown supplement specifying the consolidated push cadence, per-tenant push config, hash stagger, idempotency, recipient resolution, hybrid flag rendering, shadow-mode pattern, operator surface (debug endpoint + flip CLI), and acceptance criteria `6.28.v2-AC1` through `6.28.v2-AC10`. Cross-references SRS §23 (Voice/Tone/Formatting from v6.3.18). The canonical `docs/ZetaOps_SRS_v6_6.docx` (and successors) require manual paste from this supplement on the next refresh — same pattern v6.3.18 used for `docs/srs_section_23_voice_tone.md`.
- **`CLAUDE.md` current-state paragraph** rewritten to reflect v6.3.19 shadow-mode shipping. Migration head pointer advanced 032 → 034 (architecture rule 3). Test-suite baseline note bumped from "332 passing at v6.3.0-whatsapp-industry" to current "1015 unit + 22 integration + 13 xfailed". Product version pointer advanced "v6.3.17 shipped, v6.4 next" → "v6.3.19 shipped (shadow mode), v6.3.19.1 next".
- **`DELIVERY_LEDGER.md` row** for "Consolidated push cadence (morning + evening)" — status flipped from `in progress` to `shipped (shadow mode)` with explicit deferred-to-v6.3.19.1 list (cutover flip; delay/conflict dispatchers; detector test anchoring fix; Meta v2 conditional template re-submission; legacy 5-min tick code removal in v6.3.20; per-recipient locale; `briefing_*` → `push_*` namespace unification). Acceptance count `10/10` against the SRS supplement's AC1..AC10. Migration column `033 + 034`.
- **CHANGELOG `[Unreleased]` → `[v6.3.19]`** moved with release-header narrative. Empty `[Unreleased]` block reset above for the next release window.

### Added (slice 2D-flip — admin CLI for the cutover gate)
- **`backend/scripts/push_v2_flip.py`** (new) — admin CLI to flip the `PUSH_V2_ENABLED` gate. Three subcommands: `--enable` writes `PUSH_V2_ENABLED=true` to `backend/.env` (creating the file or replacing the existing line in place; never duplicating); `--disable` writes false; `--status` reports the current value plus a count of `push.shadow_log` events in the last 24h. Atomic write via `tempfile.mkstemp` + `os.replace` (crash-consistent on POSIX and Windows). `--env-file` argument lets ops point at a non-default path (used by the integration tests). The script does NOT itself flip production — it is invoked manually by ops AFTER the shadow-log verification gate criteria in `docs/v6_3_19_smoke_tests.md` are all green. **Concurrent-run safety:** atomic write prevents half-written .env, but two simultaneous flips race on last-writer-wins. Documented in the module docstring.
- **`backend/tests/integration/test_push_v2_flip.py`** (new) — 7 integration tests against a per-test temp `.env`: enable on empty file, disable, replace-existing-line (no duplicate), --status round-trip, --status on missing file (implicit-false note), library-level `set_flag` returns literal, atomic write leaves no temp files behind. All 7 green.

### Added (slice 2D-tests — failure-mode coverage matrix)
- **`backend/tests/integration/test_2d_dispatcher.py`** (new) — 15-case failure-mode coverage matrix for `push_v2_tick` + `dispatch_morning` + `dispatch_evening` + the debug endpoint. Marked `@pytest.mark.integration` (excluded from unit-tier gate; runs explicitly via `pytest tests/integration/test_2d_dispatcher.py -v`). Mocks Meta throughout via a local `mock_meta_sender` fixture; no real Meta calls. Self-contained — does not import from `tests/services/conftest.py` since the integration directory is a sibling. Test list (FM = failure mode):
  - `test_recipient_resolution_basic` (FM2 — wrong recipients)
  - `test_recipient_skips_paused_tenant` (FM2)
  - `test_recipient_skips_disabled_direction` (FM2)
  - `test_now_kwarg_discipline` (FM8 — clock drift; uses `unittest.mock.patch` to freeze `datetime.now()` and verify the dispatcher uses the passed `now`)
  - `test_idempotent_repeated_call` (FM4 — duplicate sends; locks the slice 2C events-table dedup contract)
  - `test_old_tick_short_circuits_when_flag_enabled` (FM5 — both systems sending; spies on `dispatch_due_briefings` to verify it is NOT called when `PUSH_V2_ENABLED=True`)
  - `test_new_tick_shadow_logs_when_flag_disabled` (FM5)
  - `test_meta_api_exception_logged_does_not_crash` (FM6 — silent crash)
  - `test_one_tenant_failure_does_not_block_others` (FM6 — cascade crash; one tenant raises, the other completes)
  - `test_hash_stagger_spreads_sends` (FM7 — thundering herd; 100 tenants × mod-60 buckets, asserts ≤3 per second and ≥40 of 60 buckets used)
  - `test_locale_resolution_per_recipient` (FM9; locks the slice 2C A1 default-`hi_en` contract — when `User.language_preference` lands, this test must be REPLACED, not deleted)
  - `test_24_hour_simulation_old_vs_new_parity` (the cutover-safety invariant; simplified scope — verifies cadence + recipient-set parity by construction since both old and new ticks resolve recipients via PhoneTenantMap with default-True alert prefs)
  - `test_debug_endpoint_shadow_mode_returns_payload` (curl-equivalent; FM3-adjacent)
  - `test_debug_endpoint_force_send_actually_sends`
  - `test_debug_endpoint_requires_top_tier_auth`
- **`docs/v6_3_19_smoke_tests.md`** (new) — operator manual checklist for shadow-mode verification: 6 numbered curl + log-tail steps for the morning shadow dispatch, shadow-log inspection, force-send, idempotency dedup, legacy-tick gating, and new-tick verification. Includes the v6.3.19.1 cutover gate criteria (5 boxes) that must all be checked before flipping `PUSH_V2_ENABLED=true` in production.

### Added (slice 2D-shadow — push_v2_tick + flag + debug endpoint)
- **`backend/app/services/consolidated_briefing.push_v2_tick`** — async APScheduler entry point. Cron-triggered every minute on the 0-second mark (cron not interval to avoid drift over long uptimes). Iterates tenants whose configured `briefing_morning_time` / `briefing_evening_time` matches `now` in their timezone, applies `tenant_id % 60` hash stagger via `asyncio.sleep`, and calls `dispatch_morning` / `dispatch_evening` per tenant. Exceptions per tenant are caught and logged as `push.tick_failed` events so one bad tenant cannot abort the tick. `apply_stagger=False` kwarg lets tests bypass the up-to-59-second wait.
- **`shadow=True` kwarg on `dispatch_morning` / `dispatch_evening`** — when set, the dispatcher renders the message and resolves recipients but does NOT call `_send_whatsapp_message`. All log writes consolidate under a single `push.shadow_log` event_type with `payload.kind`, `payload.stage` ('skipped_disabled' / 'skipped_paused' / 'skipped_no_recipients' / 'sent' / 'send_failed'), and `would_send=False`. Idempotency dedup is skipped in shadow mode so every tick logs for verification.
- **`backend/app/config.PUSH_V2_ENABLED: bool = False`** — cutover gate. While False (the v6.3.19 ship default), `push_v2_tick` runs in shadow mode and the legacy `whatsapp_alerts.run_briefing_dispatch_tick` continues to send authoritatively. When flipped to True (v6.3.19.1+), `push_v2_tick` becomes authoritative and `run_briefing_dispatch_tick` early-returns. Ops sets via env `PUSH_V2_ENABLED=true` after shadow-log verification.
- **`backend/app/config.DEBUG_DISPATCH_ENABLED: bool = True`** — gates `POST /api/v1/whatsapp/debug/dispatch`. Defaults True for dev / staging convenience; production deployments must set False in `.env`.
- **`backend/app/routers/whatsapp_debug.py`** (new) — `POST /api/v1/whatsapp/debug/dispatch` operator endpoint. Accepts `{type, tenant_id, now, force_send}`; runs the dispatcher in shadow mode (default) or real-send mode (`force_send=true`). Returns `{actually_sent, skip_reason, would_send_to, rendered_message, sent_count, success, shadow_log_event_id}`. Top-tier auth + `DEBUG_DISPATCH_ENABLED` gate enforced inside the route. `type` of `'delay_alert'` / `'conflict_alert'` returns 400 — those dispatchers are scoped to v6.3.19.1 and not yet implemented (D4 scope reduction).
- **`backend/app/services/whatsapp_alerts.run_push_v2_tick`** — APScheduler-side wrapper that opens a sync session, calls `consolidated_briefing.push_v2_tick`, and logs the result counts. Registered as cron job `push_v2_tick_job` (every minute on second=0) in `start_scheduler()`.
- **`run_briefing_dispatch_tick` early-return gate** — when `settings.PUSH_V2_ENABLED=True`, the legacy 5-min briefing tick logs "skipped — PUSH_V2_ENABLED=true" and returns immediately. Per slice 2D scope reduction (D4), this is the ONLY legacy tick gated by the flag in v6.3.19; the 8:00 delay tick and 8:30 conflict tick remain authoritative regardless until v6.3.19.1.
- **Per-tenant hash stagger `_offset_seconds_for(tenant_id) -> int`** = `tenant_id % 60`. Tenant 1 → 1s, tenant 12 → 12s, tenant 60 → 0s, tenant 120 → 0s, tenant 31 → 31s, tenant 59 → 59s. Deterministic so an owner sees the same arrival second day after day.
- **Extended `DispatchResult`** — added `recipients: tuple[str, ...]` and `event_id: int | None` fields so the debug endpoint can surface the resolved phone list and the anchor events row id without a follow-up DB query.
- **`backend/app/knowledge_graph/schema_context.py`** — header note enumerating the new push.* event_type vocabulary (`push.morning_sent` / `push.evening_sent` / `push.morning_skipped_*` / `push.evening_skipped_*` / `push.morning_send_failed` / `push.evening_send_failed` / `push.shadow_log` / `push.tick_failed`). Migration head pointer advanced 033 → 034.
- **6 new dispatcher smoke tests** in `tests/services/test_consolidated_briefing.py` covering: hash-stagger spread, push_v2_tick with no due tenants, shadow mode without sending, real mode sending when flag enabled, skipped-disabled-direction tenant filter, direct `dispatch_morning(..., shadow=True)` shadow log shape. Total file now 49 cases (35 from slices 1–2C + 6 added in 2D-shadow), all green.
- **8 additional `@pytest.mark.xfail` markers** on date-drift-sensitive detector tests (see Notes — total xfailed now 13).

### Added (slice 2C — async dispatchers)
- **`backend/app/services/consolidated_briefing.dispatch_morning` and `dispatch_evening`** (async). Wire `PushConfig` (slice 2A) + field computers (slice 2B) + `select_flag_and_next_step` (slice 1) + Meta-bound `MORNING_BRIEFING_EN/HI` template + the existing `_send_whatsapp_message` transport. Argument order `(tenant_id, now, db)` — matches slice 2B helpers, deviates from the brief sketch in favour of merged-code consistency. `now` is the single source of time truth — zero `datetime.utcnow()` / `datetime.now()` calls inside the module.
- **`DispatchResult` dataclass** (frozen) — return value of dispatch_*. Fields: `success, tenant_id, kind, sent_count, skip_reason, rendered_message, error`. Skips count as `success=True` with `skip_reason` set (`paused | disabled | idempotent | no_recipients | tenant_not_found`).
- **Idempotency via events-table dedup.** Each dispatch checks for an existing `push.{kind}_sent` event with matching `payload['scheduled_for_date']` for this tenant before sending. Same-day repeat calls return early with `skip_reason='idempotent'`. The `_sent` event only fires when at least one recipient receives the message — full-failure paths leave the dedup window open so the next tick can retry.
- **Migration 034 — `ix_events_tenant_type_dedup` composite index** on `events(tenant_id, event_type)`. Supports the dedup query at scale; without it the dispatcher would full-scan the events table on every tick. Reversible.
- **Recipient resolution via `PhoneTenantMap`** (slice 2C decision B1). New alert-preference keys `push_morning` / `push_evening` added to the vocabulary alongside the existing `morning_briefing` / `job_delay` / `machine_down` / `conflict`. Top-tier role gate via `PhoneTenantMap.is_top_tier` (`phone_role in TOP_TIER_ROLES`). Default-True for missing alert prefs — same convention as `whatsapp_alerts._get_active_phone_mappings`.
- **`backend/tests/services/test_consolidated_briefing.py`** — 14 new dispatcher tests across morning + evening + cross-tenant isolation. Covers happy path, paused-skip, disabled-skip, no-recipients-skip, idempotency, success event payload shape, Meta-failure-no-raise, hi_en default locale, hybrid placeholder render, no-jobs render, evening-vs-morning event-type isolation, evening-disabled-independent. Uses a per-test `mock_meta_sender` fixture (monkeypatches `_send_whatsapp_message` in the consolidated_briefing namespace) and a local autouse `patch_now_defaults_for_sqlite` fixture that mirrors `test_signup_v6_4.py`'s pattern (covers Tenant + User + RefreshToken + PhoneTenantMap + Event tables).

### Notes (slice 2C scope decisions, captured for future readers)
- **A1 — locale defaults to `'hi_en'` for ALL recipients.** Per-recipient locale resolution is deferred. The brief assumed a `User.language_preference` field exists; an audit found it does not. Adding the column + the migration + the routing logic is a future-slice concern — not in v6.3.19 scope. Documented in the dispatcher docstring.
- **B1 — recipient resolution matches the v5.10 `PhoneTenantMap` pattern exactly.** The User-based recipient model the brief originally sketched would have changed audience between old and new tick paths and broken shadow-mode parity verification (slice 2D test 12). Audience-model unification (PhoneTenantMap ↔ User) belongs in its own slice.
- **D4 — slice 2C ships morning + evening only. Delay/conflict dispatchers deferred to v6.3.19.1.** The legacy 8:00 delay tick and 8:30 conflict tick in `whatsapp_alerts.py` remain authoritative and ungated by `push_v2_enabled` in this release. Slice 2D-shadow's scope reduces accordingly: only the 5-min briefing tick is replaced. v6.3.19.1 (small follow-up) migrates delay/conflict once morning/evening shadow verification is clean.
- **Argument order — `(tenant_id, now, db)` matches slice 2B field helpers**, deviates from the brief's `(now, db, tenant_id)` sketch. Slice 2B is merged and stable; consistency with merged code wins.
- **Hybrid flag rendering** uses benign placeholders ("Aaj sab routine hai" / "All systems normal today") for `flag` and ("Koi action nahi chahiye" / "No action needed") for `next_step` when no blocker-class signal fires. The current `MORNING_BRIEFING_EN/HI` templates carry hard `{flag}` and `{next_step}` placeholders — collapsing to empty would require a Meta v2 conditional-section template re-submission and a constant rewrite, both deferred to the v2 hybrid switch.

### Changed
- 

### Fixed
- 

### Migration
- `032 → 033` — `add_push_columns_to_tenants`. Three nullable columns on `tenants` (`morning_sections`, `evening_sections`, `push_paused_until`). No backfill, reversible.
- `033 → 034` — `add_events_dedup_index`. Composite btree index `ix_events_tenant_type_dedup` on `events(tenant_id, event_type)` to support slice 2C dispatcher dedup queries. No data change, reversible. Single head 034.

### Notes
- **`next_step` rendering uses a static lookup in `consolidated_briefing._NEXT_STEP_TEMPLATES` rather than a field on `SignalResult`.** Deliberate v6.3.19 choice: extending `SignalResult` with `next_step_hi_en` / `next_step_en` would have touched the 13-evaluator catalog and risked the 5 xfailed detector tests. The static-lookup approach has the smallest blast radius, keeps the catalog free of action-text concerns, and gives one edit point for tone refreshes. Trade-off: action text lives away from the detector that fires it. Revisit after the broader pattern-briefing rollout (`PATTERN_BRIEFING_TENANT_IDS` widens beyond the pilot set) when the cost of the indirection becomes visible.
- **Naming bridge in `resolve_push_config` (slice 2A scope decision).** Migration 027 (v6.3.1) already added `briefing_morning_time`, `briefing_evening_time`, `briefing_timezone`, `briefing_morning_enabled`, and `briefing_evening_enabled` to `tenants`. Migration 033 adds only the three columns the brief did not already have an equivalent for — `morning_sections`, `evening_sections`, `push_paused_until`. The slice 2A part 2 resolver bridges the existing `briefing_*` columns into a `PushConfig` dataclass whose field names (`morning_push_time`, `morning_enabled`, etc.) match the v6.3.19 brief, so dispatcher callers see one consistent surface. **Future deferred work — slice 2A-rename:** unify the namespace by renaming `briefing_*` → `push_*` in a single breaking migration when the cost of the inconsistency outweighs migration churn (touches ~5–10 caller sites).
- **schema_context backfill (gap, not new in this slice).** `app/knowledge_graph/schema_context.py` was last fully reconciled at migration 027. Migrations 028 (events table), 029 (extraction_candidates), 030 (confirmation_* cols), 031 (Day-7 anchor + engagement ladder state), and 032 (skills.source) added tables / columns that are not yet reflected in the AI-facing schema text. v6.3.19 slice 2A documents its own three columns and bumps the head pointer to 033 but does not retroactively backfill 028–032. Schedule a dedicated docs slice — small, mechanical — before any release that materially changes the AI Copilot's behaviour around those tables.
- **Inline emoji in AI Copilot reply builder.** `app/routers/ai_chat.py:249–276` contains 7 inline emoji codepoints (👋 📋 🔴 ⚠️ 📌 👥 🏭). Noticed during the v6.3.18 dispatcher audit but outside the strict gate target set (`whatsapp_alerts.py`, `briefing_intelligence/`, `whatsapp_router.py`, `whatsapp.py`). Migrate to `AI_REPLY_HEADER` + the named constants in `app/services/message_emoji.py` whenever the AI Copilot surface refresh lands (currently planned for v6.4).
- **Meta template positional numbering verification.** `meta/templates_v2.json` (and its in-tree copy at `backend/app/services/whatsapp_meta_templates.json`) uses `{{1}}{{1}}` numbering where HEADER `{{1}}` and BODY `{{1}}` are independent positions per Meta's spec. The v6.3.18 alignment audit (`tests/test_message_templates.py::test_23_ac7_*`) treats them as independent and the count math passes, but the assumption has not been spot-checked against a real Meta submission for a non-trivial template. Action: cross-reference one approved template's submission JSON in the BSP/Meta dashboard against the in-tree entry; if the positional model differs, adjust the count-parity test accordingly.
- **13 v6.3.11 detector tests marked `xfail` (was 5 at v6.3.18; expanded to 13 in v6.3.19 slice 2D-shadow as further tests fell to the same date-drift pattern).** **Cause is test-infrastructure, not application behaviour.** The fixture timestamp builders (`make_attendance_event`, `make_assignment`, `make_employee`, etc. in `tests/services/conftest.py`) anchor `created_at` / `assigned_at` to `datetime.now(timezone.utc) - timedelta(days=N)` (wall-clock now), while the detector invocation passes a hardcoded `TODAY = date(2026, 5, 4)` anchor. As wall-clock now drifts past 2026-05-04, fixture rows fall outside the detector's `created_at >= cutoff_dt` window where `cutoff_dt` is computed from `TODAY` — so trigger conditions that should fire silently no-op. **Production behaviour is unaffected:** real attendance.recorded events carry true `now()` `created_at` timestamps and the dispatcher passes the live tenant-local today, so the two anchors stay in sync at runtime. The bug is exclusively in test infrastructure. Affected functions:
  - `tests/services/test_detect_no_progress.py::TestDetectNoProgress::{test_fires_for_stale_in_progress_job, test_status_normalization_handles_titlecase_in_progress, test_severity_equals_count_of_stale_jobs}` (3 — original v6.3.18 batch).
  - `tests/services/test_detect_new_employee_no_show.py::TestDetectNewEmployeeNoShow::{test_fires_when_new_hire_marked_absent_every_day, test_skips_employees_added_more_than_14_days_ago}` (2 — first test from v6.3.18, second added v6.3.19 slice 2D-shadow).
  - `tests/services/test_detect_status_change_alert.py::TestDetectStatusChangeAlert::test_skips_old_status_changes` (1 — v6.3.18 batch).
  - `tests/services/test_detect_idle_machine.py::TestDetectIdleMachine::{test_fires_for_idle_operational_machine, test_status_normalization_treats_active_lowercase_as_operational, test_picks_worst_idle_when_multiple_qualify}` (3 — added v6.3.19 slice 2D-shadow).
  - `tests/services/test_detect_low_utilization.py::TestDetectLowUtilization::{test_fires_when_utilization_below_30pct, test_severity_score_inversely_tracks_ratio}` (2 — added v6.3.19 slice 2D-shadow).
  - `tests/services/test_detect_manager_silence.py::TestDetectManagerSilence::{test_fires_when_few_checkins_in_window, test_severity_grows_as_silence_extends}` (2 — added v6.3.19 slice 2D-shadow).

  Decorator format: the original 5 use multi-line `@pytest.mark.xfail(reason=…, strict=False)`; the 8 added in slice 2D-shadow use single-line `@pytest.mark.xfail(strict=False, reason="date drift, see CHANGELOG note 92")`.

  **Fix planned for v6.3.19.1:** rewrite the 13 affected tests to use a single hardcoded `TODAY` / `NOW` anchor consistently across fixture setup AND detector invocation. Verification will run the suite at multiple simulated wall-clock dates (e.g. `freezegun` parametrisation across a 90-day span) to prove robustness against future calendar drift. Once the fix lands, all 13 markers are removed; `import pytest` lines added by this xfail batch get stripped.

  **Hard deadline:** this list of 13 must NOT grow further. If a 14th detector test fails for the same reason before v6.3.19.1 ships, treat it as a release blocker and bring v6.3.19.1 forward — do not silently add a 14th xfail.

---

## [v6.3.18] — 2026-05-08
**Branch:** v5-whatsapp

WhatsApp message styling pass. Centralises the *style* of every user-facing WhatsApp message — emoji vocabulary, entity formatters, dispatcher-shape templates, Meta HSM template bindings — into shared modules, and migrates the v5.10 cron dispatcher (`whatsapp_alerts.py`) and the WhatsApp AI reply path (`routers/whatsapp.py:1089`) onto the new infrastructure. No new user capability, no schedule changes, no schema. Code-only release that ships against the mock; the Meta-bound `_EN`/`_HI` constants in `message_formatters.py` are shaped 1:1 to Meta-approvable HSM templates so registration is mechanical when Meta Business portfolio approval lands.

Note on numbering: the v6.3.18 brief proposed "SRS Section 11 — Voice, Tone, and Formatting Standards"; the existing Section 11 ("Optimisation Algorithm Specification") is load-bearing technical content, so the new section was placed at **Section 23** without renumbering. AC IDs are `23-AC1` through `23-AC8`. Tests, ledger, and SRS all use the same prefix per the CLAUDE.md AC convention.

### Added
- **`backend/app/services/message_emoji.py`** — single source of truth for every emoji that may appear in a WhatsApp message. Module-level constants only, grouped STATUS / SEVERITY / DOMAIN / PROMPT. 15 named constants. Adding new emoji literal in a dispatcher module is now a Section 23 / AC 23-AC1 review-gate violation.
- **`backend/app/services/message_formatters.py`** — folded surface from `whatsapp_formatter.py` (markdown post-processor + `detect_language`) plus four new pure formatters (`format_jobs_list`, `format_employee_status`, `format_relative_date`, `format_machine_status`) plus five named template constants (`MORNING_BRIEFING_EN`, `MORNING_BRIEFING_HI`, `DELAY_ALERT_EN`, `CONFLICT_ALERT_EN`, `AI_REPLY_HEADER`). Every constant carries a docstring binding it to a Meta template name + placeholder map. `format_relative_date` uses Asia/Kolkata calendar-day deltas (NOT 24-hour deltas — explicit AC 23-AC2 guarantee).
- **`backend/app/services/message_templates.py`** — locale-dict templates for the v5.10 dispatcher path: `MORNING_BRIEFING` (en / hi-en / hi), `DELAY_ALERT` (en single string), `CONFLICT_ALERT` (en single string), `MACHINE_DOWN_ALERT` (en / hi-en / hi), and `AI_REPLY_HEADER` + `render_ai_reply()` wrapper for the WhatsApp AI reply path. Distinct from the Meta-bound _EN/_HI constants in `message_formatters.py`: those anticipate the v6.4 data shape; these mirror what the v5.10 dispatcher actually sends today, with visual hierarchy + emoji + Hinglish tone applied. Locale resolution via `pick(template, locale)` falls back to `DEFAULT_LOCALE = "hi-en"` (matches existing v5.10 string convention).
- **`backend/app/services/whatsapp_meta_templates.py`** — registration-metadata loader exposing typed `META_TEMPLATES: dict[(name, language), MetaTemplate]`. Reads sibling JSON file at import time, merges with `PYTHON_CONSTANT_BINDINGS` (the v6.3.18 wired subset). No send logic. Includes Meta-submission procedure as a module docstring (manual, never executed by code).
- **`backend/app/services/whatsapp_meta_templates.json`** — verbatim copy of `meta/templates_v2.json` (35 entries spanning 23 unique template names, en_US and hi where applicable) plus one additive Hindi sibling for `zetaops_job_conflict_alert` carrying `status: "draft_pending_meta_submission"` so ops knows it has not yet been pushed through Meta review. Code-mixing style matches the existing `zetaops_morning_briefing (hi)` convention.
- **`backend/tests/test_message_formatters.py`** — 25 unit tests covering the four new formatters + the folded markdown surface. Eight `test_23_ac2_*` cases lock the IST day-boundary contract.
- **`backend/tests/test_message_templates.py`** — 26 structural / snapshot / alignment tests across AC IDs 23-AC1 through 23-AC8, including the Meta-binding alignment test (every wired Python constant's named-kwarg count equals the Meta `{{n}}` count across HEADER + BODY).
- **`backend/tests/services/test_message_dispatcher_templates.py`** — 24 snapshot + structural tests for the new dispatcher-shape templates in `message_templates.py`. Covers MORNING_BRIEFING (with and without delay line), DELAY_ALERT (singular and plural), CONFLICT_ALERT, MACHINE_DOWN_ALERT, and the AI_REPLY_HEADER wrapper (with name, without name, empty body). Length caps (23-AC5), action-prompt presence (23-AC3), and emoji-vocabulary purity (23-AC6) verified.
- **SRS Section 23 (Voice, Tone, and Formatting Standards)** — new top-level section codifying tone principles, visual hierarchy, length caps (800 soft / 1000 hard), emoji vocabulary policy, Hindi-English code-mixing rule, and the Meta template binding bridge. AC IDs 23-AC1 through 23-AC8 enumerated.
- **SRS Section 1.2 SHIPPED list** updated with v6.3.18 line.
- **SRS version table** new row "Document v6.7" describing the Section 23 addition. Document version banner advanced from v6.6 to v6.7.

### Changed
- **`backend/app/services/whatsapp_formatter.py`** reduced to a backwards-compatibility re-export shim. Existing callers (`whatsapp_alerts.py` × 3 late-imports, `whatsapp_checkin.py`, `routers/whatsapp.py`) continue to import `format_for_whatsapp` and `detect_language` without edits; the implementation now lives in `message_formatters.py`. New code should import from the canonical location directly.
- **`backend/app/services/whatsapp_alerts.py`** — `_build_morning_briefing`, `_build_delay_alert`, `_build_conflict_alert`, and `send_machine_down_alert` migrated off inline f-strings to the new dispatcher templates in `message_templates.py`. Job lists in delay/conflict alerts now route through `format_jobs_list` (5-item cap with `+N more` tail). Function signatures unchanged; the wire content is the same active/total/delayed/team counts, with visual hierarchy + emoji + length cap centralised.
- **`backend/app/routers/whatsapp.py`** — AI reply path at line 1089 now wraps the post-`format_for_whatsapp` body with `render_ai_reply()` from `message_templates.py`. The first token of `identity.display_name` (when present) is interpolated into the warm-greeting header; missing display name renders as `"Namaste! 👋"` with no name-shaped gap. Adds the SRS §23.2 visual hierarchy (header line, blank line, body).
- **CLAUDE.md, DELIVERY_LEDGER.md, this file** — updated to reflect v6.3.18 shipped state.

### Fixed
- (none)

### Migration
- (none — head stays at 032)

### Tests
- 25 + 26 + 24 = **75 new passing tests** across `test_message_formatters.py`, `test_message_templates.py`, and `tests/services/test_message_dispatcher_templates.py`. Run via `pytest tests/test_message_formatters.py tests/test_message_templates.py tests/services/test_message_dispatcher_templates.py -v`.
- Meta-binding alignment audit (AC 23-AC7) green for all four wired pairs: `zetaops_morning_briefing (en_US/hi)` 6==6, `zetaops_job_conflict_alert (en_US)` 5==5, `zetaops_job_ending_soon (en_US)` 5==5.
- Pre-v6.3.18 regression suite green: `test_whatsapp_alerts_send_routing.py` (4/4), `test_whatsapp_router.py` (17/17), `test_whatsapp_pipeline.py` (29/29).

### Deferred
- **Routing existing dispatcher calls through Meta-bound MORNING_BRIEFING_EN / DELAY_ALERT_EN / CONFLICT_ALERT_EN constants.** The Meta-bound templates in `message_formatters.py` anticipate fields the v5.10/v6.3.4 dispatcher does not yet compute (`jobs_starting` vs `continuing` distinction; `crew_expected` as a fraction; `flag`; `next_step`). v6.3.18 instead routes the existing dispatcher through dispatcher-shape templates in `message_templates.py` that mirror the current data model with visual hierarchy + emoji + length cap applied — preserving SRS §23 brief rule "do not change *what* is sent, only *how* it is formatted". The Meta-bound constants stay as infrastructure for v6.4 when the morning briefing data shape catches up.
- **`AI_REPLY_HEADER` integration in `routers/ai_chat.py`.** That router is outside the v6.3.18 dispatcher-gate target set; the existing inline `"Namaste! 👋"` literal at `app/routers/ai_chat.py:249` (and 6 other emoji on lines 254, 256, 266, 271, 274, 276) was noted but not modified per "scope discipline = list bugs, do not fix". Schedule the AI Copilot non-WhatsApp reply path to migrate to `AI_REPLY_HEADER` + `message_emoji` constants when v6.4 lights up the AI surface refresh. The WhatsApp router AI path (`routers/whatsapp.py:1089`) IS migrated by v6.3.18.
- **`CONFLICT_ALERT_HI` Python constant.** The Hindi `zetaops_job_conflict_alert` entry exists as a draft in the JSON registry but is not yet bound (`python_constant: None`). Wire it up the same release that submits the Hindi entry to Meta and flips its `status` field.
- **`whatsapp_router.py`** — the v6.3.18 brief listed it as a possible alias; the actual codebase only has `routers/whatsapp.py`. The grep gate handles missing paths gracefully.

### Bugs noticed (not fixed per scope)
- `app/routers/ai_chat.py:249–276` — 7 inline emoji codepoints in the AI Copilot response builder (`👋 📋 🔴 ⚠️ 📌 👥 🏭`). Outside the strict dispatcher-gate target set; deferred per "do not fix in this PR" rule from the v6.3.18 brief §6.
- `app/services/seed_v2.py` and `seed_scheduling.py` use emoji in `print()` statements. These are dev-only seed scripts that never reach a WhatsApp wire — flagged for completeness only, no action needed.

### Acceptance
- 8 / 8 ACs (23-AC1 through 23-AC8) passing — see SRS §23.7 for the verifying test names.

---

## [v6.3.17] — 2026-05-07
**Commit:** `4dfc365`
**Branch:** v5-whatsapp

WhatsApp owner-bypass entity writes. Top-tier WhatsApp messages
containing an explicit creation verb (`add karo`, `add kar do`,
`banao`, `bana do`, `jodo`, `daalo`, `register karo`, `create`)
plus an entity name now write directly to `employees` /
`machines` / `skills` / `employee_skills` with
`source='whatsapp_owner'`, bypassing the v6.3.14 extractor
confidence threshold and the v6.3.15 nightly confirmation cycle.
Manager / operator / NULL / unknown roles still fall through to
the existing extractor path unchanged. The heuristic
deliberately errs toward false negatives — missed creates fall
through to extraction (fine), false positives (accidental writes
to a customer's production DB) are not.

### Added
- **`app/services/owner_entity_writer.py`** — heuristic detector + four writers (`write_employee`, `write_machine`, `write_skill`, `link_employee_skill`) + `evaluate_and_write` entry point. Strict role gate (NULL / unknown / mid-tier / operator return None — no caching, decided per-message). Idempotency via the existing v6.3.15 `fuzzy_match.fuzzy_best_match` (rapidfuzz token_set_ratio threshold 85, ratio fallback 90). Owner-bypass writes skip duplicate inserts and emit no second audit row when the fuzzy short-circuit fires.
- **New audit-event type `entity.owner_added`** on the v6.3.3 events table. Payload: `{entity_type, entity_id, raw_message, source: 'whatsapp_owner', actor_user_id, parse_strategy: 'heuristic', fuzzy_skipped}`. The `parse_strategy` field is reserved for v6.4.x evolution to a hybrid LLM-assisted parser without payload-schema break.
- **Dispatcher branch (Step 6a.5)** in `app/routers/whatsapp.py:_process_inbound_message`, between the role-blocked early-return and the existing action_type confirmation loop. Self-contained session, late import, exception-swallowing — gate failures never affect the rest of the pipeline.
- **`tests/services/test_owner_entity_writer.py`** — 40 tests covering 10 negative heuristic cases (`"Mukesh ko sambhaalo aaj"`, `"Suresh aaj nahi aaya"`, `"Naya welder chahiye"`, `"Mukesh achha kaam karta hai"`, `"Mukesh ki salary kya hai"`, `"Mukesh ko aaj kya kaam mila"`, `"Ek welder kal aayega"`, `"Welder chahiye urgent"`, `"Heidelberg add kar do"`, `"ek aur machine aayi hai, naam Cutter 4"`), 4 positive cases, full role-gate matrix (4 top-tier × proceed + 6 non-top-tier × fall-through including NULL / empty / case-mismatch + role-change between messages), 4 writer happy paths, 3 cross-entity dependency paths, 4 idempotency paths, and the audit-event payload contract.
- **`'whatsapp_owner'`** added to `VALID_SOURCE_VALUES` in `app/models/employee.py`. Distinguishes owner-asserted writes from manager-typed (`'whatsapp'`) and bot-promoted (`'whatsapp_inferred'`) rows.

### Changed
- **`app/models/skill.py`** gained a `source` column to match the Employee/Machine pattern (CLAUDE.md rule #2 — provenance is structural, never remove). Imports `VALID_SOURCE_VALUES` from `models/employee.py` so a single canonical vocabulary covers all three entity tables.
- **`tests/test_employees.py::test_valid_source_values_constant`** updated from `len == 4` to `len == 5` and added `whatsapp_owner` membership check.
- **`tests/test_alembic_migrations.py`** head test renamed `test_head_is_031` → `test_head_is_032`; added `test_032_in_chain`.
- **CLAUDE.md** head bumped from `031` to `032` in three places.

### Migration
- **032 — `add_source_to_skills.py`** — adds `source VARCHAR(20) NOT NULL DEFAULT 'manual'` to the `skills` table. Reversible. Existing rows back-fill atomically via the server_default. Verified end-to-end against dev Postgres: round-trip (`upgrade head` → `downgrade -1` → `upgrade head`) clean.

### Tests
- `pytest tests/services/test_owner_entity_writer.py -v` — **40 passed**.
- `pytest tests/ -m "not integration"` — **888 passed**, 4 pre-existing date-drift failures (3 in `test_detect_no_progress`, 1 in `test_detect_new_employee_no_show` — both rely on `TODAY=date(2026,5,4)` and need an unrelated fix), 3 skipped, 12 deselected. Zero regressions caused by v6.3.17.
- Smoke test against dev Postgres tenant 12 (no Mukesh on disk before): happy path inserted Mukesh as Employee with `source='whatsapp_owner'`, role-gate refused the same message from a manager-role phone with `None`, idempotency short-circuited a second identical owner message with `"Mukesh pehle se team mein hai."` — no duplicate row, no second audit event. Tenant 12 restored to its pre-smoke state (the audit row left intact by design — events are append-only).

### Deferred
- **`"ek aur machine aayi hai, naam Cutter 4"` phrasing** — has no creation verb in the tight set and is therefore a false negative. The message falls through to the v6.3.14 extractor and surfaces later via the v6.3.15 confirmation cycle. Per the Q1 directive ("missed creates fall through, fine; false positives, not fine"), this is the intended trade-off. Revisit when real owner messages give us evidence that this phrasing is common.
- **DELETE / UPDATE / bulk-add intents** — explicitly out of scope per the spec; audit / confirmation requirements are stronger and deserve their own version.
- **Customer-add path** — `customers` table still does not exist; `Job.customer` remains free-text VARCHAR. Defer to whichever future version adds the schema.
- **Reply localisation** — replies are romanised Hindi/Hinglish, matching the existing dispatcher convention. v6.3.18 message-formatter pass owns the standardisation.
- **AC IDs** — batched with v6.3.7..v6.3.17 SRS annotation pass.

### Notes
- Owner-bypass writes are **only** for explicit-creation messages from a top-tier phone. Anything else flows through the existing extractor + nightly confirmation cycle unchanged.
- The strict role gate is enforced inside `evaluate_and_write` (using the canonical `TOP_TIER_ROLES` from `app.models.auth`), independent of the existing `detect_write_intent` role gate. This means a future change to either gate cannot accidentally widen the bypass surface.
- v5.11 WhatsApp go-live remains blocked on Meta portfolio review.

---

## [v6.3.16] — 2026-05-06
**Commit:** `d8fb094`
**Branch:** v5-whatsapp

Day-7 First-Insight Gate. After seven calendar days of delivered
morning briefings, the dispatcher fires a one-shot owner message
that picks the strongest of four signals (attendance pattern,
skill bottleneck, machine utilisation spread, recurring customer
name) or a routine-set fallback when no signal crosses threshold.
Idempotency lives in a new `tenants.engagement_ladder_state` JSONB
ledger so the gate cannot fire twice per tenant.

### Added
- **`app/services/day7_insight.py`** — `evaluate_and_send(tenant_id, db)` entry point. Four signal detectors (attendance pattern with two sub-variants — chronic worker absent ≥4 of last 7 working days, OR ≥2 distinct workers absent on the same weekday; skill bottleneck where one worker handles ≥70% of jobs requiring a specific skill over the look-back; machine utilisation spread where the most-used machine ran ≥4× the least-used machine, with a 0.5 hr/day floor on the denominator; recurring customer name from `extraction_candidates` mention_count ≥5 and not appearing in any existing `Job.customer`, with a 4-character contiguous substring overlap rule to skip aliases). Priority order matches the spec; first signal that fires wins. Fallback message — the romanised-Hindi `zetaops_day7_routine_set` body — when no signal qualifies. Three audit event types: `engagement.day7_owner_sent` (happy path, ledger marked), `engagement.day7_owner_suppressed` (anchor older than the 14-day suppression window, ledger marked without sending), `engagement.day7_owner_failed` (fan-out totally failed, ledger NOT marked so the gate retries on the next morning tick).
- **`app/services/day7_thresholds.py`** — pure-data threshold constants for the four signals plus the >14-day suppression guard. Stdlib only, no logic. Designed to move into `engagement_ladder/thresholds.py` in v6.4.0 without changes.
- **Dispatcher integration** in `app/services/briefings/dispatcher.py`. Two changes: (a) `dispatch_briefing` now sets `tenant.first_briefing_sent_at = now()` on the first successful morning send for a tenant (one-shot anchor, never updated thereafter); (b) `dispatch_due_briefings` calls `evaluate_and_send` after a successful morning commit, in its own try/commit block so gate failures cannot affect the briefing or the rest of the cron tick.
- **18 unit tests** in `tests/services/test_day7_insight.py` covering all four signal detectors firing, the fallback when no signal crosses, idempotency of a second call, the three skip paths (no anchor / too early / suppression for >14-day anchor), total + partial send-failure ledger semantics, alias-overlap exclusion in the customer detector, and signal priority (attendance wins over machine when both qualify).

### Changed
- **`app/models/auth.py:Tenant`** gained two new columns mapped to the migration-031 schema: `first_briefing_sent_at TIMESTAMPTZ NULL` (the day-counting anchor) and `engagement_ladder_state JSONB NOT NULL DEFAULT '{}'` (the per-tenant idempotency ledger; v6.3.16 writes one key, `day7_owner_sent_at`, with v6.4.0 reserved keys documented in the migration header).
- **`tests/test_alembic_migrations.py`** head test renamed `test_head_is_030` → `test_head_is_031`; added `test_031_in_chain`.
- **CLAUDE.md** head bumped from `028` (which was already stale) to `031`, plus the "Current state in one paragraph" section refreshed in a follow-up commit (`c30f7d1`) to cover v6.3.7 through v6.3.16.

### Migration
- **031 — `add_day7_engagement_columns.py`** — adds the two new columns on `tenants`. Backfills `first_briefing_sent_at` for existing tenants from the earliest `briefing.sent` event with payload `kind='morning'` (Postgres `payload ->> 'kind'` text-extract). Tenants with no morning-briefing history retain NULL and the gate silently skips them. Reversible. Verified end-to-end against dev Postgres: round-trip (`upgrade head` → `downgrade -1` → `upgrade head`) clean; 2 of 37 tenants got an anchor backfilled (the rest had never received a morning briefing — correctly NULL).

### Tests
- `pytest tests/services/test_day7_insight.py -v` — **18 passed**.
- `pytest tests/test_alembic_migrations.py` — 7 passed, 3 skipped (live-DB tier).
- `pytest tests/ -m "not integration"` — **848 passed**, 3 pre-existing date-drift failures in `test_detect_no_progress` (verified against unmodified baseline; not introduced by this branch), 3 skipped, 12 deselected.
- Smoke test against dev Postgres tenant 12: happy path fired the routine-set fallback to two recipient phones (`[MOCK ALERT]` lines visible in uvicorn log), failure mode (raising send_fn) wrote `engagement.day7_owner_failed` and left the ledger untouched, suppression mode (anchor 30 days old) marked the ledger without sending. Tenant 12 restored to its pre-smoke state.

### Deferred
- **The existing `briefing_intelligence/catalog/tenancy.py:detect_day_7` marker** (a single-line celebratory message inside the morning briefing) is left in place. v6.3.16's docstring explicitly tags this as the "wow gate" that supersedes the marker, but coexistence on day 7 is acceptable per spec — the user receives one short marker line inside the briefing AND one signal-driven (or fallback) message after. v6.4.0 owns retiring or gating the marker.
- **`zetaops_day7_routine_set` Meta template registration** — the en_US + hi bodies are documented in the spec; submission to Meta as a template fallback for the rare expired-session case is a separate ops step. v6.3.16 uses Cloud API session messages everywhere (the gate fires on the morning push tick, where the 24h session window is always open).
- **AC IDs** — batched with the v6.3.7..v6.3.17 SRS annotation pass.

### Notes
- The Q1-confirmed >14-day suppression guard means existing pilot tenants whose backfilled anchor is more than 14 days in the past are silently retired without ever receiving a Day-7 message. This prevents post-hoc surprise messages on production tenants who installed before the gate existed.
- The customer-recurrence detector treats `Job.customer` (a free-text VARCHAR — there is no customers table) as the "is this name new?" check, with a 4-character contiguous substring rule to catch alias-style duplicates ("Patel Trading Co." vs "Patel Traders").

---

## [v6.3.15] — 2026-05-05
**Branch:** v5-whatsapp

Candidate-promotion job. Reads from `extraction_candidates` (the
v6.3.14 staging table) and materialises high-confidence, frequently-
mentioned candidates into the canonical `employees` and `machines`
tables. Runs nightly at 02:00 IST via the existing
`AsyncIOScheduler`. Customer promotion is intentionally out of scope
at v6.3.15 — no `customers` table exists in the v6.3.x schema — and
qualifying customer candidates emit a deduped
`extraction.candidate_skipped` audit event with
`reason="customer_table_not_yet_implemented"` so the deferred
backlog stays grep-able when a customers table eventually lands.

### Added
- **`promote_for_tenant` + `promote_for_all_tenants`** (`app/services/promotion/promoter.py`) — per-tenant unit of work plus the APScheduler entry that fans out across tenants opted into `ENTITY_EXTRACTION_TENANT_IDS`. Per-tenant 60s wall-clock budget via `asyncio.wait_for` + `asyncio.to_thread` (sync DB body offloaded to a worker thread so the timeout actually fires). Per-candidate failures rolled back and recorded in `summary.errors`; per-tenant failures logged with structured tenant_id context. The job NEVER raises into APScheduler.
- **`fuzzy_best_match`** (`app/services/promotion/fuzzy_match.py`) — hybrid string-similarity helper: `token_set_ratio` for multi-token candidates (threshold 85) with a `ratio` fallback for single-token candidates (threshold 90). Powers v6.3.15's idempotency (Q9): the second nightly run fuzzy-matches the just-inserted entity and writes `extraction.candidate_confirmed` instead of duplicating the row.
- **Three new audit-event types** on the v6.3.3 `events` table — `extraction.candidate_promoted`, `extraction.candidate_confirmed`, `extraction.candidate_skipped`. Entity_type stamped as `'extraction_candidate'` with `entity_id = candidate.id`. No schema change; existing `event_type String(50)` accepts new values without migration.
- **`PROMOTION_*` env settings** (`app/config.py`) — `PROMOTION_MENTION_THRESHOLD=3`, `PROMOTION_CONFIDENCE_THRESHOLD=0.7`, `PROMOTION_FUZZY_MATCH_THRESHOLD=85`, `PROMOTION_RATIO_FALLBACK_THRESHOLD=90`, `PROMOTION_DAILY_CAP_PER_TENANT=10`. Defaults in code, env override (matches `ENTITY_EXTRACTION_TENANT_IDS` precedent). Tenant scoping reuses the extractor's flag — no separate `PROMOTION_TENANT_IDS`.
- **`--show-promotions` flag on `inspect_extractions.py`** — buckets recent `extraction.*` events for a tenant by event_type, sorted by `created_at desc`. Use after a nightly run to see what got promoted, confirmed, or skipped.
- **APScheduler registration** (`app/services/whatsapp_alerts.py`) — new `candidate_promotion_job` at 02:00 IST (`CronTrigger(hour=2, minute=0, timezone='Asia/Kolkata')`, `coalesce=True`, `max_instances=1`, `replace_existing=True`). Also added to `set_dev_schedule()` for dev-mode parity.
- **Smoke tooling** — three scripts at backend root: `smoke_promotion_e2e.py` (happy path: 30/30 assertions), `smoke_promotion_idempotency.py` (Q9 critical guarantee: 19/19 assertions across 3 consecutive runs with no duplicates), `smoke_promotion_cap.py` (Q5 cap behaviour: 14/14 assertions). All run against real Postgres using a scratch tenant id `9999` and clean up via CASCADE on exit.
- `tests/services/test_promotion_promoter.py` — 23 tests covering threshold gating, tenant scoping, customer-skip with dedupe, daily cap, idempotency, audit-event payload shape, per-candidate failure isolation, and per-industry happy paths (printing/manufacturing/fabrication/chemical/field_service).
- `tests/services/test_promotion_fuzzy_match.py` — 10 tests covering exact match, minor typo, single-token fallback, empty inputs, threshold overrides, and best-of-multiple selection.

### Changed
- **`VALID_SOURCE_VALUES`** (`app/models/employee.py`) extended from 3 to 4 values to add `whatsapp_inferred`. Distinguishes bot-extracted-and-promoted rows from `whatsapp` (user-typed via WhatsApp). Constants-only change — the `source` column is `String(20)` with no DB-level enum, so no migration. Importers (`app/schemas/{employee,machine}.py`, `app/models/machine.py`) accept the new value automatically because they use `str` not `Literal[VALID_SOURCE_VALUES]`.
- `tests/test_employees.py::test_valid_source_values_constant` — assertion updated from `len == 3` to `len == 4` and added `whatsapp_inferred` membership check.

### Migration
- None (head stays at `029`).

### Tests
- `pytest tests/ -m "not integration"`: **746 passed**, 3 skipped, 12 deselected. Baseline was 713 (post v6.3.14); +33 new tests, zero regressions.
- All three smoke scripts PASS against real Postgres (63 assertions total across the three scripts). Scratch tenant fully cleaned up afterwards.

### Deferred
- **Customer promotion** — no `customers` table exists in the v6.3.x schema (the only customer-shaped data is the free-text `Job.customer` String column). Qualifying customer candidates remain in `extraction_candidates` and emit a deduped `extraction.candidate_skipped` event. Re-evaluate when a customers table lands (likely v7.x ERP work or sooner if the roadmap brings it forward).
- **Per-tenant promotion settings UI** — v6.3.19 will introduce tenant-level settings infrastructure; until then thresholds are global-via-env.
- **Surfacing promotions back to the user** ("we added Suresh — confirm?") — v6.3.16+.
- **NL-undo flow** ("undo Suresh promotion") — v6.3.17.
- **30-day production review of fuzzy threshold (85)** — per Q1 operational note. If romanisation-variant duplicates appear on tenant 12 (e.g. "Suresh" / "Soorish" treated as different people), lower to 80 or add an LLM-judged secondary match step in a future v6.3.x. The env-overridable threshold is the safety valve.
- **AC IDs** — this version has no SRS section yet; deferred to the batched v6.3.7..v6.3.15 doc-trinity reconciliation pass that already covers v6.3.7..v6.3.12.

### Dependencies
- **New:** `rapidfuzz>=3.10,<4` pinned in `requirements.txt`. Range pin (not `==`) so wheels are available across Python 3.10..3.14 — exact pinning at the point release would lock out CI / dev environments on different interpreters.

### Notes
- **Inert until opted in.** No tenant runs the promoter until its id appears in `ENTITY_EXTRACTION_TENANT_IDS`. The flag is empty by default.
- **Q9 idempotency edge case (acceptable risk).** If the owner renames a just-inserted entity by more than the fuzzy threshold tolerates within 24h (e.g. "Suresh" → "S. Kumar"), the next nightly run treats the candidate as new and inserts a duplicate. Documented in the `promote_for_tenant` docstring; the daily cap of 10 bounds the blast radius.
- **Builds on v6.3.13 + v6.3.14**, whose CHANGELOG entries appear immediately below (backfilled in this same release cycle).
- v5.11 WhatsApp go-live remains blocked on Meta portfolio review. v6.3.15 runs end-to-end in mock mode and is feature-complete behind that gate.

---

## [v6.3.14] — 2026-05-05
**Commit:** `1ef8cc4`
**Branch:** v5-whatsapp

Entity extractor service. Each inbound WhatsApp message triggers
a fire-and-forget `asyncio.create_task` that runs a Groq JSON-mode
call extracting candidate entities by 7 categories (employee,
machine, customer, skill, material, job, issue) and upserts them
into the `extraction_candidates` table from migration 029. Per-
tenant feature flag, default OFF. No user-facing change at this
version — it is the foundation the v6.3.15 promotion job consumes.

### Added
- **`app/models/extraction_candidate.py`** — SQLAlchemy ORM mapping for the migration-029 table.
- **`app/services/extraction/`** package:
  - `__init__.py` — public surface
  - `feature_flag.py` — `ENTITY_EXTRACTION_TENANT_IDS` parsing with `lru_cache` + `_reset_cache` test helper
  - `industry_vocabularies.py` — backend mirror of the frontend industry config
  - `entity_extractor.py` — main service (prompt assembly, JSON parsing, normalisation, upsert)
- **`inspect_extractions.py`** — dev CLI for prompt tuning and smoke verification (`python inspect_extractions.py --tenant-id 12`).
- **`schedule_extraction()` call** wired into `app/routers/whatsapp.py` after Step 6b (`add_message_to_session`). The reply path returns immediately; extraction runs as a detached task.
- **`ENTITY_EXTRACTION_TENANT_IDS`** setting in `app/config.py` (env-CSV, empty = OFF for everyone).
- `tests/services/test_entity_extractor.py` — 23 tests.
- `tests/services/test_extraction_feature_flag.py` — 6 tests.
- `tests/services/test_industry_vocabularies_sync.py` — 6 tests (drift detection between frontend + backend industry configs).
- `tests/services/conftest.py` — SQLite fixture extended for the `extraction_candidates` table.

### Architecture
- **Fire-and-forget.** `asyncio.create_task` from the WhatsApp router; tasks held in a module-level set so the event loop's weak ref does not GC them mid-flight.
- **Same Groq client / model** (`llama-3.3-70b-versatile`) as the chat reply path, but a separate instance configured with `response_format={"type":"json_object"}` so chat-path params can drift independently.
- **10 few-shot examples** in the prompt — 2 per industry (one positive, one empty/uncertain). The empty case is the critical one: it teaches the model that returning `[]` is the correct answer when a message has no clear entities, instead of fabricating one to avoid an empty answer.
- **Industry-specific vocabulary** mirrors the frontend config; a sync test enforces drift detection between the two.
- **Upsert** via PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` keyed on `(tenant_id, entity_type, normalized_value)`; SQLite fallback for the unit-test path uses a query-then-update / insert branch.

### Failure handling
- Every error path swallowed at the module boundary with `logger.error(..., exc_info=True)` and structured `tenant_id` / `message_id` / `error_class` context.
- The reply path is sacred — extraction NEVER raises into it.

### Migration
- None (head stays at `029`; v6.3.13 already added the table).

### Tests
- `pytest -m "not integration"`: **713 passed** (+35 from v6.3.13's 678).

### Manual smoke
- Verified against tenant 12 (printing) with real inbound messages. Each message produced an `entity_extraction_ok` log line with `candidates=2`; rows landed in `extraction_candidates` with the expected `entity_type`, `normalized_value`, and `confidence` shape; identity resolved correctly to `industry=printing`.

### Operational note
- Each extraction call adds 200-500ms of background Groq latency and 3,500-9,000 input tokens. Concentrated dev testing can hit the Groq free-tier 12K TPM limit; production traffic at 1-2 messages/min sits comfortably within budget. Token trim is a candidate optimisation for v6.3.14.1 if real-world volume justifies it.

### Deferred
- Promotion to canonical tables — **v6.3.15 (now shipped)**.
- Surfacing extracted entities to users ("we noticed X — should I add this?") — v6.3.16+.
- NL entity edits reading from this table — v6.3.17.
- Prompt token trim — v6.3.14.1 if real-world volume justifies.
- `<function=...>` system-prompt fix — separate hotfix outside the extractor's scope.
- SRS Section 6.30 expansion — batched doc-trinity reconciliation pass.

### Notes
- This CHANGELOG entry was backfilled in the v6.3.15 release cycle. The feature itself shipped in commit `1ef8cc4` on 2026-05-05.

---

## [v6.3.13] — 2026-05-05
**Commit:** `5c6c883`
**Branch:** v5-whatsapp

Schema-only release. Adds migration 029 introducing the
`extraction_candidates` staging table — the foundation for the
v6.3.14 entity extractor and the v6.3.15 candidate-promotion job.
No application code reads or writes the table at this version; it
sits empty after the upgrade.

### Added
- **Migration 029** — `extraction_candidates` table.
  - 13 columns capturing entity provenance (`raw_value`, `normalized_value`, `source_type`, `source_message_id`), temporal context (`first_seen`, `last_seen`, `created_at`, `updated_at`), and operational state (`confidence`, `mention_count`).
  - 3 lookup indexes: `(tenant_id, entity_type)`, `(tenant_id, normalized_value)`, and `(tenant_id, mention_count)` — the last one is explicitly for v6.3.15's threshold scan.
  - Unique constraint on `(tenant_id, entity_type, normalized_value)` enforcing the upsert invariant: one row per distinct entity per tenant. Backs the v6.3.14 `INSERT ... ON CONFLICT DO UPDATE` upsert.
  - FK CASCADE on `tenant_id` for tenant isolation.

### Schema decisions
- **`entity_type` is `VARCHAR(50)` with NO CHECK constraint.** The vocabulary (employee, machine, customer, skill, material, job, issue) lives in the migration docstring and is enforced at the application layer. Lets v6.3.14+ add new types without a follow-up schema change.
- **`confidence` has no CHECK constraint either.** Documented range is [0.0, 1.0] LLM-self-reported; v6.3.15's promotion threshold is `>= 0.7`. Allowing experimental out-of-range values (e.g. `-1` for "unknown") keeps the door open without a migration.
- **`mention_count` uses upsert-on-conflict semantics** — single row per distinct entity, mutated on re-mention. The events table from migration 028 still provides the immutable audit trail; this table is the materialised running count, not the audit log.
- **`source_message_id` nullable** for non-WhatsApp or internally triggered candidates.

### Migration
- 029 chains `down_revision = "028"` (v6.3.3 events table).
- `alembic upgrade` + `downgrade` + `upgrade` cycle verified clean against dev Postgres. All 13 columns, 3 indexes, and 1 unique constraint landed correctly.

### Tests
- `pytest -m "not integration"`: **678 passed** (+1 net from the migration chain check).

### Deferred
- SQLAlchemy ORM model + Pydantic schemas — **v6.3.14**.
- Entity extractor service — **v6.3.14**.
- Promotion job — **v6.3.15 (now shipped)**.
- SRS Section 6.30 — batched doc-trinity reconciliation.

### Notes
- This CHANGELOG entry was backfilled in the v6.3.15 release cycle. The schema itself shipped in commit `5c6c883` on 2026-05-05.

---

## [v6.3.12] — 2026-05-05
**Commit:** `2833421`
**Branch:** v5-whatsapp

Day-1 onboarding sequence. When a fresh tenant finishes adding their first
employees + machines on `/onboarding`, the backend now dispatches a single
hinglish WhatsApp confirmation message acknowledging the setup and setting
expectations for tomorrow's morning push.

### Added
- **`POST /api/v1/onboarding/complete`** — fire-and-forget endpoint called from `OnboardingSetup.tsx`'s "Save and continue" handler after the employee + machine `Promise.all` save resolves. Auth-gated by `require_top_tier()`. Returns 204 on every outcome path. (`app/routers/onboarding.py`)
- **Three-state idempotency via the v6.3.3 events table** — `onboarding.message_sent` (consent ready, dispatched), `onboarding.pending_consent` (phone exists, awaiting HAAN), `onboarding.skipped_no_phone` (desktop-first, no phone). Single-fire enforced via `_is_already_handled()` check before dispatch. (`app/services/onboarding_message.py`)
- **HAAN-flip resume hook** in `routers/whatsapp.py` — when an owner replies HAAN to the consent welcome, any staged `onboarding.pending_consent` event is converted to `message_sent` and the message dispatched. Safe to call on every HAAN reply (no-op when nothing is pending).
- **Vertical-aware vocabulary** — `INDUSTRY_LABELS` in `briefings/templates.py` gains a new `workspace_label` key for all 5 verticals: `factory` / `shop floor` / `workshop` / `plant` / `sites`. Existing `employees` (plural) and `machines` (plural) keys reused unchanged.
- **Forward-compat schedule helper** — new `app/services/push_schedule.py` exports `get_morning_briefing_time(tenant)` and `get_evening_briefing_time(tenant)`. Today the body reads `Tenant.briefing_morning/evening_time`; v6.3.19 will swap the body to the `industry_push_config` cascade with tenant override fallback. Call sites stay stable.
- **`onboarding_complete` response strings** — added to `whatsapp_responses.py` `RESPONSES` dict with all three locale variants (en, hinglish, hindi). Hinglish dispatches today; en + hindi stubs wired for v6.3.18 locale routing.
- **Frontend wiring** — `ONBOARDING.complete` constant in `api_endpoints.ts`; `OnboardingSetup.tsx`'s `handleSave` fires `apiClient.post(ONBOARDING.complete).catch(() => {})` after the existing `Promise.all` resolves and before navigation to `<DoneScreen>`.
- **Smoke tooling** — `tests/smoke/smoke_v6_3_12.py` (4 scenarios: consented immediate / pending / HAAN-resume / desktop-first skip; 37 assertions including idempotency on re-fire) and `tests/smoke/preview_onboarding_message.py` (renders the message for all 5 verticals + None fallback in all 3 locales).

### Migration
- None (head stays at `028`).

### Tests
- `pytest -m "not integration"`: **677 passed**, 3 skipped, 12 deselected. No regressions.
- Smoke test: 37/37 assertions across 4 scenarios passing in `WHATSAPP_MOCK_MODE=True`.
- Frontend click-through verified end-to-end: `onboarding.pending_consent` event row landed for the test tenant after clicking "Save and continue".

### Deferred
- **Locale routing** for en + hindi response stubs — v6.3.18 styling pass will route via `detect_language()`.
- **Field-service "aapka sites" grammar nit** — acceptable in code-mixed hi-en; v6.3.18 will revisit voice across all sibling messages.
- **`push_schedule.py` body update** — v6.3.19 swaps direct column reads for the `industry_push_config` cascade. Helper signatures stay the same.
- **AC ID annotation** — v6.3.7..v6.3.12 doc-trinity reconciliation pass will mint AC IDs and add the corresponding SRS §6 section.

### Notes
- v5.11 WhatsApp go-live remains blocked on Meta portfolio review. v6.3.12 runs end-to-end in mock mode and is feature-complete behind that gate.
- The HAAN-flip resume path uses direct `await` from the already-async whatsapp router; no new event-loop architecture introduced.
- `chemical` industry is supported by templates (`workspace_label="plant"`, `machines="reactors"`) but excluded from signup enum (Plan B only per CLAUDE.md), so it cannot reach this code path today.

### Companion fix
- A separate commit immediately preceding this one (`fix: time-pin make_tenant fixture for evaluator tests`) repaired 8 v6.3.11 evaluator unit-test failures triggered by UTC midnight rollover (test fixtures were anchored to real `datetime.now()` while test files pinned `TODAY = date(2026, 5, 4)`). No production code touched. Listed here because it was discovered during v6.3.12 smoke testing.

---

## [v6.3.9] — 2026-05-03
**Branch:** v5-whatsapp

Bug-fix release. Two issues found during v6.3.7 live testing closed.

### Fixed
- **Groq `tool_use_failed` no longer breaks user replies.** Llama 3.3 70B on Groq occasionally emits XML-style `<function=...>` markup in the content channel instead of structured `tool_calls`. Groq rejects it with HTTP 400 `tool_use_failed`, which previously bubbled up to `routers/whatsapp.py` and surfaced as "Maafi kijiye, abhi AI service available nahi hai" — or, in the pass-through path, raw markup in the WhatsApp reply. `run_ai_chat` now catches `BadRequestError`, retries without `tools=`, and returns the model's plain answer (no live data lookup, but no error either). New helpers `_is_tool_use_failed` / `_extract_failed_generation` handle both top-level and nested `code` / `failed_generation` body shapes. (`app/services/ai_service.py`)
- **System prompt hardened against tool-call markup leakage.** Added a CRITICAL output rule at the top of `_SYSTEM_PROMPT_BASE` explicitly forbidding `<function=...>`, `<|python_tag|>`, or JSON envelopes in text replies. Routing-table arrows changed from `→ tool_name` to `: call \`tool_name\`` so the model reads the names as identifiers, not syntax to emit. Preventive — should reduce how often the retry path fires. (`app/services/ai_service.py`)
- **`remap_phone.py` now refreshes the `industry_type` snapshot when re-pointing `tenant_id`.** `PhoneTenantMap.industry_type` is a denormalized snapshot per the BUG-6 design (`whatsapp_identity.link_phone_to_tenant`); the dev script previously updated only `tenant_id`, leaving the snapshot stale and causing the AI to load the wrong RAG vertical (e.g. `field_service` knowledge for a printing tenant). Now reads the target tenant's `industry_type` and updates both columns in the same transaction. (`backend/remap_phone.py`)

### Added
- `tests/test_ai_service_tool_use_failed.py` — 10 unit tests covering both helpers, the retry path, the empty-content fallback, and that non-`tool_use_failed` `BadRequestError`s still bubble up.

### Migration
- None (head stays at `028`).

### Tests
- `pytest -m "not integration"`: **559 passed** (up from 549), 3 skipped, 12 deselected.

### Notes
- Bug 2 blast radius is dev-only — no production path remaps `tenant_id` on `PhoneTenantMap` (verified via grep across `app/` and `scripts/`). Any future "transfer phone between tenants" feature must also refresh `industry_type`; the BUG-6 snapshot rule is documented in the script comment.
- Layer B (parsing leaked XML markup back into a synthetic tool call) considered and deferred. Layer A + C close the user-visible symptom; Layer B would only recover the actual data and adds parsing risk that doesn't pay off until the catch is observed firing in production.

---

## [v6.3.6] — 2026-04-29
**Commit:** `38a0bea`
**Branch:** v5-whatsapp

> **Status: stub.** No information available from the SRS or the rest of
> the CHANGELOG. v6.3.6 is tagged on the same day as v6.3.5 (2026-04-29);
> SRS §6.28.4 mentions a "WhatsApp Briefings sub-page on Settings" as
> "planned for v6.3.6" — that's the most likely scope, but unverified.

### Added
- ?

### Changed
- ?

### Fixed
- ?

### Migration
- ? (head: ?)

### Acceptance
- ? of SRS Section ? acceptance criteria passing

### Notes
- Fill in from:
  - `git log v6.3.5..v6.3.6 --pretty=fuller`
  - `git show v6.3.6`
  - `alembic history` — confirm head did not advance past 028
- Most likely scope per SRS §6.28.4 "Out of scope (deferred)": the
  WhatsApp Briefings sub-page on Settings, shown as a disabled stub in
  v6.3.5 with copy "Coming in v6.3.6."

---

## [v6.3.5] — 2026-04-29
**Commit:** `3d4e1c1`
**Branch:** v5-whatsapp
**Spec:** SRS Section 6.28.4 (UI Consolidation)

### Added
- `InviteMemberModal` component (single entry point for both WhatsApp and desktop invites)
- `/welcome` minimal post-signup landing page for whatsapp_first proprietors
- `whatsapp_status` field on `TeamMemberOut` schema
- `WHATSAPP_BOT_NUMBER` config setting in `app/config.py`
- `member.invited_whatsapp` event type written to events table on welcome dispatch

### Changed
- Team and Roles page redesigned as phone-shaped table (Person / Phone / WhatsApp / Role / Actions)
- `TeamMemberOut.email` becomes `Optional[str]`; synthesised `invite-XXX@invite.zetaops.com` and `*@whatsapp.local` placeholders no longer leak into API responses
- `RegisterPage.tsx` routes whatsapp_first signups to `/welcome` instead of `/connect-whatsapp`

### Removed
- Standalone `/whatsapp` page (`LinkWhatsApp.tsx`) and sidebar nav item
- `/connect-whatsapp` transitional placeholder (`ConnectWhatsApp.tsx`)
- Frontend API wrappers used only by the deleted pages

### Migration
- No new schema in v6.3.5 itself. Documents migration 028 (events audit table from v6.3.3) in SRS Section 9.2.

### Acceptance
- 12/12 of SRS Section 6.28.4 acceptance criteria passing (verify and update)
- ACs closed in this release: 6.28.4-AC1 through 6.28.4-AC12

### Notes
- Documentation-only release per SRS — UI surface for the v6.4 entry-gate strategy.
- Migration head remains at 028 (migration 028 introduced in v6.3.3).
- Verify against `git show v6.3.5` and update any items above marked uncertain.

---

## [v6.3.4] — 2026-04-?? (2 days ago)
**Commit:** `f2ae190`
**Branch:** v5-whatsapp
**Spec:** SRS Section 6.28 Feature 3 (Daily Push Briefings) — _spec linkage unverified_

> **Status: stub.** SRS §1.2 lists v6.4 as "NEXT TO BUILD" and not shipped,
> while this CHANGELOG and the v6.3.5 entry both reference v6.3.4 as the
> dispatcher landing point. The two docs disagree. Source of truth is the
> commit. Resolve with the commands in **Notes** below before treating any
> bullet here as fact.

### Added
- _Likely_ briefing dispatcher per SRS §6.28 Feature 3: APScheduler job on a 5-minute tick, per-tenant scheduled time check, content generation reusing v5.10 trigger-endpoint logic, recipient fan-out to top-tier users with active `PhoneTenantMap`, idle template when no jobs, manual-trigger path on WhatsApp keywords ("morning briefing", "today's plan", "evening briefing", "today's summary"), `events` rows for `briefing.sent` / `briefing.send_failed` / `briefing.manual_trigger`, tenant-hash stagger to spread send load across the briefing window. **Verify each before crossing off.**

### Migration
- ? — 027 (entry-gate columns on `tenants` and `users`, role enum extensions) is a candidate but unverified. The migration table in SRS §9.2 lists 027 as required for v6.4; whether v6.3.4 is the tag that actually applies it is what `alembic history` will tell.

### Acceptance
- ? of SRS Section 6.28's 13 acceptance criteria passing
- Likely candidates closed: 6.28-AC7 (dispatcher fires on working days), 6.28-AC8 (per-user time override), 6.28-AC9 (manual trigger via WhatsApp). **None confirmed.**

### Notes
- Fill in from:
  - `git log v6.3.3..v6.3.4 --pretty=fuller` — full commit list with messages
  - `git show v6.3.4` — diff at the tag
  - `alembic history` — confirm whether 027 lands here
  - `pytest tests/ -k briefing -v` — confirm dispatcher tests exist and pass
- Reconcile with SRS §1.2 ("Current State") in the same commit that closes this stub.

---

## [v6.3.3] — 2026-04-?? (2 days ago)
**Commit:** `280e3aa`
**Branch:** v5-whatsapp
**Spec:** SRS Section 9.2 (migration 028)

### Added
- Events audit table (migration 028) — backs role-change audit trail from `app/routers/team_management.py` and consumed by `briefing.*` events from v6.3.4 dispatcher and `member.invited_whatsapp` events from v6.3.5 invite flow
  - Columns: `id`, `tenant_id` (FK CASCADE), `event_type` (VARCHAR 50, dotted vocabulary like `user.role_changed`, `briefing.sent`), `entity_type` (VARCHAR 50, discriminator), `entity_id` (INTEGER nullable, no FK because events span entity types), `actor_user_id` (FK SET NULL, NULL for system events), `source` (VARCHAR 20, permissive String not DB enum), `payload` (JSONB nullable, JSON for SQLite test DB), `created_at` (TIMESTAMPTZ NOT NULL)
  - Indexes: `idx_events_tenant_id`, `idx_events_tenant_event_type` (composite), `idx_events_entity` (composite entity_type + entity_id)
  - Invariants: append-only (no `updated_at`; corrections are new rows referencing the prior); tenant isolation enforced at FK CASCADE level, application layer must additionally filter by `tenant_id`
- ? — additional v6.3.3 commits beyond the migration are not yet documented here. The CHANGELOG entry exists, but only the migration is verified from SRS §9.2. Run `git show v6.3.3` and `git log v6.3.2.4..v6.3.3` to enumerate the rest.

### Migration
- 028 — events audit table

### Notes
- Migration head advances from 027 to 028.
- Next migration must use revision ID 029 and chain `down_revision = "028"`.

---

## v6.3.2 hotfix chain — [v6.3.2.4] / [v6.3.2.3] / [v6.3.2.2] / [v6.3.2.1] — 2026-04-??

> **Status: stub for the entire chain.** Four hotfix tags shipped against
> the same parent v6.3.2 issue. Without `git show` for each tag the
> contents and the parent issue are both unknown. Resolve the chain in
> one pass — they likely share a theme (a single bug found and reopened
> three times, or a series of follow-on regressions from one fix).

### Tags in order

| Tag         | Commit     | Date           |
|-------------|------------|----------------|
| v6.3.2.1    | `5a0d287`  | 2026-04-?? (3 days ago) — first in chain |
| v6.3.2.2    | `a70332a`  | 2026-04-?? (3 days ago) |
| v6.3.2.3    | `6b37284`  | 2026-04-?? (2 days ago) |
| v6.3.2.4    | `605752a`  | 2026-04-?? (2 days ago) — last in chain |

### Fixed
- ? (each tag is a hotfix in the v6.3.2 series; SRS rolls these into the parent v6.3.2 entry per §1.1)

### Notes
- One git pass closes all four:
  ```
  git log v6.3.1..v6.3.2.4 --pretty=fuller
  git show v6.3.2.1 v6.3.2.2 v6.3.2.3 v6.3.2.4
  ```
- Identify the parent v6.3.2 issue this series fixes — the first hotfix's
  commit message usually names it.
- Branch for all four: `v5-whatsapp`.

---

## [v6.3.1] — 2026-04-?? (3 days ago)
**Commit:** `8ecb34d`
**Branch:** v5-whatsapp

> **Status: stub.** First v6.3.x release after the v6.3.0-whatsapp-industry
> baseline. Likely the start of WhatsApp Entry Gate (SRS §6.28)
> implementation, but the SRS lists v6.4 as "NEXT TO BUILD" so the
> partition between v6.3.x prep work and actual v6.4 feature work is
> ambiguous from docs alone.

### Added
- ?

### Migration
- ? — 027 candidate if entry-gate columns started rolling out here. Verify with `alembic history`.

### Notes
- Fill in from:
  - `git log v6.3.0-whatsapp-industry..v6.3.1 --pretty=fuller`
  - `git show v6.3.1`
  - `alembic history` — confirm whether 027 (or any new migration) lands here
- The migration head pointer at this tag is what disambiguates v6.3.1 from later v6.3.x tags.

---

## [v6.3.0-whatsapp-industry] — 2026-04-22
**Branch:** v5-whatsapp

### Fixed
- BUG-6: `link_phone()` in `routers/whatsapp.py` was reading `industry_type` from User ORM (no such column) and falling through to hardcoded `"printing"` default. Result: every `PhoneTenantMap` row stored `"printing"` regardless of actual tenant industry, silently degrading SRS sections 6.13, 6.20, 6.21. Fix reads `industry_type` from Tenant ORM.

### Added
- `scripts/backfill_phone_industry_type.py` — idempotent backfill for existing rows
- Two regression tests in `tests/test_link_phone_industry.py`

### Migration
- No schema change. Migration head remained at 023.

### Tests
- 332 passing (baseline 330 + 2 new regression tests)

### Notes
- Foundation release for v6.4. The v6.4 entry-gate work pre-creates `PhoneTenantMap` rows at signup using the same correct industry-attribution logic fixed here.

---

## [v6.2.2-test-recovery] — 2026-04-20
**Branch:** v5-whatsapp

### Fixed
- 3 test clusters: WhatsApp pipeline, CSV import, scheduler
- SQLite StaticPool fix in `conftest.py` (was causing `test_skills.py` errors due to cross-connection state)

### Tests
- 199 passing, 0 failed, 0 errors

### Notes
- Permanent recovery point. Non-production change — no migration, no feature.

---

## [v6.2] — 2026-04-13

### Added
- `IndustryContext.tsx`: reads `industry_type` from `AuthContext` at login
- `useLabels()` hook for dynamic UI labels
- Sidebar and page titles now industry-dynamic

### Fixed
- 39 TypeScript errors resolved across 5 frontend files
- RegisterPage auth bug: `localStorage.setItem('access_token')` was bypassing `AuthContext.register()`. Fixed to call `register()` from context.

### Notes
- Printing tenant now sees "Print Jobs", "Press Operators", "Presses".
- TypeScript strict mode clean baseline.

---

## [v6.0 + v6.1-rag-pipeline] — 2026-04-10
**Commit:** `f3516436c844c374246cea3cb8ec648e1354212b`
**Tag:** `v6.1-rag-pipeline` (single tag covering both v6.0 and v6.1 scope)
**Branch:** v5-whatsapp
**Spec:** SRS Section 17.2 (schema context), §6.22 (RAG pipeline)

### Note on combined release
The commit message reads `feat: v6.0 schema context + v6.1 RAG pipeline —
industry-aware AI`. Two version numbers, one tag, one commit. v6.0 covers
the schema context layer; v6.1 covers the RAG pipeline. They were finished
and tagged together. The SRS describes them in separate sections (§17.2
and §6.22 respectively); this CHANGELOG entry covers the single release.
(Verified 2026-05-08: only `v6.1-rag-pipeline` exists as a tag — no
standalone `v6.0` tag was ever pushed. Findings #8 in
`SRS_RECONCILIATION_FINDINGS.md`.)

### Added (v6.0 — Schema Context layer)
- `app/knowledge_graph/schema_context.py` — complete DB schema described
  for AI consumption (entities, FK relationships with exact column names,
  common multi-hop query patterns).
- `app/knowledge_graph/context_builder.py` — assembles tenant context
  before every AI query.
- `tenant_id` mandate enforced in all AI-generated queries.

### Added (v6.1 — RAG pipeline)
- RAG pipeline with industry templates: `rag_data/_templates/{industry}/`
  for printing, manufacturing, fabrication, field_service. Chemical
  excluded — Plan B only.
- `seed_rag_from_template(tenant_id, industry_type)` called by `auth.py`
  register endpoint.
- `_build_system_prompt()` injects tenant RAG context before every AI
  query.

### Migration
- None. Migration head unchanged.

### Notes
- Flat-file MVP. pgvector migration deferred to v6.8 (renumbered from
  earlier roadmap slots v6.3 then v6.7).
- Foundation for all intelligent features in v6.x.

---

## [v5.16] — 2026-04-09

### Added
- Day 1 Simple Table — first screen new tenant sees after registration
- Onboarding question: "Do you have employee/job data in SAP, Tally, or Excel?"

### Migration
- 023 — `source` field on Employee + Machine (`manual` | `whatsapp` | `erp_sync`); `worker_type` field on Employee (`permanent` | `contractor`)

### Notes
- The `source` field is the structural decision that keeps v7.0 ERP a sprint, not a rewrite. Never remove.

---

## [v5.15] — 2026-04-10

### Added
- Manager Check-in Flow (7:00am): APScheduler triggers WhatsApp prompt; manager replies parsed against v5.16 seed table; absent worker → skill lookup → substitute suggestion
- Owner Briefing (7:15am): single clean briefing generated FROM manager inputs (not scheduled data alone)

### Notes
- WhatsApp loop is real in mock mode. Ready for v5.11 go-live.

---

## [v5.10-proactive-alerts / v5.12-role-language] — 2026-04-07
**Commit:** `ccdc7b953ca88e4ec8d7581c82cb9b73bec4320c`
**Branch:** v4-dev → merged into v5-whatsapp
**Spec:** SRS Section 6.13 (proactive alerts), §6.17 (role limiting), §6.18 (3-language)

### Note on dual tagging
Two tags were placed on a single commit because two feature streams
finished together at merge. v5.10 covers proactive alerts; v5.12 covers
role limiting and 3-language support. The features are described in
separate SRS sections, but they shipped together as one release —
they are not independently revertable. (Verified 2026-05-08: both
`v5.10-proactive-alerts` and `v5.12-role-language` resolve to the same
commit SHA. Findings #7 in `SRS_RECONCILIATION_FINDINGS.md`.)

### Added
- (v5.10) Proactive alerts dispatched via the WhatsApp trigger endpoint:
  morning briefing, conflict alert, job-ending-soon. Gated by the
  `whatsapp_copilot` feature flag.
- (v5.12) Phone-role enforcement (`owner` / `manager` / `viewer`)
  inside `detect_write_intent()` — blocked actions never reach the
  AI layer.
- (v5.12) `detect_language()` in `whatsapp_responses.py`: Hindi
  (Devanagari), Hinglish (marker words: aaj, kaam, nahi, theek),
  English (default).
- (v5.12) `LANGUAGE_INSTRUCTION` injected into `_build_system_prompt()`
  per detected language.

### Fixed
- `whatsapp_alerts.py` v2.0: fix `_get_conflicts`, add full file docs
  (verbatim commit message subject).

### Migration
- None. Migration head unchanged.

### Notes
- Manager and owner have structurally different WhatsApp experiences from this point on.

---

## Earlier versions

For releases before v5.12, see:
- SRS Section 7 (Bug Fixes & Issues Resolved) for fix history
- `VERSIONS.md` for cross-branch v4-dev ↔ v5-whatsapp mapping
- Git tag history: `git log --tags --simplify-by-decoration --pretty="format:%h %d %s"`

---

## How to update this file

When you tag a release:

1. Move the `[Unreleased]` content into a new `[vX.Y.Z]` section above
2. Add the commit hash, date, and branch
3. Reference SRS section numbers for spec linkage
4. Note acceptance criteria pass count if the release closed any
5. Update the matching row in `DELIVERY_LEDGER.md` in the same commit
6. Reset `[Unreleased]` to empty `Added` / `Changed` / `Fixed` / `Migration` headers

The CHANGELOG describes the *change*. The DELIVERY_LEDGER describes the
*state*. Both must be updated when a release lands. They are not redundant —
one tells the story, the other tells the truth right now.
