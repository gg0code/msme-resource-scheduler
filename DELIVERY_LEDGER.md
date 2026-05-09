# ZetaOps Copilot — Delivery Ledger

**Purpose.** This file is the source of truth for *what is actually built* — as
distinct from the SRS, which describes *what the product should be*. When the
two disagree, this file wins for "is it shipped"; the SRS wins for "what is the
spec." Both must be reconciled in any release that closes the gap.

**Update rule.** Any commit that changes the status of a feature updates the
matching row in the same commit. Treat this like a file-header version number —
not optional, not deferred to a cleanup pass.

**Last updated:** 2026-05-09 — v6.3.19 slice 2A part 1 landed: migration `033_add_push_columns_to_tenants` adds three nullable columns to `tenants` (`morning_sections JSONB`, `evening_sections JSONB`, `push_paused_until DATE`). Tenant ORM in `app/models/auth.py` and `app/knowledge_graph/schema_context.py` updated in the same commit. Migrations 027 columns (`briefing_morning_time`, `briefing_evening_time`, `briefing_timezone`, `briefing_morning_enabled`, `briefing_evening_enabled`) are deliberately reused — see CHANGELOG `[Unreleased]` "Naming bridge in resolve_push_config" for the slice 2A scope decision and the deferred `slice 2A-rename` follow-up. Migration head advances 032 → 033; xfail count unchanged at 5; alembic chain verified single-head.

**Last updated:** 2026-05-09 — v6.3.19 morning-briefing flag/next_step selector landed as a lookup-table-only slice. New row added below for "Morning-briefing flag/next_step rendering" — status `in progress`. `backend/app/services/consolidated_briefing.py` ships `select_flag_and_next_step` (pure function over a pre-sorted `SignalResult` list) plus `_BLOCKER_CLASS_SIGNALS` (8 ids) and `_NEXT_STEP_TEMPLATES` (16 strings: hi_en + en for each id). 7 unit tests in `tests/services/test_consolidated_briefing.py` (11 cases incl. parametrised invalid-locale cases) — all green; xfail count unchanged at 5; migration head unchanged at 032. The dispatcher rewrite, cascade resolver, migrations 033/034, template registry wiring, and Meta v2 hybrid-template handoff are deferred to follow-up prompts in the v6.3.19 release window.

**Last updated:** 2026-05-08 — v6.3.18 WhatsApp message styling pass shipped: centralised emoji vocabulary (`message_emoji.py`), entity formatters + 5 Meta-bound template constants (`message_formatters.py`), Meta HSM template registry (`whatsapp_meta_templates.py` + `.json`, 35 entries from `meta/templates_v2.json` plus new Hindi `zetaops_job_conflict_alert` draft), dispatcher-shape templates (`message_templates.py`) wired into `whatsapp_alerts.py` (`_build_morning_briefing`, `_build_delay_alert`, `_build_conflict_alert`, `send_machine_down_alert`) and the WhatsApp AI reply path (`routers/whatsapp.py:1089` via `render_ai_reply()`). New SRS Section 23 (Voice, Tone, and Formatting Standards), AC IDs 23-AC1–AC8 all verified by 75 new passing tests (51 in `test_message_formatters.py` + `test_message_templates.py`, 24 in `tests/services/test_message_dispatcher_templates.py`). Migration head stays 032; no schema. Old `whatsapp_formatter.py` reduced to a backwards-compat re-export shim. Meta-bound `_EN`/`_HI` constants stay as infrastructure for v6.4 when the morning briefing data shape catches up — see CHANGELOG `[v6.3.18]` "Deferred" subsection for details.

**Last updated:** 2026-05-08 — version-number gap policy documented; v5.11 / v5.13 / v5.14 retired from "blocked" list (work shipped under v6.3.7+v6.3.8, v5.2-voice-notes, v6.3.5 respectively).

**Last updated:** 2026-05-07 — v6.3.16 Day-7 First-Insight Gate and v6.3.17 WhatsApp owner-bypass entity writes shipped and tagged on dev. Both verified end-to-end against real Postgres tenant 12 in mock-mode. CHANGELOG entries written in the same pass that updated this ledger.

Prior update (2026-05-06 → 2026-05-07): v6.3.15 (revised) Owner-Confirmed Candidate Promotion landed (silent insertion retracted; nightly job now batches qualifying candidates per tenant and sends a single WhatsApp confirmation requesting explicit HAAN/NAHI; only on HAAN does insertion happen; reply-parser is hybrid heuristic+LLM; migration `030` added the four `confirmation_*` columns to `extraction_candidates`).

Prior update (2026-05-05): v6.3.13 + v6.3.14 CHANGELOG entries backfilled (the prerequisite versions for the v6.3.15 Candidate Promotion Job that shipped earlier the same day).

**Current migration head:** `033` (per `alembic heads`). Chain through the v6.3.x
window: `028` events audit table (v6.3.3); `029` `extraction_candidates`
staging table (v6.3.13); `030` `confirmation_*` columns on
`extraction_candidates` (v6.3.15 revised); `031` `first_briefing_sent_at`
+ `engagement_ladder_state` columns on `tenants` (v6.3.16); `032` `source`
column on `skills` (v6.3.17); `033` `morning_sections` + `evening_sections`
+ `push_paused_until` columns on `tenants` (v6.3.19 slice 2A). Next
migration must use revision ID `034` and chain `down\_revision = "033"`.

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
|Morning-briefing flag/next_step rendering|6.28|v6.3.19 (planned)|in progress|—|(no flag — code-only; pattern signals still gated by `PATTERN_BRIEFING_TENANT_IDS`)|033 (slice 2A pt 1)|0/n|`resolve_push_config()` cascade + `push_defaults.yaml` (slice 2A pt 2); field computers (`_compute_jobs_starting`/`_compute_continuing`/`_compute_crew_expected` — slice 2B); consolidated dispatcher (`dispatch_morning`/`dispatch_evening` — slice 2C); APScheduler tick refactor (slice 2D); Meta v2 conditional template re-submission for `{flag_section}`/`{next_step_section}`; hybrid registry switch from placeholder to v2-shape; integration tests + snapshots; AC IDs (assigned when full release lands)|
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

