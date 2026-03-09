// src/api/api_gantt.ts
// Fetches job data for the Production Timeline (Gantt) page.
// Matches the GanttJob schema returned by GET /api/gantt/

import apiClient from './client'

export interface GanttJob {
  id: number
  name: string
  customer: string | null
  start_date: string | null
  end_date: string | null
  priority: string | null
  status: string | null
  timer_status: string | null
  assigned_employees: string[]
  assigned_machines: string[]
  has_conflict: boolean
  conflict_reasons: string[]
  /** 'ready' | 'conflict' | 'in_progress' | 'completed' | 'stopped' */
  status_icon: string
  tentative_cost: number | null
  tentative_profit: number | null
}

export async function fetchGanttData(): Promise<GanttJob[]> {
  const res = await apiClient.get<GanttJob[]>('/api/gantt/')
  return res.data
}
