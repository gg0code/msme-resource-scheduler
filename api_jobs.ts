/**
 * ═══════════════════════════════════════════════════════════════════════════════════════════
 * FILE: api_jobs.ts
 * BRANCH: v4-dev (production-stable)
 * PURPOSE: TypeScript API client functions for job management operations
 * ═══════════════════════════════════════════════════════════════════════════════════════════
 *
 * FILE PURPOSE
 * This file provides a centralized TypeScript API client interface for all job-related HTTP
 * operations in the ZetaOps Copilot frontend. It acts as the bridge between React components
 * and the backend FastAPI job endpoints, handling CRUD operations, timer controls, resource
 * assignments, and availability checks. This file was introduced in early v4 development to
 * replace direct Axios calls scattered throughout components and sits in the frontend API
 * abstraction layer between React UI components and backend services.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Imports the shared apiClient instance from './client' which handles authentication tokens
 * 2. Imports the Job TypeScript type definition from '../types' for type safety
 * 3. Exports a jobsApi object containing 8 different job-related API functions
 * 4. Each function wraps an HTTP call using the authenticated apiClient
 * 5. All functions follow consistent patterns: make HTTP request, extract .data, return result
 * 6. Functions cover full job lifecycle: list, get, create, update, delete, timer, assign, check
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : jobsApi.list
 * Type         : function
 * Purpose      : Fetches all jobs for the current authenticated user's tenant. Returns the
 *                complete list of jobs that the user has permission to see, which is automatically
 *                filtered by tenant_id on the backend to ensure tenant isolation and security.
 * Parameters   : none
 * Returns      : Promise<Job[]> - array of Job objects containing all job fields like id,
 *                tenant_id, name, priority, status, dates, raw_materials, timer_status, etc.
 * Calls        : apiClient.get() from './client', which uses the authenticated Axios instance
 * DB/API       : HTTP GET to /api/jobs/ endpoint, backend queries Job table filtered by tenant_id
 * Side effects : none - pure read operation
 *
 * Name         : jobsApi.get
 * Type         : function
 * Purpose      : Fetches a single job by its ID for viewing or editing. Backend automatically
 *                verifies the job belongs to the user's tenant before returning data, preventing
 *                cross-tenant data access. Used when user clicks on a job to see details.
 * Parameters   : id (number) - the primary key ID of the job to retrieve
 * Returns      : Promise<Job> - single Job object with all fields populated, or throws error
 *                if job doesn't exist or user lacks permission
 * Calls        : apiClient.get() from './client' with dynamic URL path
 * DB/API       : HTTP GET to /api/jobs/{id} endpoint, backend queries Job table with id AND tenant_id filter
 * Side effects : none - pure read operation
 *
 * Name         : jobsApi.create
 * Type         : function
 * Purpose      : Creates a new job in the database with the provided data. Backend automatically
 *                sets tenant_id from the authenticated user's session, ensuring the job is created
 *                in the correct tenant scope. Used when user submits the "Create Job" form.
 * Parameters   : payload (object) - job data including name, priority, start_date, end_date,
 *                raw_materials JSON, job_type, quantity, and any other Job model fields
 * Returns      : Promise<Job> - the newly created Job object with server-assigned ID and
 *                any server-computed fields like created timestamps
 * Calls        : apiClient.post() from './client' with JSON payload
 * DB/API       : HTTP POST to /api/jobs/ endpoint, backend INSERTs into Job table with tenant_id
 * Side effects : creates new database record, may trigger scheduling recalculations
 *
 * Name         : jobsApi.update
 * Type         : function
 * Purpose      : Updates an existing job's fields with partial data. Backend verifies job
 *                ownership by tenant_id before allowing modification. Used when user edits
 *                job details, changes priority, updates dates, or modifies raw materials.
 * Parameters   : id (number) - primary key of job to update, p (object) - partial job data
 *                with only the fields that should be changed
 * Returns      : Promise<Job> - the updated Job object reflecting all current database values
 *                after the modification
 * Calls        : apiClient.patch() from './client' with partial payload
 * DB/API       : HTTP PATCH to /api/jobs/{id} endpoint, backend UPDATEs Job table with tenant_id filter
 * Side effects : modifies database record, may trigger schedule recomputation if dates/priority changed
 *
 * Name         : jobsApi.delete
 * Type         : function
 * Purpose      : Permanently removes a job and all associated JobStep and JobAssignment records
 *                from the database. Backend enforces tenant isolation and may prevent deletion
 *                if job is currently running or has dependencies.
 * Parameters   : id (number) - primary key of the job to delete
 * Returns      : Promise<void> - resolves when deletion completes successfully, no data returned
 * Calls        : apiClient.delete() from './client'
 * DB/API       : HTTP DELETE to /api/jobs/{id} endpoint, backend CASCADE deletes Job, JobStep, JobAssignment
 * Side effects : permanently destroys database records, frees up assigned resources
 *
 * Name         : jobsApi.timer
 * Type         : function
 * Purpose      : Controls job timer state for time tracking and production monitoring. Sends
 *                start/stop/pause commands to update the job's timer_status field and log
 *                timing events for later reporting and productivity analysis.
 * Parameters   : id (number) - job ID to control, action (string) - timer command like
 *                "start", "stop", "pause", "resume"
 * Returns      : Promise<unknown> - server response with updated timer state and timestamps
 * Calls        : apiClient.post() from './client' with action payload
 * DB/API       : HTTP POST to /api/jobs/{id}/timer endpoint, backend updates Job.timer_status
 * Side effects : modifies job timer_status, creates timing logs, may affect scheduling priority
 *
 * Name         : jobsApi.checkAvailability
 * Type         : function
 * Purpose      : Validates whether required employees and machines are available for a specific
 *                job's time window. Returns availability conflicts (red) and skill gaps (amber)
 *                to help users understand scheduling constraints before making assignments.
 * Parameters   : id (number) - job ID to check availability for
 * Returns      : Promise<unknown> - availability report with conflicts, skill gaps, and
 *                resource utilization data
 * Calls        : apiClient.get() from './client', note this uses /assignments/ prefix not /jobs/
 * DB/API       : HTTP GET to /api/assignments/check/{id}, backend calls availability_engine.py service
 * Side effects : none - pure analysis operation, does not modify any
 */

```
 */

import apiClient from './client'
import type { Job } from '../types'

export const jobsApi = {
  list: ()                        => apiClient.get<Job[]>('/jobs/').then(r => r.data),
  get:  (id: number)              => apiClient.get<Job>(`/jobs/${id}`).then(r => r.data),
  create: (payload: object)       => apiClient.post<Job>('/jobs/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Job>(`/jobs/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/jobs/${id}`),
  timer:  (id: number, action: string) => apiClient.post(`/jobs/${id}/timer`, { action }).then(r => r.data),
  checkAvailability: (id: number) => apiClient.get(`/assignments/check/${id}`).then(r => r.data),
  assign: (jobId: number, employeeIds: number[], machineIds: number[]) =>
    apiClient.post('/assignments/', { job_id: jobId, employee_ids: employeeIds, machine_ids: machineIds }).then(r => r.data),
}
