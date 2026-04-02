/**
 * FILE PURPOSE
 * This file provides the frontend API client functions for all machine-related operations
 * in the ZetaOps Copilot workforce scheduling system. It was introduced in early v4 
 * development and serves as the bridge between React components and the FastAPI backend's
 * machine endpoints. This sits in the API layer of the frontend architecture, abstracting
 * HTTP calls and providing type-safe interfaces for machine CRUD operations, CSV imports,
 * and job assignment queries.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Imports the configured apiClient instance from './client' which handles authentication
 * 2. Imports TypeScript type definitions for Machine objects and CSV import results
 * 3. Exports a single machinesApi object containing all machine-related API functions
 * 4. Provides standard CRUD operations (list, get, create, update, delete) for machines
 * 5. Includes a specialized assignments function to fetch job assignments for a machine
 * 6. Implements CSV import functionality with FormData handling for bulk machine creation
 * 7. Provides template download capability for users to understand CSV import format
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : machinesApi.list
 * Type         : function
 * Purpose      : Fetches all machines for the current tenant from the backend. This is used
 *                to populate machine selection dropdowns, machine overview pages, and for
 *                the scheduler to know what equipment is available for job assignments.
 * Parameters   : none
 * Returns      : Promise<Machine[]> - array of Machine objects with all machine data
 * Calls        : apiClient.get() which makes authenticated HTTP request to backend
 * DB/API       : GET /machines/ - backend queries machines table filtered by tenant_id
 * Side effects : none - pure read operation
 *
 * Name         : machinesApi.get
 * Type         : function
 * Purpose      : Fetches a single machine by its ID for detailed views, editing forms, or
 *                when the scheduler needs specific machine capabilities and availability data.
 * Parameters   : id (number) - the unique machine ID to retrieve
 * Returns      : Promise<Machine> - single Machine object with all fields populated
 * Calls        : apiClient.get() with machine ID in URL path
 * DB/API       : GET /machines/{id} - backend queries specific machine with tenant scoping
 * Side effects : none - pure read operation
 *
 * Name         : machinesApi.create
 * Type         : function
 * Purpose      : Creates a new machine record in the system. Used by machine creation forms
 *                to add new equipment to the tenant's available resources for scheduling.
 *                The payload is loosely typed to accommodate different machine creation scenarios.
 * Parameters   : payload (object) - machine data including name, type, capabilities, rates
 * Returns      : Promise<Machine> - the newly created Machine object with assigned ID
 * Calls        : apiClient.post() to send machine data to backend
 * DB/API       : POST /machines/ - backend inserts new machine with current tenant_id
 * Side effects : creates new database record, affects future scheduling availability
 *
 * Name         : machinesApi.update
 * Type         : function
 * Purpose      : Updates an existing machine's properties like name, status, capabilities,
 *                or hourly rates. Critical for maintaining accurate scheduling data and
 *                handling equipment maintenance status changes.
 * Parameters   : id (number) - machine ID to update, p (object) - partial machine data
 * Returns      : Promise<Machine> - the updated Machine object with new values
 * Calls        : apiClient.patch() to send partial update to backend
 * DB/API       : PATCH /machines/{id} - backend updates machine record with tenant validation
 * Side effects : modifies database record, may affect active job assignments and scheduling
 *
 * Name         : machinesApi.delete
 * Type         : function
 * Purpose      : Removes a machine from the system permanently. Used when equipment is
 *                decommissioned or no longer available. Backend should handle cascade deletion
 *                of related assignments and prevent deletion if machine has active jobs.
 * Parameters   : id (number) - machine ID to delete
 * Returns      : Promise<void> - no data returned, success indicated by resolved promise
 * Calls        : apiClient.delete() with machine ID in URL
 * DB/API       : DELETE /machines/{id} - backend removes machine with safety checks
 * Side effects : permanently removes database record, affects scheduling engine availability
 *
 * Name         : machinesApi.assignments
 * Type         : function
 * Purpose      : Retrieves all current job assignments for a specific machine. Essential for
 *                machine utilization views, conflict detection, and understanding what work
 *                is currently allocated to each piece of equipment.
 * Parameters   : id (number) - machine ID to get assignments for
 * Returns      : Promise<JobAssignment[]> - array of assignment records linking jobs to machine
 * Calls        : apiClient.get() to fetch assignment data from backend
 * DB/API       : GET /assignments/machine/{id} - backend queries JobAssignment table
 * Side effects : none - pure read operation for reporting and visualization
 *
 * Name         : machinesApi.importCsv
 * Type         : function
 * Purpose      : Handles bulk machine creation from CSV file uploads. Creates FormData object
 *                to properly encode file for multipart upload. Used by import wizards to
 *                populate machine data quickly for new tenants or bulk equipment additions.
 * Parameters   : file (File) - browser File object from file input or drag-drop
 * Returns      : Promise<ImportResult> - summary of import success/failure with error details
 * Calls        : apiClient.post() with FormData containing the CSV file
 * DB/API       : POST /import/machines - backend processes CSV and creates multiple machines
 * Side effects : creates multiple database records, validates CSV format, reports conflicts
 *
 * Name         : machinesApi.downloadTemplate
 * Type         : function
 * Purpose      : Downloads a CSV template file showing the expected format and columns for
 *                machine imports. Helps users understand required fields and data formats
 *                before attempting bulk imports.
 * Parameters   : none
 * Returns      : Promise<Blob> - binary CSV file data for browser download
 * Calls        : apiClient.get() with blob response type for file download
 * DB/API       : GET /import/template/machines - backend returns pre-formatted CSV template
 * Side effects : triggers browser file download with template CSV
 *
 * WHO CALLS THIS FILE
 * - ../pages/MachinesPage.tsx - main machine management interface
 * - ../pages/MachineDetailPage.tsx - individual machine view and editing
 * - ../pages/ImportWizardPage.tsx - bulk CSV import functionality  
 * - ../components/MachineSelector.tsx - dropdown for job assignment forms
 * - ../components/ScheduleView.tsx - displays machine utilization and assignments
 * - ../components/ResourceAvailability.tsx - shows machine availability for scheduling
 *
 * IMPORTS EXPLAINED
 * - apiClient from './client': The configured Axios instance with authentication headers,
 *   base URL, and token refresh logic that handles all HTTP communication with the backend.
 * - Machine type: TypeScript interface defining the shape of machine objects including
 *   id, name, machine_type, status, hourly_rate, and other machine properties.
 * - ImportResult
 */

```
 */

import apiClient from './client'
import type { Machine, ImportResult } from '../types'

export const machinesApi = {
  list: ()                        => apiClient.get<Machine[]>('/machines/').then(r => r.data),
  get:  (id: number)              => apiClient.get<Machine>(`/machines/${id}`).then(r => r.data),
  create: (payload: object)       => apiClient.post<Machine>('/machines/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Machine>(`/machines/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/machines/${id}`),
  assignments: (id: number)       => apiClient.get(`/assignments/machine/${id}`).then(r => r.data),
  importCsv: (file: File)         => {
    const fd = new FormData(); fd.append('file', file)
    return apiClient.post<ImportResult>('/import/machines', fd).then(r => r.data)
  },
  downloadTemplate: ()            => apiClient.get('/import/template/machines', { responseType: 'blob' }),
}
