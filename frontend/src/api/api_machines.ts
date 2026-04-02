/**
 * frontend/src/api/api_machines.ts
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Provides all frontend API functions for machine management in ZetaOps Copilot.
 * Machines are physical production assets (CNC lathes, welders, grinders) that get
 * assigned to jobs. This file is the single source of all HTTP calls related to
 * machines — CRUD operations, assignment queries, and CSV/XLSX import. Introduced
 * in v4.0.9. Sits in the frontend API layer; UI components never call fetch() or
 * axios directly, they always go through this file.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Imports the shared authenticated Axios instance (apiClient) from ./client.
 * 2. Imports Machine and ImportResult TypeScript types from types_index.ts.
 * 3. Exports machinesApi object with all machine-related API methods as properties.
 * 4. list() — fetches all machines for the current tenant.
 * 5. get() — fetches a single machine by ID.
 * 6. create() — POSTs a new machine record.
 * 7. update() — PATCHes an existing machine (partial update).
 * 8. delete() — DELETEs a machine by ID.
 * 9. assignments() — fetches all job assignments linked to a specific machine.
 * 10. importCsv() — uploads a CSV or XLSX file to bulk-import machines.
 * 11. downloadTemplate() — downloads the CSV/XLSX template for bulk import.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : machinesApi.list
 * Type         : function
 * Purpose      : Fetches all machines for the authenticated tenant. Backend filters
 *                by tenant_id automatically from the JWT token — no tenant param needed.
 * Parameters   : none
 * Returns      : Promise<Machine[]>
 * Calls        : apiClient.get('/api/machines/')
 * DB/API       : GET /api/machines/
 * Side effects : none
 *
 * Name         : machinesApi.get
 * Type         : function
 * Purpose      : Fetches one machine by its database ID. Used by edit forms and
 *                detail views that need complete machine data including skill requirements.
 * Parameters   : id: number — machine primary key
 * Returns      : Promise<Machine>
 * Calls        : apiClient.get('/api/machines/{id}')
 * DB/API       : GET /api/machines/{id}
 * Side effects : none
 *
 * Name         : machinesApi.create
 * Type         : function
 * Purpose      : Creates a new machine record. The backend sets tenant_id from the
 *                JWT token. Triggers plan limit check on the backend (free plan: 10 machines).
 * Parameters   : payload: object — machine fields matching MachineCreate schema
 * Returns      : Promise<Machine> — the created machine with server-assigned ID
 * Calls        : apiClient.post('/api/machines/')
 * DB/API       : POST /api/machines/
 * Side effects : inserts machine row, may be blocked by plan limit (HTTP 402)
 *
 * Name         : machinesApi.update
 * Type         : function
 * Purpose      : Partially updates a machine. Only fields present in the payload
 *                are changed. Used by the machine edit form.
 * Parameters   : id: number, p: object — partial machine fields
 * Returns      : Promise<Machine> — the updated machine
 * Calls        : apiClient.patch('/api/machines/{id}')
 * DB/API       : PATCH /api/machines/{id}
 * Side effects : updates machine row in DB
 *
 * Name         : machinesApi.delete
 * Type         : function
 * Purpose      : Deletes a machine permanently. Requires proprietor role on backend.
 *                Cascades to skill requirements and availability overrides via DB FK.
 * Parameters   : id: number
 * Returns      : Promise (void on 204)
 * Calls        : apiClient.delete('/api/machines/{id}')
 * DB/API       : DELETE /api/machines/{id}
 * Side effects : permanently removes machine + cascaded FK rows
 *
 * Name         : machinesApi.assignments
 * Type         : function
 * Purpose      : Fetches all job assignments for a given machine. Used to show which
 *                jobs a machine is currently or historically assigned to.
 * Parameters   : id: number — machine ID
 * Returns      : Promise<any[]> — array of assignment objects
 * Calls        : apiClient.get('/api/assignments/machine/{id}')
 * DB/API       : GET /api/assignments/machine/{id}
 * Side effects : none
 *
 * Name         : machinesApi.importCsv
 * Type         : function
 * Purpose      : Uploads a CSV or XLSX file to bulk-import machines. Sends as
 *                multipart/form-data. Backend returns row counts and per-row errors.
 * Parameters   : file: File — the CSV or XLSX file selected by the user
 * Returns      : Promise<ImportResult> — { rows_imported, rows_failed, errors[] }
 * Calls        : apiClient.post('/api/import/machines', FormData)
 * DB/API       : POST /api/import/machines
 * Side effects : inserts multiple machine rows, creates skills if missing
 *
 * Name         : machinesApi.downloadTemplate
 * Type         : function
 * Purpose      : Downloads the CSV/XLSX import template for machines. Returns a
 *                binary blob that the caller saves as a file download.
 * Parameters   : none
 * Returns      : Promise<AxiosResponse> with responseType: 'blob'
 * Calls        : apiClient.get('/api/import/template/machines')
 * DB/API       : GET /api/import/template/machines
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Machines.tsx — CRUD operations and import
 * - frontend/src/pages/Jobs.tsx — machine list for job assignment
 * - frontend/src/components/common/CsvImport.tsx — import and template download
 *
 * IMPORTS EXPLAINED
 * - apiClient from './client': Authenticated Axios instance with JWT bearer token,
 *   base URL, and 401 auto-refresh. All HTTP calls go through this.
 * - Machine from '../types/types_index': TypeScript shape of a machine record.
 * - ImportResult from '../types/types_index': Shape of the bulk import response.
 *
 * INTERN NOTES
 * - Tenant scoping is handled automatically by the backend — never pass tenant_id
 *   in the payload. The JWT token already identifies the tenant (Design Principle 2).
 * - The delete endpoint requires proprietor role. Calling it as a scheduler will
 *   return HTTP 403 — handle this in the UI before calling.
 * - importCsv uses FormData, not JSON. The Content-Type header is set automatically
 *   by the browser when appending a File to FormData — do not set it manually.
 * - downloadTemplate returns a blob. The caller must create a URL.createObjectURL()
 *   and trigger an anchor click to save it — see CsvImport.tsx for the pattern.
 * - Design Principle 4: All endpoint paths start with /api/ — never omit this prefix.
 * - If list() returns an empty array unexpectedly: check that the tenant has machines
 *   seeded, that the JWT is valid, and that the backend /api/machines/ endpoint is
 *   registered in main.py.
 */

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
