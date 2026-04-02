/**
```typescript
/**
 * FILE PURPOSE
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * This file provides the frontend API client functions for all job-related operations
 * in the ZetaOps Copilot scheduling system. It serves as the bridge between React
 * components and the FastAPI backend's job endpoints, handling CRUD operations,
 * timer controls, and resource assignment functionality. This file was introduced
 * in the early v4.x releases and sits in the frontend API layer, abstracting
 * HTTP calls and providing type-safe interfaces for job management operations.
 *
 * WHAT THIS FILE DOES — step by step
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 1. Imports the configured Axios client from './client' that handles authentication
 * 2. Imports the Job type definition from the shared types system
 * 3. Exports a single jobsApi object containing all job-related API functions
 * 4. Provides standard CRUD operations (list, get, create, update, delete) for jobs
 * 5. Offers specialized job timer control functionality (start/pause/stop/reset)
 * 6. Includes resource availability checking before job assignment
 * 7. Handles job-to-resource assignment operations (employees and machines)
 * 8. All functions return promises that resolve to typed data or handle errors
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * Name         : jobsApi.list
 * Type         : function
 * Purpose      : Fetches all jobs for the current tenant from the backend.
 *                This is used by job listing pages and dashboard components
 *                to display the complete job inventory. The backend automatically
 *                filters by tenant_id based on the authenticated user's context.
 * Parameters   : none
 * Returns      : Promise<Job[]> - array of Job objects representing all jobs
 *                accessible to the current tenant
 * Calls        : apiClient.get() which uses the authenticated Axios instance
 * DB/API       : GET /api/jobs/ - backend queries Job table with tenant filtering
 * Side effects : none - pure read operation
 *
 * Name         : jobsApi.get
 * Type         : function
 * Purpose      : Retrieves a single job by its ID, including all related data
 *                like job steps, assignments, and metadata. Used by job detail
 *                views and edit forms that need complete job information.
 * Parameters   : id (number) - the unique job ID to fetch
 * Returns      : Promise<Job> - single Job object with all related data
 * Calls        : apiClient.get() with job-specific endpoint
 * DB/API       : GET /api/jobs/{id} - backend queries Job table with tenant+ID filter
 * Side effects : none - pure read operation
 *
 * Name         : jobsApi.create
 * Type         : function
 * Purpose      : Creates a new job in the system with the provided job data.
 *                Used by job creation forms and import processes. The payload
 *                must contain all required job fields as defined in backend schemas.
 * Parameters   : payload (object) - job creation data matching backend Pydantic schema
 * Returns      : Promise<Job> - the newly created Job object with assigned ID
 * Calls        : apiClient.post() to submit job data
 * DB/API       : POST /api/jobs/ - backend inserts into Job table with tenant_id
 * Side effects : creates new database record, may trigger scheduling recalculation
 *
 * Name         : jobsApi.update
 * Type         : function
 * Purpose      : Updates an existing job with partial or complete new data.
 *                Used by job edit forms and bulk update operations. Only
 *                provided fields are updated, others remain unchanged.
 * Parameters   : id (number) - job ID to update
 *                p (object) - partial job data matching backend update schema
 * Returns      : Promise<Job> - the updated Job object with new values
 * Calls        : apiClient.patch() with job-specific endpoint
 * DB/API       : PATCH /api/jobs/{id} - backend updates Job table with tenant filtering
 * Side effects : modifies database record, may trigger scheduling recalculation
 *
 * Name         : jobsApi.delete
 * Type         : function
 * Purpose      : Permanently removes a job and all its related data (steps,
 *                assignments, timers) from the system. Used by job management
 *                interfaces when users confirm job deletion.
 * Parameters   : id (number) - job ID to delete
 * Returns      : Promise<void> - resolves when deletion completes
 * Calls        : apiClient.delete() with job-specific endpoint
 * DB/API       : DELETE /api/jobs/{id} - backend cascades deletion with tenant filtering
 * Side effects : removes database records, triggers scheduling recalculation
 *
 * Name         : jobsApi.timer
 * Type         : function
 * Purpose      : Controls job timer state for time tracking functionality.
 *                Accepts actions like "start", "pause", "stop", or "reset"
 *                to manage job execution timing. Used by job control interfaces
 *                and mobile timer widgets.
 * Parameters   : id (number) - job ID to control timer for
 *                action (string) - timer action ("start"|"pause"|"stop"|"reset")
 * Returns      : Promise<any> - timer status and updated job timing data
 * Calls        : apiClient.post() with timer-specific endpoint
 * DB/API       : POST /api/jobs/{id}/timer - backend updates Job.timer_status
 * Side effects : modifies job timing fields, may update JobStep timing data
 *
 * Name         : jobsApi.checkAvailability
 * Type         : function
 * Purpose      : Validates whether required employees and machines are available
 *                for the specified job based on scheduling constraints and
 *                existing assignments. Used before job assignment to prevent
 *                conflicts and provide user feedback about resource availability.
 * Parameters   : id (number) - job ID to check availability for
 * Returns      : Promise<any> - availability report with conflict details
 * Calls        : apiClient.get() with assignment-specific endpoint
 * DB/API       : GET /api/assignments/check/{id} - backend queries availability engine
 * Side effects : none - pure read operation that checks constraints
 *
 * Name         : jobsApi.assign
 * Type         : function
 * Purpose      : Creates job assignments linking the specified job to selected
 *                employees and machines. This establishes the resource allocation
 */

import apiClient from './client'
import type { Job } from '../types/types_index'

export const jobsApi = {
  list: ()                        => apiClient.get<Job[]>('/api/jobs/').then(r => r.data),
  get:  (id: number)              => apiClient.get<Job>(`/api/jobs/${id}`).then(r => r.data),
  create: (payload: object)       => apiClient.post<Job>('/api/jobs/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Job>(`/api/jobs/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/api/jobs/${id}`),
  timer:  (id: number, action: string) => apiClient.post(`/api/jobs/${id}/timer`, { action }).then(r => r.data),
  checkAvailability: (id: number) => apiClient.get(`/api/assignments/check/${id}`).then(r => r.data),
  assign: (jobId: number, employeeIds: number[], machineIds: number[]) =>
    apiClient.post('/api/assignments/', { job_id: jobId, employee_ids: employeeIds, machine_ids: machineIds }).then(r => r.data),
}
