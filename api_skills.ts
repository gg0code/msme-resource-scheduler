/**
```typescript
/**
 * Skills API Client Module
 * 
 * FILE PURPOSE
 * This file provides TypeScript client functions for interacting with the Skills API endpoints
 * in the ZetaOps Copilot manufacturing scheduling system. It exists to centralize all skill-related
 * HTTP requests and provide type-safe API calls to React components. This file was introduced in
 * the v4-dev branch and sits in the frontend API layer, acting as a bridge between React components
 * and the FastAPI backend's skills endpoints.
 * 
 * WHAT THIS FILE DOES — step by step
 * 1. Imports the shared apiClient (authenticated Axios instance) from client.ts
 * 2. Imports TypeScript types for Skill entities and CSV import results
 * 3. Exports a skillsApi object containing 6 methods for CRUD operations and CSV import/export
 * 4. Each method wraps apiClient HTTP calls with proper TypeScript generics for response typing
 * 5. Handles FormData creation for file uploads in the CSV import functionality
 * 6. Provides blob response handling for CSV template downloads
 * 
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 * 
 * Name         : skillsApi.list
 * Type         : function
 * Purpose      : Retrieves all skills for the current tenant from the backend API. Used by
 *                skill management pages to display existing skills in tables or dropdowns.
 * Parameters   : none
 * Returns      : Promise<Skill[]> - array of skill objects with id, name, description, tenant_id
 * Calls        : apiClient.get() which calls backend /api/skills/ endpoint
 * DB/API       : GET /api/skills/ - backend queries skills table filtered by tenant_id
 * Side effects : none (read-only operation)
 * 
 * Name         : skillsApi.create
 * Type         : function
 * Purpose      : Creates a new skill record by sending skill data to the backend. Used by
 *                skill creation forms to persist new skills to the database.
 * Parameters   : payload: object - skill data including name, description, and other properties
 * Returns      : Promise<Skill> - the newly created skill object with generated id
 * Calls        : apiClient.post() which calls backend /api/skills/ endpoint
 * DB/API       : POST /api/skills/ - backend inserts new skill with current user's tenant_id
 * Side effects : creates new database record, increments skill count for tenant
 * 
 * Name         : skillsApi.update
 * Type         : function
 * Purpose      : Updates an existing skill by sending partial data to the backend. Used by
 *                skill edit forms to save changes to skill properties like name or description.
 * Parameters   : id: number - the skill ID to update
 *                p: object - partial skill data containing only fields to update
 * Returns      : Promise<Skill> - the updated skill object with all current values
 * Calls        : apiClient.patch() which calls backend /api/skills/{id} endpoint
 * DB/API       : PATCH /api/skills/{id} - backend updates skill record if tenant owns it
 * Side effects : modifies existing database record, triggers audit log entry
 * 
 * Name         : skillsApi.delete
 * Type         : function
 * Purpose      : Deletes a skill record from the system. Used by skill management interfaces
 *                when users confirm deletion of skills no longer needed.
 * Parameters   : id: number - the skill ID to delete
 * Returns      : Promise<void> - resolves when deletion completes successfully
 * Calls        : apiClient.delete() which calls backend /api/skills/{id} endpoint
 * DB/API       : DELETE /api/skills/{id} - backend soft-deletes skill if tenant owns it
 * Side effects : removes skill from database, may cascade to employee skill associations
 * 
 * Name         : skillsApi.importCsv
 * Type         : function
 * Purpose      : Uploads a CSV file containing skill data for bulk import. Used by import
 *                workflows to allow users to create multiple skills at once from spreadsheets.
 * Parameters   : file: File - the CSV file object from HTML file input element
 * Returns      : Promise<ImportResult> - contains success/failure counts and error details
 * Calls        : apiClient.post() which calls backend /api/import/skills endpoint
 * DB/API       : POST /api/import/skills - backend processes CSV and creates skill records
 * Side effects : creates FormData object, potentially creates many database records
 * 
 * Name         : skillsApi.downloadTemplate
 * Type         : function
 * Purpose      : Downloads a CSV template file showing the expected format for skill imports.
 *                Used by import workflows to help users format their data correctly.
 * Parameters   : none
 * Returns      : Promise<Blob> - binary data for CSV file that browser can save/download
 * Calls        : apiClient.get() with blob responseType for file download
 * DB/API       : GET /api/import/template/skills - backend returns CSV template file
 * Side effects : triggers file download in browser when response is processed
 * 
 * WHO CALLS THIS FILE
 * - src/pages/SkillsPage.tsx - main skills management interface
 * - src/components/SkillForm.tsx - skill creation and editing forms
 * - src/components/ImportSkillsModal.tsx - CSV import dialog component
 * - src/components/EmployeeSkillsSelector.tsx - skill assignment dropdowns
 * - src/pages/EmployeePage.tsx - when managing employee skill associations
 * 
 * IMPORTS EXPLAINED
 * - apiClient from './client' - the configured Axios instance with authentication headers and
 *   base URL that handles JWT tokens and automatic refresh token logic for all API calls
 * - Skill type from '../types' - TypeScript interface defining the shape of skill objects
 *   including id, tenant_id, name, description, and created_at fields
 * - ImportResult type from '../types' - TypeScript interface for CSV import responses
 *   containing success_count, error_count, and errors array for import feedback
 * 
 * INTERN NOTES
 * - Easiest thing to break without realising: changing the endpoint URLs without updating
 *   corresponding backend routes, or modifying payload structure without backend coordination
 * - Non-obvious design decision and why: all methods extract .data from Axios responses to
 *   return just the payload, hiding HTTP metadata from React components for cleaner usage
 * - Most common mistake when editing: forgetting to update TypeScript generics when changing
 *   payload or response structures, leading to type safety issues that only surface at runtime
 * - Which design principle this implements: Design principle #4 - all backend routes use /api/
 *   prefix, and principle #2 - tenant scoping handled automatically by authenticated apiClient
 * - What to check if this file behaves unexpectedly: verify apiClient authentication state,
 *   check network tab for HTTP status codes, and ensure backend skills router is registered
 * - v4-dev specific: this file is stable and should not be modified without coordinating
 *   with backend API changes, as skills are core to the scheduling engine functionality
 */
```
 */

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
