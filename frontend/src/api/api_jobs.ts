import apiClient from './client'
import type { Job } from '../types/types_index'
import { JOBS, ASSIGNMENTS } from './api_endpoints'

export const jobsApi = {
  list: ()                        => apiClient.get<Job[]>(JOBS.list).then(r => r.data),
  get:  (id: number)              => apiClient.get<Job>(JOBS.detail(id)).then(r => r.data),
  create: (payload: object)       => apiClient.post<Job>(JOBS.list, payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Job>(JOBS.detail(id), p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(JOBS.detail(id)),
  timer:  (id: number, action: string) => apiClient.post(JOBS.timer(id), { action }).then(r => r.data),
  checkAvailability: (id: number) => apiClient.get(ASSIGNMENTS.check(id)).then(r => r.data),
  assign: (jobId: number, employeeIds: number[], machineIds: number[]) =>
    apiClient.post(ASSIGNMENTS.create, { job_id: jobId, employee_ids: employeeIds, machine_ids: machineIds }).then(r => r.data),
}
