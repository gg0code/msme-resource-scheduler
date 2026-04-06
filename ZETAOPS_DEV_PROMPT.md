# ZetaOps Copilot - Master Development Prompt
# Version: 3.0 (unified from MASTER_DEV_PROMPT v1.0 + DEVELOPMENT_HYGIENE v2.0)
# Paste this at the start of every Claude session involving code changes.
# Delete MASTER_DEV_PROMPT.md and DEVELOPMENT_HYGIENE.md - this replaces both.
# =============================================================================

You are working on ZetaOps Copilot - a multi-tenant production scheduling SaaS
for Indian MSMEs. Stack: FastAPI + SQLAlchemy 2.0 (backend), React 18 +
TypeScript + Vite + TailwindCSS (frontend), PostgreSQL, Alembic migrations.

Repo: C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler
Backend:  backend/
Frontend: frontend/
Branch:   v5-whatsapp (v4-dev is production-stable)

=============================================================================
SECTION 1 - THE CORE RULE
=============================================================================

Code is not done until it passes ALL verification gates. "Works in dev" is not done.

  Frontend:  npx tsc --noEmit          - zero errors, no exceptions
  Backend:   python -m py_compile      - zero errors + no deprecated patterns
  Tests:     pytest tests/ -v          - zero failures on all non-empty test files
  Migration: alembic heads             - exactly one head at all times

=============================================================================
SECTION 2 - API PATH RULES (added v4.0.9 - critical)
=============================================================================

ALL API paths in the frontend are defined in ONE file only:
  frontend/src/api/api_endpoints.ts

NEVER hardcode any path string like '/api/jobs/' anywhere in the project.
Every apiClient call must reference a constant from api_endpoints.ts:
  CORRECT:  apiClient.get(JOBS.list)
  WRONG:    apiClient.get('/api/jobs/')

Backend prefix rules for main.py registration:
  - Standard routers:     prefix="/api/routername"
  - Routers whose paths already include resource segment: prefix="/api"
    (steps, material_estimate, schedule_suggestions, scheduler_router, scan,
     features, unavailability)
  - auth router:          no prefix  (/auth/*)
  - whatsapp router:      no prefix  (self-prefixes at /api/v1/whatsapp)
  - ai_chat router:       prefix="/api/ai"

If a new endpoint is added to the backend, add it to api_endpoints.ts
immediately in the same commit. No exceptions.

=============================================================================
SECTION 2B - IMPORT PATH RULES (frontend)
=============================================================================

RELATIVE IMPORT DEPTH - memorise this table, never guess:

  File location                        | Import api_endpoints.ts as
  -------------------------------------|--------------------------------
  src/api/*.ts                         | './api_endpoints'
  src/pages/*.tsx                      | '../api/api_endpoints'
  src/components/*.tsx                 | '../api/api_endpoints'
  src/components/common/*.tsx          | '../../api/api_endpoints'
  src/context/*.tsx                    | '../api/api_endpoints'
  src/auth/*.tsx                       | '../api/api_endpoints'
  src/scheduler/*.ts                   | '../api/api_endpoints'

RULES
- Count folder depth from src/ to the file, then go up that many levels to reach src/api/
- Never guess the depth - check the file location first
- Wrong depth = silent import failure at runtime (no TypeScript error in some cases)
- When adding an import to any file, verify the path resolves to a real file on disk

BACKEND API PATH RULES - the /api prefix table:

  What the router file contains         | Register in main.py as
  --------------------------------------|--------------------------------
  paths like "/", "/{id}"              | prefix="/api/routername"
  paths like "/jobs/{id}/steps"        | prefix="/api"  (path already has segment)
  auth paths (/login, /register etc)   | no prefix
  whatsapp (self-prefixes internally)  | no prefix

  NEVER double-prefix. If router path is "/jobs/{id}/steps" and you add
  prefix="/api/jobs", the result is "/api/jobs/jobs/{id}/steps" - wrong.
  If router path is "/" and you add prefix="/api/jobs", result is "/api/jobs/" - correct.

HOW TO VERIFY A NEW ENDPOINT IS CORRECT
  After registering any new router, always run:
    python -c "
    from app.main import app
    routes = [(sorted(r.methods)[0], r.path) for r in app.routes if hasattr(r, 'methods')]
    for m, p in sorted(routes, key=lambda x: x[1]): print(m, p)
    "
  Scan output for doubled segments like /api/jobs/jobs/ or missing /api/ prefix.
  Fix in main.py before writing any frontend code for that endpoint.

=============================================================================
SECTION 3 - BACKEND DESIGN PRINCIPLES
=============================================================================

1. BACKEND COMPUTES, FRONTEND DISPLAYS
   Scheduling logic, cost calculations, conflict detection, availability -
   all computed on backend. Frontend only renders what backend returns.
   Never recompute backend logic in frontend components.

2. TENANT ISOLATION IS MANDATORY
   Every DB query must filter by tenant_id. No exceptions. Pattern:
     db.query(Model).filter(Model.tenant_id == current_user.tenant_id)
   A missing tenant_id filter is a security vulnerability, not a style issue.

3. SECRETS NEVER IN CODE
   SECRET_KEY, GROQ_API_KEY, DATABASE_URL, ANTHROPIC_API_KEY, WHATSAPP_MOCK_MODE
   all come from .env via Settings (pydantic-settings). Never hardcode.
   Settings uses extra="ignore" so unknown .env keys don't cause ValidationError.

4. ALL API ROUTES HAVE /api/ PREFIX
   Exception: /auth/* and /api/v1/whatsapp/* (self-prefixed) and /scan (public).
   Every new router must be registered in main.py with correct prefix.

5. RESOURCE AVAILABILITY != SCHEDULING CONFLICTS
   availability_engine.py != scheduler/engine.py. Different systems.

6. MIGRATIONS ARE APPEND-ONLY
   Never edit an existing migration. Always create a new one.
   Chain must always have exactly ONE head.
   After adding a migration: alembic heads - must show exactly one revision.
   Naming: NNN_description.py where NNN is next sequential number.
   Current head: 020.

7. PYDANTIC V2 STYLE EVERYWHERE
   model_config = ConfigDict(...)  not  class Config
   model_validate()                not  from_orm()
   @field_validator               not  @validator
   datetime.now(timezone.utc)     not  datetime.utcnow()

8. FEATURE FLAGS GATE EVERYTHING
   New features start with flag=False in features_config.py.
   Backend: use require_feature("flag_name") at top of gated endpoints.
   Frontend: check useFeatureFlags() before rendering.
   Never ship a feature without a flag.

9. PLAN LIMITS ARE ENFORCED DUAL-LAYER
   Backend: HTTP 402 when limit reached.
   Frontend: LimitedButton + PlanLimitBanner disable UI before the API call.
   Both layers must be kept in sync.

10. SCAN PAGE IS ALWAYS PUBLIC
    /scan route has no auth. Never add authentication to ScanPage.tsx or
    /api/scan/* endpoints. Printed QR codes must always be scannable.

=============================================================================
SECTION 4 - FRONTEND DESIGN PRINCIPLES
=============================================================================

11. TYPESCRIPT STRICT MODE - ZERO ERRORS
    npx tsc --noEmit must show ZERO errors before any commit.
    No `any` types. No unused variables. No missing return types.
    Use types from frontend/src/types/types_index.ts.
    Never create a new types file - add to types_index.ts.

12. QUERY KEYS ARE CONTRACTS
    TanStack Query keys must be consistent across the entire app:
      ['employees'], ['machines'], ['skills'], ['jobs'], ['dashboard']
    GettingStarted.tsx reads these keys for onboarding detection.
    Delete mutations must invalidate BOTH the resource key AND ['dashboard'].
    Never change a query key without grepping for all usages.

13. INDUSTRY LABELS NOT HARDCODED STRINGS
    Never hardcode "Jobs", "Employees", "Machines" in UI text.
    Always use: const labels = useLabels() then labels.jobs, labels.employees etc.
    CSS theme colours come from CSS variables (--brand-primary etc).
    Never apply theme colours as inline Tailwind classes.

14. API FILES USE UNDERSCORE PREFIX
    All API files: api_employees.ts, api_machines.ts, api_jobs.ts etc.
    Import from '../api/api_employees' not '../api/employees'.

15. COMPONENT HIERARCHY - NO CIRCULAR IMPORTS
    pages/      imports from: components/, api/, hooks/, context/, types/
    components/ imports from: api/, context/, types/ - NEVER from pages/
    hooks/      imports from: api/ only
    context/    imports from: api/ and auth/ only

16. NO SPECIAL CHARACTERS IN COMMENTS OR HEADERS
    Never use in any comment or file header:
    - Em dash (U+2014) - use hyphen - instead
    - En dash (U+2013) - use hyphen - instead
    - Box drawing chars - use plain - or = instead
    - Backtick fences ``` - never inside source files
    - Curly quotes - use straight quotes only
    Python file headers: # comments only. Never use docstrings as file headers.

=============================================================================
SECTION 5 - TYPESCRIPT HYGIENE (enforced on every file)
=============================================================================

- Never use a type before defining or importing it
- Never call a function with more arguments than its signature accepts
- Never use implicit `any` - every parameter and return type must be explicit
- Never use `catch (err: any)` - use `catch (err: unknown)` with safe cast:
    const message = err instanceof Error ? err.message : String(err)
- Never leave unused imports - unused imports are compile errors in strict mode
- Always use `import type` for type-only imports
- Never use React.FC - use plain function signatures with explicit prop types
- Never use React.useXxx - import hooks directly: import { useState } from 'react'
- Event handler types must be explicit:
    (e: React.ChangeEvent<HTMLInputElement>)
    (e: React.FormEvent<HTMLFormElement>)
    (e: React.MouseEvent<HTMLButtonElement>)
- useRef must specify element type: useRef<HTMLDivElement>(null)
- React.CSSProperties for inline style objects

=============================================================================
SECTION 6 - PYTHON HYGIENE (enforced on every file)
=============================================================================

DATETIME
  Always: datetime.now(timezone.utc)
  Never:  datetime.utcnow()
  Always: from datetime import datetime, timezone
  Column defaults: default=lambda: datetime.now(timezone.utc)
  Column onupdate: onupdate=lambda: datetime.now(timezone.utc)

AUTH IMPORTS
  get_current_user, require_role - always from app.core.dependencies
  get_db                         - always from app.database

PYDANTIC V2
  model_config = ConfigDict(from_attributes=True)  not  class Config
  model_validate()  not  from_orm()
  @field_validator  not  @validator

SQLALCHEMY
  Every tenant data query must filter by tenant_id
  ForeignKey on tenant_id must include ondelete="CASCADE"
  async def functions must use AsyncSession
  sync functions must use Session - never mix
  Never await sync Session methods

FASTAPI
  Use lifespan context manager not @app.on_event("startup"/"shutdown")
  Feature flag guard: call require_feature("flag") at top of gated endpoints
  Plan limit: use Depends(check_plan_limit("resource", Model)) on POST endpoints

SECRETS
  All secrets from settings.* loaded from .env
  Never hardcode any secret, API key, or database URL

=============================================================================
SECTION 7 - MIGRATION RULES
=============================================================================

Before writing a migration:
  alembic heads    - must show single head (currently: 020)
  alembic current  - shows current DB revision

Creating a migration:
  Always create manually - never use autogenerate in production
  Copy last migration file, increment number
  File naming: NNN_describe_what_changes.py
  Set revision and down_revision correctly
  Write both upgrade() and downgrade()
  Use IF NOT EXISTS in raw SQL for safety on column adds
  Use server_default not default for NOT NULL columns on existing tables

After writing a migration:
  alembic upgrade head
  alembic heads             - must still show single head
  python -m py_compile alembic/versions/NNN_new_migration.py

Never:
  Edit an existing migration that has been run in any environment
  Delete a migration file
  Use non-ASCII characters in migration files
  Leave downgrade() empty without documenting why

=============================================================================
SECTION 8 - PRE-COMMIT CHECKLIST (run every time, in order)
=============================================================================

STEP 1 - TYPESCRIPT
  cd frontend
  npx tsc --noEmit
  MUST: zero output = zero errors

STEP 2 - BACKEND SYNTAX
  cd backend
  python -m py_compile app/main.py app/routers/*.py app/models/*.py app/services/*.py
  MUST: no output = all clean

STEP 3 - PYTEST
  pytest tests/ -v
  MUST: all tests pass. Zero failures.
  Warnings about Pydantic v1 style and utcnow() are acceptable for now.

STEP 4 - MIGRATION CHAIN
  alembic heads
  MUST: exactly one revision shown (020 or latest)
  alembic check
  MUST: "No new upgrade operations detected"

STEP 5 - ROUTE/FILE CONSISTENCY
  Every file in frontend/src/pages/ must have a route in App.tsx
  Every route in App.tsx must have a file in frontend/src/pages/
  Every new API endpoint must have a constant in api_endpoints.ts

STEP 6 - DEAD CODE AUDIT
  No unused imports: npx tsc --noEmit catches most
  No orphan files: every .ts/.tsx file must be imported somewhere
  No dead routes: every route in App.tsx renders a real component
  No hardcoded secrets: grep -r "sk-ant\|gsk_\|password.*=" frontend/src/
  No hardcoded API paths: grep -r "'/api/\|'/auth/" frontend/src/ (should be empty)

STEP 7 - PROVIDER STACK
  Every new React Context Provider must be added to App.tsx provider stack.
  Provider order: QueryClient > Auth > FeatureFlags > Industry >
    Scheduler > Onboarding > Layout
  Never add a Provider inside a page component.

STEP 8 - REFERENCE INTEGRITY
  If a file was renamed: grep old name across entire repo and fix all references
  If a feature was replaced: delete old file in same commit
  If a hook/utility was written: at least one file must import it

STEP 9 - GIT DIFF REVIEW
  git diff --stat
  git status
  Review every changed file. No local-only debug files.
  No .env files committed ever.

=============================================================================
SECTION 9 - GIT COMMIT STRATEGY
=============================================================================

BRANCH STRATEGY
  v4-dev       - Production-stable. All fixes go here first.
  v5-whatsapp  - WhatsApp Copilot feature branch. Merges from v4-dev regularly.
  master       - Release branch. Only merge when deploying to production.
  Never commit directly to master.

COMMIT MESSAGE FORMAT
  <type>: <short description> (<=72 chars)

  Types:
    feat:      New feature or endpoint
    fix:       Bug fix
    docs:      Comments, README, headers only
    refactor:  Code restructure, no behaviour change
    test:      pytest additions or fixes
    chore:     Config changes, dependency updates, migration files
    perf:      Performance improvement
    migration: Alembic migration files only

COMMIT SEQUENCE
  git add -A
  git status          # review one more time
  git commit -m "type: description"
  git push origin v4-dev

  # Sync to v5-whatsapp:
  git checkout v5-whatsapp
  git merge v4-dev --no-ff -m "merge: description from v4-dev"
  git push origin v5-whatsapp
  git checkout v4-dev

NEVER IN GIT
  .env files, __pycache__/, node_modules/, *.pyc
  Local test scripts (seed_test.py, scratch.js)
  Log files, any file with a real API key or password

=============================================================================
SECTION 10 - PROJECT-SPECIFIC PATTERNS
=============================================================================

TENANT SCOPING
  Every model has tenant_id. Every query on user data must include:
    .filter(Model.tenant_id == tenant_id)
  Hard rule with no exceptions.

FEATURE FLAGS
  Gated by require_feature("flag_name") from app.utils.feature_guard.
  Flag list lives in app.features_config.FEATURE_FLAGS.
  To add a new gate: add flag to FEATURE_FLAGS first, then add guard to endpoint.

PLAN LIMITS
  Defined in app.core.plan_limits.PLAN_LIMITS.
  To change a limit, edit that dict only - applies everywhere automatically.

WHATSAPP SERVICES
  All WhatsApp services use sync SQLAlchemy Session - never AsyncSession.
  Router handles async/sync bridge via run_in_executor in whatsapp_bridge.py.
  Router self-prefixes at /api/v1/whatsapp - registered in main.py with no prefix.

SCHEDULER ENGINE
  app/scheduler/engine.py is pure Python - zero SQLAlchemy, zero DB calls.
  Takes and returns dataclasses only.
  Never add DB imports to this file.
  All DB loading happens in scheduler_router.py before calling run_scheduler().

UNAVAILABILITY
  Employee leaves:   app/models/unavailability.py - EmployeeLeave model
  Machine downtimes: app/models/unavailability.py - MachineDowntime model
  Router:            app/routers/unavailability.py - registered at prefix /api
  Frontend calls:    UNAVAILABILITY.* from api_endpoints.ts

=============================================================================
SECTION 11 - KNOWN TECHNICAL DEBT (fix separately, do not mix with features)
=============================================================================

1. PydanticDeprecatedSince20: class-based Config in schemas/
   Files: app/schemas/employee.py, app/schemas/machine.py, app/routers/gantt.py
   Fix: Replace class Config: from_attributes = True with
        model_config = ConfigDict(from_attributes=True)
   Commit as: "chore: fix Pydantic v2 deprecation warnings in schemas"

2. DeprecationWarning: datetime.utcnow() in SQLAlchemy column defaults
   Files: app/models/employee.py, app/models/machine.py
   Fix: Replace datetime.utcnow with lambda: datetime.now(timezone.utc)
   Commit as: "chore: fix utcnow deprecation in employee and machine models"

These do not block tests but must be fixed before v5.0 release.

=============================================================================
SECTION 12 - DEV SESSION STARTUP
=============================================================================

TERMINAL 1 - Backend:
  cd backend
  venv\Scripts\activate
  alembic upgrade head
  alembic heads                  # confirm single head (020)
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
  Watch for: "Application startup complete"

TERMINAL 2 - Frontend:
  cd frontend
  npx tsc --noEmit               # fix any errors before starting
  npm run dev
  Watch for: "VITE ready" at http://localhost:3000

BROWSER:
  http://localhost:3000           # app + health check fires in console on login
  http://localhost:8000/docs      # API explorer - verify all routes present

QUICK ROUTE VERIFICATION:
  python -c "
  from app.main import app
  routes = [(sorted(r.methods)[0], r.path) for r in app.routes if hasattr(r, 'methods')]
  for m, p in sorted(routes, key=lambda x: x[1]): print(m, p)
  "

=============================================================================
SECTION 13 - PRE-DEPLOYMENT CHECKLIST
=============================================================================

  cd frontend && npx tsc --noEmit
  cd frontend && npm run build
  cd backend && pytest tests/ -v
  cd backend && alembic heads
  cd backend && alembic check
  cd backend && python -c "from app.main import app; print(len(app.routes), 'routes')"
  git log --oneline -5
  git status
  grep -r "localhost:8000" frontend/src/
  grep -r "console.log" frontend/src/

ENVIRONMENT VARIABLES AUDIT (.env must have all):
  DATABASE_URL         - points to production DB
  SECRET_KEY           - long random string, not "changeme"
  GROQ_API_KEY         - valid Groq API key
  ANTHROPIC_API_KEY    - valid Anthropic key
  ALLOWED_ORIGINS      - production frontend URL, not localhost
  UPSTASH_REDIS_URL    - set if using WhatsApp session persistence
  WHATSAPP_MOCK_MODE   - False in production, True in dev

=============================================================================
END OF PROMPT - paste this at the start of every Claude dev session
=============================================================================
