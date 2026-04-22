# ZetaOps Copilot — Test Audit Prompt for Claude Code

Paste this entire prompt into a Claude Code session **opened at the repo root**
(`C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler`). Make sure the
`v5-whatsapp` branch is checked out and your Python venv is activated before
starting.

---

## 1. Context

You are auditing the ZetaOps Copilot test suite against SRS v5.1. Read these
two files **before writing any code or tests**:

1. `ZETAOPS_DEV_PROMPT.md` — architectural rules, stack, testing rules (Section 13).
2. `docs/ZetaOps_SRS_v5_1.docx` — Software Requirements Specification.
   If this file is not in the repo, I will paste the relevant sections.
   Otherwise: `python -c "import docx; d=docx.Document('docs/ZetaOps_SRS_v5_1.docx'); [print(p.text) for p in d.paragraphs]"`
   to extract text.

Current state: `v5-whatsapp` branch, tag `v6.2.2-test-recovery`. Expected baseline:
**199 tests passing, 0 failed, 0 errors** on `pytest tests/ -m "not integration" -v`.
If this baseline does not hold, stop and report it before proceeding.

## 2. Scope — SHIPPED features only (test these)

Per SRS Section 1.2 "Current State (as of April 20, 2026)", these are the
**only** features in scope for this audit:

| SRS § | Feature                                              | Release                  |
|-------|------------------------------------------------------|--------------------------|
| 6.1   | Tenant & Organisation Management                     | v4.0 + v6.2              |
| 6.2   | Employee / Operator Master Data                      | v3.x + v5.16 source      |
| 6.3   | Machine / Work Center Master Data                    | v3.x + v5.16 source      |
| 6.4   | Skills / Qualification Catalogue                     | v3.x                     |
| 6.5   | Job Definition & Management                          | v3.x                     |
| 6.6   | Step Intelligence                                    | V3 tier                  |
| 6.7   | QR Scan & Print Job Cards                            | V3 tier                  |
| 6.8   | Resource Availability Engine                         | v3.x                     |
| 6.9   | Schedule Suggestions                                 | v3.9.7                   |
| 6.10  | Material Estimate                                    | v3.9.8                   |
| 6.11  | Auto-Scheduler Engine                                | V2 tier                  |
| 6.12  | Dashboard & Visualisation                            | v3.x + v4.0.9            |
| 6.13  | AI Copilot (web + WhatsApp mock)                     | v3.9 + v4.0.8 + v5.x     |
| 6.14  | Demo Data Seeder                                     | v4.0.6                   |
| 6.15  | Getting Started Onboarding                           | v4.1                     |
| 6.16  | CSV / Excel Import                                   | V4 tier                  |
| 6.17  | WhatsApp Copilot — Role Limiting                     | v5.12                    |
| 6.18  | WhatsApp Copilot — 3-Language Support                | v5.12                    |
| 6.19  | Day 1 Simple Table (source + worker_type, migration 023) | v5.16                |
| 6.20  | Manager Check-in Flow                                | v5.15                    |
| 6.21  | Owner Briefing                                       | v5.15                    |
| 6.22  | RAG Pipeline (flat files)                            | v6.1                     |
| 6.23  | Industry-Aware Dynamic Labels                        | v6.2                     |
| —     | v6.2.1 scheduler fixes (lock, availability, conflict dedup) | v6.2.1            |
| —     | v6.2.2 test recovery (SQLite StaticPool in conftest) | v6.2.2                   |

## 3. OUT OF SCOPE — do NOT write tests for these

Per SRS Section 1.2, skip anything in these buckets:

- **BLOCKED (Meta portfolio review):** v5.11 WhatsApp Go-Live, v5.13 Voice Notes,
  v5.14 Live E2E.
- **NEXT TO BUILD (not shipped):** 6.24 KPI Baseline (v6.3), 6.25 Material
  Estimator standalone (v6.4), 6.26 Compliance Tracker (v6.5), 6.27 GST
  E-Invoicing (v6.6), v6.7 pgvector, v6.8 Supervisor Agent.
- **V7 era (ERP connector, contractor layer):** v7.0, v7.1, v7.2.

If a test case would require a feature flag that is still `False` in
`features_config.py`, mark it **SKIPPED-BY-FLAG** in the report rather than
writing or running it.

## 4. What to do — step by step

Do these steps in this order. Do not skip steps. After each step, report
briefly what you did before moving on.

### Step A — Baseline check

1. Confirm branch is `v5-whatsapp` and tag is at or after `v6.2.2-test-recovery`:
   `git status`, `git describe --tags`.
2. Run the existing suite and capture the result:
   `pytest tests/ -m "not integration" -v --tb=short 2>&1 | tee baseline_run.log`
3. Confirm Alembic head is **023** and exactly one head:
   `cd backend && alembic heads`.
4. If baseline is not clean, STOP. Report which tests fail and do not proceed
   to Step B until I respond.

### Step B — Map SRS features to test cases

For each SRS section listed in Scope table above, produce a list of
test cases. For each feature, write **both**:

- **Functional / behavioural test cases** — "Given … when … then …" style.
  These describe observable behaviour from the SRS, independent of code.
- **Unit test mappings** — which existing test file (if any) already covers
  this, and where the gap is.

Example for 6.8 Resource Availability Engine:

```
FR-6.8.1  Machine already allocated on date X is reported unavailable
FR-6.8.2  Employee without required skill level is filtered out
FR-6.8.3  Overbooking attempt returns named conflict with dates + resource
FR-6.8.4  Feasibility score is 100% when all requirements met, 0% when none
FR-6.8.5  Tenant isolation — tenant A cannot see tenant B resources
Existing coverage: tests/test_scheduler_engine.py (partial), tests/test_conflict_detection.py
```

Save this mapping to `docs/test_audit/srs_to_test_map.md`.

### Step C — Generate / run tests per feature

For each SRS section in scope:

1. Check whether test coverage exists. Look in `backend/tests/` — file names
   typically match the feature area (e.g., `test_scheduler_engine.py`,
   `test_role_limiting.py`, `test_language_detection.py`, `test_skills.py`).
2. If coverage is **missing or thin**, write new unit tests that:
   - Use SQLite in-memory with StaticPool (per Section 22 of SRS and `conftest.py`).
   - Include `tenant_id` in every query (per Section 6 Rule 1 of dev prompt).
   - Use pytest markers consistently. Unit tests have **no** marker. Tests
     needing real PostgreSQL get `@pytest.mark.integration` and will be skipped
     in the default run.
   - Follow Pydantic v2, datetime.now(timezone.utc), SQLAlchemy 2.0 patterns
     (Section 6 of dev prompt).
3. Do not touch existing test files that already pass unless you are filling
   a documented gap. Add new files rather than editing passing ones.
4. Run `pytest tests/ -m "not integration" -v --tb=short` after each new test
   file you add. If a new test fails, diagnose it rather than deleting it.
   Rule: a failing test that correctly reflects the SRS is valuable — it has
   found a real bug or a spec-vs-code drift. Report it honestly.

### Step D — Produce the audit report

Produce **one markdown file** at `docs/test_audit/test_audit_report.md` with
this exact structure:

```
# ZetaOps Copilot Test Audit Report
Generated: <ISO timestamp>
Branch: v5-whatsapp
Tag: <output of git describe --tags>
Baseline: <N passed / M failed / K errors> from `pytest -m "not integration"`

## Summary
- Total SRS features in scope: <N>
- Features with adequate test coverage: <N>
- Features with gaps (new tests added): <N>
- Features with gaps (tests NOT added and reason): <N>
- New tests added by this audit: <N>
- Tests passing after audit: <N>
- Tests failing after audit: <N>

## Results Table

| # | SRS § | Feature | Test Type | Test Case ID | Status | Test File | Function | Failure Reason | Suspect Source File/Function |
|---|-------|---------|-----------|--------------|--------|-----------|----------|----------------|------------------------------|
| 1 | 6.1 | Tenant registration seeds demo data | Functional | test_registration_seeds_demo | PASS | tests/test_registration.py | test_demo_seed_on_register | — | — |
| 2 | 6.8 | Overbooking returns named conflict | Functional | test_overbook_named_conflict | FAIL | tests/test_conflict_detection.py | test_named_conflict | AssertionError: expected "Ravi on 2026-04-22" in message, got "conflict" | app/services/availability.py :: check_job_availability (line 87 returns generic string) |
| 3 | 6.13 | AI Copilot respects daily query limit | Unit | test_ai_limit_hits_402 | SKIPPED-BY-FLAG | — | — | ai_copilot flag is False in features_config.py for test tenant | — |

## Failures — Detail

For every row with Status = FAIL, repeat here with:
- Full pytest output (short trace).
- Quoted SRS text the test maps to (with section number).
- Best guess at the offending file / function / line.
- Whether this is a real bug, a spec drift, or a test defect (and why you
  think so).

## Gaps NOT Covered By New Tests

List any SRS requirements you could not test and explain why (e.g., needs real
WhatsApp API, needs Groq API key, needs real PostgreSQL, blocked by feature
flag, requires browser automation).

## Appendix — New Test Files Added

List every new `test_*.py` file you created, with a one-line description of
what it covers.
```

### Step E — Do NOT modify production code

This audit is **read-only** with respect to `app/`. You may:

- Add new files under `backend/tests/`.
- Add new files under `docs/test_audit/`.

You may NOT:

- Edit any file under `backend/app/` even if a test fails.
- Edit any migration.
- Change `features_config.py` default values.
- Edit existing passing test files.

If a test reveals a bug in production code, **report it in the audit, do not
fix it**. I will triage bug fixes separately so that test results remain
diagnostic, not a moving target.

## 5. Non-negotiables

- Tenant isolation in every query. No exceptions. A test without `tenant_id`
  in its query is itself a bug.
- SQLite StaticPool for unit tests (per v6.2.2 conftest fix). Do not revert
  to default pool.
- Pydantic v2 only: `model_config = ConfigDict(...)`, `model_validate()`,
  `@field_validator`, `datetime.now(timezone.utc)`.
- Migration head stays at 023. Do not generate migrations.
- WHATSAPP_MOCK_MODE=True during tests. Never hit real Interakt API.
- AI Copilot tests must mock Groq — never call real API in unit tier.
- Commit nothing. Leave the audit report and new test files staged but
  uncommitted so I can review them before they hit git.

## 6. Final checklist before you report done

- [ ] `pytest tests/ -m "not integration" -v` still green (new failures are
      allowed ONLY if they correspond to real SRS-vs-code drift, and are
      documented as such in the report).
- [ ] `npx tsc --noEmit` still zero errors (if you touched any frontend file,
      which you should not have).
- [ ] `alembic heads` shows exactly 023.
- [ ] Report at `docs/test_audit/test_audit_report.md` follows the exact
      table schema above.
- [ ] Mapping at `docs/test_audit/srs_to_test_map.md` exists.
- [ ] Nothing under `backend/app/` was modified.

Begin with Step A.
