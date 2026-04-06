import apiClient from './client'
import type { Machine, ImportResult } from '../types/types_index'
import { MACHINES, ASSIGNMENTS, IMPORT } from './api_endpoints'

export const machinesApi = {
  list: ()                        => apiClient.get<Machine[]>(MACHINES.list).then(r => r.data),
  get:  (id: number)              => apiClient.get<Machine>(MACHINES.detail(id)).then(r => r.data),
  create: (payload: object)       => apiClient.post<Machine>(MACHINES.list, payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Machine>(MACHINES.detail(id), p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(MACHINES.detail(id)),
  assignments: (id: number)       => apiClient.get(ASSIGNMENTS.byMachine(id)).then(r => r.data),
  importCsv: (file: File)         => {
    const fd = new FormData(); fd.append('file', file)
    return apiClient.post<ImportResult>(IMPORT.machines, fd).then(r => r.data)
  },
  downloadTemplate: ()            => apiClient.get(IMPORT.template("machines"), { responseType: 'blob' }),
}
