# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MSME Resource Scheduler — a multi-tenant SaaS app for small manufacturing businesses to manage jobs, employees, machines, and scheduling. Stack: FastAPI + PostgreSQL (backend), React + TypeScript + Vite (frontend).

---

## Dev Commands

### Backend

```bash
# Start PostgreSQL (Docker)
docker-compose up -d db

# Install deps
pip install -r backend/requirements.txt

# Run migrations
cd backend && alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173
npm run build
npm run lint
```

### Database Migrations

```bash
cd backend
alembic upgrade head                                     # apply all
alembic revision --autogenerate -m "description"         # create new
```

### Environment

Copy `.env.example` to `backend/.env` and configure:
- `DATABASE_URL`, `SECRET_KEY`, `GROQ_API_KEY`, `ALLOWED_ORIGINS`

Frontend: `frontend/.env` with `VITE_API_BASE_URL=http://localhost:8000`

---

## Architecture

### Multi-Tenancy

Every table has a `tenant_id` FK. All queries **must** filter by `current_user.tenant_id`. Never skip tenant isolation. Violations cause cross-tenant data leaks.

### Authentication

- Short-lived JWT access tokens (30 min, in-memory on frontend)
- Long-lived refresh tokens (7 days, httpOnly cookie)
- RBAC: **proprietor** (full access) > **scheduler** (jobs/assignments) > **viewer** (read-only)
- Backend deps in `backend/app/core/dependencies.py`: `get_current_user`, `require_role()`, `ProprietorOnly`, `SchedulerAbove`, `AnyAuthUser`
- Frontend: Axios interceptor in `frontend/src/api/client.ts` does silent refresh on 401, queues failed requests

### Plan Limits (Freemium)

- Free tier: 10 employees, 5 jobs, 5 machines, 20 skills
- Enforced via `check_plan_limit()` dependency on POST endpoints — returns HTTP 402 when exceeded
- Single source of truth: `backend/app/core/plan_limits.py`
- Frontend guard: `PlanLimitGuard` component

### Key Backend Services

| File | Purpose |
|------|---------|
| `app/services/availability_engine.py` | Conflict detection — checks if employee/machine is free for job date range, validates skill levels |
| `app/services/ai_service.py` | AI copilot — 50+ tools, per-tenant daily query limits, Groq API (Llama 3.3) |
| `app/services/cost_service.py` | Cost/profit calculations |
| `app/core/plan_limits.py` | Freemium tier limits |

### API Routers (`backend/app/routers/`)

All data routes prefixed `/api/`. Auth routes at `/auth`.

| Router | Prefix | Notes |
|--------|--------|-------|
| `auth.py` | `/auth` | register, login, refresh, logout, me |
| `jobs.py` | `/api/jobs` | CRUD + auto-scheduling; most complex router |
| `assignments.py` | `/api/assignments` | Job → employee/machine links |
| `gantt.py` | `/api/gantt` | Timeline data for Gantt view |
| `dashboard.py` | `/api/dashboard` | KPI aggregates |
| `timer.py` | `/api/timer` | Production timer (start/pause/resume/end) |
| `ai_chat.py` | `/api/ai` | AI copilot chat + usage stats |
| `availability.py` | `/api/availability` | Resource conflict checking |
| `import_csv.py` | `/api/import` | Bulk CSV upload |

### Key Models (`backend/app/models/`)

- **Job** — production order; has timer fields (`timer_status`, `actual_start_at`, `paused_seconds`), cost fields (`order_value`, `misc_cost`), scheduling fields (`start_mode`, `is_locked`, `has_conflict`, `earliest_date`, `latest_date`)
- **JobAssignment** — links Job → Employee or Machine with allocation %
- **Tenant** — root of multi-tenancy; has `plan`, `job_id_prefix`, AI usage counters
- **Employee** — has `hourly_rate`, `overtime_rate`, `base_availability_pct`; many-to-many with Skills

### Frontend Structure

- **`src/auth/AuthContext.tsx`** — global auth state (`user`, `token`, `login`, `logout`)
- **`src/api/client.ts`** — Axios instance with auto-refresh logic
- **`src/api/api_*.ts`** — one file per resource (jobs, employees, machines, etc.)
- **`src/pages/`** — page components (Jobs, GanttPage, Dashboard, Employees, Machines, Skills)
- **`src/components/Layout.tsx`** — sidebar + header shell
- **`src/components/AICopilot.tsx`** — floating AI chat panel

### Database Migrations

8 migrations in `backend/alembic/versions/`. Latest (`008`) added flexible scheduling fields to Job. Always run `alembic upgrade head` after pulling changes.
