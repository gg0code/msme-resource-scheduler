import apiClient from './client'
import type { Skill, ImportResult } from '../types'

export const skillsApi = {
  list: ()                        => apiClient.get<Skill[]>('/skills/').then(r => r.data),
  create: (payload: object)       => apiClient.post<Skill>('/skills/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Skill>(`/skills/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/skills/${id}`),
  importCsv: (file: File)         => {
    const fd = new FormData(); fd.append('file', file)
    return apiClient.post<ImportResult>('/import/skills', fd).then(r => r.data)
  },
  downloadTemplate: ()            => apiClient.get('/import/template/skills', { responseType: 'blob' }),
}
