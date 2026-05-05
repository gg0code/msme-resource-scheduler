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
