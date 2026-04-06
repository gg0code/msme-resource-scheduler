import apiClient from './client'
import type { Employee, ImportResult } from '../types/types_index'
import { EMPLOYEES, ASSIGNMENTS, IMPORT } from './api_endpoints'

export const employeesApi = {
  list: ()                        => apiClient.get<Employee[]>(EMPLOYEES.list).then(r => r.data),
  get:  (id: number)              => apiClient.get<Employee>(EMPLOYEES.detail(id)).then(r => r.data),
  create: (payload: object)       => apiClient.post<Employee>(EMPLOYEES.list, payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Employee>(EMPLOYEES.detail(id), p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(EMPLOYEES.detail(id)),
  assignments: (id: number)       => apiClient.get(ASSIGNMENTS.byEmployee(id)).then(r => r.data),
  importCsv: (file: File)         => {
    const fd = new FormData(); fd.append('file', file)
    return apiClient.post<ImportResult>(IMPORT.employees, fd).then(r => r.data)
  },
  downloadTemplate: ()            => apiClient.get(IMPORT.template("employees"), { responseType: 'blob' }),
}
