/**
 * frontend/src/api/api_timer.ts — v2.0
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Provides all frontend API functions and TypeScript types for the job timer system
 * in ZetaOps Copilot. The timer tracks real working time on jobs — start, pause, resume,
 * stop, and end — and computes actual vs tentative cost breakdowns. This file was
 * introduced in v2.0 as part of the time-tracking feature and exists in both branches.
 * It sits in the frontend API layer and is the single source of all HTTP calls to
 * the /api/timer/ endpoints.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines CostBreakdown interface — financial breakdown with hours, costs, profit.
 * 2. Defines AssignedEmployee interface — employee with hourly rate for cost preview.
 * 3. Defines AssignedMachine interface — machine with hourly rate for cost preview.
 * 4. Defines TimerJobState interface — full job state returned after every timer action.
 * 5. Defines JobSummaryResponse interface — data for the End Job modal.
 * 6. Defines EndJobPayload interface — what the caller sends when ending a job.
 * 7. Exports timerApi object with start/pause/resume/stop/summary/end methods.
 * 8. Each method calls the corresponding /api/timer/{jobId}/action endpoint.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : timerApi.start
 * Type         : function
 * Purpose      : Starts the job timer. Sets timer_status to 'running' and records
 *                actual_start_at. Returns full updated job state for UI sync.
 * Parameters   : jobId: number
 * Returns      : Promise<TimerJobState>
 * Calls        : apiClient.post('/api/timer/{jobId}/start')
 * DB/API       : POST /api/timer/{jobId}/start
 * Side effects : updates job.timer_status, job.actual_start_at in DB
 *
 * Name         : timerApi.pause
 * Type         : function
 * Purpose      : Pauses the running timer. Accumulates elapsed seconds into
 *                paused_seconds. Sets timer_status to 'paused'.
 * Parameters   : jobId: number
 * Returns      : Promise<TimerJobState>
 * Calls        : apiClient.post('/api/timer/{jobId}/pause')
 * DB/API       : POST /api/timer/{jobId}/pause
 * Side effects : updates job.timer_status, job.paused_seconds in DB
 *
 * Name         : timerApi.resume
 * Type         : function
 * Purpose      : Resumes a paused timer. Sets timer_status back to 'running'.
 * Parameters   : jobId: number
 * Returns      : Promise<TimerJobState>
 * Calls        : apiClient.post('/api/timer/{jobId}/resume')
 * DB/API       : POST /api/timer/{jobId}/resume
 * Side effects : updates job.timer_status in DB
 *
 * Name         : timerApi.stop
 * Type         : function
 * Purpose      : Stops the timer without completing the job. Sets timer_status
 *                to 'stopped'. Job remains open for restarting later.
 * Parameters   : jobId: number
 * Returns      : Promise<TimerJobState>
 * Calls        : apiClient.post('/api/timer/{jobId}/stop')
 * DB/API       : POST /api/timer/{jobId}/stop
 * Side effects : updates job.timer_status in DB
 *
 * Name         : timerApi.summary
 * Type         : function
 * Purpose      : Fetches data for the End Job modal before the user confirms ending.
 *                Returns actual hours, current assignments, cost preview, and lists
 *                of available employees/machines the user can adjust before closing.
 * Parameters   : jobId: number
 * Returns      : Promise<JobSummaryResponse>
 * Calls        : apiClient.get('/api/timer/{jobId}/summary')
 * DB/API       : GET /api/timer/{jobId}/summary
 * Side effects : none — read only
 *
 * Name         : timerApi.end
 * Type         : function
 * Purpose      : Ends the job, records actual_end_at, computes and saves the final
 *                actual cost breakdown, and marks the job as completed. The user
 *                can adjust which employees/machines to include in the final cost
 *                calculation via the EndJobPayload.
 * Parameters   : jobId: number, payload: EndJobPayload — employee_ids and machine_ids
 * Returns      : Promise<TimerJobState> — final job state after completion
 * Calls        : apiClient.post('/api/timer/{jobId}/end', payload)
 * DB/API       : POST /api/timer/{jobId}/end
 * Side effects : updates job status to 'completed', writes actual cost fields to DB
 *
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Jobs.tsx — timer controls inline in the jobs list
 * - frontend/src/components/EndJobModal.tsx — summary and end actions
 * - frontend/src/pages/Dashboard.tsx — timer status display
 *
 * IMPORTS EXPLAINED
 * - apiClient from './client': Authenticated Axios instance — all HTTP calls go here.
 *
 * INTERN NOTES
 * - CostBreakdown appears twice on a job: tentative_cost (planned) and actual_cost
 *   (real, only after end). actual_cost is null until the job is ended — always null-check.
 * - The end() call is irreversible — it marks the job completed and writes actual costs.
 *   The UI must show a confirmation dialog before calling timerApi.end().
 * - timer_log is a JSON array of { event, timestamp } entries for audit trail.
 *   It grows with every timer action and should not be displayed directly — format it.
 * - Design Principle 1: The backend computes all costs. The frontend only displays
 *   what summary() returns — never compute costs in the frontend.
 * - Design Principle 4: All paths start with /api/.
 * - If start() returns 422: the job is already running or in a state that cannot be started.
 *   Check job.timer_status before calling start().
 */

import apiClient from './client'

export interface CostBreakdown {
  hours: number
  employee_cost: number
  machine_cost: number
  material_cost: number
  misc_cost: number
  total_cost: number
  order_value: number
  profit: number
}

export interface AssignedEmployee {
  id: number
  full_name: string
  hourly_rate: number
}

export interface AssignedMachine {
  id: number
  name: string
  hourly_rate: number
}

export interface TimerJobState {
  id: number
  name: string
  status: string
  timer_status: string
  priority: string
  start_date: string | null
  end_date: string | null
  actual_start_at: string | null
  actual_end_at: string | null
  paused_seconds: number
  timer_log: { event: string; timestamp: string }[]
  has_conflict: boolean
  conflict_reasons: string[]
  assigned_employees: AssignedEmployee[]
  assigned_machines: AssignedMachine[]
  tentative_cost: CostBreakdown
  actual_cost: CostBreakdown | null
}

export interface JobSummaryResponse {
  job_id: number
  job_name: string
  actual_hours: number
  current_employee_ids: number[]
  current_machine_ids: number[]
  cost_preview: CostBreakdown
  available_employees: AssignedEmployee[]
  available_machines: AssignedMachine[]
}

export interface EndJobPayload {
  employee_ids: number[]
  machine_ids: number[]
}

const timerApi = {
  start:   (jobId: number) =>
    apiClient.post<TimerJobState>(`/api/timer/${jobId}/start`, {}).then(r => r.data),

  pause:   (jobId: number) =>
    apiClient.post<TimerJobState>(`/api/timer/${jobId}/pause`, {}).then(r => r.data),

  resume:  (jobId: number) =>
    apiClient.post<TimerJobState>(`/api/timer/${jobId}/resume`, {}).then(r => r.data),

  stop:    (jobId: number) =>
    apiClient.post<TimerJobState>(`/api/timer/${jobId}/stop`, {}).then(r => r.data),

  summary: (jobId: number) =>
    apiClient.get<JobSummaryResponse>(`/api/timer/${jobId}/summary`).then(r => r.data),

  end:     (jobId: number, payload: EndJobPayload) =>
    apiClient.post<TimerJobState>(`/api/timer/${jobId}/end`, payload).then(r => r.data),
}

export default timerApi
