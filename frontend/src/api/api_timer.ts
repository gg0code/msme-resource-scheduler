// src/api/api_timer.ts - V2.0
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
