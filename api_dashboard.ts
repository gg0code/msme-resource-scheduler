// src/api/api_dashboard.ts — V2.0
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

export interface DashboardJob {
  id: number
  name: string
  customer?: string
  priority: string
  status: string
  timer_status: string
  start_date: string | null
  end_date: string | null
  actual_start_at: string | null
  actual_end_at: string | null
  paused_seconds: number
  has_conflict: boolean
  conflict_reasons: string[]
  status_icon: string
  assigned_employees: { id: number; full_name: string }[]
  assigned_machines: { id: number; name: string }[]
  tentative_cost: number
  tentative_profit: number
  tentative_breakdown: CostBreakdown
  actual_cost: number | null
  actual_profit: number | null
  actual_breakdown: CostBreakdown | null
  order_value: number | null
}

export interface DashboardData {
  total_active_jobs: number
  available_machines: number
  available_employees: number
  jobs_by_status: Record<string, number>
  upcoming_jobs_this_week: {
    id: number
    name: string
    start_date: string
    end_date: string
    priority: string
    status: string
  }[]
  jobs: DashboardJob[]
}

export const dashboardApi = {
  get: () => apiClient.get<DashboardData>('/dashboard/').then(r => r.data),
}
