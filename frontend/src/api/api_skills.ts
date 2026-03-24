import apiClient from './client'
import type { Skill, ImportResult } from '../types'

export const skillsApi = {
  list: ()                        => apiClient.get<Skill[]>('/api/skills/').then(r => r.data),
  create: (payload: object)       => apiClient.post<Skill>('/api/skills/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Skill>(`/api/skills/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/api/skills/${id}`),
  importCsv: (file: File)         => {
    const fd = new FormData(); fd.append('file', file)
    return apiClient.post<ImportResult>('/api/import/skills', fd).then(r => r.data)
  },
  downloadTemplate: ()            => apiClient.get('/api/import/template/skills', { responseType: 'blob' }),
}
