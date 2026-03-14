# AI_PROJECT_CONTEXT.md
# MSME Resource Scheduler — Master Project Brief
# Reference tag: #MSMEPROJBRIEF
# Use this block at the top of every feature / bug / test prompt.

---

## #MSMEPROJBRIEF

**Project:** MSME Resource Scheduler — Multi-tenant SaaS for small manufacturing units
**Repo:** https://github.com/gg0code/msme-resource-scheduler
**Active branch:** v3-dev | **Latest tag:** v3.6
**Dev machine:** Windows + PowerShell | venv at `backend\`
**Frontend:** http://localhost:3000 | **Backend:** http://localhost:8000

---

### Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.14, Uvicorn |
| ORM | SQLAlchemy 2.0 (no Alembic migrations — raw SQL via `engine.execute`) |
| Database | PostgreSQL (psycopg2-binary) |
| Auth | JWT via python-jose, bcrypt direct (passlib bcrypt bug on Py3.14) |
| Frontend | React 18 + TypeScript + Vite, port 3000 |
| Data fetching | TanStack React Query (`useQuery`, `useMutation`) |
| Styling | Tailwind CSS utility classes only (no component libs except lucide-react) |
| AI Copilot | Groq SDK — Llama 3.3 70B |
| Excel/CSV | openpyxl (backend), papaparse (frontend) |
| QR Codes | qrcode.react (frontend, client-side only) |

---

### Architecture Facts

**Backend**
- All routers live in `backend/app/routers/`
- All models live in `backend/app/models/`
- Every router is registered in `backend/app/main.py` with explicit prefix
- **Every DB query must include `tenant_id` filter — no exceptions**
- DB migrations are raw SQL run directly via PowerShell (no Alembic)
- `Date` columns return Python `datetime` — always call `.date()` before comparing
- Auth token is in-memory (`tokenStore`) — new browser tabs lose session, use `navigate()` not `window.open()`
- bcrypt imported directly (`import bcrypt`) — never via passlib on Python 3.14

**Frontend**
- Pages live in `frontend/src/pages/`
- Shared components in `frontend/src/components/common/`
- Scheduler state machine in `frontend/src/scheduler/` (SchedulerContext, useScheduler, SchedulerToolbar)
- API client: `frontend/src/api/client.ts` (axios instance with JWT interceptor)
- Query key conventions: `['jobs']`, `['steps', jobId]`, `['employees']`, `['machines']`, `['dashboard']`
- After any mutation that affects scheduling: call `markDirty()` from `useSchedulerContext()`
- After step add/delete: invalidate both `['steps', jobId]` AND `['jobs']`

**Scheduler**
- Algorithm: greedy forward-scan (NOT RCPSP) — finds first gap where all resources are free
- Locked jobs = fixed anchors in occupancy map
- Unlocked jobs = reschedule to next available slot from today
- Employee leaves + machine downtimes block the occupancy map same as locked jobs
- Auto-schedule endpoint: `POST /api/jobs/auto-schedule`

---

### Key DB Tables

| Table | Purpose |
|---|---|
| `jobs` | Main job table |
| `job_assignments` | Employee + machine assignments per job |
| `job_steps` | Step intelligence (sequence, type, duration, status) |
| `step_resources` | Per-step resource overrides |
| `employee_leaves` | Employee unavailability periods |
| `machine_downtimes` | Machine unavailability periods |
| `employees`, `machines`, `skills` | Core resource tables |
| `sched_jobs`, `sched_steps` | Legacy scheduler — do not touch |

---

### Current Zone
- [ ] Backend — auth
- [ ] Backend — jobs / scheduler
- [ ] Backend — employees / machines
- [ ] Backend — imports / exports
- [ ] Frontend — Jobs page
- [ ] Frontend — Gantt / Timeline
- [ ] Frontend — Employees / Machines
- [ ] Frontend — Dashboard
- [ ] Frontend — Print / QR
- [ ] AI Copilot
- [ ] Infra / AWS deployment

*(Check the relevant zone above when using this brief in a prompt)*

---

### Master Prompt Rules (apply to all prompts)

1. Inspect minimum context — do not scan whole repo
2. Stay within allowed files unless absolutely necessary
3. If another file is required, name it first and explain why
4. Prefer the smallest working patch
5. Do not refactor unless explicitly asked
6. Do not reformat unrelated code
7. Do not rename files/functions unless necessary
8. Keep explanation brief and technical — diagnose root cause first, then patch
9. Always pin exact file paths
10. For backend changes — state whether a DB migration is needed
11. For frontend changes — state which React Query keys need invalidating
12. Never use `SELECT *` — list columns explicitly
13. All new DB columns must have a default or be nullable
14. Tenant-scoped always — every new DB query must filter by `tenant_id`
