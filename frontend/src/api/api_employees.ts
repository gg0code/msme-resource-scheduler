import apiClient from './client'
import type { Employee, ImportResult } from '../types'

export const employeesApi = {
  list: ()                        => apiClient.get<Employee[]>('/api/employees/').then(r => r.data),
  get:  (id: number)              => apiClient.get<Employee>(`/api/employees/${id}`).then(r => r.data),
  create: (payload: object)       => apiClient.post<Employee>('/api/employees/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Employee>(`/api/employees/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/api/employees/${id}`),
  assignments: (id: number)       => apiClient.get(`/api/assignments/employee/${id}`).then(r => r.data),
  importCsv: (file: File)         => {
    const fd = new FormData(); fd.append('file', file)
    return apiClient.post<ImportResult>('/api/import/employees', fd).then(r => r.data)
  },
  downloadTemplate: ()            => apiClient.get('/api/import/template/employees', { responseType: 'blob' }),
}
