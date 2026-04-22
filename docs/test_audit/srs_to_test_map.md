# ZetaOps Copilot — SRS to Test Map
Generated: 2026-04-21
Branch: v5-whatsapp  |  Alembic head: 023

---

## 6.1 Tenant & Organisation Management

FR-6.1.1  New tenant registration creates a Tenant record with correct plan and slug.
FR-6.1.2  Registration seeds demo data for the tenant.
FR-6.1.3  ai_queries_today resets to 0 on a new date (migration 019 columns).
FR-6.1.4  Tenant isolation — a user can only see records belonging to their tenant_id.

Existing coverage: none dedicated.
Gap: `tests/test_tenant.py` (new file added by this audit).

---

## 6.2 Employee / Operator Master Data (+ v5.16 source/worker_type)

FR-6.2.1  Create employee returns 201 with correct fields.
FR-6.2.2  List employees is filtered by tenant_id.
FR-6.2.3  Get employee 404 when wrong tenant.
FR-6.2.4  Update employee changes only specified fields.
FR-6.2.5  Delete employee returns 204.
FR-6.2.6  source field defaults to 'manual' when not provided.
FR-6.2.7  source field rejects values outside (manual, whatsapp, erp_sync).
FR-6.2.8  worker_type defaults to 'permanent' when not provided.
FR-6.2.9  worker_type rejects values outside (permanent, contractor).
FR-6.2.10 Inactive employee status is preserved after update.

Existing coverage: test_employees.py exists but is empty.
Gap: test_employees.py filled by this audit.

---

## 6.3 Machine / Reactor / Work Center Master Data

FR-6.3.1  Create machine returns 201 with correct fields.
FR-6.3.2  List machines is filtered by tenant_id.
FR-6.3.3  Get machine 404 when wrong tenant.
FR-6.3.4  Delete machine returns 204.
FR-6.3.5  source field defaults to 'manual' when not provided.
FR-6.3.6  source field rejects values outside (manual, whatsapp, erp_sync).

Existing coverage: none.
Gap: tests/test_machines.py (new file added by this audit).

---

## 6.4 Skill / Qualification / Certification Catalogue

FR-6.4.1  Create skill returns 201.
FR-6.4.2  List skills filtered by tenant.
FR-6.4.3  Get skill by ID.
FR-6.4.4  Update skill fields.
FR-6.4.5  Delete skill.

Existing coverage: tests/test_skills.py — 5 tests, full CRUD.
Gap: none.

---

## 6.5 Job Definition & Management

FR-6.5.1  Create job with required fields returns 201.
FR-6.5.2  List jobs filtered by tenant_id.
FR-6.5.3  Get job 404 for wrong tenant.
FR-6.5.4  Update job restores original_start_date and original_end_date on first change.
FR-6.5.5  is_locked defaults to False on creation.
FR-6.5.6  Locked job cannot be updated.

Existing coverage:
  test_jobs_api.py — integration only (@pytest.mark.integration), skipped in default run.
  test_jobs.py — empty.
Gap: tests/test_jobs_unit.py (new file added by this audit).

---

## 6.6 Step Intelligence

FR-6.6.1  Create step on a job returns step with sequence_no.
FR-6.6.2  Step status transitions: ready -> in_progress -> complete.
FR-6.6.3  Invalid transition returns 422 / 400.
FR-6.6.4  Completed step cannot be reversed.

Existing coverage: none.
Gap: CANNOT fully test via HTTP without auth bypass complexity. Step logic tested
     indirectly via test_scheduler_engine.py (step sequencing). Partial coverage.
     Marked GAPS-NOT-COVERED in report.

---

## 6.7 QR Scan & Print Job Cards

FR-6.7.1  /api/scan/{job_id} returns 200 with no auth header.
FR-6.7.2  /api/scan/{job_id} returns 404 for unknown job.

Existing coverage: none.
Gap: Scan page is always public (no auth). HTTP-level tests need integration DB.
     Marked GAPS-NOT-COVERED.

---

## 6.8 Resource Availability Engine

FR-6.8.1  Machine already assigned to another job on overlapping dates is reported busy.
FR-6.8.2  Employee without the required skill level is excluded from candidates.
FR-6.8.3  Feasibility score is 100 when all requirements met.
FR-6.8.4  Feasibility score is 0 when no requirements met.
FR-6.8.5  Tenant isolation — busy check uses tenant_id on all queries.
FR-6.8.6  Date range utility returns correct list of dates.
FR-6.8.7  Skill level ranking: Premium >= Intermediate >= Generic.

Existing coverage: test_availability_engine.py exists but is empty.
Gap: test_availability_engine.py filled by this audit.

---

## 6.9 Schedule Suggestions (v3.9.7)

FR-6.9.1  _score_candidate returns higher score when machines are free.
FR-6.9.2  _score_candidate returns higher score when employees are free.
FR-6.9.3  Deadline proximity boosts score when start is close to deadline.
FR-6.9.4  Score is 0 when no machines or employees are free.

Existing coverage: none.
Gap: tests/test_schedule_suggestions.py (new file added by this audit).

---

## 6.10 Material Estimate (v3.9.8)

FR-6.10.1  Returns empty list when no past completed jobs of that type.
FR-6.10.2  Returns per-material estimate based on average rate from past jobs.
FR-6.10.3  Confidence is 'none' for 0 jobs, 'low' for 1, 'medium' for 2, 'high' for 3+.
FR-6.10.4  Jobs with quantity=0 are excluded from rate calculation.

Existing coverage: none.
Gap: tests/test_material_estimate.py (new file added by this audit).

---

## 6.11 Auto-Scheduler Engine

FR-6.11.1  Single-step job resolves to a scheduled entry.
FR-6.11.2  Higher priority job wins over lower priority for same machine slot.
FR-6.11.3  Locked entry blocks machine for other jobs.
FR-6.11.4  Locked job is skipped entirely.
FR-6.11.5  Step 2 waits for step 1 to complete.
FR-6.11.6  Job rejected when it cannot meet deadline.

Existing coverage: test_scheduler_engine.py (11 tests), test_scheduler.py (4 tests). Good coverage.
Gap: none.

---

## 6.12 Dashboard & Visualisation

FR-6.12.1  Conflict detected when schedule_entries count < expected days.
FR-6.12.2  No conflict when all days scheduled.
FR-6.12.3  original_dates used for expected-day count (migration 022).
FR-6.12.4  Job not in entry map is not flagged as conflict.
FR-6.12.5  Conflict message is actionable (contains job name or date range).

Existing coverage: test_conflict_detection.py — 9 tests. Good coverage.
Gap: none.

---

## 6.13 AI Copilot (web + WhatsApp mock)

FR-6.13.1  AI query is blocked when daily limit reached (402).
FR-6.13.2  AI response returns structured JSON (tool-calling pattern).
FR-6.13.3  Groq call is never made in mock mode — unit tests must mock the client.
FR-6.13.4  WhatsApp bridge routes messages through pipeline (test_whatsapp_pipeline.py).
FR-6.13.5  AI Copilot flag must be enabled — else endpoint returns 403.

Existing coverage:
  test_whatsapp_pipeline.py — covers pipeline intent detection / role gating.
  test_whatsapp_router.py — covers payload extraction.
  No coverage for web AI Copilot endpoint or Groq mock.
Gap: tests/test_ai_copilot.py (new file, mocks Groq).

---

## 6.14 Demo Data Seeder

FR-6.14.1  Seeder creates at least one skill, employee, machine, and job.
FR-6.14.2  Seeder is idempotent — calling twice does not create duplicates.
FR-6.14.3  All seeded records belong to the given tenant_id.

Existing coverage: none.
Gap: tests/test_demo_seeder.py (new file added by this audit).

---

## 6.15 Getting Started Onboarding

FR-6.15.1  Onboarding state stored in localStorage per user (frontend only).
FR-6.15.2  ? button in header resets tour.

Existing coverage: none. Frontend-only localStorage feature.
Gap: CANNOT test in backend unit tier. Marked GAPS-NOT-COVERED.

---

## 6.16 CSV / Excel Import

FR-6.16.1  CSV with valid employee rows creates employee records.
FR-6.16.2  CSV with valid machine rows creates machine records.
FR-6.16.3  Malformed CSV row is skipped with error reported.
FR-6.16.4  BOM is stripped from CSV files.
FR-6.16.5  XLSX import produces same result as equivalent CSV.

Existing coverage: none.
Gap: tests/test_csv_import.py (new file added by this audit).

---

## 6.17 WhatsApp Copilot — Role Limiting

FR-6.17.1  Owner passes all query categories.
FR-6.17.2  Manager blocked on financial queries.
FR-6.17.3  Manager blocked on create/delete operations.
FR-6.17.4  Operator blocked on schedule queries.
FR-6.17.5  Blocked response is localised to detected language.
FR-6.17.6  Blocked actions never reach the AI layer.

Existing coverage: test_role_limiting.py — 23 tests. Full coverage.
Gap: none.

---

## 6.18 WhatsApp Copilot — 3-Language Support

FR-6.18.1  Devanagari text detected as 'hindi'.
FR-6.18.2  Hinglish marker words detected as 'hinglish'.
FR-6.18.3  Latin text with no markers detected as 'en'.
FR-6.18.4  All response keys have all three language variants.
FR-6.18.5  Unknown key returns safe fallback string.

Existing coverage: test_language_detection.py — 10 tests. Full coverage.
Gap: none.

---

## 6.19 Day 1 Simple Table (source + worker_type — migration 023)

FR-6.19.1  source column exists on Employee with default 'manual'.
FR-6.19.2  source column exists on Machine with default 'manual'.
FR-6.19.3  worker_type column exists on Employee with default 'permanent'.
FR-6.19.4  source values are constrained to (manual, whatsapp, erp_sync).
FR-6.19.5  worker_type values are constrained to (permanent, contractor).
FR-6.19.6  VALID_SOURCE_VALUES constant is importable from models.

Existing coverage: test_alembic_migrations.py — test_schema_columns verifies
  is_locked and original_dates but not source/worker_type.
Gap: source/worker_type column tests added to test_employees.py and test_machines.py.

---

## 6.20 Manager Check-in Flow

FR-6.20.1  normalise() strips whitespace and lowercases.
FR-6.20.2  Absent marker words include 'nahi aaya' and 'absent'.
FR-6.20.3  Employee matched by first or last name case-insensitively.
FR-6.20.4  Cross-tenant isolation — substitute search limited to same tenant.
FR-6.20.5  Substitute found with matching skill.
FR-6.20.6  No substitute returned when skill is unique to absent employee.
FR-6.20.7  Check-in state stored and retrieved per tenant.

Existing coverage: test_whatsapp_checkin.py — extensive coverage.
Gap: none.

---

## 6.21 Owner Briefing

FR-6.21.1  Confirmation words (haan, yes, ok) return True from is_confirmation().
FR-6.21.2  Cancellation words (nahi, no, cancel) return True from is_cancellation().
FR-6.21.3  Confirmation and cancellation sets do not overlap.
FR-6.21.4  Pending action stored and retrieved by phone number.
FR-6.21.5  Different phones have separate pending action state.

Existing coverage: test_whatsapp_phase4.py — 64 tests. Full coverage.
Gap: none.

---

## 6.22 RAG Pipeline (flat files — v6.1)

FR-6.22.1  seed_rag_from_template copies .txt files from template to tenant folder.
FR-6.22.2  Seeding with invalid industry_type returns False without error.
FR-6.22.3  load_rag_context returns concatenated string from tenant folder.
FR-6.22.4  load_rag_context returns empty string when no files exist.
FR-6.22.5  Seeding never overwrites existing tenant files.
FR-6.22.6  Tenant isolation — load_rag_context reads only from rag_data/{tenant_id}/.

Existing coverage: none.
Gap: tests/test_rag_pipeline.py (new file added by this audit).

---

## 6.23 Industry-Aware Dynamic Labels

FR-6.23.1  useLabels() returns 'Print Jobs' for industry_type='printing'.
FR-6.23.2  useLabels() returns 'Production Orders' for 'manufacturing'.
FR-6.23.3  No hardcoded 'Jobs'/'Employees'/'Machines' strings in src/pages/.
FR-6.23.4  IndustryContext reads industry_type from AuthContext at login.

Existing coverage: none. Frontend-only React hook.
Gap: CANNOT test in backend unit tier. Verified by grep in CI instead.
     Marked GAPS-NOT-COVERED.

---

## v6.2.1 Scheduler fixes (lock, availability, conflict dedup)

FR-v621.1  Lock button toggles is_locked on job.
FR-v621.2  resource-availability endpoint returns 200 with correct shape.
FR-v621.3  Conflict deduplication — same conflict not listed twice.
FR-v621.4  Health check returns 200.

Existing coverage: test_scheduler.py covers locked job blocking.
Gap: test_scheduler.py already covers FR-v621.1 indirectly.

---

## v6.2.2 Test recovery (SQLite StaticPool)

FR-v622.1  SQLite in-memory DB creates all tables visible to the session.
FR-v622.2  auth_headers fixture creates tenant + user in same session.

Existing coverage: test_skills.py — validates conftest auth_headers fixture.
Gap: none.
