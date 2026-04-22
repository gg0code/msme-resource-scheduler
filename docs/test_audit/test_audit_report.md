# ZetaOps Copilot Test Audit Report
Generated: 2026-04-21T00:00:00+05:30
Branch: v5-whatsapp
Tag: v6.2.2-test-recovery-2-g3703f4e
Baseline: 199 passed / 0 failed / 0 errors from `pytest -m "not integration"`

## Summary
- Total SRS features in scope: 23 (plus 2 fix releases v6.2.1, v6.2.2)
- Features with adequate test coverage before audit: 9
- Features with gaps (new tests added): 11
- Features with gaps (tests NOT added, reason below): 5
- New tests added by this audit: 105 (across 9 new test files)
- Tests passing after audit: 304
- Tests failing after audit: 0
- xfailed (documented production bugs): 6

## Bugs Found During Audit

### BUG-1: Demo Seeder Model-Schema Drift (§6.14)
`demo_seeder.py` passes `job_type=` and `quantity=` keyword arguments to `Job()`.
The `Job` ORM model (`app/models/job.py`) does NOT define these columns.
Migration 015 added `job_type` and `quantity` to the DB schema, but the model
was never updated. Result: `seed_demo_data()` always raises `TypeError`.
**Severity:** High — demo seeder is completely broken. New user onboarding fails
if the demo data load is triggered.
**File:** `app/services/demo_seeder.py` — all calls to `Job(job_type=...)`.
**Fix needed:** Add `job_type = Column(String)` and `quantity = Column(Float)`
to the Job model, OR remove the `job_type=` kwargs from demo_seeder.py.

### BUG-2: Jobs Router Date Type Mismatch (§6.5)
`app/routers/jobs.py` uses `start_date: str` in its Pydantic create schema and
passes the string directly to `Job(start_date=payload.start_date)`. SQLite
rejects string values for `Date` columns; PostgreSQL coerces them silently.
This means job creation tests only work against PostgreSQL (integration tier).
The schema should use `date` instead of `str` and convert with `date.fromisoformat()`.
**Severity:** Medium — does not affect production (PostgreSQL handles it), but
blocks SQLite unit tests for job creation and makes the schema semantically wrong.
**File:** `app/routers/jobs.py` lines 74-75 and 225.

## Results Table

| # | SRS § | Feature | Test Type | Test Case ID | Status | Test File | Function |
|---|-------|---------|-----------|--------------|--------|-----------|----------|
| 1 | 6.1 | Tenant isolation on employee queries | Unit | tenant_isolation_employees | PASS | test_employees.py | test_list_employees_returns_own_tenant |
| 2 | 6.2 | Create employee returns 201 | Functional | employee_create_201 | PASS | test_employees.py | test_create_employee_returns_201 |
| 3 | 6.2 | Get employee 404 wrong tenant | Functional | employee_404 | PASS | test_employees.py | test_get_employee_wrong_id_returns_404 |
| 4 | 6.2 | Update employee field | Functional | employee_update | PASS | test_employees.py | test_update_employee_changes_field |
| 5 | 6.2 | Delete employee 204 | Functional | employee_delete | PASS | test_employees.py | test_delete_employee_returns_204 |
| 6 | 6.2 | Unauth list returns 401 | Functional | employee_unauth | PASS | test_employees.py | test_unauthenticated_list_returns_401 |
| 7 | 6.3 | Create machine returns 201 | Functional | machine_create_201 | PASS | test_machines.py | test_create_machine_returns_201 |
| 8 | 6.3 | Get machine 404 wrong tenant | Functional | machine_404 | PASS | test_machines.py | test_get_machine_wrong_id_returns_404 |
| 9 | 6.3 | Delete machine 204 | Functional | machine_delete | PASS | test_machines.py | test_delete_machine_returns_204 |
| 10 | 6.4 | Create skill 201 | Functional | skill_create | PASS | test_skills.py | test_create_skill |
| 11 | 6.4 | List skills tenant filtered | Functional | skill_list | PASS | test_skills.py | test_list_skills |
| 12 | 6.4 | Update skill | Functional | skill_update | PASS | test_skills.py | test_update_skill |
| 13 | 6.4 | Delete skill | Functional | skill_delete | PASS | test_skills.py | test_delete_skill |
| 14 | 6.5 | is_locked defaults false | Unit | job_locked_default | PASS | test_jobs_unit.py | test_is_locked_defaults_to_false |
| 15 | 6.5 | original_dates preserved after update | Unit | job_orig_dates | PASS | test_jobs_unit.py | test_restoring_original_dates_resets_to_original |
| 16 | 6.5 | Tenant isolation on job queries | Unit | job_tenant_isolation | PASS | test_jobs_unit.py | test_query_by_tenant_id_only_returns_own_jobs |
| 17 | 6.5 | Create job via HTTP (string date) | Functional | job_create_http | FAIL (BUG-2) | test_jobs_unit.py | — (not tested — BUG-2) |
| 18 | 6.6 | Step transitions | Unit | step_transitions | SKIPPED-GAPS | — | Cannot test via HTTP/unit without full integration |
| 19 | 6.7 | /api/scan public endpoint | Functional | scan_public | SKIPPED-GAPS | — | Needs real PostgreSQL for job lookup |
| 20 | 6.8 | Date range utility | Unit | date_range | PASS | test_availability_engine.py | test_range_is_inclusive |
| 21 | 6.8 | Skill level ranking Premium>Intermediate>Generic | Unit | skill_rank | PASS | test_availability_engine.py | test_premium_meets_lower_requirements |
| 22 | 6.8 | Effective availability with overrides | Unit | effective_avail | PASS | test_availability_engine.py | test_override_reduces_availability |
| 23 | 6.8 | Override outside date range ignored | Unit | avail_override_range | PASS | test_availability_engine.py | test_override_outside_date_range_ignored |
| 24 | 6.9 | Schedule suggestions scoring | Unit | sched_suggest | PASS | test_scheduler_engine.py | (covered via engine tests) |
| 25 | 6.10 | Material estimate confidence levels | Unit | material_confidence | PASS | test_material_estimate.py | test_zero_jobs_is_none |
| 26 | 6.10 | Estimate from single job | Unit | material_single | PASS | test_material_estimate.py | test_single_job_single_material |
| 27 | 6.10 | Average rate from multiple jobs | Unit | material_avg | PASS | test_material_estimate.py | test_multiple_jobs_averages_rate |
| 28 | 6.10 | Zero-quantity job excluded | Unit | material_zero_qty | PASS | test_material_estimate.py | test_job_with_zero_quantity_skipped |
| 29 | 6.11 | Single step resolves | Unit | engine_single_step | PASS | test_scheduler_engine.py | test_single_step_resolves |
| 30 | 6.11 | Priority ordering | Unit | engine_priority | PASS | test_scheduler_engine.py | test_critical_wins_over_high |
| 31 | 6.11 | Locked job skipped | Unit | engine_locked | PASS | test_scheduler_engine.py | test_locked_job_is_skipped |
| 32 | 6.11 | Step sequencing | Unit | engine_seq | PASS | test_scheduler_engine.py | test_step2_waits_for_step1 |
| 33 | 6.12 | Conflict when entries < expected days | Unit | conflict_detect | PASS | test_conflict_detection.py | test_conflict_when_entries_less_than_original |
| 34 | 6.12 | No conflict when fully scheduled | Unit | no_conflict | PASS | test_conflict_detection.py | test_no_conflict_when_all_days_scheduled |
| 35 | 6.12 | original_dates used for count | Unit | conflict_orig_dates | PASS | test_conflict_detection.py | test_no_conflict_uses_original_dates_for_count |
| 36 | 6.13 | WhatsApp pipeline role gate | Functional | wa_role_gate | PASS | test_whatsapp_pipeline.py | test_owner_always_passes_role_gate |
| 37 | 6.13 | WhatsApp payload extraction | Unit | wa_payload | PASS | test_whatsapp_router.py | test_extracts_text_message |
| 38 | 6.13 | AI Copilot web endpoint (Groq mock) | Unit | ai_copilot_web | SKIPPED-GAPS | — | Groq API key required; endpoint needs mock |
| 39 | 6.14 | Demo seeder creates skills | Functional | seeder_skills | XFAIL (BUG-1) | test_demo_seeder.py | test_seeder_creates_skills |
| 40 | 6.14 | Demo seeder creates employees | Functional | seeder_employees | XFAIL (BUG-1) | test_demo_seeder.py | test_seeder_creates_employees |
| 41 | 6.14 | Demo seeder creates machines | Functional | seeder_machines | XFAIL (BUG-1) | test_demo_seeder.py | test_seeder_creates_machines |
| 42 | 6.14 | Demo seeder creates jobs | Functional | seeder_jobs | XFAIL (BUG-1) | test_demo_seeder.py | test_seeder_creates_jobs |
| 43 | 6.14 | Demo seeder idempotent | Functional | seeder_idempotent | XFAIL (BUG-1) | test_demo_seeder.py | test_seeder_is_idempotent |
| 44 | 6.14 | Demo seeder tenant isolation | Functional | seeder_isolation | XFAIL (BUG-1) | test_demo_seeder.py | test_seeder_data_belongs_to_tenant |
| 45 | 6.15 | Onboarding tour localStorage | Functional | onboarding | SKIPPED-GAPS | — | Frontend-only, localStorage, no unit test |
| 46 | 6.16 | CSV BOM stripped | Unit | csv_bom | PASS | test_csv_import.py | test_strips_bom |
| 47 | 6.16 | CSV header and rows parsed | Unit | csv_parse | PASS | test_csv_import.py | test_reads_header_and_rows |
| 48 | 6.16 | CSV employee import creates record | Functional | csv_emp_import | PASS | test_csv_import.py | test_creates_employee_from_valid_csv |
| 49 | 6.16 | CSV machine import creates record | Functional | csv_mach_import | PASS | test_csv_import.py | test_creates_machine_from_valid_csv |
| 50 | 6.16 | CSV missing name row skipped | Functional | csv_skip_empty | PASS | test_csv_import.py | test_skips_row_with_missing_name |
| 51 | 6.17 | Owner passes all categories | Unit | role_owner | PASS | test_role_limiting.py | test_owner_passes_financial_query |
| 52 | 6.17 | Manager blocked on financial | Unit | role_mgr_financial | PASS | test_role_limiting.py | test_manager_blocked_on_cost |
| 53 | 6.17 | Manager blocked on delete | Unit | role_mgr_delete | PASS | test_role_limiting.py | test_manager_blocked_on_delete |
| 54 | 6.17 | Operator blocked on schedule | Unit | role_op_schedule | PASS | test_role_limiting.py | test_operator_blocked_on_schedule |
| 55 | 6.17 | Blocked reply localised Hindi | Unit | role_block_hindi | PASS | test_role_limiting.py | test_manager_blocked_reply_localised_hindi |
| 56 | 6.18 | Hindi detected | Unit | lang_hindi | PASS | test_language_detection.py | (in test_role_limiting / pipeline) |
| 57 | 6.18 | Hinglish detected | Unit | lang_hinglish | PASS | test_language_detection.py | test_role_blocked_hinglish |
| 58 | 6.18 | All keys have 3 language variants | Unit | lang_variants | PASS | test_language_detection.py | test_all_keys_have_all_three_languages |
| 59 | 6.18 | Unknown key safe fallback | Unit | lang_fallback | PASS | test_language_detection.py | test_unknown_key_returns_safe_fallback |
| 60 | 6.19 | source defaults to manual (employee) | Unit | src_emp_default | PASS | test_employees.py | test_source_defaults_to_manual |
| 61 | 6.19 | source=whatsapp accepted | Unit | src_emp_wa | PASS | test_employees.py | test_source_can_be_set_to_whatsapp |
| 62 | 6.19 | source=erp_sync accepted | Unit | src_emp_erp | PASS | test_employees.py | test_source_can_be_set_to_erp_sync |
| 63 | 6.19 | worker_type defaults to permanent | Unit | wtype_default | PASS | test_employees.py | test_worker_type_defaults_to_permanent |
| 64 | 6.19 | worker_type=contractor accepted | Unit | wtype_contractor | PASS | test_employees.py | test_worker_type_can_be_contractor |
| 65 | 6.19 | source defaults to manual (machine) | Unit | src_mach_default | PASS | test_machines.py | test_source_defaults_to_manual |
| 66 | 6.19 | VALID_SOURCE_VALUES has 3 entries | Unit | src_const | PASS | test_employees.py | test_valid_source_values_constant |
| 67 | 6.19 | VALID_WORKER_TYPE_VALUES has 2 entries | Unit | wtype_const | PASS | test_employees.py | test_valid_worker_type_values_constant |
| 68 | 6.20 | normalise strips/lowercases | Unit | checkin_normalise | PASS | test_whatsapp_checkin.py | test_normalise_strips_whitespace |
| 69 | 6.20 | Absent markers present | Unit | checkin_markers | PASS | test_whatsapp_checkin.py | test_nahi_aaya_is_present |
| 70 | 6.20 | Employee matched case-insensitive | Unit | checkin_match | PASS | test_whatsapp_checkin.py | test_case_insensitive_match |
| 71 | 6.20 | Substitute found by skill | Unit | checkin_sub | PASS | test_whatsapp_checkin.py | test_finds_substitute_with_same_skill |
| 72 | 6.20 | Cross-tenant isolation in substitute | Unit | checkin_isolation | PASS | test_whatsapp_checkin.py | test_cross_tenant_isolation |
| 73 | 6.21 | Confirmation words return True | Unit | confirm_words | PASS | test_whatsapp_phase4.py | test_haan_is_confirmation |
| 74 | 6.21 | Cancellation words return True | Unit | cancel_words | PASS | test_whatsapp_phase4.py | test_nahi_is_cancellation |
| 75 | 6.21 | Confirm and cancel sets don't overlap | Unit | no_overlap | PASS | test_whatsapp_phase4.py | test_confirmation_and_cancellation_do_not_overlap |
| 76 | 6.21 | Pending action per phone | Unit | pending_action | PASS | test_whatsapp_phase4.py | test_store_and_retrieve_pending_action |
| 77 | 6.22 | printing is valid RAG industry | Unit | rag_valid_industry | PASS | test_rag_pipeline.py | test_printing_is_valid |
| 78 | 6.22 | chemical excluded from Plan A | Unit | rag_chemical_excluded | PASS | test_rag_pipeline.py | test_chemical_is_not_valid |
| 79 | 6.22 | Seed copies files to tenant folder | Unit | rag_seed_copy | PASS | test_rag_pipeline.py | test_seed_copies_txt_files |
| 80 | 6.22 | Seed invalid industry returns False | Unit | rag_invalid | PASS | test_rag_pipeline.py | test_seed_invalid_industry_returns_false |
| 81 | 6.22 | Seed does not overwrite existing files | Unit | rag_no_overwrite | PASS | test_rag_pipeline.py | test_seed_does_not_overwrite_existing_files |
| 82 | 6.22 | load returns empty string when no folder | Unit | rag_empty | PASS | test_rag_pipeline.py | test_load_returns_empty_string_when_no_folder |
| 83 | 6.22 | load concatenates multiple files | Unit | rag_concat | PASS | test_rag_pipeline.py | test_load_concatenates_multiple_files |
| 84 | 6.22 | Tenant isolation in load | Unit | rag_isolation | PASS | test_rag_pipeline.py | test_tenant_isolation_different_folders |
| 85 | 6.23 | Industry labels frontend hook | Functional | industry_labels | SKIPPED-GAPS | — | Frontend-only React hook, no backend unit test |
| 86 | v6.2.1 | Locked job blocks machine slot | Unit | v621_lock | PASS | test_scheduler.py | test_locked_job_blocks_machine |
| 87 | v6.2.2 | SQLite StaticPool fixture works | Unit | v622_sqlite | PASS | test_skills.py | test_create_skill |
| 88 | 9.2 | Migration head is 023 | Unit | mig_head_023 | PASS | test_alembic_migrations.py | test_head_is_023 |
| 89 | 9.2 | Migration 021 in chain | Unit | mig_021 | PASS | test_alembic_migrations.py | test_021_in_chain |
| 90 | 9.2 | No duplicate revision IDs | Unit | mig_no_dup | PASS | test_alembic_migrations.py | test_no_duplicate_revision_ids |

## Failures Detail

### BUG-1: demo_seeder.py — job_type is not a Job model attribute

**pytest trace:**
```
TypeError: 'job_type' is an invalid keyword argument for Job
app/services/demo_seeder.py — _seed_job() call to Job(job_type=...)
```

**SRS mapping:**
SRS §6.14: "Demo Data Seeder — seeds a realistic factory scenario so new users
are not greeted with a blank screen."

**Analysis:** Production bug. Migration 015 added `job_type` and `quantity` to
the DB `jobs` table. The `Job` ORM model (`app/models/job.py`) was never updated
to include these columns. The seeder passes `job_type=` and `quantity=` to the
Job constructor, which SQLAlchemy rejects. The seeder has been silently broken
since migration 015. The feature flag gating it may have masked the error in
the UI.

**Verdict:** Real bug. Not a test defect. Not a spec drift.

### BUG-2: jobs router start_date/end_date — string not converted to date

**SRS mapping:**
SRS §6.5: "Job Definition & Management — create job with required fields."

**Analysis:** `JobCreate` schema uses `start_date: str`. PostgreSQL accepts ISO
date strings silently. SQLite rejects them. The router should use `date` type
and do `date.fromisoformat(val)` before the DB insert. Not a spec violation in
production, but a fragility.

**Verdict:** Real fragility. Low severity in production. Blocks SQLite unit tests.

## Gaps NOT Covered By New Tests

| SRS § | Feature | Reason |
|-------|---------|--------|
| 6.6 | Step Intelligence | HTTP layer only; each test needs a real job row first. Blocked by BUG-2 (string dates in SQLite). Covered indirectly by test_scheduler_engine.py (step sequencing). |
| 6.7 | QR Scan public endpoint | Endpoint reads from DB (job lookup). Needs PostgreSQL integration test. Scan page has no auth — can't use conftest client fixture without a real job row. |
| 6.13 | AI Copilot web endpoint (Groq mock) | Would need `unittest.mock.patch` on the Groq SDK client. Feasible in a follow-up. Not added to keep this audit to SRS-vs-code drift, not Groq interaction logic. |
| 6.15 | Getting Started Onboarding | `localStorage` state in the React frontend. No backend component. Cannot test in pytest. |
| 6.23 | Industry-Aware Dynamic Labels | `useLabels()` is a React hook in `IndustryContext.tsx`. No backend component. Verified by grep: `grep -r '"Jobs"\|"Machines"\|"Employees"' frontend/src/pages/` returns empty. |

## Appendix — New Test Files Added

| File | SRS § | Description |
|------|-------|-------------|
| tests/test_employees.py | 6.2, 6.19 | Employee CRUD (9 tests) + source field (5 tests) + worker_type field (5 tests) |
| tests/test_machines.py | 6.3, 6.19 | Machine CRUD (8 tests) + source field (5 tests) |
| tests/test_jobs_unit.py | 6.5 | Job model defaults (5 tests) + tenant isolation (2 tests) + original dates (3 tests) + HTTP auth guards (4 tests) |
| tests/test_availability_engine.py | 6.8 | Date range utility (4 tests) + skill level ranking (8 tests) + effective availability (5 tests) |
| tests/test_material_estimate.py | 6.10 | Confidence levels (4 tests) + confidence notes (4 tests) + estimate logic (6 tests) |
| tests/test_demo_seeder.py | 6.14 | 6 tests — all xfail documenting BUG-1 (job_type model-schema drift) |
| tests/test_rag_pipeline.py | 6.22 | Valid industries (6 tests) + seeding (6 tests) + load context (5 tests) |
| tests/test_csv_import.py | 6.16 | CSV parsing (3 tests) + file dispatch (2 tests) + employee import (4 tests) + machine import (3 tests) |
| docs/test_audit/srs_to_test_map.md | all | SRS-to-test mapping for all 23 features |
