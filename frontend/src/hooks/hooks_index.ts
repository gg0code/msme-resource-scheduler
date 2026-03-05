// Shared React Query hooks — use these in pages instead of inline queryFn calls

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { employeesApi } from '../api/employees'
import { machinesApi }  from '../api/machines'
import { skillsApi }    from '../api/skills'
import { jobsApi }      from '../api/jobs'
import { dashboardApi } from '../api/dashboard'

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
