/**
 * api_resource_availability.ts  (frontend/src/api/)
 * API call function for GET /api/jobs/{jobId}/resource-availability.
 * Returns real-time computed free capacity for every employee and machine
 * assigned to a job, scoped to the job's specific date range.
 * Used by the job side panel to replace static base_availability_pct sliders.
 * Added in v3.9.4. The materials array is always empty until v3.9.5.
 */

import apiClient from './client'

// ---------------------------------------------------------------------------
// Types - mirror the backend schemas/resource_availability.py shapes
// ---------------------------------------------------------------------------

/**
 * A job that is consuming a resource (employee or machine) on overlapping dates.
 * allocation_pct is only set for employee blocking jobs.
 * start_date / end_date are only set for machine blocking jobs.
 */
export interface BlockingJob {
  job_id: number
  job_name: string
  allocation_pct?: number   // employee overlap only
  start_date?: string       // machine overlap only - ISO date string
  end_date?: string         // machine overlap only - ISO date string
}

/**
 * Computed availability for one employee on the job's date range.
 * free_pct = base_pct - allocated_pct (clamped to 0 minimum).
 * status: 'free' = nothing committed, 'partial' = some committed, 'unavailable' = fully committed.
 */
export interface EmployeeAvailability {
  employee_id: number
  name: string
  base_pct: number
  allocated_pct: number
  free_pct: number
  status: 'free' | 'partial' | 'unavailable'
  blocking_jobs: BlockingJob[]
}

/**
 * Computed availability for one machine on the job's date range.
 * Machines are exclusive - is_free is binary (true = no overlap, false = blocked).
 * status: 'free' | 'busy'.
 */
export interface MachineAvailability {
  machine_id: number
  name: string
  is_free: boolean
  status: 'free' | 'busy'
  blocking_jobs: BlockingJob[]
}

/**
 * Full response from GET /api/jobs/{jobId}/resource-availability.
 * date_range is null when the job has no start/end dates set.
 * error === 'no_dates' signals the job needs dates before availability can be computed.
 * materials is always an empty array in v3.9.4 - reserved for v3.9.5 stock tracking.
 */
export interface ResourceAvailabilityResponse {
  job_id: number
  date_range: { start: string; end: string } | null
  employees: EmployeeAvailability[]
  machines: MachineAvailability[]
  materials: []
  error?: 'no_dates' | string
}

// ---------------------------------------------------------------------------
// API call
// ---------------------------------------------------------------------------

/**
 * Fetches real-time resource availability for a job from the backend.
 * Calls GET /api/jobs/{jobId}/resource-availability.
 * Returns computed free capacity per employee and machine on the job's dates.
 * Throws on network error or non-2xx response - caller should handle with try/catch.
 */
export async function getResourceAvailability(
  jobId: number
): Promise<ResourceAvailabilityResponse> {
  const response = await apiClient.get<ResourceAvailabilityResponse>(
    `/api/jobs/${jobId}/resource-availability`
  )
  return response.data
}

// ---------------------------------------------------------------------------
// Display helpers - used by the job panel component to render sliders
// ---------------------------------------------------------------------------

/**
 * Returns the slider colour hex code for an employee based on their availability status.
 * free        → green  (fully available on job dates)
 * partial     → amber  (partially committed to other jobs)
 * unavailable → red    (fully committed, no capacity left)
 */
export function employeeStatusColor(status: EmployeeAvailability['status']): string {
  switch (status) {
    case 'free':        return '#1D9E75'  // green
    case 'partial':     return '#BA7517'  // amber
    case 'unavailable': return '#A32D2D'  // red
    default:            return '#888780'  // gray fallback
  }
}

/**
 * Returns a human-readable subtitle for an employee slot in the job panel.
 * free        → empty string (no subtitle needed)
 * partial     → "X% committed to Job #N" (first blocking job)
 * unavailable → "Fully committed - Job #N"
 */
export function employeeStatusLabel(emp: EmployeeAvailability): string {
  if (emp.status === 'free') return ''
  const first = emp.blocking_jobs[0]
  if (!first) return ''
  if (emp.status === 'unavailable') return `Fully committed - ${first.job_name}`
  return `${emp.allocated_pct}% committed to ${first.job_name}`
}

/**
 * Returns a human-readable status line for a machine slot in the job panel.
 * free → "Available"
 * busy → "Busy - Job #N (Mar 14 – Mar 28)"
 */
export function machineStatusLabel(machine: MachineAvailability): string {
  if (machine.status === 'free') return 'Available'
  const first = machine.blocking_jobs[0]
  if (!first) return 'Busy'
  if (first.start_date && first.end_date) {
    const fmt = (d: string) =>
      new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
    return `Busy - ${first.job_name} (${fmt(first.start_date)} – ${fmt(first.end_date)})`
  }
  return `Busy - ${first.job_name}`
}
