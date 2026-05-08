# SRS Reconciliation Findings — 2026-05-07

Cross-checking `ZetaOps_SRS_v6_6.docx` ↔ `CHANGELOG.md` ↔ `DELIVERY_LEDGER.md` ↔ `CLAUDE.md` against the actual git tag history on `origin/v5-whatsapp` (HEAD `e74d264`, 77 tagged commits total).

This document is the working artifact — what's wrong, why, and what to do about it. Apply fixes section by section; each finding is independent.

---

## Findings overview

| # | Severity | Where | What's wrong |
|---|---|---|---|
| 1 | **High** | SRS Section 1.2 | Listed releases don't match git tag descriptions; multiple shipped tags missing entirely |
| 2 | **High** | SRS Section 9.2 + Section 22 | Migration head conflicts inside the document itself (says 028 in §9.2 NOTE, 023 in §22 verification gates, 032 in v6.6 banner) |
| 3 | **High** | SRS document footer | Reads `SRS v6.5 \| Updated through v6.3.4 in progress \| April 29, 2026` — stale by two doc versions |
| 4 | **Medium** | CHANGELOG.md | Six entries (v6.3.6 down through v6.3.2.1) have unfilled `?` placeholders |
| 5 | **Medium** | DELIVERY_LEDGER.md | Header says "Current migration head: 028"; CLAUDE.md and v6.6 SRS banner say 032 |
| 6 | **Medium** | DELIVERY_LEDGER.md | Five rows have `?` in Status, Shipped, and Acceptance columns |
| 7 | **Medium** | CHANGELOG.md + SRS | v5.10 and v5.12 listed as separate releases but in git they point to the **same commit** |
| 8 | **Medium** | CHANGELOG.md + SRS | v6.0 and v6.1 listed as separate releases but git has a single combined tag `v6.1-rag-pipeline` |
| 9 | **Low** | SRS Section 1.2 (old) | "as of April 28, 2026" — stale relative to v6.6 banner date 2026-05-07 |
| 10 | **Low** | SRS glossary | Glossary definitions for v6.4 features still claim "shipped in v6.4" but pieces have actually shipped across v6.3.1–v6.3.4 |
| 11 | **Info** | All docs | v5.11 / v5.13 / v5.14 marked BLOCKED on Meta review, but v6.3.8 (May 3) **already removed Interakt and switched to Meta Cloud API direct** — so the architectural blocker is gone, only the portfolio approval remains |
| 12 | **Info** | All docs | The v6.2.x mid-series tags (`v6.2.3-test-audit` through `v6.2.9-me-industry`, eight tags) are **invisible** in the docs |
| 13 | **Critical** | SRS Section 9.2 | Migration files `024`, `025`, `026` are listed in detail in §9.2 but **DO NOT EXIST** on disk. Chain jumps from 023 → 027 with three holes. |

Detailed findings below.

---

## Finding 1 — SRS Section 1.2 doesn't match git

**Already fixed** in the latest pass on `ZetaOps_SRS_v6_6.md`. The new Section 1.2 lists every tag (43 total in scope) with its actual commit-message description. Notable corrections vs. the previous version of the doc:

| Earlier doc claim | Git ground truth |
|---|---|
| "v6.2 — Industry-Aware Dynamic UI Labels + RegisterPage auth bug fix" | `v6.2-ts-clean`: "fix: resolve 39 TypeScript errors across 5 frontend files." Dynamic-labels work isn't this tag. |
| "v6.3.6 — (see CHANGELOG)" | `v6.3.6`: "dead-code sweep + 3 React 19 lint errors fixed" |
| "v6.3.7 .. v6.3.10 — v6.4 entry-gate columns (027), role rename, inbound intent routing" | Wrong on all four. v6.3.7 = Meta Cloud API direct send. v6.3.8 = Interakt removal + E.164 normalization. v6.3.9 = Groq retry. v6.3.10 = Bootstrap UI trim + tenant_id join-table fix. The entry-gate columns landed at **v6.3.1 / v6.3.2 / v6.3.3 / v6.3.4**, not v6.3.7+. |
| Implies v5.10 and v5.12 are separate releases | Both tags point to commit `4d35d0c` (one commit, two tags). |
| Implies v6.0 and v6.1 are separate releases | Single tag `v6.1-rag-pipeline` covers both. |

---

## Finding 2 — SRS migration-head value contradicts itself

The SRS document v6.6 says different things in different sections:

- **Section 1.2 banner (v6.6 cover note):** "Migration head 032."
- **Section 9.2 NOTE callout:** "Always use 'alembic upgrade head' — not raw SQL files. The migration chain is managed by Alembic. **Current head: 028.**"
- **Section 22 verification gates:** "alembic heads -- exactly one head (**023**)."

Three different values inside one document. The v6.6 banner is right (032 — confirmed by `CLAUDE.md` and migration-table progression in §9.2's body, which lists 027, 028, then stops). Sections 9.2 NOTE and 22 are stale.

**Fix.** In SRS:
- §9.2 NOTE: change `Current head: 028` → `Current head: 032`.
- §22: change `alembic heads -- exactly one head (023)` → `alembic heads -- exactly one head (032)`.
- §9.2 migrations table: extend to include **029** (`extraction_candidates` staging table, v6.3.13), **030** (`confirmation_*` columns on `extraction_candidates`, v6.3.15 revised), **031** (`first_briefing_sent_at` + `engagement_ladder_state` on tenants, v6.3.16), **032** (`source` column on `skills`, v6.3.17). The v6.6 cover banner already lists these in narrative form; they need rows in the table.

---

## Finding 3 — SRS document footer is stale

Last line of the doc reads:

> ZetaOps Copilot | SRS v6.5 | Updated through v6.3.4 in progress; v6.3.5 UI consolidation scope formalised | April 29, 2026 | End of Document

But the version table at the top now goes through v6.6 (May 7, 2026). The footer wasn't updated when v6.6 was added.

**Fix.** Replace footer line with:

> ZetaOps Copilot | SRS v6.6 | Updated through v6.3.17 (HEAD) | 2026-05-07 | End of Document

Also remove the duplicate stray footer two lines below it:

> ZetaOps Copilot | SRS v3.0 | Updated through v4.0.9 | March 2026

(This is leftover from the original 2026-03 export that was never cleaned up across versions.)

---

## Finding 4 — CHANGELOG has unfilled `?` placeholders

`CHANGELOG.md` has explicit `?` placeholders for these entries (text from the file):

- `[v6.3.6]` Added: `?`, Changed: `?`, Fixed: `?`, Migration: `?`, Acceptance: `?`
- `[v6.3.4]` Added: `?`, Migration: `?`, Acceptance: `?`
- `[v6.3.3]` includes `? (role matrix changes referenced by SRS Section 6.28.4 may also be here)`
- `[v6.3.2.4]` Fixed: `?`
- `[v6.3.2.3]` Fixed: `?`
- `[v6.3.2.2]` Fixed: `?`
- `[v6.3.2.1]` Fixed: `?`
- `[v6.3.1]` Added: `?`, Migration: `?`

**Fix — fill in from git commit messages:**

| Tag | Real git commit message |
|---|---|
| v6.3.1 | `WhatsApp entry gate foundation — schema + lookup helpers` |
| v6.3.2.1 | `split contexts into Provider + hook files for Vite Fast Refresh` |
| v6.3.2.2 | `quick set-state + exhaustive-deps fixes (5 lint problems eliminated)` |
| v6.3.2.3 | `backend + frontend hygiene cleanup` |
| v6.3.2.4 | `fix AI prompt format-string crash ('"mode"' KeyError)` |
| v6.3.3 | `top-tier role group + permission gating` |
| v6.3.4 | `daily push briefings dispatcher (cron + manual trigger)` — migration head goes 027→028 here per §9.2 |
| v6.3.6 | `dead-code sweep + 3 React 19 lint errors fixed` |

The CHANGELOG also has stale "[Unreleased]" content because v6.3.7 through v6.3.17 (eleven tags) were never moved out of Unreleased into proper sections. Entries needed:

- v6.3.7 (May 3) — Meta Cloud API direct send + Phase 1 alerts refactor
- v6.3.8 (May 3) — Phase 2 Interakt removal + E.164 inbound normalization
- v6.3.9 (May 3) — Groq tool_use_failed retry + dev-script industry snapshot fix
- v6.3.10 (May 4) — Bootstrap UI trim + tenant_id join-table fix
- v6.3.11 (May 4) — pattern-aware briefing intelligence (signal evaluator framework)
- v6.3.12 (May 5) — Day-1 onboarding sequence
- v6.3.13 (May 5) — extraction_candidates staging table (migration 029)
- v6.3.14 (May 5) — entity extractor service
- v6.3.15 (May 6, revised) — owner-confirmed candidate promotion (migration 030)
- v6.3.16 (May 6) — Day-7 First-Insight Gate (migration 031)
- v6.3.17 (May 7) — WhatsApp owner-bypass entity writes (migration 032)

---

## Finding 5 — DELIVERY_LEDGER migration-head header is stale

`DELIVERY_LEDGER.md` line 16:

> **Current migration head:** `028` (per `alembic heads`). Aligned with SRS v6.5 Section 9.2.

But `CLAUDE.md` says 032 and the SRS v6.6 banner says 032. The ledger header was last updated when v6.3.5 doc landed and not advanced since.

**Fix.** Update ledger header:

> **Current migration head:** `032` (per `alembic heads`). Aligned with SRS v6.6 Section 9.2. Migration `032` adds the `source` column on `skills` (v6.3.17 — WhatsApp owner-bypass entity writes). Next migration must use revision ID `033` and chain `down_revision = "032"`.

Also: `Last updated:` line still reads `YYYY-MM-DD — fill in on every edit.` Replace with `2026-05-07`.

---

## Finding 6 — DELIVERY_LEDGER has `?` rows

The V6 era table has these rows with `?` in Status / Shipped / Acceptance:

- KPI Baseline + Monthly Savings (v6.3 — Section 6.24)
- Top-Tier Role Group (v6.4 — Section 6.28-F2)
- Entry Mode Configuration (v6.4 — Section 6.28-F1)
- Daily Push Briefings (v6.4 — Section 6.28-F3)
- UI Consolidation (v6.3.5 — Section 6.28.4)
- Events audit table (v6.3.3 — Section 9.2)

**Fix — set these from git:**

| Feature | Status | Shipped in | Migration |
|---|---|---|---|
| KPI Baseline + Monthly Savings | `not started` | — | none yet (planned 024) |
| Top-Tier Role Group | `shipped` | v6.3.3 | 027 |
| Entry Mode Configuration | `shipped` | v6.3.2 | 027 |
| Daily Push Briefings | `shipped` | v6.3.4 | (no schema in 028 for this; 028 is the events audit table that backs it) |
| UI Consolidation | `shipped` | v6.3.5 | 028 |
| Events audit table | `shipped` | v6.3.3 | 028 |

Acceptance pass-counts still need to come from running the test suite — no shortcut for that.

---

## Finding 7 — v5.10 and v5.12 are the same commit

In git:

```
2026-04-07 16:34:33 +0530  (tag: v5.12-role-language, tag: v5.10-proactive-alerts, ...) fix: whatsapp_alerts.py v2.0 - fix _get_conflicts, add full file docs
```

Both tags point to the same commit `2898f5e`. This is unusual — implies that during v5.10/v5.12 development, the work was branched off `v4-dev`, both features were finished, both tags were pushed at the same merge point.

**What this means for docs.** The SRS treats v5.10 (proactive alerts) and v5.12 (role limiting + 3-language) as two separate spec sections (§6.13 vs §6.17 + §6.18). That's fine — the *spec* can describe them separately. But the CHANGELOG and ledger should be honest that they shipped in one tagged commit, not two.

**Fix.** In CHANGELOG, merge the two entries into one with both version numbers. In ledger, keep both rows (they describe different feature boundaries) but make sure both list `Shipped in: v5.10/v5.12 (same commit)` and don't pretend they're independently revertable.

---

## Finding 8 — v6.0 and v6.1 are also one tag

```
2026-04-10 11:40:26 +0530  (tag: v6.1-rag-pipeline) feat: v6.0 schema context + v6.1 RAG pipeline — industry-aware AI
```

Same pattern as Finding 7 — the commit message itself acknowledges combining both versions. CHANGELOG currently has separate `[v6.1]` and `[v6.0]` entries.

**Fix.** Merge into a single `[v6.0 + v6.1-rag-pipeline]` entry.

---

## Finding 9 — Stale "as of" dates (cosmetic)

- SRS old §1.2: "as of April 28, 2026" → already fixed in latest pass to "2026-05-07"
- DELIVERY_LEDGER header: `Last updated: YYYY-MM-DD — fill in on every edit.` → set to `2026-05-07`
- CLAUDE.md "Current state in one paragraph": `(as of 2026-05-06)` → bump to `2026-05-07` (latest commit `e74d264` is a docs commit on 2026-05-07)

---

## Finding 10 — Glossary entries promise v6.4 ship; pieces have already shipped

The SRS Glossary (§20) defines `entry_mode`, `size_segment`, `Top-Tier Role Group`, `Factory Manager`, `Co-Owner`, `Daily Push Briefing`, `PhoneTenantMap pre-creation`, `created_via` — each annotated "Introduced v6.4."

But in git: `entry_mode` and `size_segment` columns shipped at **v6.3.2** (signup wiring); the role group shipped at **v6.3.3**; the daily push dispatcher shipped at **v6.3.4**. The v6.4 *tag* doesn't exist yet. The features are out under v6.3.x tags.

**Fix.** Either:
- (a) replace "Introduced v6.4" with the actual v6.3.x tag where each piece landed, or
- (b) keep "Introduced v6.4" as the *spec* version (matches Section 6.28) and add a note to each entry: *"Implementation shipped piecemeal across v6.3.1 – v6.3.4; v6.4 is the integration release (not yet tagged)."*

Option (b) is closer to how the docs already think (SRS = spec, ledger = shipped), and avoids changing eight glossary entries.

---

## Finding 11 — Meta blocker description is out of date (info)

SRS Section 1.2, DELIVERY_LEDGER, and CLAUDE.md all say:

> v5.11 WhatsApp Go-Live — blocked on Meta portfolio review.

But on May 3, **v6.3.7** shipped "Meta Cloud API direct send" and **v6.3.8** shipped "Phase 2 Interakt removal." The product no longer goes through Interakt for outbound at all — it talks to Meta directly. The architectural transition v5.11 was supposed to represent has effectively happened under different version numbers.

What's *actually* blocked is just the Meta Business portfolio approval (a process gate), not any code work. The docs read as if there's pending engineering, which there isn't.

**Fix.** Reword the v5.11 entries everywhere:

> v5.11 WhatsApp production cutover — pending Meta Business portfolio approval. Engineering complete: v6.3.7 / v6.3.8 (May 3) replaced Interakt with direct Meta Cloud API integration. The cutover from `WHATSAPP_MOCK_MODE=True` to production credentials is a config flip, not a code change.

---

## Finding 12 — Eight v6.2.x mid-series tags are invisible in docs (info)

These tags exist in git but appear nowhere in SRS, CHANGELOG, or LEDGER:

- v6.2.3-test-audit (Apr 22) — 105 new tests, BUG-1 + BUG-2 documented
- v6.2.4-bugfixes (Apr 22) — date-type tightening (BUG-2)
- v6.2.5-cleanup (Apr 22) — datetime.utcnow() → datetime.now(timezone.utc)
- v6.2.6-registration-seed (Apr 22) — demo seeding on registration (BUG-3)
- v6.2.7-industry-type (Apr 22) — industry_type on RegisterRequest (BUG-4)
- v6.2.8-audit-closed (Apr 22) — gitignore per-tenant rag_data
- v6.2.9-me-industry (Apr 22) — industry_type on /auth/me (BUG-5)

(v6.2.1 and v6.2.2 *are* in CHANGELOG. v6.2-ts-clean isn't — CHANGELOG has just `v6.2`.)

These are all genuinely small (audit tests, refactor, gitignore tweak, single-bug fixes), so it's defensible to roll them up rather than break out individually. But they should at least be acknowledged — the BUG-3, BUG-4, BUG-5 fixes are interesting because they form a coherent "registration flow audit" sequence that closed five bugs over a single afternoon (Apr 22).

**Fix.** Add a single CHANGELOG entry under `[v6.2 audit series]` covering the seven tags collectively. Or list each individually if you want bug-traceable history.

---

## Finding 13 — SRS §9.2 describes three migrations that don't exist on disk

**This is the most important finding in this report.** SRS Section 9.2 currently has rows for migrations 024, 025, and 026 with full schema descriptions:

> **024** | KPI Baseline -- creates tenant_kpi_snapshot table with daily operational metrics and is_baseline flag. Required for v6.3.
>
> **025** | Compliance tracking -- creates compliance_item, compliance_document, and compliance_reminder_log tables. Required for v6.6.
>
> **026** | E-invoicing support -- adds gstin (VARCHAR 15, nullable) to customers table. Required for v6.7.

The actual file listing of `backend/alembic/versions/` (29 migration files) shows the chain goes:

```
023_add_source_and_worker_type.py        (Apr 9)
027_whatsapp_entry_gate.py               (Apr 28)    ← jumps from 023 directly to 027
028_events_table.py                      (Apr 29)
029_add_extraction_candidates_table.py   (May 5)
030_add_confirmation_state_columns.py    (May 6)
031_add_day7_engagement_columns.py       (May 6)
032_add_source_to_skills.py              (May 7)
```

**There are no files numbered 024, 025, or 026.** The chain almost certainly chains `027.down_revision = "023"`, skipping the three numbers entirely. (Confirming this requires a one-line check inside `027_whatsapp_entry_gate.py`, but the file numbering already strongly implies it.)

**What's actually going on.** Sections 6.24 (KPI Baseline), 6.26 (Compliance Tracker), and 6.27 (GST E-Invoicing) are **not yet implemented**. They're planned features per Section 1.2. The ledger correctly lists them as `not started`. But Section 9.2 was written *as if those migrations existed*, claiming specific table names, columns, and types — content that should never have left the spec section into the migration-chain section. The migration chain section is supposed to describe what's on disk, not what's coming.

**Why this matters.**

1. **Anyone running `alembic upgrade head` against a fresh database will succeed**, because the chain doesn't reference the missing files. So this isn't a runtime bug. But it's a documentation lie, and it lies in the most load-bearing place in the SRS — the section that's supposed to be ground truth for the migration chain.
2. **When v6.3 (KPI Baseline) actually ships**, whoever writes that migration will see "024 already taken" in the SRS and will likely number the new migration 033 to avoid the collision. This is the wrong choice — the right choice is to number it 024 (gap-fill), since 027 doesn't reference 024 as its parent. But you'll get there only if Section 9.2 is honest about the gap. Right now it pretends 024 exists.
3. **The SRS migrations table is the single document we tell new contributors to trust** — per `CLAUDE.md`: *"Migration chain truth: Section 9.2 of this document. Current head: 032."* If §9.2 lies, the rule has to change.

**Fix — three options, in order of preference:**

(a) **Honest gap.** Replace rows 024/025/026 in §9.2 with a single explanatory row:

> **024 – 026** | *Reserved for future migrations.* No files on disk between 023 and 027. The v6.3 KPI Baseline (Section 6.24, planned) is expected to land at migration 024; v6.6 Compliance Tracker (Section 6.26) at 025; v6.7 GST E-Invoicing (Section 6.27) at 026. Until those features ship, the chain skips these numbers — `027.down_revision = "023"`.

This is what I'd recommend. It tells the truth about disk state and preserves the planned slot allocation as a roadmap, where it belongs.

(b) **Move the planning content to the relevant feature sections.** The 024/025/026 schema details are *spec content* (here's what we'll build), not *migration-chain content* (here's what's on disk). Move the table/column descriptions into Sections 6.24, 6.26, 6.27 where they belong. Leave §9.2 as a true list of what's actually deployed.

(c) **Squat the slot numbers.** Create empty placeholder migration files 024.py, 025.py, 026.py that do nothing, just to make the SRS retroactively true. This is the worst option — it pollutes the chain with no-op migrations and signals a sloppy attitude toward the migration ledger. Don't do this.

**Cross-check on 029-032.** Good news: the four migrations that v6.6 banner adds (029 extraction_candidates, 030 confirmation_*, 031 Day-7 engagement, 032 source on skills) all have matching files on disk with sensible names. So the only hole is the 024/025/026 gap.

**Also verify:** I'm reading `031_add_day7_engagement_columns.py` as covering both `first_briefing_sent_at` AND `engagement_ladder_state` on tenants per the v6.6 banner, but the file name only mentions Day-7 engagement. If the file actually adds only `engagement_ladder_state` and `first_briefing_sent_at` is in a different migration, the SRS narrative needs adjusting. Worth a one-line check inside that file.

---

## Suggested order of operations

1. **Apply Finding 13 to SRS** (migration-chain honesty — the load-bearing fix). Replace 024/025/026 rows in §9.2 with the gap-explanatory row, OR move the schema descriptions into §6.24/§6.26/§6.27. 15 minutes.
2. **Apply Findings 2 + 3 to SRS** (migration head consistency + footer). One commit. 5 minutes. *(Already done in the latest output.)*
3. **Apply Finding 1 to SRS** — Section 1.2 rewritten against git. *(Already done in the latest output.)*
4. **Apply Findings 4 + 7 + 8 to CHANGELOG** — fill in `?` entries from git messages, merge the two paired releases. 30 minutes.
5. **Apply Findings 5 + 6 to DELIVERY_LEDGER** — header migration head, six `?` rows from git. 15 minutes.
6. **Apply Finding 11 globally** — reword v5.11 description in all four files. 10 minutes.
7. **Apply Finding 10 to SRS Glossary** — option (b), one note added to each of eight entries. 10 minutes.
8. **Apply Finding 12 to CHANGELOG** — single roll-up entry for the v6.2.x audit series. 5 minutes.
9. **Apply Finding 9** — date stamps. 2 minutes.

Total: roughly 90 minutes of careful editing. None of it requires running tests or touching code.

---

## What this still doesn't tell us

Two open questions remain. The migration file listing closed one of them; what's left:

1. **Acceptance criterion pass counts** for the v6.3.x features. Need `pytest tests/ -m "not integration" -v` output to fill in the `Acceptance N/M` columns in the ledger.
2. **Whether `031_add_day7_engagement_columns.py` actually adds both `first_briefing_sent_at` AND `engagement_ladder_state`** as the v6.6 banner claims, or only one of them. The file name suggests only the engagement-ladder column. A `head -50 backend/alembic/versions/031_add_day7_engagement_columns.py` paste would close that.
3. **Whether `alembic heads` actually returns `032`** as a single value, or returns multiple heads (which would indicate a branching mistake somewhere). The file count and numbering suggest a clean single-head chain, but `alembic heads` is the only way to be 100% sure.
