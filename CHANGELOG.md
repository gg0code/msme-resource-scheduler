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

---

## [Unreleased]

### Added
- (work in progress goes here)

### Changed
- 

### Fixed
- 

### Migration
- 

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

## [v6.1] — 2026-04-10

### Added
- RAG pipeline with industry templates: `rag_data/_templates/{industry}/` for printing, manufacturing, fabrication, field_service (chemical excluded — Plan B only)
- `seed_rag_from_template(tenant_id, industry_type)` called by auth.py register endpoint
- `_build_system_prompt()` injects tenant RAG context before every AI query

### Notes
- Flat-file MVP. pgvector migration deferred to v6.8 (renumbered from v6.3, v6.7).

---

## [v6.0] — 2026-04-10

### Added
- `app/knowledge_graph/schema_context.py`: complete DB schema described for AI consumption
- `app/knowledge_graph/context_builder.py`: assembles tenant context before every AI query
- `tenant_id` mandate enforced in all AI-generated queries

### Notes
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

## [v5.12] — 2026-04-08

### Added
- `phone_role` enforcement: owner / manager / operator
- 3-language support: Hindi (Devanagari) / Hinglish (marker words) / English (default)
- `detect_language()` in `whatsapp_responses.py`
- `LANGUAGE_INSTRUCTION` in `_build_system_prompt()`
- Role check in `detect_write_intent()` BEFORE AI is called — blocked actions never reach AI layer

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
