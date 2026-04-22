# ZetaOps Copilot Test Audit Report
Generated: 2026-04-21T00:00:00+05:30
Branch: v5-whatsapp
Tag: v6.2.2-test-recovery-2-g3703f4e
Baseline: 199 passed / 0 failed / 0 errors from `pytest -m "not integration"`

**Audit follow-up (2026-04-21 evening → 2026-04-22):** All four findings from this audit are now resolved.
- BUG-1 and BUG-2 fixed in tag `v6.2.4-bugfixes` (2026-04-21).
- BUG-3 and BUG-4 discovered during manual verification of the BUG-1/BUG-2 fixes, both fixed on 2026-04-22.
- BUG-3 fixed in tag `v6.2.6-registration-seed`.
- BUG-4 fixed in tag `v6.2.7-industry-type`.
- Post-fix test count: **328 passed, 0 failed, 0 xfailed** (310 after BUG-1/BUG-2 fixes, +6 from BUG-3 regression tests, +11 from BUG-4 schema tests, +1 from re-enabled xfail tests).

## Summary
- Total SRS features in scope: 23 (plus 2 fix releases v6.2.1, v6.2.2)
- Features with adequate test coverage before audit: 9
- Features with gaps (new tests added): 11
- Features with gaps (tests NOT added, reason below): 5
- New tests added by this audit: 105 (across 9 new test files during the initial audit)
- Additional tests added during BUG-3 and BUG-4 fix sessions: 17
- Tests passing after audit (pre-fix): 304
- Tests passing after BUG-1 and BUG-2 fixes: 310
- Tests passing after BUG-3 fix: 316
- Tests passing after BUG-4 fix: 328
- Tests failing: 0
- xfailed: 0 — all four bugs fixed

## Bugs Found During Audit

### BUG-1: Demo Seeder Model-Schema Drift (§6.14) — FIXED

**Status: FIXED in commit `765d5a3` (tag `v6.2.4-bugfixes`), April 21 2026.**
Added `job_type` and `quantity` columns to `app/models/job.py` matching migration 015. Updated `app/schemas/job.py` and `app/routers/jobs.py` to carry the fields through Create/Update/Response. All 6 xfail decorators removed from `tests/test_demo_seeder.py`; tests now pass. Tenant isolation test rewritten to use two real tenants instead of asserting empty global state. Side effect: `material_estimate` router/service (which read `job.job_type`) was silently broken with AttributeError and is now working without any code change to those files.

**Original finding (preserved for reference):**

`demo_seeder.py` passes `job_type=` and `quantity=` keyword arguments to `Job()`.
The `Job` ORM model (`app/models/job.py`) did NOT define these columns.
Migration 015 added `job_type` and `quantity` to the DB schema, but the model
was never updated. Result: `seed_demo_data()` always raised `TypeError`.
**Severity:** High — demo seeder was completely broken. New user onboarding failed
if the demo data load was triggered.
**File:** `app/services/demo_seeder.py` — all calls to `Job(job_type=...)`.
**Fix taken:** Added `job_type = Column(String)` and `quantity = Column(Float)`
to the Job model, matching migration 015.

### BUG-2: Jobs Router Date Type Mismatch (§6.5) — FIXED

**Status: FIXED in commit `83b2192` (tag `v6.2.4-bugfixes`), April 21 2026.**
Changed `start_date: str` and `end_date: str` to `start_date: date` and `end_date: date` on JobCreate and JobUpdate in `app/routers/jobs.py`. Added `date` to the `datetime` import. No router handler changes needed — Pydantic v2 transparently parses ISO date strings into `date` objects. No behavior change for valid API clients. SQLite unit tests for §6.5 Job CRUD are now unblocked. Two other string-typed date fields identified and left intentionally as-is: `scan.py:expires_at` (JWT expiry, not DB Date) and `ai_chat.py:date` (free-text LLM filter, not a DB field).

**Original finding (preserved for reference):**

`app/routers/jobs.py` used `start_date: str` in its Pydantic create schema and
passed the string directly to `Job(start_date=payload.start_date)`. SQLite
rejected string values for `Date` columns; PostgreSQL coerced them silently.
This meant job creation tests only worked against PostgreSQL (integration tier).
The schema should use `date` instead of `str` and convert with `date.fromisoformat()`.
**Severity:** Medium — did not affect production (PostgreSQL handled it), but
blocked SQLite unit tests for job creation and made the schema semantically wrong.
**File:** `app/routers/jobs.py` lines 74-75 and 225.
**Fix taken:** Schema fields changed from `str` to `date`. Pydantic v2 handles
ISO string parsing automatically — no explicit `fromisoformat()` call needed.

### BUG-3: Registration Does Not Call Demo Seeder (§6.1, §6.14) — FIXED

**Status: FIXED in commit `1cca6b5` (tag `v6.2.6-registration-seed`), April 22 2026.**
Discovered during manual end-to-end verification of BUG-1 via Swagger: registration succeeded but the new tenant landed on a completely empty dashboard (zero skills, zero employees, zero machines, zero jobs). Root cause: `register_tenant_and_user()` in `app/services/auth_service.py` omitted `tenant_id` from its return dict, causing the router's `result.get("tenant_id")` to always return None. The router's `if tenant_id:` guard evaluated False every time, silently skipping both RAG seeding (which had been no-op'ing since it shipped) and — since no demo seed call existed at all — meant demo seeding was also never wired up. Two fixes: (1) `auth_service.py` now returns `tenant_id` in the dict, (2) `routers/auth.py` has a new demo-seed try/except block mirroring the existing RAG seed block contract (per SRS §6.14: "Never breaks registration"). Six regression tests added in `tests/test_registration_seeds.py` covering the return-dict shape, seeder output by entity type, and tenant isolation.

**Original finding:**

Demo seeder function exists at `app/services/demo_seeder.py:588` and is well-tested (BUG-1 xfail tests pass after fix). But a grep for `seed_demo_data` across `app/` returned only the function definition — zero callers in production code. SRS §6.1 says "Demo data auto-seeded on registration"; SRS §6.14 says "Auto-seeded on registration for every new tenant." Neither had ever been true. Every new-tenant registration since the feature was specified landed on an empty dashboard.

**Severity:** High — user-visible UX failure on every registration. Spec-vs-code drift.
**Side effect of fix:** RAG seeding, which had been silently broken for the same root cause (missing `tenant_id` in return dict), started working simultaneously. No RAG-specific code change needed.

### BUG-4: RegisterRequest Schema Missing industry_type Field (§6.1) — FIXED

**Status: FIXED in commit `77fb429` (tag `v6.2.7-industry-type`), April 22 2026.**
Discovered during manual BUG-3 verification: new tenants registered as "fabrication" received fabrication-specific demo jobs BUT the Tenant row stored `industry_type = None`. Two related gaps: (1) `RegisterRequest` in `app/schemas/auth.py` did not declare `industry_type`, Pydantic v2 silently dropped it; frontend had been sending the field since v4.0.2 to no effect. (2) `register_tenant_and_user()` in `app/services/auth_service.py` created the Tenant without passing `industry_type` even once the schema gap was closed. Both gaps fixed: (1) added `industry_type: Literal["printing", "manufacturing", "fabrication", "field_service"] = "printing"` to `RegisterRequest`, matching the four Plan A industries in SRS §1.2 (chemical excluded, Plan B), (2) added `industry_type=payload.industry_type` to the Tenant constructor. End-to-end verified: fabrication registration now stores "fabrication" on the Tenant row; chemical returns 422 with clear validation error; omitted field defaults to "printing". Integration tests `test_jobs_api.py` and `test_assignment_service.py` updated from invalid `"general"` to valid `"printing"` fixture value. 11 new tests in `tests/test_auth_schema.py` covering validation, default, and rejection paths.

**Original finding:**

Frontend's `RegisterPayload` interface (in `frontend/src/auth/AuthContext.tsx`) has included `industry_type` since v4.0.2. `RegisterPage.tsx` sends the value from the industry picker at line 129. But `RegisterRequest` Pydantic schema only declared `email`, `password`, `company_name`, `slug`. Pydantic v2 silently drops unknown fields by default, so `payload.industry_type` was never present at the router layer. The router's `getattr(payload, "industry_type", None) or "printing"` fallback always returned `"printing"` regardless of user selection.

**Severity:** Medium — user-visible UX failure (fabrication customers got printing demo data). Silently degraded AI Copilot industry-aware terminology (SRS §6.13) since `ai_chat.py` reads `tenant.industry_type` which was stuck at None for all registrations after v4.0. Every customer that registered via the frontend has been affected.

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
| 17 | 6.5 | Create job via HTTP (string date) | Functional | job_create_http | UNBLOCKED | test_jobs_unit.py | — (BUG-2 fixed in 83b2192; follow-up session can now add the HTTP test) |
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
| 39 | 6.14 | Demo seeder creates skills | Functional | seeder_skills | PASS (BUG-1 fixed in 765d5a3) | test_demo_seeder.py | test_seeder_creates_skills |
| 40 | 6.14 | Demo seeder creates employees | Functional | seeder_employees | PASS (BUG-1 fixed in 765d5a3) | test_demo_seeder.py | test_seeder_creates_employees |
| 41 | 6.14 | Demo seeder creates machines | Functional | seeder_machines | PASS (BUG-1 fixed in 765d5a3) | test_demo_seeder.py | test_seeder_creates_machines |
| 42 | 6.14 | Demo seeder creates jobs | Functional | seeder_jobs | PASS (BUG-1 fixed in 765d5a3) | test_demo_seeder.py | test_seeder_creates_jobs |
| 43 | 6.14 | Demo seeder idempotent | Functional | seeder_idempotent | PASS (BUG-1 fixed in 765d5a3) | test_demo_seeder.py | test_seeder_is_idempotent |
| 44 | 6.14 | Demo seeder tenant isolation | Functional | seeder_isolation | PASS (BUG-1 fixed in 765d5a3) | test_demo_seeder.py | test_seeder_does_not_leak_to_other_tenant |
| 44a | 6.1, 6.14 | Registration returns tenant_id | Unit | reg_returns_tenant_id | PASS (BUG-3 fixed in 1cca6b5) | test_registration_seeds.py | test_register_returns_tenant_id |
| 44b | 6.14 | Seed invoked from registration — skills | Functional | reg_seeds_skills | PASS (BUG-3 fixed in 1cca6b5) | test_registration_seeds.py | test_seed_demo_data_produces_skills |
| 44c | 6.14 | Seed invoked from registration — employees | Functional | reg_seeds_employees | PASS (BUG-3 fixed in 1cca6b5) | test_registration_seeds.py | test_seed_demo_data_produces_employees |
| 44d | 6.14 | Seed invoked from registration — machines | Functional | reg_seeds_machines | PASS (BUG-3 fixed in 1cca6b5) | test_registration_seeds.py | test_seed_demo_data_produces_machines |
| 44e | 6.14 | Seed invoked from registration — jobs | Functional | reg_seeds_jobs | PASS (BUG-3 fixed in 1cca6b5) | test_registration_seeds.py | test_seed_demo_data_produces_jobs |
| 44f | 6.14 | Seed isolation across tenants (reg path) | Functional | reg_seed_isolation | PASS (BUG-3 fixed in 1cca6b5) | test_registration_seeds.py | test_seed_does_not_leak_to_other_tenant |
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
| 91 | 6.1 | RegisterRequest accepts printing | Unit | reg_schema_printing | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_accepts_valid_industry[printing] |
| 92 | 6.1 | RegisterRequest accepts manufacturing | Unit | reg_schema_manufacturing | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_accepts_valid_industry[manufacturing] |
| 93 | 6.1 | RegisterRequest accepts fabrication | Unit | reg_schema_fabrication | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_accepts_valid_industry[fabrication] |
| 94 | 6.1 | RegisterRequest accepts field_service | Unit | reg_schema_field_service | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_accepts_valid_industry[field_service] |
| 95 | 6.1 | RegisterRequest defaults to printing | Unit | reg_schema_default | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_defaults_to_printing_when_omitted |
| 96 | 6.1 | RegisterRequest rejects chemical | Unit | reg_schema_reject_chemical | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_rejects_invalid_industry[chemical] |
| 97 | 6.1 | RegisterRequest rejects textile | Unit | reg_schema_reject_textile | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_rejects_invalid_industry[textile] |
| 98 | 6.1 | RegisterRequest rejects uppercase | Unit | reg_schema_reject_case | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_rejects_invalid_industry[PRINTING] |
| 99 | 6.1 | RegisterRequest rejects empty string | Unit | reg_schema_reject_empty | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_rejects_invalid_industry[] |
| 100 | 6.1 | RegisterRequest rejects "general" | Unit | reg_schema_reject_general | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_rejects_invalid_industry[general] |
| 101 | 6.1 | RegisterRequest rejects wrong type (int) | Unit | reg_schema_reject_int | PASS (BUG-4 fixed in 77fb429) | test_auth_schema.py | test_rejects_wrong_type |

## Failures Detail

### BUG-1: demo_seeder.py — job_type is not a Job model attribute (FIXED)

**Resolved in commit `765d5a3` on April 21 2026.** See the "Bugs Found During Audit" section at the top of this document for full resolution detail.

**Original finding below, preserved for reference:**

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

### BUG-2: jobs router start_date/end_date — string not converted to date (FIXED)

**Resolved in commit `83b2192` on April 21 2026.** See the "Bugs Found During Audit" section at the top of this document for full resolution detail.

**Original finding below, preserved for reference:**

**SRS mapping:**
SRS §6.5: "Job Definition & Management — create job with required fields."

**Analysis:** `JobCreate` schema uses `start_date: str`. PostgreSQL accepts ISO
date strings silently. SQLite rejects them. The router should use `date` type
and do `date.fromisoformat(val)` before the DB insert. Not a spec violation in
production, but a fragility.

**Verdict:** Real fragility. Low severity in production. Blocks SQLite unit tests.

### BUG-3: registration does not call seed_demo_data (FIXED)

**Resolved in commit `1cca6b5` on April 22 2026.** See the "Bugs Found During Audit" section at the top of this document for full resolution detail.

**Discovery trace:**
Manual end-to-end verification of BUG-1 via Swagger:
- Registration of `bug1test@test.com` returned 200.
- Python REPL showed `tenant.id=20` with 0 skills, 0 employees, 0 machines, 0 jobs.
- `Select-String -Path app -Pattern "seed_demo"` returned only the function definition in `app/services/demo_seeder.py` — zero callers in production code.

**SRS mapping:**
SRS §6.1: "Demo data auto-seeded on registration — industry-specific jobs, employees, machines, skills, steps and assignments. Idempotent. Never breaks registration."
SRS §6.14: "Auto-seeded on registration for every new tenant."

**Analysis:** Spec violation. The seeder function was implemented correctly (BUG-1 fix proved that) but was never invoked from any production code path. Every new tenant since the feature was specified has landed on a blank dashboard. Root cause in `auth_service.py`: `register_tenant_and_user()` omitted `tenant_id` from its return dict, so the router's `result.get("tenant_id")` always returned None; the router's `if tenant_id:` guard for RAG seeding silently evaluated False; demo seeding was not wired up at all.

**Verdict:** Real bug. High severity. Spec-vs-code drift, discoverable only by end-to-end verification (unit tests all passed because they called the seeder function directly, not through the HTTP registration flow).

### BUG-4: RegisterRequest schema missing industry_type + not persisted on Tenant (FIXED)

**Resolved in commit `77fb429` on April 22 2026.** See the "Bugs Found During Audit" section at the top of this document for full resolution detail.

**Discovery trace:**
Manual end-to-end verification of BUG-3 fix via Swagger:
- Registration with `"industry_type": "fabrication"` returned 201 and seeded fabrication-specific demo jobs (proof BUG-3 fix worked).
- Python REPL showed `tenant.industry_type = None` on the Tenant row.
- Investigation revealed two related gaps: (1) `RegisterRequest` schema missing the field, (2) `Tenant()` constructor in `register_tenant_and_user()` not passing `industry_type`.

**SRS mapping:**
SRS §6.1: "Two-step registration: Step 1 selects industry vertical (5 options with icons and descriptions)."
SRS §1.2: Four active Plan A industries — printing, manufacturing, fabrication, field_service. Chemical is Plan B.
SRS §6.13: "Industry-aware system prompt (v4.0.8): injects correct terminology per tenant industry_type."

**Analysis:** Every customer that registered via the frontend since v4.0.2 has been affected. User-picked industry was silently discarded by Pydantic (unknown field dropped) AND silently not persisted on the Tenant row (constructor call omitted it). AI Copilot's industry-aware terminology (`ai_chat.py` reads `tenant.industry_type`) has been getting None for all post-v4.0 tenants; it would have been falling back to default behavior. Fabrication / manufacturing / field_service customers all saw printing demo data.

**Verdict:** Real bug. Medium severity in terms of operational failure (app still works), but significant user-experience regression and multi-subsystem silent degradation. Spec-vs-code drift across three layers: schema, service, and Tenant persistence.

## Gaps NOT Covered By New Tests

| SRS § | Feature | Reason |
|-------|---------|--------|
| 6.6 | Step Intelligence | HTTP layer only; each test needs a real job row first. BUG-2 (which blocked this) was fixed in `83b2192` — follow-up session can now add the HTTP-layer tests. Covered indirectly by test_scheduler_engine.py (step sequencing). |
| 6.7 | QR Scan public endpoint | Endpoint reads from DB (job lookup). Needs PostgreSQL integration test. Scan page has no auth — can't use conftest client fixture without a real job row. |
| 6.13 | AI Copilot web endpoint (Groq mock) | Would need `unittest.mock.patch` on the Groq SDK client. Feasible in a follow-up. Not added to keep this audit to SRS-vs-code drift, not Groq interaction logic. |
| 6.15 | Getting Started Onboarding | `localStorage` state in the React frontend. No backend component. Cannot test in pytest. |
| 6.23 | Industry-Aware Dynamic Labels | `useLabels()` is a React hook in `IndustryContext.tsx`. No backend component. Verified by grep: `grep -r '"Jobs"\|"Machines"\|"Employees"' frontend/src/pages/` returns empty. |

## Housekeeping Items Identified (Non-Bug, Tracked for Future Sessions)

These are code hygiene improvements surfaced during this audit and its follow-up sessions. None are bugs; all are safe to defer.

| Item | Description | Effort |
|------|-------------|--------|
| Pydantic v1 `class Config` in `gantt.py` | `GanttJob(BaseModel)` uses the deprecated `class Config` pattern. Will break in Pydantic v3. | ~10 min |
| Alembic `path_separator` warning | `env.py` uses legacy space/comma/colon splitting for `prepend_sys_path`. Add explicit `path_separator=os`. | ~5 min |
| Router `getattr` fallback in `auth.py` | After BUG-4 fix, `getattr(payload, "industry_type", None) or "printing"` is belt-and-suspenders. Schema default already handles the missing case. Safe to remove. | ~5 min |
| Dev tenants in test DB (ids 19–24) | Test tenants from BUG-1/BUG-3/BUG-4 verification. Delete if desired; harmless if left. | ~2 min |
| `ZETAOPS_*_PROMPT.md` files at repo root | Six prompt files from audit + four bug-fix sessions. Decide: commit under `docs/prompts/` or add to `.gitignore`. | ~5 min |
| Stray leading `"` on two commit messages | Commits `765d5a3` (BUG-1) and `ca21df7` (datetime cleanup) have a stray `"` at the start of their messages (PowerShell quoting accident). Pushed; not worth history rewrite. | Won't fix |

## Appendix — New Test Files Added

| File | SRS § | Description |
|------|-------|-------------|
| tests/test_employees.py | 6.2, 6.19 | Employee CRUD (9 tests) + source field (5 tests) + worker_type field (5 tests) |
| tests/test_machines.py | 6.3, 6.19 | Machine CRUD (8 tests) + source field (5 tests) |
| tests/test_jobs_unit.py | 6.5 | Job model defaults (5 tests) + tenant isolation (2 tests) + original dates (3 tests) + HTTP auth guards (4 tests) |
| tests/test_availability_engine.py | 6.8 | Date range utility (4 tests) + skill level ranking (8 tests) + effective availability (5 tests) |
| tests/test_material_estimate.py | 6.10 | Confidence levels (4 tests) + confidence notes (4 tests) + estimate logic (6 tests) |
| tests/test_demo_seeder.py | 6.14 | 6 tests (originally xfail per BUG-1, now passing after fix in `765d5a3`) + 1 rewritten tenant isolation test using two real tenants |
| tests/test_rag_pipeline.py | 6.22 | Valid industries (6 tests) + seeding (6 tests) + load context (5 tests) |
| tests/test_csv_import.py | 6.16 | CSV parsing (3 tests) + file dispatch (2 tests) + employee import (4 tests) + machine import (3 tests) |
| tests/test_registration_seeds.py | 6.1, 6.14 | 6 tests added during BUG-3 fix: register_returns_tenant_id + 4 "seeder produces {entity}" tests + cross-tenant isolation |
| tests/test_auth_schema.py | 6.1 | 11 tests added during BUG-4 fix: 4 valid industry accepts (parametrized) + 1 default + 5 rejection cases (parametrized) + 1 wrong-type reject |
| docs/test_audit/srs_to_test_map.md | all | SRS-to-test mapping for all 23 features |

## Release Ladder — Commits Tracked in This Report

| Tag | Date | Content |
|-----|------|---------|
| `v6.2.2-test-recovery` | 2026-04-20 | SQLite StaticPool fix in conftest.py (pre-audit baseline) |
| `v6.2.3-test-audit` | 2026-04-21 | 105 new tests, BUG-1 + BUG-2 documented |
| `v6.2.4-bugfixes` | 2026-04-21 | BUG-1 + BUG-2 fixed |
| `v6.2.5-cleanup` | 2026-04-21 | `datetime.utcnow()` → `datetime.now(timezone.utc)` sweep (10 files, 36 call sites) |
| `v6.2.6-registration-seed` | 2026-04-22 | BUG-3 fixed |
| `v6.2.7-industry-type` | 2026-04-22 | BUG-4 fixed |
