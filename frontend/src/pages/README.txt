AUTO-GENERATED — frontend/src/pages/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/pages/
PURPOSE: One React component per application screen. These are the route targets.

FILES
  LoginPage.tsx       — Sign-in form. Calls AuthContext.login(). Public route. Both.
  RegisterPage.tsx    — New tenant registration with industry selector. Public. Both.
  UnauthorizedPage.tsx — Role mismatch error page. Redirected from ProtectedRoute. Both.
  Dashboard.tsx       — Main dashboard: KPIs, job list, timer controls. Auto-refetches
                        every 30s. Both.
  Jobs.tsx            — Main job management page (~2500 lines). Full lifecycle: create,
                        edit, assign, steps, timer, print, scheduler, AI. Both.
  Employees.tsx       — Employee CRUD + skills + leave management + CSV import. Both.
  Machines.tsx        — Machine CRUD + skill requirements + downtime + CSV import. Both.
  Skills.tsx          — Skills catalogue. Proprietor-only. Both.
  GanttPage.tsx       — Production timeline visualisation. Feature-flagged. Both.
  Availability.tsx    — Availability override management. Both.
  Checker.tsx         — Resource availability checker for a specific job. Both.
  ScanPage.tsx        — QR scan execution. NO AUTH. Mobile-first. Uses native fetch.
                        Both.
  PrintJobCard.tsx    — Print-optimised job card with QR codes. Auth required,
                        no layout. Both.
  LinkWhatsApp.tsx    — WhatsApp phone number linking. v5-whatsapp only (nav item
                        gated by flags.whatsapp).

ARCHITECTURE NOTES
Every page is a route target registered in App.tsx. Pages import from api/, hooks/,
components/, context/, and auth/. Pages never import from other pages. The most complex
page is Jobs.tsx (~2500 lines) — it contains several inline sub-components (JobWizard,
StepManager, ResourcePanel) because they are tightly coupled to job state. ScanPage.tsx
is the only page that uses native fetch() instead of apiClient — it must work without a
JWT token since factory workers are not logged in.

DESIGN PRINCIPLES
Principle 1: Pages display data computed by the backend — they never recompute
  scheduling logic, cost calculations, or conflict detection client-side.
Principle 2: All API calls are tenant-scoped automatically via JWT.
Principle 8: GanttPage and LinkWhatsApp are gated behind feature flags in Layout.tsx.
  Skills.tsx is gated behind proprietor role in App.tsx ProtectedRoute.
Principle 10: ScanPage.tsx is outside ProtectedRoute intentionally. Never add auth
  to it — printed QR cards must always be scannable.

GOTCHAS
1. Jobs.tsx is 2500 lines. Do not try to read it all at once. Each major section
   starts with a ── SectionName ── comment block.
2. The ['jobs'], ['employees'], ['machines'], ['skills'], ['dashboard'] query keys
   in these pages must match exactly what GettingStarted.tsx reads from cache and
   what hooks_index.ts invalidates on mutations.
3. ScanPage uses VITE_API_URL (not VITE_API_BASE_URL). Check both env vars if
   the scan page cannot reach the backend.
