import apiClient from './client'
import type { DashboardData } from '../types'

export const dashboardApi = {
  get: () => apiClient.get<DashboardData>('/dashboard/').then(r => r.data),
}
