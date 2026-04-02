/**
 * frontend/src/api/api_skills.ts
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Provides all frontend API functions for skill management in ZetaOps Copilot.
 * Skills are competency tags (e.g. "CNC Operation", "Welding") that get attached
 * to employees and used as requirements on jobs and machines. This file is the
 * single source of all HTTP calls related to skills — CRUD, CSV import, and
 * template download. Sits in the frontend API layer; introduced in v4.0.9.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Imports the shared authenticated Axios instance from ./client.
 * 2. Imports Skill and ImportResult TypeScript types from types_index.ts.
 * 3. Exports skillsApi object with all skill-related API methods.
 * 4. list() — fetches all skills for the current tenant.
 * 5. create() — creates a new skill.
 * 6. update() — partially updates an existing skill.
 * 7. delete() — removes a skill by ID.
 * 8. importCsv() — bulk-imports skills from a CSV file.
 * 9. downloadTemplate() — downloads the CSV template for bulk import.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : skillsApi.list
 * Type         : function
 * Purpose      : Fetches all active skills for the tenant. Used by employee forms
 *                (assign skills to employees), job forms (skill requirements), and
 *                the Skills management page.
 * Parameters   : none
 * Returns      : Promise<Skill[]>
 * Calls        : apiClient.get('/api/skills/')
 * DB/API       : GET /api/skills/
 * Side effects : none
 *
 * Name         : skillsApi.create
 * Type         : function
 * Purpose      : Creates a new skill record for the tenant. Used by the skill creation
 *                form on the Skills page. Requires proprietor or scheduler role.
 *                Free plan limit: 20 skills (enforced by backend).
 * Parameters   : payload: object — skill fields matching SkillCreate schema
 * Returns      : Promise<Skill>
 * Calls        : apiClient.post('/api/skills/')
 * DB/API       : POST /api/skills/
 * Side effects : inserts skill row, may be blocked by plan limit (HTTP 402)
 *
 * Name         : skillsApi.update
 * Type         : function
 * Purpose      : Partially updates a skill (name, category, is_active etc.).
 *                Used by the inline edit form on the Skills page.
 * Parameters   : id: number, p: object — partial skill fields
 * Returns      : Promise<Skill>
 * Calls        : apiClient.patch('/api/skills/{id}')
 * DB/API       : PATCH /api/skills/{id}
 * Side effects : updates skill row
 *
 * Name         : skillsApi.delete
 * Type         : function
 * Purpose      : Soft-deletes or hard-deletes a skill. Backend behaviour depends
 *                on whether the skill has existing employee/job references.
 * Parameters   : id: number
 * Returns      : Promise (void on 204)
 * Calls        : apiClient.delete('/api/skills/{id}')
 * DB/API       : DELETE /api/skills/{id}
 * Side effects : removes or marks skill inactive
 *
 * Name         : skillsApi.importCsv
 * Type         : function
 * Purpose      : Bulk-imports skills from a CSV file. Only CSV is supported for
 *                skills (unlike employees/machines which also support XLSX).
 * Parameters   : file: File — the CSV file
 * Returns      : Promise<ImportResult> — { rows_imported, rows_failed, errors[] }
 * Calls        : apiClient.post('/api/import/skills', FormData)
 * DB/API       : POST /api/import/skills
 * Side effects : inserts multiple skill rows, skips duplicates
 *
 * Name         : skillsApi.downloadTemplate
 * Type         : function
 * Purpose      : Downloads the CSV template for skill import.
 * Parameters   : none
 * Returns      : Promise<AxiosResponse> with responseType: 'blob'
 * Calls        : apiClient.get('/api/import/template/skills')
 * DB/API       : GET /api/import/template/skills
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Skills.tsx — full CRUD and import
 * - frontend/src/pages/Employees.tsx — skill list for employee skill assignment
 * - frontend/src/pages/Jobs.tsx — skill list for job skill requirements
 * - frontend/src/pages/Machines.tsx — skill list for machine skill requirements
 *
 * IMPORTS EXPLAINED
 * - apiClient from './client': Authenticated Axios instance — all HTTP calls go here.
 * - Skill from '../types/types_index': TypeScript shape of a skill record.
 * - ImportResult from '../types/types_index': Shape of the bulk import response.
 *
 * INTERN NOTES
 * - Skills are unique per tenant (unique constraint on tenant_id + name). Importing
 *   a duplicate name will skip that row and report it in errors[], not fail the whole import.
 * - The Skills page is restricted to proprietor role only (App.tsx ProtectedRoute).
 *   The API calls themselves require proprietor or scheduler — the UI guard is extra protection.
 * - Design Principle 2: Tenant scoping is automatic via JWT. Never pass tenant_id manually.
 * - Design Principle 4: All paths start with /api/.
 * - Skills must exist before employees or jobs can reference them. If a job form shows
 *   no skills in the dropdown, run: seed_generic_roles.py --tenant-id <id> to populate defaults.
 * - If list() returns empty unexpectedly: verify the tenant has skills seeded and the JWT
 *   token is valid (check Network tab in browser devtools).
 */

import apiClient from './client'
import type { Skill, ImportResult } from '../types/types_index'

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
