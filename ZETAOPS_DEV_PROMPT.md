# ZETAOPS_DEV_PROMPT.md
# ZetaOps Copilot - Master Development Prompt
# Version: 6.0 — updated Apr 8 2026. Reflects revised version roadmap with
#           manager input flow, Day 1 simple table, ERP connector strategy,
#           4-vertical MSME focus, language support, RAG architecture.
# Paste this at the start of every Claude session involving code changes.
# =============================================================================

You are working on ZetaOps Copilot — a multi-tenant production scheduling SaaS
for Indian MSMEs. Stack: FastAPI + SQLAlchemy 2.0 (backend), React 18 +
TypeScript + Vite + TailwindCSS (frontend), PostgreSQL, Alembic migrations.

PRODUCT STRATEGY (read before writing any code):
- One engine. Two entry points. Same briefing.
- Manager feeds the system (WhatsApp input channel, 7:00am).
- Owner gets the signal (WhatsApp output channel, 7:15am).
- ERP replaces WhatsApp input when the customer has one (v7.0).
- Plan A (MSME, no ERP): WhatsApp-first + Day 1 simple table.
- Plan B (mid-market, has ERP): Python connector feeds same engine.
- 4 active verticals: printing, manufacturing, fabrication, field_service.
- Chemical / process industry excluded from Plan A — batch-first, different entry model.
- source field on Employee and Machine (manual | whatsapp | erp_sync) is the
  structural decision that keeps v7.0 a sprint not a rewrite. Never remove it.

Repo:      https://github.com/gg0code/msme-resource-scheduler
Local:     C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler
Backend:   backend/
Frontend:  frontend/
Branches:  v5-whatsapp (ACTIVE — all new work), v4-dev (FROZEN — bug fixes only)
           v6-ai (CREATE from v5-whatsapp when starting v6.0 work)
Current:   v5-whatsapp tag v5.12-role-language (build in progress)
Migration: head = 022 (023 reserved for v5.16 source field on Employee + Machine)

Test tenant: what@what.what / qazx1234 / tenant_id=12 / phone: +919876543210


=============================================================================
SECTION 1 - THE CORE RULE
=============================================================================

Code is not done until it passes ALL verification gates. "Works in dev" is not done.

  Frontend:  npx tsc --noEmit          - zero errors, no exceptions
  Backend:   python -m py_compile      - zero errors, no deprecated patterns
  Tests:     pytest tests/ -m "not integration" -v  - zero failures
  Migration: alembic heads             - exactly ONE head (currently: 022)


=============================================================================
SECTION 2 - STACK REFERENCE
=============================================================================

| Layer         | Technology                                        |
|---------------|---------------------------------------------------|
| Backend       | FastAPI, Python 3.14, Uvicorn                     |
| ORM           | SQLAlchemy 2.0, Alembic migrations (append-only)  |
| Database      | PostgreSQL (psycopg2-binary), Docker container    |
| Auth          | JWT (python-jose), bcrypt direct (not passlib)    |
| Frontend      | React 18 + TypeScript + Vite, port 5173           |
| Data fetching | TanStack React Query (useQuery, useMutation)      |
| Styling       | Tailwind CSS only (lucide-react for icons)        |
| AI Copilot    | Groq SDK - Llama 3.3 70B                         |
| WhatsApp      | Interakt API (WHATSAPP_MOCK_MODE=True in dev)     |
| Scheduling    | APScheduler (AsyncIOScheduler) for alerts         |
| Excel/CSV     | openpyxl (backend), papaparse (frontend)          |
| Voice Notes   | OpenAI Whisper API (v5.13+)                      |
| RAG           | Flat files MVP (v6.1), pgvector migration (v6.3) |


=============================================================================
SECTION 3 - ARCHITECTURE FACTS
=============================================================================

BACKEND
- All routers:   backend/app/routers/
- All models:    backend/app/models/
- All services:  backend/app/services/
- Auth deps:     backend/app/core/dependencies.py - get_current_user, require_role
- DB session:    backend/app/database.py - SessionLocal, get_db
- Settings:      backend/app/config.py - all secrets from .env via pydantic-settings
- Every router registered in main.py with explicit prefix (see Section 5)
- Every DB query must include tenant_id filter - no exceptions, ever
- Knowledge graph: backend/app/knowledge_graph/ - schema_context.py, context_builder.py
- RAG data:      backend/rag_data/_templates/{industry}/ and rag_data/{tenant_id}/

FRONTEND
- Pages:         frontend/src/pages/
- Components:    frontend/src/components/
- API files:     frontend/src/api/api_*.ts (one file per resource)
- API constants: frontend/src/api/api_endpoints.ts (single source of truth)
- API client:    frontend/src/api/client.ts (Axios with JWT auto-refresh)
- Types:         frontend/src/types/types_index.ts (only types file - never create another)
- Industry cfg:  frontend/src/config/industries/ (types.ts + one file per industry)
- Industry ctx:  frontend/src/context/IndustryContext.tsx
- Scheduler UI:  frontend/src/scheduler/ (SchedulerContext, useScheduler, SchedulerToolbar)
- Auth:          frontend/src/auth/AuthContext.tsx

SCHEDULER ENGINE
- Pure Python: app/scheduler/engine.py - zero SQLAlchemy, zero DB calls
- Takes and returns dataclasses only
- All DB loading happens in scheduler_router.py before calling run_scheduler()
- Never add DB imports to engine.py

WHATSAPP SERVICES
- All WhatsApp services use sync SQLAlchemy Session - never AsyncSession
- Async/sync bridge: run_in_executor in whatsapp_bridge.py
- Router self-prefixes at /api/v1/whatsapp - registered in main.py with no prefix
- WHATSAPP_MOCK_MODE=True in dev - logs [MOCK ALERT] instead of real sends
- Conflict detection uses schedule_entries GROUP BY count - NOT Job.has_conflict
- Language detection: detect_language() in whatsapp_responses.py
- All outbound strings in 3 languages: whatsapp_responses.py RESPONSES dict

LANGUAGE SUPPORT (v5.12+)
- Detect language of inbound message once per message: detect_language(text)
- Returns: 'hindi' | 'hinglish' | 'en'
- Hindi = Devanagari Unicode range [\u0900-\u097F]
- Hinglish = common Hindi marker words in Latin script (kya, hai, bhai, aaj...)
- English = everything else / default
- AI responses: LANGUAGE_INSTRUCTION in _build_system_prompt() handles mirroring
- Hardcoded responses: get_response(key, lang, **kwargs) from whatsapp_responses.py
- Never ask user to set language preference - detect and mirror automatically

RAG ARCHITECTURE (v6.1+)
- Option B folder structure - industry templates + tenant overrides:
    backend/rag_data/_templates/{industry}/  <- default knowledge per industry
    backend/rag_data/{tenant_id}/            <- tenant-specific files (seeded at registration)
- 4 active verticals: printing, manufacturing, fabrication, field_service
- Chemical excluded from Plan A — batch-first vertical, different entry model
- At registration: seed_rag_from_template(tenant_id, industry_type) in rag_service.py
- At query time: read tenant folder, inject into _build_system_prompt()
- Never compute logic in LLM - pass structured JSON, LLM converts to explanation
- Migration path: flat files (v6.1) -> pgvector (v6.3) - folder structure unchanged


=============================================================================
SECTION 4 - KEY ROUTERS AND MODELS
=============================================================================

ROUTERS (backend/app/routers/)

| Router              | Prefix           | Purpose                            |
|---------------------|------------------|------------------------------------|
| auth.py             | /auth            | register, login, refresh, logout   |
| jobs.py             | /api/jobs        | CRUD + scheduler trigger           |
| assignments.py      | /api/assignments | Job-to-resource links              |
| gantt.py            | /api/gantt       | Timeline data for Gantt view       |
| dashboard.py        | /api/dashboard   | KPI aggregates                     |
| scheduler_router.py | /api/scheduler   | Auto-schedule engine               |
| ai_chat.py          | /api/ai          | AI copilot chat                    |
| whatsapp.py         | (no prefix)      | WhatsApp pipeline, self-prefixed   |
| availability.py     | /api/availability| Resource conflict checking         |
| unavailability.py   | /api             | Employee leaves, machine downtimes |
| timer.py            | /api/timer       | Production timer                   |
| import_csv.py       | /api/import      | Bulk CSV upload                    |
| scan.py             | /api             | QR scan - always public, no auth   |

KEY MODELS (backend/app/models/)

- Job            - production order. Fields: is_locked, original_start_date,
                   original_end_date, timer_status, order_value, misc_cost
- JobAssignment  - links Job to Employee or Machine with allocation_pct
- ScheduleEntry  - one row per scheduled day per job (in scheduler_router.py)
- PhoneTenantMap - WhatsApp phone to tenant mapping. Fields: phone_role
                   (owner | manager | operator)
- Employee       - hourly_rate, overtime_rate, base_availability_pct, Skills M2M,
                   worker_type (permanent | contractor),
                   source (manual | whatsapp | erp_sync) — added migration 023
- Machine        - source (manual | whatsapp | erp_sync) — added migration 023
- Tenant         - root of multi-tenancy, plan, AI usage counters, industry_type

SOURCE FIELD RULE (v5.16+):
  Never hardcode assumptions that data comes from WhatsApp only.
  Every Employee and Machine record has source field.
  Values: 'manual' (Day 1 table), 'whatsapp' (captured via conversation),
          'erp_sync' (v7.0 ERP connector).
  This field costs one column now. Removing it forces a rewrite at v7.0.


=============================================================================
SECTION 5 - API PATH RULES
=============================================================================

ALL API paths in the frontend are defined in ONE file only:
  frontend/src/api/api_endpoints.ts

NEVER hardcode any path string anywhere in the project.
  CORRECT:  apiClient.get(JOBS.list)
  WRONG:    apiClient.get('/api/jobs/')

IMPORT DEPTH TABLE - memorise, never guess:

  File location                     | Import api_endpoints.ts as
  ----------------------------------|----------------------------
  src/api/*.ts                      | './api_endpoints'
  src/pages/*.tsx                   | '../api/api_endpoints'
  src/components/*.tsx              | '../api/api_endpoints'
  src/components/common/*.tsx       | '../../api/api_endpoints'
  src/scheduler/*.ts                | '../api/api_endpoints'
  src/auth/*.tsx                    | '../api/api_endpoints'
  src/context/*.tsx                 | '../api/api_endpoints'

BACKEND PREFIX RULES for main.py registration:
  - Standard routers (paths are "/", "/{id}"):     prefix="/api/routername"
  - Routers where path already has resource name:  prefix="/api"
    (steps, unavailability, scan, features, scheduler_router)
  - auth router:      prefix="" (routes at /auth/*)
  - whatsapp router:  prefix="" (self-prefixes at /api/v1/whatsapp)
  - ai_chat:          prefix="/api/ai"

VERIFY NEW ENDPOINT AFTER REGISTERING:
  python -c "
  from app.main import app
  routes = [(sorted(r.methods)[0], r.path) for r in app.routes if hasattr(r, 'methods')]
  for m, p in sorted(routes, key=lambda x: x[1]): print(m, p)
  "
  Scan for doubled segments like /api/jobs/jobs/ or missing /api/ prefix.


=============================================================================
SECTION 6 - BACKEND DESIGN PRINCIPLES
=============================================================================

1. TENANT ISOLATION IS MANDATORY
   Every DB query must filter by tenant_id. Pattern:
     db.query(Model).filter(Model.tenant_id == current_user.tenant_id)
   Missing tenant_id is a security vulnerability, not a style issue.

2. BACKEND COMPUTES, FRONTEND DISPLAYS
   Scheduling, cost calculations, conflict detection - all on backend.
   Frontend only renders what backend returns.

3. SECRETS NEVER IN CODE
   All from .env via settings. Never hardcode any key, URL, or password.
   Settings uses extra="ignore" - unknown .env keys do not cause errors.

4. MIGRATIONS ARE APPEND-ONLY
   Never edit a migration that has been run. Always create a new one.
   Chain must always have exactly ONE head.
   Naming: NNN_describe_what_changes.py (next after 022).
   New NOT NULL columns on existing tables use server_default, not default.
   Always write both upgrade() and downgrade().

5. CONFLICT DETECTION IS CENTRALISED
   One function: _has_scheduling_conflict(job, entry_count_map)
   Used in: dashboard.py, gantt.py, jobs.py, whatsapp_alerts.py
   Logic: schedule_entries count < expected days = conflict
   Never query Job.has_conflict - that column does not exist.

6. N+1 QUERIES ARE FORBIDDEN
   Never call a DB query inside a loop. Build a map first:
     rows = db.execute(select(Model.job_id, func.count()).group_by(...)).all()
     count_map = {row[0]: row[1] for row in rows}
   Use selectinload for relationships - never lazy-load inside a loop.

7. PYDANTIC V2 EVERYWHERE
   model_config = ConfigDict(from_attributes=True)  not  class Config
   model_validate()  not  from_orm()
   @field_validator  not  @validator
   datetime.now(timezone.utc)  not  datetime.utcnow()

8. FEATURE FLAGS GATE EVERYTHING
   New features start with flag=False in features_config.py.
   Backend: require_feature("flag_name") at top of gated endpoints.
   Frontend: check useFeatureFlags() before rendering.

9. PLAN LIMITS ARE DUAL-LAYER
   Backend: HTTP 402 when limit reached via check_plan_limit().
   Frontend: LimitedButton + PlanLimitBanner disable UI before the API call.

10. SCAN PAGE IS ALWAYS PUBLIC
    /scan has no auth. Never add authentication to ScanPage.tsx or /api/scan/*.

11. AI NEVER COMPUTES LOGIC
    Pass structured JSON to LLM. LLM converts to human explanation only.
    Never ask LLM to calculate costs, quantities, or scheduling decisions.
    Schema context + RAG data injected into system prompt before every AI query.

12. WHATSAPP ROLE ACCESS MATRIX
    owner    - everything allowed
    manager  - view schedule, mark absent, check machine status
               BLOCKED: financial data, create job, delete job
    operator - view own assignments today only
               BLOCKED: everything else
    Role check happens in detect_write_intent() BEFORE AI is called.
    Blocked actions never reach the AI layer.

13. RAG DATA IS TENANT-ISOLATED
    Always read from rag_data/{tenant_id}/ - never from another tenant folder.
    Seed at registration from rag_data/_templates/{industry_type}/.
    If schema_context.py is updated (new migration), update it in same commit.


=============================================================================
SECTION 7 - FRONTEND DESIGN PRINCIPLES
=============================================================================

11. TYPESCRIPT STRICT MODE - ZERO ERRORS
    npx tsc --noEmit must show ZERO errors before any commit.
    No any types. No unused imports. No missing return types.
    All types in frontend/src/types/types_index.ts - never create another file.
    Industry config types live in src/config/industries/types.ts only.

12. QUERY KEYS ARE CONTRACTS
    Consistent keys across the entire app:
      ['employees'], ['machines'], ['skills'], ['jobs'], ['dashboard'],
      ['sched-jobs'] (Gantt auto-refresh after scheduler runs)
    Delete mutations invalidate BOTH the resource key AND ['dashboard'].
    Never change a query key without searching for all usages first.

13. INDUSTRY LABELS - NEVER HARDCODED
    Never hardcode "Jobs", "Employees", "Machines" in UI text.
    Use: const labels = useLabels() then labels.jobs, labels.employees etc.
    CSS theme colours from CSS variables (--brand-primary etc), not inline Tailwind.
    IndustryContext reads user.industry_type from AuthContext at login.
    Provider stack order: QueryClient > Auth > FeatureFlags > Industry > Scheduler

14. API FILES USE UNDERSCORE PREFIX
    api_employees.ts, api_machines.ts, api_jobs.ts etc.
    Import as '../api/api_employees' not '../api/employees'.

15. COMPONENT HIERARCHY - NO CIRCULAR IMPORTS
    pages/      imports from: components/, api/, hooks/, context/, types/
    components/ imports from: api/, context/, types/ - NEVER from pages/
    hooks/      imports from: api/ only

16. PROVIDER STACK ORDER IN App.tsx
    QueryClient > Auth > FeatureFlags > Industry > Scheduler > Onboarding > Layout
    Never add a Provider inside a page component.

17. NO NON-ASCII IN SOURCE FILES
    Never use em dash, en dash, box-drawing chars, or curly quotes in source files.
    Python file headers: # comments only. Never docstrings as file headers.

18. REGISTER PAGE AUTH BUG - KNOWN ISSUE (fix in v6.2)
    RegisterPage.tsx line 136 uses localStorage.setItem('access_token') directly.
    This bypasses AuthContext.register(). Fix: call register() from AuthContext
    instead of apiClient.post() + localStorage directly.


=============================================================================
SECTION 8 - TYPESCRIPT HYGIENE
=============================================================================

- Never use implicit any - every parameter and return must be typed
- catch (err: unknown) with: const msg = err instanceof Error ? err.message : String(err)
- Never leave unused imports - they are compile errors in strict mode
- Use import type for type-only imports
- Never use React.FC - plain function signatures with explicit prop types
- Import hooks directly: import { useState } from 'react'
- Event handler types must be explicit:
    (e: React.ChangeEvent<HTMLInputElement>)
    (e: React.FormEvent<HTMLFormElement>)
    (e: React.MouseEvent<HTMLButtonElement>)
- useRef must specify type: useRef<HTMLDivElement>(null)
- React.CSSProperties for inline style objects


=============================================================================
SECTION 9 - PYTHON HYGIENE
=============================================================================

DATETIME
  Always: datetime.now(timezone.utc)
  Never:  datetime.utcnow()
  Column defaults: default=lambda: datetime.now(timezone.utc)

AUTH IMPORTS
  get_current_user, require_role - always from app.core.dependencies
  get_db                         - always from app.database

SQLALCHEMY
  Every tenant data query must filter by tenant_id
  ForeignKey on tenant_id must include ondelete="CASCADE"
  Sync functions use Session - async functions use AsyncSession - never mix
  Never await sync Session methods
  Raw SQL loaders (text()) for data reads inside scheduler loops - prevents
  SQLAlchemy identity map contamination when job dates are updated mid-run

FASTAPI
  Use lifespan context manager, not @app.on_event("startup"/"shutdown")
  Feature flag guard: require_feature("flag") at top of gated endpoints

FILE HEADERS - MANDATORY ON EVERY SERVICE/ROUTER FILE
  # filename.py - Version X.Y
  # Branch: both / v4-dev / v5-whatsapp / v6-ai
  # FILE PURPOSE
  # WHO CALLS THIS FILE
  # WHAT THIS FILE CALLS
  # KEY DESIGN DECISIONS

FUNCTION DOCSTRINGS - MANDATORY FORMAT
  Called by: who calls this function
  Calls:     what this function calls
  What it does: behaviour description
  Side effects: DB writes, external calls, or "None - pure function"


=============================================================================
SECTION 10 - FILE AND FUNCTION DOCUMENTATION STANDARD
=============================================================================

Every backend service and router file MUST have this header block.
No exceptions. When a file is updated, bump the version number.

PYTHON FILE HEADER FORMAT:
  # filename.py - Version X.Y
  # Branch: both | v4-dev | v5-whatsapp | v6-ai
  #
  # FILE PURPOSE
  # One sentence: what this file does and why it exists.
  #
  # WHO CALLS THIS FILE
  # List every caller with the specific function or endpoint they call:
  #   app/main.py           - calls start_scheduler() on startup
  #   app/routers/jobs.py   - calls compute_cost() on job save
  #   POST /api/scheduler/run - entry point from frontend
  #
  # WHAT THIS FILE CALLS
  # List every dependency with what is used from it:
  #   app/database.py          - SessionLocal, get_db
  #   app/models/job.py        - Job, JobAssignment
  #   app/services/cost.py     - compute_tentative_cost()
  #   httpx                    - POST to Interakt API (production only)
  #
  # KEY DESIGN DECISIONS
  # Explain non-obvious architectural choices so the next developer
  # does not undo them accidentally.

PYTHON FUNCTION DOCSTRING FORMAT:
  Every function (public and private) must have a docstring with these fields.

  def my_function(...):
      """
      One sentence: what this function does.

      Called by:   who calls this function and in what context
      Calls:       what this function calls
      Args:
          param1:  what it is, valid range or constraints
      Returns:
          what is returned, shape, or None if side-effect only
      Side effects:
          DB writes, external HTTP calls, logging, or "None - pure function"
      """

WHEN TO WRITE/UPDATE DOCUMENTATION:
  - New file created: write full header and all docstrings before first commit
  - Existing file modified: update any docstrings affected by the change
  - Function added to existing file: add docstring immediately
  - Called-by changes: update the "Called by" section of the affected function
  - Never leave a function without a docstring if it is longer than 10 lines

CHECKLIST BEFORE COMMITTING A FILE:
  - [ ] File header present with version, branch, purpose, who calls, what calls
  - [ ] Version number bumped from previous version
  - [ ] Every public function has a docstring
  - [ ] Every private function longer than 10 lines has a docstring
  - [ ] "Called by" sections are accurate (no stale callers listed)
  - [ ] Side effects accurately stated (not left as "None" if there are writes)


=============================================================================
SECTION 11 - PRE-COMMIT CHECKLIST (run in order, skip none)
=============================================================================

STEP 1 - TYPESCRIPT
  cd frontend && npx tsc --noEmit
  MUST: zero output = zero errors

STEP 2 - BACKEND SYNTAX
  cd backend
  python -m py_compile app/main.py app/routers/*.py app/models/*.py app/services/*.py
  MUST: no output = all clean

STEP 3 - IMPORT CHECK
  python -c "from app.main import app; print('imports clean')"

STEP 4 - PYTEST
  pytest tests/ -m "not integration" -v
  MUST: all unit tests pass, zero failures

STEP 5 - MIGRATION CHAIN
  alembic heads
  MUST: exactly one revision (022 or latest)

STEP 6 - DIFF REVIEW
  git diff HEAD
  For each changed file verify:
  - Imports added match imports removed
  - No dead variables left
  - No old column names referenced (e.g. has_conflict)
  - Version number in file header bumped
  - If a function was removed, confirm no other file still calls it
  - "Called by" sections updated for any function whose callers changed

STEP 7 - DOCUMENTATION CHECK
  Every changed backend file must have:
  - File header with version, branch, purpose, who calls, what calls
  - Every new or modified function has a docstring
  - Version number bumped in header

STEP 8 - DEAD CODE AUDIT
  No hardcoded API paths:   grep -r "'/api/" frontend/src/    (must be empty)
  No hardcoded secrets:     grep -r "sk-ant\|gsk_" frontend/src/
  No debug files:           remove debug_*.py, check_*.py, scratch files
  No hardcoded UI labels:   grep -r '"Jobs"\|"Machines"\|"Employees"' frontend/src/pages/

STEP 9 - ROUTE CONSISTENCY
  Every file in frontend/src/pages/ must have a route in App.tsx
  Every new API endpoint must have a constant in api_endpoints.ts
  Every new React Context Provider must be in the App.tsx provider stack

STEP 10 - SCHEMA CONTEXT SYNC (v6.0+)
  If migration added new table or FK:
  Update backend/app/knowledge_graph/schema_context.py in same commit.


=============================================================================
SECTION 12 - GIT WORKFLOW
=============================================================================

BRANCH STRATEGY
  v4-dev       - FROZEN. Bug fixes only. No new features ever.
  v5-whatsapp  - ACTIVE. All WhatsApp + core features. Current working branch.
  v6-ai        - Create from v5-whatsapp when starting v6.0 work.
  master       - Release only. Never commit directly to master.

BRANCH RULES
  - All new work goes on v5-whatsapp (or v6-ai for AI features)
  - v4-dev is a museum - touch only if a customer on v4 reports a critical bug
  - v6-ai branch: git checkout -b v6-ai v5-whatsapp (create when ready)
  - Do NOT merge v4-dev into v5-whatsapp unless critical bug fix is confirmed missing

COMMIT MESSAGE FORMAT
  <type>: <description> (72 chars max)
  feat / fix / docs / refactor / test / chore / perf / migration

COMMIT SEQUENCE
  git add -A
  git status && git diff --stat       # review before committing
  git commit -m "type: description"
  git push origin v5-whatsapp

TAGGING
  Format:  vX.Y-feature-name
  Example: git tag -a v5.12-role-limiting -m "v5.12 role limiting + language support"
  Push:    git push origin tagname

VERSIONS.md - cross-branch map (keep updated):
  v4.0.11  <-> v5.9-scheduler-v3    (scheduler v3, gap viz, Apr 2026)
  v4.0.10  <-> v5.8-frontend-clean  (frontend audit)

NEVER IN GIT
  .env files, __pycache__/, node_modules/, *.pyc
  debug_*.py, check_*.py, scratch files, log files, API keys
  rag_data/{tenant_id}/  (tenant data is not committed - add to .gitignore)
  rag_data/_templates/   (templates ARE committed - they are code)


=============================================================================
SECTION 13 - TESTING RULES
=============================================================================

BACKEND UNIT TESTS
  pytest tests/ -m "not integration" -v  - must pass on every commit, no DB needed
  conftest.py must patch PG types (ARRAY, JSONB) to JSON for SQLite compat
  pytest.ini must exclude integration marker from default run
  New engine logic must cover: priority ordering, locked entries, sequential gate,
  deadline enforcement

BACKEND INTEGRATION TESTS
  pytest tests/ -m integration -v  - run against live DB before tagging a version
  Requires TEST_DATABASE_URL in .env

FRONTEND
  npx tsc --noEmit before every commit - zero errors is the only acceptable state
  After merge conflict resolution: reload app, check console, verify SVG renders
  After backend schema change: check browser console for API shape errors

WHATSAPP ALERTS TESTING
  PowerShell: Invoke-WebRequest -Method POST "http://localhost:8000/api/v1/whatsapp/trigger-dev-alerts?alert_type=all"
  Or Swagger: http://localhost:8000/docs -> trigger-dev-alerts -> Try it out
  Watch uvicorn logs for [MOCK ALERT] lines
  Verify all three: briefing, delays, conflicts fire without errors

ROLE LIMITING TESTS (v5.12+)
  pytest tests/test_role_limiting.py -v
  Must cover: owner allowed, manager blocked on financial, operator blocked on all
  except own assignments

LANGUAGE DETECTION TESTS (v5.12+)
  pytest tests/test_language_detection.py -v
  Must cover: Hindi (Devanagari), Hinglish (marker words), English (default)


=============================================================================
SECTION 14 - DEV SESSION STARTUP
=============================================================================

TERMINAL 1 - BACKEND:
  cd C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler\backend
  venv\Scripts\activate
  alembic upgrade head
  alembic heads                      # must show: 022 (single head)
  python -c "from app.main import app; print('imports clean')"
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

  Watch for: "Application startup complete", "WhatsApp alert scheduler started"

TERMINAL 2 - FRONTEND:
  cd C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler\frontend
  npx tsc --noEmit                   # fix any errors before starting
  npm run dev

  Watch for: "VITE ready" at http://localhost:5173

BROWSER:
  http://localhost:5173              # app
  http://localhost:8000/docs         # API explorer

PORTS REFERENCE:
  Frontend:   http://localhost:5173
  Backend:    http://localhost:8000
  API docs:   http://localhost:8000/docs
  PostgreSQL: localhost:5432


=============================================================================
SECTION 15 - COMMON ERRORS AND FIXES
=============================================================================

ERROR: "uvicorn: command not found"
FIX:   venv\Scripts\activate

ERROR: "relation 'tenants' does not exist"
FIX:   alembic upgrade head

ERROR: "FATAL: password authentication failed"
FIX:   Check DATABASE_URL in backend/.env

ERROR: "Failed to resolve import '../api/employees'"
FIX:   Change to '../api/api_employees' (underscore prefix)

ERROR: tsc "Property 'X' does not exist on type 'Job'"
FIX:   Add field X to Job interface in frontend/src/types/types_index.ts

ERROR: Frontend shows blank white screen
FIX:   Check browser console. Check backend on port 8000.
       Check VITE_API_BASE_URL in frontend/.env.local

ERROR: AI Copilot shows "temporarily busy"
FIX:   Check GROQ_API_KEY in backend/.env

ERROR: curl fails in PowerShell
FIX:   Use: Invoke-WebRequest -Method POST "http://localhost:8000/api/..." | Select-Object -ExpandProperty Content

ERROR: Merge conflict after git merge v4-dev
FIX:   Resolve file by file. GanttPage.tsx: keep both ReactMouseEvent alias (v5)
       AND useQuery import (v4). git add <file> && git commit

ERROR: "Multiple head revisions"
FIX:   alembic merge heads -m "merge heads" && alembic upgrade head

ERROR: useLabels() returns undefined
FIX:   Check IndustryContext is in provider stack in App.tsx above the component.
       Check user.industry_type is returned from /auth/me endpoint.

ERROR: RAG context not injecting
FIX:   Check rag_data/{tenant_id}/ folder exists and has .txt files.
       Check seed_rag_from_template() was called at registration.
       Check _build_system_prompt() reads from correct tenant folder.


=============================================================================
SECTION 16 - VERSION ROADMAP
=============================================================================

CORE PRINCIPLE:
  V5 = WhatsApp-first product for Indian MSMEs
  V6 = AI-first intelligent platform
  V7 = ERP-connected mid-market platform

  One engine. Two entry points. Same briefing.
  Manager feeds the system. Owner gets the signal.
  ERP replaces WhatsApp input when the customer has one.

  Everything that makes WhatsApp work better belongs in V5.
  Everything that makes AI smarter belongs in V6.
  Everything that opens the ERP pipe belongs in V7.

CURRENT: v5.10-proactive-alerts
ACTIVE BRANCH: v5-whatsapp

-----------------------------------------------------------------------------
WHAT YOU CAN BUILD RIGHT NOW - IN ORDER
-----------------------------------------------------------------------------

v5.12  Role Limiting + Language
  Dependency: None - build first
  - phone_role enforcement: owner / manager / operator
  - 3-language support: Hindi / Hinglish / English
  - detect_language() in whatsapp_responses.py
  - LANGUAGE_INSTRUCTION in _build_system_prompt()
  - Role check in detect_write_intent() BEFORE AI is called
  - Blocked actions never reach AI layer
  Unlocks: Manager and owner have structurally different WhatsApp experiences.
           Foundation for all conversation design that follows.

v5.16  Day 1 Simple Table
  Dependency: v5.12 done
  - First screen a new tenant sees after registration - before Gantt, before jobs
  - Worker name + primary skill (one word: welder, stitching, cutting, finishing)
  - Worker type: permanent or contractor
  - Machine name + machine type
  - Nothing else - no hourly rates, no availability pct, no shift timings
  - Onboarding question: "Do you have employee/job data in SAP, Tally, or Excel?"
    Yes -> ERP path placeholder (v7.0), No -> proceed with this table
  - Migration 023: add source field to Employee (manual | whatsapp | erp_sync)
  - Migration 023: add source field to Machine (manual | whatsapp | erp_sync)
  - Migration 023: add worker_type field to Employee (permanent | contractor)
  Unlocks: From Day 1, manager saying "Suresh nahi aaya" gets immediate substitute
           suggestion. No week of learning needed. Owner briefing has context on
           Day 1 first absence. source field keeps v7.0 a sprint not a rewrite.

v5.15  Manager Input Flow
  Dependency: v5.16 done - seed data must exist before manager input means anything
  TWO DISTINCT WHATSAPP FLOWS - not one:

  MANAGER PHONE (7:00am) - input channel:
  - APScheduler triggers manager check-in prompt at 7:00am
  - "Aaj kaun kaun aaya?" - manager replies naturally, system parses names
    against v5.16 seed table
  - Absent worker identified -> skill looked up -> substitute suggested immediately
  - "Machines theek hain?" - manager flags downtime -> writes to unavailability table
  - "Aaj ke main kaam kya hain?" - manager states work -> maps to skill requirements
  - All inputs write to availability engine
  - Conversation ends: "Got it. Sahab ko summary bhej raha hoon."

  OWNER PHONE (7:15am) - output channel:
  - Single clean briefing generated FROM manager inputs - not from scheduled data alone
  - Format: who present, who absent, skill gap, order at risk, one suggested action
  - No questions asked to owner - signal only, zero input required
  - Owner reads, acts, moves on

  Unlocks: Owner briefing grounded in real morning reality. Manager has useful
           daily interaction. Attendance, machine status, active orders captured
           daily with zero web UI. By end of week 1: real attendance patterns,
           skill usage, machine reliability all in system passively.

v6.0  Schema Context
  Dependency: v5.15 done
  - schema_context.py: complete DB schema described for AI consumption
  - context_builder.py: assembles tenant context before every AI query
  - AI knows exact table structure, field names, relationships
  - tenant_id mandate enforced in all AI-generated queries - never cross-tenant
  Unlocks: "Who is free today for stitching?" is a real query, not a guess.
           Foundation for all intelligent features in v6.x.

v6.1  RAG Pipeline
  Dependency: v6.0 done
  - rag_data/_templates/ for 4 verticals: printing, manufacturing, fabrication,
    field_service (chemical excluded - batch-first, different entry model)
  - Tenant seeding at registration: seed_rag_from_template(tenant_id, industry_type)
  - _build_system_prompt() injects tenant RAG context before every AI query
  - Flat file MVP - pgvector migration in v6.3
  Unlocks: AI knows industry norms. "Kitna paper chahiye 5000 brochures ke liye?"
           works. Each tenant gets industry-personalised knowledge from Day 1.

v6.2  Industry Labels
  Dependency: v6.1 done
  - IndustryContext.tsx: reads industry_type from AuthContext at login
  - useLabels() hook: dynamic labels throughout UI
  - Sidebar labels dynamic - never hardcoded "Jobs", "Employees", "Machines"
  - Page titles dynamic per industry
  - RegisterPage auth bug fix: replace localStorage.setItem directly with
    AuthContext.register()
  - Verify: grep -r '"Jobs"\|"Machines"\|"Employees"' frontend/src/pages/ = empty
  Unlocks: Printing tenant sees "Print Jobs", "Press Operators", "Presses".
           Fabrication tenant sees "Fabrication Orders", "Fitters", "CNC Machines".

-----------------------------------------------------------------------------
BLOCKED VERSIONS - EXACT DEPENDENCIES
-----------------------------------------------------------------------------

v5.11  WhatsApp Go-Live
  Blocked by:
  - Meta Zero Zeta Business Portfolio restriction - appeal submitted Apr 8, in review
  - Business verification submitted - use case "WhatsApp Business account", in review
  - Interakt: account created, GST verified, number connection pending Meta approval
  - New SIM obtained, NOT registered on consumer WhatsApp, waiting for OTP step
  - ETA: ~Apr 12 2026 (4-day Meta review cycle)
  Contains:
  - WHATSAPP_MOCK_MODE=False
  - Real INTERAKT_API_KEY, PHONE_NUMBER_ID, WHATSAPP_BUSINESS_ACCOUNT_ID in .env
  - Webhook URL set in Interakt
  - 3 message templates approved: daily_briefing, delay_alert, conflict_alert
  Unlocks: Manager check-in and owner briefing run on real devices at real times.

v5.13  Voice Notes
  Blocked by: v5.11 must be live - needs real inbound WhatsApp audio
  - OpenAI Whisper API integration
  - Inbound audio message handling in WhatsApp pipeline
  - Audio -> transcription -> intent detection -> response
  - Manager can speak attendance instead of typing
  - Hindi voice input handled naturally by Whisper
  Unlocks: Manager on factory floor speaks, doesn't type. Adoption improves.

v5.14  Live E2E Test
  Blocked by: v5.11 + v5.13 both complete
  - All 7 WhatsApp scenarios verified on real device
  - Manager attendance flow tested end to end
  - Owner briefing received and verified
  - Zero mock alerts - all real
  - git tag v5.14-live-e2e
  Unlocks: Safe to onboard first real tenant.

-----------------------------------------------------------------------------
AFTER ALL OF THE ABOVE - PLANNED FUTURE
-----------------------------------------------------------------------------

v6.3  RAG pgvector
  Dependency: v6.1 done
  - Migration 024 (023 used by v5.16 source field)
  - tenant_knowledge_base table with embeddings
  - Similarity search replaces flat file scan
  - Flat file folder structure unchanged - storage layer change only
  - Semantic queries: "koi similar job pehle kiya tha?" finds relevant history

v6.4  Material Estimation
  Dependency: v6.1 done
  - Full RAG answer for quantity and material queries per industry
  - Structured JSON passed to AI - AI explains, never computes
  - "5000 brochures kitna paper chahiye?" returns grounded answer from RAG
  - Extensible per vertical: paper (printing), steel grade (fabrication),
    thread count (manufacturing)

v6.5  Supervisor Agent
  Dependency: v6.0 done
  - Swap GroqDirectBridge -> SupervisorAgent architecture
  - Planner + executor + validator pattern
  - Complex multi-step queries: "reschedule all Friday jobs, two workers out"
  - AI plans sequence, executes steps, validates result before responding

v7.0  ERP Connector Layer
  Dependency: v5.16 source field in DB, v6.2 done
  - Onboarding routing live: "Do you have ERP?" Yes/No at registration
  - source field activates erp_sync value
  - Python connector for SAP / Tally / Excel
  - Pulls three things only: employee list with skills, active orders,
    leaves and machine downtime
  - Daily sync job runs at 6:30am before manager check-in and owner briefing
  - Same WhatsApp briefing to owner - now sourced from ERP data
  - Same scheduling engine - zero changes
  - 4 verticals x mid-market addressable without rebuilding anything

v7.1  Compliance Tracker
  Dependency: v7.0 done
  - ESI, PF, Factory Act, Pollution NOC, Fire Safety certificate deadline tracker
  - Document store per tenant - upload and attach to each compliance item
  - Dashboard widget - upcoming deadlines at a glance
  - WhatsApp reminder to owner: 30 days, 7 days, 1 day before deadline

v7.2  Contractor Labour Layer
  Dependency: v7.0 done
  - Contractor worker type fully activated (worker_type field from v5.16)
  - Daily rate tracking vs monthly salary
  - Contractor availability pool - known contractors with skills, not on payroll
  - "Who's free and qualified right now?" as first-class AI Copilot query
  - Gap filling: when permanent worker absent, system searches contractor pool
    by skill match first

-----------------------------------------------------------------------------
FULL VERSION MAP
-----------------------------------------------------------------------------

| Version | Name                    | Status         | Dependency           |
|---------|-------------------------|----------------|----------------------|
| v5.10   | Proactive Alerts        | Done           | None                 |
| v5.12   | Role Limiting + Language| BUILD NOW      | None                 |
| v5.16   | Day 1 Simple Table      | BUILD NEXT     | v5.12                |
| v5.15   | Manager Input Flow      | BUILD NEXT     | v5.16                |
| v6.0    | Schema Context          | BUILD NEXT     | v5.15                |
| v6.1    | RAG Pipeline            | BUILD NEXT     | v6.0                 |
| v6.2    | Industry Labels         | BUILD NEXT     | v6.1                 |
| v5.11   | WhatsApp Go-Live        | WAITING        | Meta + Interakt      |
| v5.13   | Voice Notes             | WAITING        | v5.11                |
| v5.14   | Live E2E Test           | WAITING        | v5.11 + v5.13        |
| v6.3    | RAG pgvector            | Planned        | v6.1                 |
| v6.4    | Material Estimation     | Planned        | v6.1                 |
| v6.5    | Supervisor Agent        | Planned        | v6.0                 |
| v7.0    | ERP Connector Layer     | Planned        | v5.16 + v6.2         |
| v7.1    | Compliance Tracker      | Planned        | v7.0                 |
| v7.2    | Contractor Labour Layer | Planned        | v7.0                 |

BUILD SEQUENCE:
  NOW:     v5.12 -> v5.16 -> v5.15 -> v6.0 -> v6.1 -> v6.2
                     |
  WAITING: v5.11 -> v5.13 -> v5.14  (blocked on Meta approval ~Apr 12)

  PLANNED: v6.3 -> v6.4 -> v6.5
           v7.0 -> v7.1 -> v7.2

WHAT EACH PHASE DELIVERS:
  v5.x complete: WhatsApp loop is real. Manager inputs at 7am. Owner gets clean
  briefing at 7:15am. Daily habit formed before a single Gantt chart is opened.

  v6.x complete: AI is genuinely intelligent. Knows schema, industry, factory
  norms. Answers "will Friday order complete if Suresh is out?" with real data,
  substitution options, and industry context.

  v7.x complete: Same product, bigger market. ERP customers plug in their data
  source. Same briefing. Same engine. Compliance tracked. Contractor pool managed.
  Mid-market addressable without rebuilding anything.

META/INTERAKT STATUS (as of Apr 8 2026):
  - Zero Zeta Business Portfolio: restriction appeal submitted, under review
  - Business verification: submitted with use case "WhatsApp Business account", in review
  - 2FA: enabled on personal Facebook account (GauRav Gupta)
  - Interakt: account created, GST verified, number connection pending Meta approval
  - ZetaOps Copilot WABA ID: 27424391460495650 (restricted, appeal pending)
  - New SIM: obtained, NOT registered on consumer WhatsApp

WHATSAPP GO-LIVE CHECKLIST (execute when Meta approval received):
  [ ] Meta approval email received
  [ ] Interakt: connect new SIM number, enter OTP
  [ ] Copy INTERAKT_API_KEY to backend/.env
  [ ] Copy PHONE_NUMBER_ID to backend/.env
  [ ] Copy WHATSAPP_BUSINESS_ACCOUNT_ID to backend/.env
  [ ] Set WHATSAPP_MOCK_MODE=False in backend/.env
  [ ] Set webhook URL in Interakt: https://yourdomain.com/api/v1/whatsapp/webhook
  [ ] Restart backend, watch for zero errors
  [ ] Trigger test alert, verify real message arrives on phone
  [ ] Submit 3 message templates in Interakt (daily_briefing, delay_alert, conflict_alert)

VERSIONS.md cross-branch map (keep updated):
  v4.0.11  <-> v5.9-scheduler-v3    (scheduler v3, gap viz, Apr 2026)
  v4.0.10  <-> v5.8-frontend-clean  (frontend audit)


=============================================================================
SECTION 17 - PRE-DEPLOYMENT CHECKLIST
=============================================================================

  cd frontend && npx tsc --noEmit && npm run build
  cd backend && pytest tests/ -v
  cd backend && alembic heads && alembic check
  cd backend && python -c "from app.main import app; print(len(app.routes), 'routes')"
  git log --oneline -5 && git status
  grep -r "localhost:8000" frontend/src/
  grep -r "console.log" frontend/src/
  grep -r '"Jobs"\|"Machines"\|"Employees"' frontend/src/pages/   # must be empty after v6.2

ENVIRONMENT VARIABLES FOR PRODUCTION:
  DATABASE_URL                  - production DB (not localhost)
  SECRET_KEY                    - long random string, not "changeme"
  GROQ_API_KEY                  - valid key
  ANTHROPIC_API_KEY             - valid key
  ALLOWED_ORIGINS               - production frontend URL
  UPSTASH_REDIS_URL             - required for WhatsApp session persistence
  WHATSAPP_MOCK_MODE            - False
  INTERAKT_API_KEY              - required when MOCK_MODE=False
  PHONE_NUMBER_ID               - from Interakt dashboard
  WHATSAPP_BUSINESS_ACCOUNT_ID  - from Interakt/Meta
  WEBHOOK_VERIFY_TOKEN          - zetaops_webhook_secret


=============================================================================
SECTION 18 - PROMPT TEMPLATES (use full files separately)
=============================================================================

FOR FEATURE ADDITIONS  - use PROMPT_FEATURE_ADD.md  (#MSMEFEATURE)
  One feature per prompt. State business rules, files in scope, out-of-scope.
  Output: plan, schema changes, migration SQL, backend patch, frontend patch,
  out-of-scope confirmation, test steps.

FOR BUG FIXES          - use PROMPT_BUG_FIX.md      (#MSMEBUFIX)
  One bug per prompt. Paste exact error. Smallest possible patch.
  Output: root cause, files changed, before/after diff, verification.

FOR REFACTORING        - use PROMPT_REFACTOR.md     (#MSMEREFACTOR)
  One zone per prompt. Clarity only - no behaviour changes.
  Output: code smells, refactor plan, updated files, no-logic-change confirmation.

APPLICATION ZONES:
  Zone 1 - Backend Core:        routers/jobs.py, employees.py, machines.py, assignments.py
  Zone 2 - Backend Scheduler:   routers/scheduler_router.py
  Zone 3 - Backend Auth/Scan:   routers/auth.py, scan.py, services/token_service.py
  Zone 4 - Frontend Pages:      pages/Jobs.tsx, Employees.tsx, Machines.tsx, GanttPage.tsx
  Zone 5 - Frontend Scheduler:  scheduler/useScheduler.ts, SchedulerContext.tsx, SchedulerToolbar.tsx
  Zone 6 - AI Copilot:          routers/ai_chat.py, components/AICopilot.tsx
  Zone 7 - WhatsApp:            routers/whatsapp.py, services/whatsapp_*.py
  Zone 8 - RAG + Knowledge:     knowledge_graph/schema_context.py, context_builder.py,
                                 services/rag_service.py, rag_data/
  Zone 9 - Industry Config:     config/industries/, context/IndustryContext.tsx,
                                 auth/AuthContext.tsx (industry_type field)


=============================================================================
SECTION 19 - WHATSAPP ROLE ACCESS MATRIX
=============================================================================

  Role       | Allowed                                    | Blocked
  -----------|--------------------------------------------|---------------------------
  owner      | Everything - schedule, alerts, write,      | Nothing
             | financial data, RAG queries                |
  manager    | View schedule, mark absent,                | Financial data, create job,
             | check machine status                       | delete job
  operator   | View own assignments today only            | Everything else

  Implementation:
  - Role check in detect_write_intent() in whatsapp_intent.py
  - Blocked response via get_response('role_blocked', lang) in whatsapp_responses.py
  - Role never reaches AI layer if blocked

  Blocked message (per language):
  - en:       "This action is only available to the owner."
  - hinglish: "Ye query sirf owner kar sakta hai, bhai."
  - hindi:    "यह काम सिर्फ मालिक कर सकता है।"


=============================================================================
SECTION 20 - LANGUAGE SUPPORT
=============================================================================

  Detection rule (detect_language() in whatsapp_responses.py):
  - Hindi    = contains Devanagari Unicode [\u0900-\u097F]
  - Hinglish = contains marker words: kya, hai, nahi, karo, bhai, aaj, kal,
               mera, meri, kaam, schedule, batao, chahiye, kitna, kab, kaun,
               kyun, kaise, theek
  - English  = default if neither of the above

  AI responses: LANGUAGE_INSTRUCTION in _build_system_prompt() instructs Groq
  to detect and mirror the user's language automatically.

  Hardcoded response keys in RESPONSES dict (whatsapp_responses.py):
  - role_blocked, not_understood, delay_alert, conflict_alert, briefing

  Usage pattern:
    lang = detect_language(message_text)          # once per inbound message
    reply = get_response('role_blocked', lang)     # for hardcoded responses
    # AI responses handle language via system prompt instruction automatically


=============================================================================
SECTION 21 - RAG ARCHITECTURE
=============================================================================

  FOLDER STRUCTURE (Option B - industry templates + tenant override):

    backend/rag_data/
      _templates/              <- committed to git
        printing/
          paper_rates.txt
          machine_specs.txt
          job_times.txt
        manufacturing/
          bom_standards.txt
          machine_specs.txt
          cycle_times.txt
        fabrication/
          material_grades.txt
          weld_times.txt
          machine_specs.txt
        field_service/
          vehicle_specs.txt
          sla_standards.txt
          parts_catalog.txt
        chemical/              <- NOT in Plan A. Excluded from MSME onboarding.
          reactor_specs.txt    <- Batch-first vertical needs different entry model.
          batch_standards.txt  <- Retained for future Plan B / v7.x work only.
          safety_limits.txt
      12/                      <- tenant folder, NOT committed to git
        paper_rates.txt        <- seeded from _templates/printing/ at registration
        machine_specs.txt
        job_times.txt

  SEEDING: seed_rag_from_template(tenant_id, industry_type) in rag_service.py
  Called by: auth.py register endpoint after tenant creation

  INJECTION: _build_system_prompt() in ai_service.py reads tenant folder
  and prepends RAG context block before every AI query

  MIGRATION PATH:
  v6.1 -> flat files (current architecture above)
  v6.3 -> pgvector: tenant_knowledge_base table, embeddings, similarity search
  Flat file folder structure is unchanged in pgvector migration


=============================================================================
END OF PROMPT - paste at the start of every Claude dev session
=============================================================================
