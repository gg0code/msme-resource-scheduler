import apiClient from './client'
import type { Job } from '../types/types_index'

export const jobsApi = {
  list: ()                        => apiClient.get<Job[]>('/api/jobs/').then(r => r.data),
  get:  (id: number)              => apiClient.get<Job>(`/api/jobs/${id}`).then(r => r.data),
  create: (payload: object)       => apiClient.post<Job>('/api/jobs/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Job>(`/api/jobs/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/api/jobs/${id}`),
  timer:  (id: number, action: string) => apiClient.post(`/api/jobs/${id}/timer`, { action }).then(r => r.data),
  checkAvailability: (id: number) => apiClient.get(`/api/assignments/check/${id}`).then(r => r.data),
  assign: (jobId: number, employeeIds: number[], machineIds: number[]) =>
    apiClient.post('/api/assignments/', { job_id: jobId, employee_ids: employeeIds, machine_ids: machineIds }).then(r => r.data),
}
