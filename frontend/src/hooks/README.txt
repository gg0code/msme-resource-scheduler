AUTO-GENERATED - frontend/src/hooks/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/hooks/
PURPOSE: Reserved for shared TanStack Query hooks. Currently empty.

HISTORY
hooks_index.ts (the v4 barrel of useEmployees, useMachines, useSkills, useJobs,
useDashboard, useDeleteEmployee, useDeleteMachine, useDeleteJob,
useEmployeeAssignments, useMachineAssignments) was removed in v6.3.6 - it was
never imported. Pages call useQuery / useMutation directly from
@tanstack/react-query against the api/api_*.ts modules.

If you re-introduce shared hooks here, the query key contract is still:
['employees'], ['machines'], ['skills'], ['jobs'], ['dashboard']. Delete
mutations must invalidate both the resource key AND ['dashboard'] so the
dashboard summary stays in sync.
