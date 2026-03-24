import apiClient from './client'
import type { Job } from '../types'

export const jobsApi = {
  list: ()                        => apiClient.get<Job[]>('/jobs/').then(r => r.data),
  get:  (id: number)              => apiClient.get<Job>(`/jobs/${id}`).then(r => r.data),
  create: (payload: object)       => apiClient.post<Job>('/jobs/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Job>(`/jobs/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/jobs/${id}`),
  timer:  (id: number, action: string) => apiClient.post(`/jobs/${id}/timer`, { action }).then(r => r.data),
  checkAvailability: (id: number) => apiClient.get(`/assignments/check/${id}`).then(r => r.data),
  assign: (jobId: number, employeeIds: number[], machineIds: number[]) =>
    apiClient.post('/assignments/', { job_id: jobId, employee_ids: employeeIds, machine_ids: machineIds }).then(r => r.data),
}
