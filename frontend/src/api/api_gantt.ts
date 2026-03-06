// src/api/api_gantt.ts — V2.0
import apiClient from './client'

export interface GanttJob {
  id: number
  name: string
  customer?: string
  start_date?: string
  end_date?: string
  priority?: string
  status?: string
  timer_status?: string
  assigned_employees: string[]
  assigned_machines: string[]
  has_conflict: boolean
  conflict_reasons: string[]
  status_icon: string
  tentative_cost?: number
  tentative_profit?: number
}

export async function fetchGanttData(): Promise<GanttJob[]> {
  const res = await apiClient.get<GanttJob[]>('/gantt/')
  return res.data
}
