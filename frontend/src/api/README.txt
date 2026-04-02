AUTO-GENERATED — frontend/src/api/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/api/
PURPOSE: All HTTP API call functions for the ZetaOps Copilot frontend.

WHAT IT DOES
This folder is the frontend API layer. Every HTTP request to the backend goes
through a function defined in one of these files. UI components and pages never
call fetch() or axios directly — they always import from one of the api_*.ts
files here. client.ts provides the shared authenticated Axios instance and the
in-memory JWT token store. All other files in this folder import client.ts and
build named API function objects on top of it. This pattern keeps HTTP logic
out of React components, makes API calls easy to find and change, and ensures
the JWT token is always attached automatically.

FILES
  client.ts                  — Axios instance, tokenStore (JWT in memory),
                               401 auto-refresh interceptor, request interceptor.
                               Branch: both. MOST CRITICAL FILE — all others depend on it.
  api_dashboard.ts           — GET /api/dashboard/ — job summaries, costs, metrics.
                               Branch: both.
  api_employees.ts           — CRUD + CSV import for employees.
                               Branch: both.
  api_gantt.ts               — GET /api/gantt/ — job data for timeline visualisation.
                               Branch: both.
  api_jobs.ts                — CRUD + timer control + assignment for jobs.
                               Branch: both.
  api_machines.ts            — CRUD + CSV import for machines.
                               Branch: both.
  api_resource_availability.ts — GET /api/jobs/{id}/resource-availability.
                               Returns real-time free capacity per resource.
                               Also exports display helpers (color, label functions).
                               Branch: both.
  api_skills.ts              — CRUD + CSV import for skills.
                               Branch: both.
  api_timer.ts               — Timer controls (start/pause/resume/stop/end) + cost preview.
                               Branch: both.

ARCHITECTURE NOTES
client.ts is the only file that imports axios directly. It creates one Axios
instance shared by every other file. The request interceptor reads tokenStore.get()
and adds Authorization: Bearer on every outgoing call. The response interceptor
catches 401 errors and silently refreshes the token using the httpOnly cookie before
retrying the failed request. If refresh fails, it clears the token and redirects to
/login. All api_*.ts files import apiClient from client.ts and call apiClient.get(),
apiClient.post() etc. — they never create their own Axios instances.
AuthContext.tsx is the only other file that touches tokenStore — it calls
tokenStore.set() after login, register, refresh, and logout.

DESIGN PRINCIPLES
Principle 1: These files only fetch and return data. They contain no business logic,
  no scheduling calculations, no cost computations. The backend does all of that.
Principle 2: Tenant scoping is automatic — the JWT in tokenStore identifies the tenant.
  Never pass tenant_id in any payload or query param from these files.
Principle 4: All endpoint paths start with /api/. Never omit this prefix.
Principle 11: All files must pass tsc --noEmit. Never use :any in function signatures.

DEPENDENCIES
  This folder imports from:
    ../types/types_index.ts  — all shared TypeScript types (Job, Employee, Machine etc.)

  This folder is imported by:
    frontend/src/pages/*     — all page components use api_*.ts files
    frontend/src/components/* — some components call API functions directly
    frontend/src/auth/AuthContext.tsx — imports tokenStore from client.ts

GOTCHAS
1. client.ts uses a module-level variable (_accessToken) for the JWT. This means
   the token is lost on page refresh. This is intentional — AuthContext restores it
   silently via the httpOnly cookie on every mount. Never add localStorage here.
2. The api_README.md file in this folder is a legacy human-written readme. It is
   less detailed than this README.txt. Prefer this file for current documentation.
3. If you add a new api_*.ts file, import apiClient from './client' — never from
   'axios' directly. This ensures the auth interceptors always apply.
