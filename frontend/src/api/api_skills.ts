import apiClient from './client'
import type { Skill, ImportResult } from '../types/types_index'
import { SKILLS, IMPORT } from './api_endpoints'

export const skillsApi = {
  list: ()                        => apiClient.get<Skill[]>(SKILLS.list).then(r => r.data),
  create: (payload: object)       => apiClient.post<Skill>(SKILLS.list, payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Skill>(SKILLS.update(id), p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(SKILLS.update(id)),
  importCsv: (file: File)         => {
    const fd = new FormData(); fd.append('file', file)
    return apiClient.post<ImportResult>(IMPORT.skills, fd).then(r => r.data)
  },
  downloadTemplate: ()            => apiClient.get(IMPORT.template("skills"), { responseType: 'blob' }),
}
