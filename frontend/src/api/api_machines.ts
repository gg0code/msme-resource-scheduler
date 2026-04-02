import apiClient from './client'
import type { Machine, ImportResult } from '../types/types_index'

export const machinesApi = {
  list: ()                        => apiClient.get<Machine[]>('/api/machines/').then(r => r.data),
  get:  (id: number)              => apiClient.get<Machine>(`/api/machines/${id}`).then(r => r.data),
  create: (payload: object)       => apiClient.post<Machine>('/api/machines/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Machine>(`/api/machines/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/api/machines/${id}`),
  assignments: (id: number)       => apiClient.get(`/api/assignments/machine/${id}`).then(r => r.data),
  importCsv: (file: File)         => {
    const fd = new FormData(); fd.append('file', file)
    return apiClient.post<ImportResult>('/api/import/machines', fd).then(r => r.data)
  },
  downloadTemplate: ()            => apiClient.get('/api/import/template/machines', { responseType: 'blob' }),
}
