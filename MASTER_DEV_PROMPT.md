# ZetaOps Copilot — Master Development & Code Quality Prompt
# Version: 1.0 | Applies to: v4-dev and v5-whatsapp branches
# Paste this at the start of every Claude session involving code changes.
# ============================================================================

You are working on ZetaOps Copilot — a multi-tenant production scheduling SaaS
for Indian MSMEs. Stack: FastAPI + SQLAlchemy 2.0 (backend), React 18 + TypeScript
+ Vite + TailwindCSS (frontend), PostgreSQL, Alembic migrations.

Repo: C:\Users\gaura\Desktop\Projects\sch\msme-resource-scheduler
Backend: backend/
Frontend: frontend/
Active branch: v5-whatsapp (v4-dev is production-stable)

════════════════════════════════════════════════════════════════════════════════
SECTION 1 — DOCUMENTATION STANDARDS
════════════════════════════════════════════════════════════════════════════════

Every folder must have a README.txt. Every file must have a header comment.
Every major function/class must have an inline comment block.

── FOLDER README.txt FORMAT ────────────────────────────────────────────────────

AUTO-GENERATED — path/to/folder/
Branch: v4-dev | v5-whatsapp (specify which)
────────────────────────────────────────────────────────────

FOLDER: path/to/folder/
PURPOSE: One sentence describing what this folder contains.

WHAT IT DOES
2-3 sentences on the folder's role in the system.

FILES
  filename.py   - One line description. Branch: both/v4-dev/v5-whatsapp.
  filename2.py  - One line description.

ARCHITECTURE NOTES
How files in this folder relate to each other and to other folders.

DESIGN PRINCIPLES
Which numbered design principles apply here and how.

DEPENDENCIES
  This folder imports from: ...
  This folder is imported by: ...

GOTCHAS
Numbered list of non-obvious things that will bite a new developer.

── FILE HEADER FORMAT (Python .py) ─────────────────────────────────────────────

# path/from/repo/root/filename.py - Version
# Branch: v4-dev | v5-whatsapp (both)
#
# FILE PURPOSE
# What this file does, why it exists, what version introduced it.
# Which layer it sits in (router/service/model/schema/core).
#
# WHAT THIS FILE DOES - step by step
# 1. First thing it does
# 2. Second thing
# ...
#
# KEY FUNCTIONS / CLASSES
#
# Name         : function_or_class_name
# Type         : function / class / FastAPI router
# Purpose      : What it does
# Parameters   : param: type - description
# Returns      : return type and what it means
# Calls        : other functions/services it calls
# DB/API       : SQL queries or external API calls made
# Side effects : DB writes, cache invalidation, email sent etc
#
# WHO CALLS THIS FILE
# - path/to/caller.py - why it calls this
#
# INTERN NOTES
# - Non-obvious decisions explained
# - Common mistakes to avoid
# - If X happens, check Y

── FILE HEADER FORMAT (TypeScript .ts / .tsx) ──────────────────────────────────

// path/from/repo/root/filename.tsx - Version
// Branch: v4-dev | v5-whatsapp (both)
//
// FILE PURPOSE
// What this file does, why it exists, what version introduced it.
//
// WHAT THIS FILE DOES - step by step
// 1. First thing
// 2. Second thing
//
// KEY FUNCTIONS / COMPONENTS
//
// Name         : ComponentOrFunction
// Type         : React component / hook / utility function
// Purpose      : What it does
// Parameters   : prop: type - description
// Returns      : JSX.Element / return type
// Calls        : API endpoints or other hooks/components
// DB/API       : GET/POST /api/endpoint
// Side effects : State changes, cache invalidation
//
// WHO CALLS THIS FILE
// - path/to/caller.tsx
//
// INTERN NOTES
// - Non-obvious decisions
// - Common mistakes
// - Design principles that apply

── INLINE FUNCTION COMMENTS ────────────────────────────────────────────────────

For every function longer than 10 lines, add:

# Python:
def my_function(param: type) -> return_type:
    """
    One line summary.

    Longer explanation if needed. Why this approach was chosen.
    What callers need to know.

    Args:
        param: what it is, valid values, units
    Returns:
        What the return value means
    Raises:
        SpecificError: when this happens
    """

// TypeScript:
/**
 * One line summary.
 * Longer explanation if needed.
 * @param param - what it is
 * @returns what the return value means
 */

── CRITICAL HEADER RULES ───────────────────────────────────────────────────────

NEVER use these characters in any comment or header - they break parsers:
  - Em dash:       — (U+2014)  → use hyphen - instead
  - En dash:       – (U+2013)  → use hyphen - instead
  - Box drawing:   ─ ═ │ (U+2500-U+257F) → use plain - or = instead
  - Left arrow:    ← (U+2190)  → use <- instead
  - Backtick fence: ``` → never use inside source files
  - Curly quotes:  " " ' '  → use straight quotes " ' instead

Python files: headers are # comments only. Never use """ docstrings as file
headers - they cause SyntaxError in some Python versions when placed at module
level with special characters.

════════════════════════════════════════════════════════════════════════════════
SECTION 2 — BACKEND DESIGN PRINCIPLES
════════════════════════════════════════════════════════════════════════════════

1. BACKEND COMPUTES, FRONTEND DISPLAYS
   The backend engine computes all scheduling logic, cost calculations, conflict
   detection, and availability. Frontend only renders what the backend returns.
   Never recompute backend logic in frontend components.

2. TENANT ISOLATION IS MANDATORY
   Every DB query must filter by tenant_id. No exceptions. Pattern:
     db.query(Model).filter(Model.tenant_id == current_user.tenant_id)
   If you forget tenant_id, one tenant sees another's data. This is a critical bug.

3. SECRETS NEVER IN CODE
   SECRET_KEY, GROQ_API_KEY, DATABASE_URL, ANTHROPIC_API_KEY all come from .env
   via Settings (pydantic-settings). Never hardcode. Settings uses extra="ignore"
   so unknown .env keys don't cause ValidationError.

4. ALL API ROUTES HAVE /api/ PREFIX
   Exception: /auth/* and /dashboard/plan-limits (registered without prefix).
   Every new router must be registered in main.py with prefix="/api/routername".

5. RESOURCE AVAILABILITY != SCHEDULING CONFLICTS
   Availability (amber/red %) = how much of a resource is free on given dates.
   Scheduling conflict = the engine cannot fit a step due to overlap or deadline.
   These are different systems. availability_engine.py != scheduler/engine.py.

6. MIGRATIONS ARE APPEND-ONLY
   Never edit an existing migration file. Always create a new one.
   Migration chain must always have exactly ONE head.
   After adding a migration: alembic heads → must show exactly one revision.
   Naming: NNN_description.py where NNN is next sequential number.

7. PYDANTIC V2 STYLE EVERYWHERE
   Use model_config = {...} not class Config.
   Use datetime.now(UTC) not datetime.utcnow().
   Use Optional[str] = None not str = None for optional fields.

8. FEATURE FLAGS GATE EVERYTHING
   New features start with flag=False in features_config.py.
   Backend: use @require_feature("flag_name") decorator.
   Frontend: check useFeatureFlags() before rendering.
   Never ship a feature without a flag.

9. PLAN LIMITS ARE ENFORCED DUAL-LAYER
   Backend: returns HTTP 402 when limit reached.
   Frontend: LimitedButton + PlanLimitBanner disable UI before the API call.
   Both layers must be kept in sync.

10. SCAN PAGE IS ALWAYS PUBLIC
    /scan route has no auth. Never add authentication to ScanPage.tsx or the
    /api/scan/* endpoints. Printed QR codes must always be scannable.

════════════════════════════════════════════════════════════════════════════════
SECTION 3 — FRONTEND DESIGN PRINCIPLES
════════════════════════════════════════════════════════════════════════════════

11. TYPESCRIPT STRICT MODE - ZERO ERRORS
    npx tsc --noEmit must show ZERO errors before any commit.
    No `any` types. No unused variables. No missing return types on functions
    longer than 5 lines. Use types from frontend/src/types/types_index.ts.
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
    CSS theme colours come from CSS variables (--brand-primary etc) set by
    IndustryContext on body. Never apply theme colours as inline Tailwind classes.

14. API IMPORT PATHS USE UNDERSCORE PREFIX
    All API files: api_employees.ts, api_machines.ts, api_jobs.ts etc.
    hooks_index.ts imports from '../api/api_employees' not '../api/employees'.
    If you see an import without the underscore prefix, fix it.

15. COMPONENT HIERARCHY - NO CIRCULAR IMPORTS
    pages/ imports from components/, api/, hooks/, context/, types/
    components/ imports from api/, context/, types/ - NEVER from pages/
    hooks/ imports from api/ only
    context/ imports from api/ and auth/ only
    Never import a page from another page or a component.

════════════════════════════════════════════════════════════════════════════════
SECTION 4 — PRE-COMMIT CHECKLIST (run every time before git commit)
════════════════════════════════════════════════════════════════════════════════

Run these in order. Fix everything before committing.

STEP 1 - TYPESCRIPT (frontend)
  cd frontend
  npx tsc --noEmit
  MUST: zero errors, zero exceptions. One error = do not commit.

STEP 2 - BACKEND SYNTAX (backend)
  cd backend
  python -m py_compile app/main.py
  python -m py_compile app/routers/*.py
  python -m py_compile app/services/*.py
  python -m py_compile app/models/*.py
  MUST: no output = all clean.

STEP 3 - PYTEST (backend)
  pytest tests/ -v
  MUST: all tests pass. Zero failures.
  Warnings about Pydantic v1 style and utcnow() are acceptable for now.

STEP 4 - MIGRATION CHAIN (backend)
  alembic heads
  MUST: exactly one revision shown (018 or latest).
  alembic check
  MUST: "No new upgrade operations detected" (or run upgrade head if needed).

STEP 5 - ROUTE/FILE CONSISTENCY (frontend)
  Every file in frontend/src/pages/ must have a route in App.tsx.
  Every route in App.tsx must have a file in frontend/src/pages/.
  Check: Get-ChildItem frontend\src\pages\ -Name
  Check: Get-Content frontend\src\App.tsx | Select-String "import\|Route"

STEP 6 - DEAD CODE AUDIT
  No unused imports: npx tsc --noEmit catches most of these.
  No orphan files: every .ts/.tsx file in src/ must be imported somewhere.
  No dead routes: every route in App.tsx renders a real component.
  No hardcoded secrets: grep -r "sk-ant\|gsk_\|password.*=" frontend/src/

STEP 7 - PROVIDER STACK (frontend)
  Every new React Context Provider must be added to App.tsx provider stack.
  Provider order matters: QueryClient > Auth > FeatureFlags > Industry >
    Scheduler > Onboarding > Layout
  Never add a Provider inside a page component.

STEP 8 - REFERENCE INTEGRITY
  If a file was renamed: grep old name across entire repo and fix all references.
  If a feature was replaced: delete old file in same commit, not a later one.
  If a hook/utility was written: at least one file must import it.
  Check: git diff --stat → verify no unexpected files, no missing deletions.

STEP 9 - GIT DIFF REVIEW
  git diff --stat
  git status
  Review every changed file. Ask: does this change make sense?
  No local-only debug files (test.py, scratch.js, temp.txt).
  No .env files committed ever.
  No __pycache__ or node_modules committed.

════════════════════════════════════════════════════════════════════════════════
SECTION 5 — GIT COMMIT STRATEGY
════════════════════════════════════════════════════════════════════════════════

BRANCH STRATEGY
  v4-dev        Production-stable. All fixes go here first.
  v5-whatsapp   WhatsApp Copilot feature branch. Merges from v4-dev regularly.
  master        Release branch. Only merge when deploying to production.
  Never commit directly to master.

COMMIT MESSAGE FORMAT
  <type>: <short description> (<files changed if helpful>)

  Types:
    feat:     New feature or endpoint
    fix:      Bug fix
    docs:     Comments, README.txt, header blocks only
    refactor: Code restructure, no behaviour change
    test:     pytest additions or fixes
    chore:    Config changes, dependency updates, migration files
    perf:     Performance improvement

  Examples:
    feat: add plan-limits endpoint to dashboard router
    fix: restore alembic migration files - remove broken doc headers
    fix: add deadline constraint check to scheduler engine slot-finding loop
    docs: add file headers and README.txt to all frontend source files
    test: add auth_headers fixture to conftest, fix test_skills auth
    chore: update config.py - add extra=ignore, GROQ_API_KEY as Optional

COMMIT SCOPE RULES
  One logical change per commit. Do not mix feature + fix + docs in one commit.
  If fixing a bug caused by a previous commit, reference it:
    fix: repair dashboard icon imports broken in 6035c8e

STANDARD COMMIT SEQUENCE
  # After all pre-commit checks pass:
  git add -A
  git status          # review one more time
  git commit -m "type: description"
  git push origin v4-dev

  # Sync to v5-whatsapp:
  git checkout v5-whatsapp
  git merge v4-dev --no-ff -m "merge: description from v4-dev"
  git push origin v5-whatsapp
  git checkout v4-dev

WHAT NEVER GOES IN GIT
  .env files (contains secrets)
  __pycache__/ directories
  node_modules/
  *.pyc files
  Local test scripts (seed_test.py, scratch.js etc)
  Log files
  Any file with a real API key or password

════════════════════════════════════════════════════════════════════════════════
SECTION 6 — ALEMBIC MIGRATION RULES
════════════════════════════════════════════════════════════════════════════════

BEFORE WRITING A MIGRATION
  alembic heads          # must show single head
  alembic current        # shows current DB revision
  alembic history        # shows full chain

CREATING A NEW MIGRATION
  # Always create manually - never use autogenerate in production
  # Copy the last migration file, increment the number
  # File naming: NNN_describe_what_changes.py
  # Set revision and down_revision correctly
  # Write both upgrade() and downgrade()

AFTER WRITING A MIGRATION
  alembic upgrade head   # apply to dev DB
  alembic heads          # must still show single head
  python -m py_compile alembic/versions/NNN_new_migration.py  # no syntax errors

MIGRATION FILE HEADER (clean, no special chars)
  # alembic/versions/NNN_description.py
  # Migration: short description
  # Introduced in: v4.0.X
  # What it does: adds X column to Y table

NEVER
  Edit an existing migration that has been run in any environment.
  Delete a migration file.
  Use non-ASCII characters in migration files.
  Merge two migration files into one.

════════════════════════════════════════════════════════════════════════════════
SECTION 7 — WARNINGS TO RESOLVE (known technical debt)
════════════════════════════════════════════════════════════════════════════════

These warnings appear in pytest but do not fail tests. Fix them when time allows:

1. PydanticDeprecatedSince20: class-based Config in schemas/
   Files: app/schemas/employee.py, app/schemas/machine.py
   Fix: Replace `class Config: from_attributes = True` with
        `model_config = ConfigDict(from_attributes=True)`

2. DeprecationWarning: datetime.utcnow() in SQLAlchemy column defaults
   Files: any model using server_default with utcnow
   Fix: Replace datetime.utcnow with lambda: datetime.now(UTC)
        from datetime import UTC

These are tracked but not blocking. Do not mix these fixes with feature commits.
Create a separate commit: "chore: fix Pydantic v2 deprecation warnings in schemas"

════════════════════════════════════════════════════════════════════════════════
SECTION 8 — PRE-DEPLOYMENT CHECKLIST
════════════════════════════════════════════════════════════════════════════════

Run ALL of these before merging to master or deploying to server:

  cd frontend && npx tsc --noEmit           # zero TS errors
  cd frontend && npm run build              # production bundle must succeed
  cd backend && pytest tests/ -v           # all tests pass
  cd backend && alembic heads              # single head
  cd backend && alembic check              # no pending migrations
  cd backend && python -c "from app.main import app; print(len(app.routes), 'routes')"
  git log --oneline -5                     # review recent commits
  git status                               # nothing uncommitted
  grep -r "localhost:8000" frontend/src/   # no hardcoded dev URLs
  grep -r "console.log" frontend/src/      # remove debug logs

ENVIRONMENT VARIABLES AUDIT (check .env has all required keys):
  DATABASE_URL         - points to production DB
  SECRET_KEY           - long random string, not "changeme"
  GROQ_API_KEY         - valid Groq API key
  ANTHROPIC_API_KEY    - valid Anthropic key (for generate_docs.py only)
  ALLOWED_ORIGINS      - production frontend URL, not localhost
  UPSTASH_REDIS_URL    - set if using WhatsApp session persistence

════════════════════════════════════════════════════════════════════════════════
SECTION 9 — HOW TO START A DEV SESSION
════════════════════════════════════════════════════════════════════════════════

TERMINAL 1 - Backend:
  cd backend
  venv\Scripts\activate
  alembic upgrade head
  alembic heads              # confirm single head
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
  Watch for: "Application startup complete"

TERMINAL 2 - Frontend:
  cd frontend
  npx tsc --noEmit           # fix any errors before starting
  npm run dev
  Watch for: "VITE ready" at http://localhost:3000

BROWSER:
  http://localhost:3000       # app
  http://localhost:8000/docs  # API explorer

════════════════════════════════════════════════════════════════════════════════
END OF PROMPT — paste this at the start of every Claude dev session
════════════════════════════════════════════════════════════════════════════════
