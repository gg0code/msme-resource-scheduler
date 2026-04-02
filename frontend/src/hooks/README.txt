AUTO-GENERATED - frontend/src/hooks/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/hooks/
PURPOSE: Shared TanStack Query hooks for data fetching and mutations.

FILES
  hooks_index.ts  - All shared hooks: useEmployees, useMachines, useSkills,
                    useJobs, useDashboard, useDeleteEmployee, useDeleteMachine,
                    useDeleteJob, useEmployeeAssignments, useMachineAssignments.
                    Branch: both.

ARCHITECTURE NOTES
All hooks in this file wrap TanStack Query's useQuery and useMutation. Delete
mutations invalidate both the resource list cache AND the dashboard cache so the
dashboard summary stays in sync. The useDashboard hook refetches every 30 seconds
because the shop floor changes throughout the day.

DESIGN PRINCIPLES
Principle 2: All API functions called here are already tenant-scoped server-side.
  No tenant_id is passed from hooks.
Principle 11: Fix the import paths (../api/api_employees not ../api/employees)
  before the next tsc run - the source file had wrong paths.

DEPENDENCIES
  This folder imports from:
    ../api/api_employees.ts, api_machines.ts, api_skills.ts, api_jobs.ts, api_dashboard.ts
    @tanstack/react-query

  This folder is imported by:
    frontend/src/pages/Employees.tsx
    frontend/src/pages/Machines.tsx
    frontend/src/pages/Skills.tsx
    frontend/src/pages/Jobs.tsx
    frontend/src/pages/Dashboard.tsx

GOTCHAS
1. The original source file had wrong import paths (../api/employees instead of
   ../api/api_employees). The documented version has been corrected. Apply the
   fix to the source file too or tsc will error.
2. Query keys here must match exactly what pages use and what GettingStarted.tsx
   reads from cache: ['employees'], ['machines'], ['skills'], ['jobs'], ['dashboard'].
