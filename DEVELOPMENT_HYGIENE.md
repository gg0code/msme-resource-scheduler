# Development Hygiene — ZetaOps Copilot
# Version: 2.0 (post v4.0.9 full audit)
# Scope: ALL code written for this project — frontend, backend, tests, scripts, migrations

---

## THE CORE RULE

**Code is not done until it passes all verification checks. "Works in dev" is not done.**

- Frontend: `npx tsc --noEmit` with zero errors
- Backend: `python -m py_compile <file>` with zero errors + no deprecated patterns
- Tests: `pytest tests/ -v` with zero failures on all non-empty test files

These are non-negotiable gates before any file is considered deliverable.

---

## FRONTEND — TYPESCRIPT

### Type safety — always enforce

- Never use a type before defining or importing it. If a component uses `useState<TabType>`, `TabType` must be defined in the same file or explicitly imported at the top.
- Never call a function with more arguments than its signature accepts. If `showToast(msg, 'error')` is needed, update the signature to `(msg: string, type?: string)` first.
- Never use implicit `any`. Every function parameter, return type, and variable that TypeScript cannot infer must have an explicit type annotation.
- Never use `catch (err: any)` — use `catch (err: unknown)` and cast safely inside: `const message = err instanceof Error ? err.message : String(err)`.
- Never leave unused imports. If an icon, hook, component, or utility is imported but not referenced in JSX or logic, remove it. Unused imports are compile errors under strict mode.
- Always use `import type` for type-only imports: `import type { Foo } from './foo'` not `import { Foo } from './foo'` when `Foo` is only used as a type annotation.
- Never use `React.FC` — use plain function signatures with explicit prop types.
- Never use `React.useXxx` — import hooks directly: `import { useState } from 'react'`.
- Only import `React` itself if using `React.createElement`, `React.cloneElement`, or JSX in a `.tsx` file that requires it.

### Import paths — always enforce

- Actual filenames in this project use underscores: `api_employees.ts`, `api_jobs.ts`, `api_machines.ts`, `api_gantt.ts`, `api_resource_availability.ts`. Never import from `'../api/employees'` — always import from `'../api/api_employees'`.
- Types shared across the application live in `src/types/types_index.ts`. Industry-specific types live in `src/config/industries/types.ts`. Never create a new types file in a random location — add to one of these two files.
- Every import path must map to a file that physically exists at that exact path with that exact filename including underscores and casing. Before writing any import statement, confirm the target file exists.

### React patterns — always enforce

- Component state types must be defined before use. Never inline a union type in `useState` without naming it first if it is used more than once.
- Event handler types must be explicit: `(e: React.ChangeEvent<HTMLInputElement>)`, `(e: React.FormEvent<HTMLFormElement>)`, `(e: React.MouseEvent<HTMLButtonElement>)`. Never use `(e: any)`.
- `React.CSSProperties` for inline style objects — never use a plain `object` type.
- When using `useRef`, always specify the element type: `useRef<HTMLDivElement>(null)`.

---

## BACKEND — PYTHON / FASTAPI / SQLALCHEMY

### Datetime — always enforce

- Never use `datetime.utcnow()` — deprecated in Python 3.12. Always use `datetime.now(timezone.utc)`.
- Never use `default=datetime.utcnow` on SQLAlchemy columns (without parentheses) — use `default=lambda: datetime.now(timezone.utc)`.
- Same for `onupdate=datetime.utcnow` — use `onupdate=lambda: datetime.now(timezone.utc)`.
- Always import `timezone` alongside `datetime`: `from datetime import datetime, timezone`.

### Auth imports — always enforce

- `get_current_user` and `require_role` always come from `app.core.dependencies`. Never import from `app.routers.auth`.
- `get_db` always comes from `app.database`. Never import from `app.core.dependencies`.

### Pydantic v2 — always enforce

- Never use `from_orm()` — use `model_validate()`.
- Never use `class Config: from_attributes = True` — use `model_config = {"from_attributes": True}`.
- Never use `class Config: orm_mode = True` — same fix.
- Use `@field_validator` not `@validator`. Use `@model_validator(mode="after")` not `@root_validator`.

### SQLAlchemy — always enforce

- Every DB query that touches tenant data must filter by `tenant_id`. No exceptions.
- When a service function takes `tenant_id` as a parameter, every query inside it must use it. Cross-tenant leakage is a security bug.
- `ForeignKey` on `tenant_id` columns must include `ondelete="CASCADE"`. Never leave `tenant_id` as a plain `Integer` with no foreign key.
- Functions declared `async` must use `AsyncSession`. Functions using sync `Session` must NOT be `async`. Never mix.

### asyncio — always enforce

- Never use `asyncio.get_event_loop()` in async context — use `asyncio.get_running_loop()`.
- Never use `await` on sync SQLAlchemy `Session` methods (`execute`, `commit`, `close`). These are not awaitable.

### FastAPI — always enforce

- Never use `@app.on_event("startup")` / `@app.on_event("shutdown")` — use `lifespan` context manager (FastAPI 0.93+).
- Feature flag guard pattern: call `require_feature("flag")` at the top of gated endpoints, return the result if truthy. Never raise HTTPException for disabled features — return a warm 200 dict.
- Plan limit check: use `Depends(check_plan_limit("resource", Model))` on POST endpoints, not inline checks.

### Secrets — always enforce

- Never hardcode secrets in source code. All secrets come from `settings` (loaded from `.env`).
- Never commit `.env` files. `.env` is in `.gitignore`.
- Token secrets, API keys, database URLs — all must come from `settings.*`.

---

## MIGRATIONS — ALEMBIC

### Chain integrity — always enforce

- Every new migration's `down_revision` must point to the current `head`. Run `alembic heads` before creating a new migration — there must be exactly one head.
- File naming must match the internal revision ID. If the file is `015_add_foo.py`, the `revision` variable inside must be `'015'` or a similarly numbered identifier. Mismatches cause confusion and must be fixed immediately.
- Every migration must have a working `downgrade()` function. Empty `downgrade()` is only acceptable for truly irreversible operations — document why.
- Use `server_default` not `default` for `NOT NULL` columns added to existing tables. `default` only applies to Python-level inserts; `server_default` handles existing rows.
- Always use `checkfirst=True` when creating PostgreSQL ENUMs: `postgresql.ENUM(..., create_type=True)` on first creation, `create_type=False` on reuse.

---

## TESTS

### Structure — always enforce

- Every API endpoint test must pass `headers=auth_headers` to every request. Auth is enforced on all endpoints — tests without headers will 401.
- The `auth_headers` fixture in `conftest.py` is the single source of auth for all tests. Never hardcode tokens or bypass auth in tests.
- `TEST_DATABASE_URL` must come from an environment variable with a fallback: `os.getenv("TEST_DATABASE_URL", "postgresql://...")`. Never hardcode credentials.
- Every test that writes to the DB relies on the savepoint/rollback pattern in `conftest.py`. Never call `db.commit()` in a test body — it breaks rollback isolation.
- Pure Python unit tests (no DB, no HTTP) go in files named `test_<module>.py` and need no fixtures.

### Coverage expectations

- Every new service function: at least one unit test.
- Every new API endpoint: at least one integration test (create + read + delete minimum).
- Every new scheduler engine feature: at least one pure Python test.

---

## GIT

### Branch strategy

- `v4-dev` — production-stable branch. All hotfixes and audit fixes land here first.
- `v5-whatsapp` — feature branch. Always rebased or merged from `v4-dev` before new feature work begins.
- `master` — release branch. Merge from `v4-dev` only when deploying to production.

### Commit message format

```
type: short description (≤72 chars)

AREA:
- specific change 1
- specific change 2

BREAKING: describe any breaking change (omit section if none)
```

Types: `fix` `feat` `refactor` `test` `docs` `chore` `migration`

### Before every push

```powershell
# Frontend
cd frontend
npx tsc --noEmit
# Must output: (nothing) — zero errors

# Backend syntax check
cd ../backend
python -m py_compile app/main.py app/routers/*.py app/models/*.py app/services/*.py

# Alembic chain check
alembic heads
# Must output exactly one head revision
```

---

## PRE-DELIVERY CHECKLIST — run mentally against every file

### Frontend (TypeScript)

1. Every type used — is it defined or imported in this file?
2. Every function call — does the argument count match the signature?
3. Every import — is it actually used in the file body?
4. Every `import { X }` where X is only used as a type — changed to `import type { X }`?
5. Every import path — does the target file exist with that exact name including underscores?
6. Any `React` default import — is `React.something` actually used, or can it be removed?
7. Any `catch (err: any)` — changed to `catch (err: unknown)` with safe cast?
8. Any event handler using `(e: any)` — given proper type?

### Backend (Python)

1. Any `datetime.utcnow()` — replaced with `datetime.now(timezone.utc)`?
2. Any `from_orm()` — replaced with `model_validate()`?
3. Any `class Config` — replaced with `model_config`?
4. Any `from app.routers.auth import get_current_user` — changed to `app.core.dependencies`?
5. Any DB query on tenant data — filtered by `tenant_id`?
6. Any `async def` function — does it use `AsyncSession` not sync `Session`?
7. Any `asyncio.get_event_loop()` — changed to `asyncio.get_running_loop()`?
8. Any hardcoded secret string — moved to `settings.*`?
9. Any new `tenant_id` column — has `ForeignKey("tenants.id", ondelete="CASCADE")`?

### Migration (Alembic)

1. `down_revision` points to current head?
2. File name matches internal revision ID?
3. `downgrade()` is implemented?
4. New `NOT NULL` columns use `server_default`?
5. `alembic heads` shows exactly one head after adding this file?

---

## KNOWN PROJECT-SPECIFIC PATTERNS

### Tenant scoping

Every model has `tenant_id`. Every query on user data must include `.filter(Model.tenant_id == tenant_id)`. This is a hard rule with no exceptions. A missing `tenant_id` filter is a security vulnerability, not a style issue.

### Feature flags

All optional features are gated by `require_feature("flag_name")` from `app.utils.feature_guard`. The flag list lives in `app.features_config.FEATURE_FLAGS`. To add a new feature gate: add the flag to `FEATURE_FLAGS` first, then add the guard to the endpoint.

### Plan limits

Free plan limits are defined in `app.core.plan_limits.PLAN_LIMITS`. To change a limit, edit that dict only — it applies everywhere automatically via the `check_plan_limit` dependency.

### WhatsApp services

All WhatsApp services (`whatsapp_identity.py`, `whatsapp_actions.py`, etc.) use sync SQLAlchemy `Session` — never `AsyncSession`. The router (`whatsapp.py`) handles the async/sync bridge via `run_in_executor` in `whatsapp_bridge.py`.

### Scheduler engine

`app/scheduler/engine.py` is pure Python — zero SQLAlchemy, zero DB calls. It takes and returns dataclasses only. Never add DB imports to this file. All DB loading happens in `scheduler_router.py` before calling `run_scheduler()`.
