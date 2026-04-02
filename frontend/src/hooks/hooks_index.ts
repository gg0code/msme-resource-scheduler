/**
 * frontend/src/hooks/hooks_index.ts
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Shared TanStack Query hooks for all major data entities. Pages import from here
 * instead of writing inline queryFn calls, keeping query keys consistent across
 * the app. Introduced to centralise data-fetching patterns and ensure cache
 * invalidation keys match between reads and mutations.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Exports useEmployees() — queries ['employees'], calls employeesApi.list.
 * 2. Exports useDeleteEmployee() — mutation, invalidates ['employees'] + ['dashboard'].
 * 3. Exports useMachines() — queries ['machines'], calls machinesApi.list.
 * 4. Exports useDeleteMachine() — mutation, invalidates ['machines'] + ['dashboard'].
 * 5. Exports useSkills() — queries ['skills'], calls skillsApi.list.
 * 6. Exports useJobs() — queries ['jobs'], calls jobsApi.list.
 * 7. Exports useDeleteJob() — mutation, invalidates ['jobs'] + ['dashboard'].
 * 8. Exports useDashboard() — queries ['dashboard'], refetches every 30 seconds.
 * 9. Exports useEmployeeAssignments(id) — queries ['emp-assignments', id].
 * 10. Exports useMachineAssignments(id) — queries ['machine-assignments', id].
 *
 * KEY FUNCTIONS
 *
 * Name         : useDashboard
 * Type         : React hook
 * Purpose      : Fetches dashboard data with 30-second auto-refresh.
 *                The dashboard is the most frequently updated view — jobs start,
 *                stop, and complete throughout the day.
 * Parameters   : none
 * Returns      : UseQueryResult<DashboardData>
 * Calls        : dashboardApi.get()
 * DB/API       : GET /api/dashboard/
 * Side effects : background refetch every 30s
 *
 * Name         : useDeleteEmployee / useDeleteMachine / useDeleteJob
 * Type         : React hooks (mutations)
 * Purpose      : Delete a resource and invalidate both the resource list cache
 *                AND the dashboard cache. Dashboard must refresh because it shows
 *                counts and summaries that change on deletion.
 * Parameters   : none (id passed to mutate())
 * Returns      : UseMutationResult
 * Calls        : employeesApi.delete / machinesApi.delete / jobsApi.delete
 * DB/API       : DELETE /api/{resource}/{id}
 * Side effects : invalidates ['employees'/'machines'/'jobs'] and ['dashboard']
 *
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Employees.tsx
 * - frontend/src/pages/Machines.tsx
 * - frontend/src/pages/Skills.tsx
 * - frontend/src/pages/Jobs.tsx
 * - frontend/src/pages/Dashboard.tsx
 *
 * IMPORTS EXPLAINED
 * - useQuery, useMutation, useQueryClient from '@tanstack/react-query': core hooks.
 * - employeesApi, machinesApi, skillsApi, jobsApi, dashboardApi: API function objects
 *   from the api/ folder.
 *
 * INTERN NOTES
 * - WARNING: The imports in this file use wrong paths (../api/employees instead of
 *   ../api/api_employees). This will cause a tsc error. Fix all imports to use the
 *   correct underscore-prefixed filenames: api_employees, api_machines, api_skills,
 *   api_jobs, api_dashboard.
 * - Query keys here must match what pages use for cache invalidation to work.
 *   ['employees'], ['machines'], ['skills'], ['jobs'], ['dashboard'] are the canonical keys.
 *   GettingStarted.tsx reads these same keys from the query cache to detect completion.
 * - refetchInterval: 30_000 on useDashboard means the dashboard auto-refreshes
 *   every 30 seconds. This is intentional — the shop floor changes in real time.
 * - Design Principle 2: All API functions are already tenant-scoped server-side.
 *   No tenant_id is passed from these hooks.
 * - Design Principle 11: Fix the import paths before the next tsc run.
 */
// Shared React Query hooks — use these in pages instead of inline queryFn calls

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { employeesApi } from '../api/api_employees'
import { machinesApi }  from '../api/api_machines'
import { skillsApi }    from '../api/api_skills'
import { jobsApi }      from '../api/api_jobs'
import { dashboardApi } from '../api/api_dashboard'

// ── Employees ─────────────────────────────────────────
export function useEmployees() {
  return useQuery({ queryKey: ['employees'], queryFn: employeesApi.list })
}
export function useDeleteEmployee() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => employeesApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['employees'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) },
  })
}

// ── Machines ──────────────────────────────────────────
export function useMachines() {
  return useQuery({ queryKey: ['machines'], queryFn: machinesApi.list })
}
export function useDeleteMachine() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => machinesApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['machines'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) },
  })
}

// ── Skills ────────────────────────────────────────────
export function useSkills() {
  return useQuery({ queryKey: ['skills'], queryFn: skillsApi.list })
}

// ── Jobs ──────────────────────────────────────────────
export function useJobs() {
  return useQuery({ queryKey: ['jobs'], queryFn: jobsApi.list })
}
export function useDeleteJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => jobsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['jobs'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }) },
  })
}

// ── Dashboard ─────────────────────────────────────────
export function useDashboard() {
  return useQuery({ queryKey: ['dashboard'], queryFn: dashboardApi.get, refetchInterval: 30_000 })
}

// ── Employee assignments ───────────────────────────────
export function useEmployeeAssignments(employeeId: number) {
  return useQuery({
    queryKey: ['emp-assignments', employeeId],
    queryFn:  () => employeesApi.assignments(employeeId),
  })
}

// ── Machine assignments ───────────────────────────────
export function useMachineAssignments(machineId: number) {
  return useQuery({
    queryKey: ['machine-assignments', machineId],
    queryFn:  () => machinesApi.assignments(machineId),
  })
}
