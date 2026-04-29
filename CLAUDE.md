# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ZetaOps Copilot — a multi-tenant production scheduling SaaS for Indian MSMEs. Stack: FastAPI + SQLAlchemy 2.0 (backend), React 18 + TypeScript + Vite + TailwindCSS (frontend), PostgreSQL, Alembic migrations.

Active branch: `v5-whatsapp`. Branch `v4-dev` is frozen (bug fixes only).

Test tenant: `what@what.what` / `qazx1234` / `tenant_id=12` / phone: `+919876543210`

---

## Commands

### Backend (run from `backend/`)
```bash
python -m uvicorn app.main:app --reload        # Dev server (port 8000)
python -m pytest tests/ -m "not integration" -v # Unit tests only
python -m pytest tests/ -v                      # All tests
python -m py_compile app/                       # Syntax check
python -m alembic upgrade head                  # Apply migrations
python -m alembic heads                         # Must show exactly ONE head (022)
python -m alembic revision --autogenerate -m "NNN_describe" # New migration
```

Verify new endpoints after registering in main.py:
```bash
python -c "
from app.main import app
routes = [(sorted(r.methods)[0], r.path) for r in app.routes if hasattr(r, 'methods')]
for m, p in sorted(routes, key=lambda x: x[1]): print(m, p)
"
```

### Frontend (run from `frontend/`)
```bash
npm run dev       # Vite dev server (port 5173)
npm run build     # TypeScript compile + bundle
npm run lint      # ESLint
npx tsc --noEmit  # TypeScript strict check — must show ZERO errors
```

### Infrastructure
```bash
docker-compose up  # Start PostgreSQL (port 5432)
```

---

## Verification Gates

Code is not done until all pass:
- `npx tsc --noEmit` — zero errors, no exceptions
- `python -m py_compile` — zero errors
- `pytest tests/ -m "not integration" -v` — zero failures
- `alembic heads` — exactly ONE head

---

## Architecture

### Directory Layout
```
backend/app/
  main.py              # FastAPI entry point — all routers registered here
  config.py            # Pydantic settings (all secrets from .env)
  features_config.py   # Feature flag definitions
  models/              # SQLAlchemy ORM models
  routers/             # FastAPI route handlers
  schemas/             # Pydantic request/response models
  services/            # Business logic layer
  scheduler/engine.py  # Pure Python scheduling algorithm (zero DB/SQLAlchemy)
  core/dependencies.py # get_current_user, require_role, get_db
  knowledge_graph/     # Schema context builders for RAG
  crud/                # Database query functions

backend/
  alembic/versions/    # Migrations (append-only, currently at head 022)
  rag_data/_templates/{industry}/  # Default knowledge per industry
  rag_data/{tenant_id}/            # Tenant-specific RAG files

frontend/src/
  pages/               # Page components
  components/          # Reusable components (never import from pages/)
  api/api_*.ts         # One API file per resource
  api/api_endpoints.ts # Single source of truth for ALL API path strings
  api/client.ts        # Axios instance with JWT auto-refresh
  types/types_index.ts # ALL TypeScript types — never create another types file
  auth/AuthContext.tsx  # JWT token management
  context/             # FeatureFlags, IndustryContext, SchedulerContext
  config/industries/   # Industry-specific label/theme configs
```

### Multi-Tenancy (Security Requirement)
Every DB query **must** filter by `tenant_id` — missing it is a security vulnerability, not a style issue:
```python
db.query(Model).filter(Model.tenant_id == current_user.tenant_id)
```
Every model's `tenant_id` FK must include `ondelete="CASCADE"`.

### Scheduler Engine
`backend/app/scheduler/engine.py` is pure Python — zero SQLAlchemy, zero DB calls. All DB loading happens in `scheduler_router.py` before calling `run_scheduler()`. Never add DB imports to `engine.py`.

### API Path Rule
All API path strings live exclusively in `frontend/src/api/api_endpoints.ts`. Never hardcode path strings anywhere else:
```ts
// CORRECT:
apiClient.get(JOBS.list)
// WRONG:
apiClient.get('/api/jobs/')
```

Import depth for `api_endpoints.ts`:
| File location | Import as |
|---|---|
| `src/api/*.ts` | `'./api_endpoints'` |
| `src/pages/*.tsx` | `'../api/api_endpoints'` |
| `src/components/*.tsx` | `'../api/api_endpoints'` |
| `src/components/common/*.tsx` | `'../../api/api_endpoints'` |
| `src/scheduler/*.ts`, `src/auth/*.tsx`, `src/context/*.tsx` | `'../api/api_endpoints'` |

### Backend Router Prefix Rules (in `main.py`)
- Standard routers (paths are `"/"`, `"/{id}"`) → `prefix="/api/routername"`
- Routers where path already contains the resource name → `prefix="/api"` (steps, unavailability, scan, features, scheduler_router)
- `auth.py` → `prefix=""` (routes at `/auth/*`)
- `whatsapp.py` → `prefix=""` (self-prefixes at `/api/v1/whatsapp`)
- `ai_chat.py` → `prefix="/api/ai"`

### WhatsApp Services
All WhatsApp services use **sync** `Session` — never `AsyncSession`. The async/sync bridge is `run_in_executor` in `whatsapp_bridge.py`. `WHATSAPP_MOCK_MODE=True` in dev logs `[MOCK ALERT]` instead of real sends.

### Provider Stack Order in `App.tsx`
`QueryClient > Auth > FeatureFlags > Industry > Scheduler > Onboarding > Layout`
Never add a Provider inside a page component.

### React Query Key Contracts
```
['employees'], ['machines'], ['skills'], ['jobs'], ['dashboard'],
['sched-jobs']  # Gantt auto-refresh after scheduler runs
```
Delete mutations invalidate **both** the resource key **and** `['dashboard']`. Never change a query key without searching all usages first.

---

## Key Constraints

### Migrations (Append-Only)
Never edit a migration that has been run. Always create a new one. Next migration is `023`. New `NOT NULL` columns on existing tables use `server_default`, not `default`. Always write both `upgrade()` and `downgrade()`.

### Conflict Detection is Centralised
One function: `_has_scheduling_conflict(job, entry_count_map)` used in `dashboard.py`, `gantt.py`, `jobs.py`, `whatsapp_alerts.py`. Logic: `schedule_entries count < expected days = conflict`. Never query `Job.has_conflict` — that column does not exist.

### N+1 Queries Are Forbidden
Never call a DB query inside a loop. Build a map first:
```python
rows = db.execute(select(Model.job_id, func.count()).group_by(...)).all()
count_map = {row[0]: row[1] for row in rows}
```
Use `selectinload` for relationships — never lazy-load inside a loop.

### Pydantic V2
```python
model_config = ConfigDict(from_attributes=True)  # not class Config
model_validate()    # not from_orm()
@field_validator    # not @validator
datetime.now(timezone.utc)  # not datetime.utcnow()
```

### Feature Flags
New features start with `flag=False` in `features_config.py`. Backend: `require_feature("flag_name")` at top of gated endpoints. Frontend: check `useFeatureFlags()` before rendering.

### Industry Labels — Never Hardcoded
Never hardcode "Jobs", "Employees", "Machines" in UI text. Use `const labels = useLabels()` then `labels.jobs`, `labels.employees` etc.

### Source Field on Employee and Machine
`source` field values: `'manual'` (Day 1 table), `'whatsapp'`, `'erp_sync'` (v7.0). Never remove — it's the structural decision that keeps v7.0 a sprint not a rewrite.

### TypeScript Hygiene
```ts
// Error handler pattern — always cast err: unknown before accessing
const msg = (err as { response?: { data?: { detail?: string } } })
              ?.response?.data?.detail ?? 'Fallback message'

// Never: err?.response  (TS2339)
// Never: React.FC — use plain function signatures with explicit prop types
// Always: useRef<HTMLDivElement>(null)
```

### AI Never Computes Logic
Pass structured JSON to LLM. LLM converts to human explanation only. Never ask LLM to calculate costs, quantities, or scheduling decisions.

### Scan Page Is Always Public
`/scan` has no auth. Never add authentication to `ScanPage.tsx` or `/api/scan/*`.

### No Non-ASCII in Source Files
Never use em dash, en dash, box-drawing characters, or curly quotes in source files. Python file headers: `#` comments only, never docstrings as file headers.

### Known Bugs

(Resolved in v6.3.2.3) ~~`RegisterPage.tsx` uses `localStorage.setItem('access_token')` directly, bypassing `AuthContext.register()`.~~ Now routes through `useAuth().register()`; token lives in the in-memory `tokenStore`. `useAuth().register()` returns `{ next_step }` so the page can route to `/dashboard` or `/connect-whatsapp`.

(Resolved in v6.3.2.4) ~~`'"mode"'` KeyError from `/api/ai/chat`.~~ Root cause: my v6.3.2.3 prompt fix added a literal `{"mode": "conflicts"}` example inside `_SYSTEM_PROMPT_BASE`, which is passed through `str.format(today=..., tomorrow=..., yesterday=...)`. Python's `str.format()` interpreted the `{...}` as a placeholder and crashed on the unknown key `'"mode"'`. Fixed by removing the literal example and simplifying the routing-header text.

**AI Copilot multi-mode tool calls fail (open, NOT in v6.3.2.4 scope).** Llama 3.3 70b on Groq emits malformed function-call text (`<function=NAME{args}</function>` — missing `>` between name and args) for tools that take arguments, instead of using the proper `tool_calls` JSON API. Groq returns `400 tool_use_failed`. Verified: tools with NO arguments (`get_monthly_revenue`, `get_machine_utilisation`, etc.) work fine — return real data via HTTP 200. Tools with `mode=` argument (`get_schedule_overview`, `get_jobs_overview`) all fail. Independent of prompt changes — proven by testing with bare-name routing hints. Three potential fixes: (a) switch model (e.g. `llama-3.1-70b-versatile` or `mixtral-8x7b-32768`), (b) split multi-mode tools into separate no-arg tools, (c) post-process Groq `failed_generation` field to recover the args. Defer to a focused AI-stability iteration.

---

## Environment Variables

Key `.env` values (see `.env.example` for full list):
```
DATABASE_URL=postgresql://msme_user:msme_pass@localhost:5432/msme_scheduler
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
ALGORITHM=HS256
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
GROQ_API_KEY=<optional>
WHATSAPP_MOCK_MODE=True  # keep True in dev
```
