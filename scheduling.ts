/**
```typescript
/**
 * FILE PURPOSE
 * This file defines the frontend API client layer for the scheduling system in ZetaOps Copilot.
 * It was introduced in v4.0.x on the v4-dev branch as part of the React frontend rewrite and serves
 * as the TypeScript interface between React components and the FastAPI backend scheduling endpoints.
 * This file sits in the frontend API layer, translating UI actions into HTTP requests to /api/
 * endpoints and providing type safety for all scheduling-related data structures.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines TypeScript types and interfaces for all scheduling domain objects (jobs, steps, resources)
 * 2. Exports union types for enums used throughout the scheduling system (priorities, statuses, shifts)
 * 3. Defines request/response interfaces for create, update, and patch operations
 * 4. Exports resourcesApi object with CRUD operations for machines and helpers
 * 5. Exports schedJobsApi object with CRUD operations for manufacturing jobs
 * 6. Exports stepsApi object with CRUD operations for job steps, including status updates
 * 7. Provides type-safe wrappers around the authenticated HTTP client for all scheduling endpoints
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : ResourceType
 * Type         : TypeScript union type
 * Purpose      : Defines the two types of manufacturing resources in the system. 'machine' represents 
 *                physical equipment like printers or fabrication machines. 'helper' represents human workers
 *                who assist with jobs but are not primary operators.
 * Parameters   : N/A (type definition)
 * Returns      : N/A (type definition)
 * Calls        : N/A
 * DB/API       : N/A
 * Side effects : N/A
 *
 * Name         : SchedPriority
 * Type         : TypeScript union type
 * Purpose      : Defines job priority levels used by the scheduling engine. 'critical' jobs get highest
 *                priority and will preempt other work. 'urgent' jobs are scheduled as soon as possible.
 *                'low' jobs fill available capacity after higher priorities are satisfied.
 * Parameters   : N/A (type definition)
 * Returns      : N/A (type definition)
 * Calls        : N/A
 * DB/API       : N/A
 * Side effects : N/A
 *
 * Name         : SchedResource
 * Type         : TypeScript interface
 * Purpose      : Represents a manufacturing resource (machine or helper) with its availability schedule.
 *                Maps directly to the Machine and Employee models in the backend, providing shift timing
 *                information for scheduling calculations.
 * Parameters   : id (unique resource identifier), tenant_id (multi-tenancy isolation), name (display name),
 *                type (ResourceType enum), shift_start/shift_end (availability window in HH:MM:SS format),
 *                created_at (audit timestamp)
 * Returns      : N/A (interface definition)
 * Calls        : N/A
 * DB/API       : N/A
 * Side effects : N/A
 *
 * Name         : SchedJob
 * Type         : TypeScript interface
 * Purpose      : Represents a complete manufacturing job with all associated steps. Contains business
 *                metadata like profit expectations and deadlines, plus operational data like lock status
 *                and current progress. The steps array provides the full workflow definition.
 * Parameters   : id (unique job identifier), tenant_id (isolation), name (display name), priority (SchedPriority),
 *                expected_profit (revenue projection), deadline (completion target), shift (time window),
 *                lock_status (prevents rescheduling), status (current progress), steps (workflow array),
 *                created_at/updated_at (audit timestamps)
 * Returns      : N/A (interface definition)
 * Calls        : N/A
 * DB/API       : N/A
 * Side effects : N/A
 *
 * Name         : SchedStep
 * Type         : TypeScript interface
 * Purpose      : Represents one step in a job workflow with resource requirements and reservation details.
 *                Maps to JobStep model in backend. Contains duration estimates, resource requirements arrays,
 *                and optional machine reservations for critical steps that need guaranteed capacity.
 * Parameters   : id (unique step identifier), job_id (parent job), sequence_order (workflow position),
 *                step_type (regular or setup), duration_minutes (time estimate), status (progress),
 *                required_machine_ids/required_helper_ids (resource requirements), reserve_machine_id (guaranteed allocation),
 *                is_setup_active (setup step flag), created_at/updated_at (audit timestamps)
 * Returns      : N/A (interface definition)
 * Calls        : N/A
 * DB/API       : N/A
 * Side effects : N/A
 *
 * Name         : resourcesApi
 * Type         : API client object
 * Purpose      : Provides type-safe CRUD operations for manufacturing resources. Handles both machines
 *                and helpers through the same interface, with optional filtering by resource type.
 *                All operations are tenant-scoped automatically by the backend.
 * Parameters   : list() accepts optional type filter, create() takes ResourceCreate data, update() takes
 *                id and partial data, delete() takes id only
 * Returns      : list() returns SchedResource[], create()/update() return single SchedResource, delete() returns void
 * Calls        : apiClient from './client' for all HTTP operations
 * DB/API       : GET /api/resources/, POST /api/resources/, PUT /api/resources/{id}, DELETE /api/resources/{id}
 * Side effects : Creates, modifies, or removes resource records in database
 *
 * Name         : schedJobsApi
 * Type         : API client object
 * Purpose      : Provides type-safe CRUD operations for manufacturing jobs. Supports optional filtering
 *                by job status for dashboard views. All operations automatically include associated
 *                job steps through backend relationships.
 * Parameters   : list() accepts optional status filter, create() takes JobCreate data, get() takes job id,
 *                update() takes id and partial data, delete() takes id only
 * Returns      : list() returns SchedJob[], create()/get()/update() return single SchedJob with steps array,
 *                delete() returns void
 * Calls        : apiClient from './client' for all HTTP operations
 * DB/API       : GET /api/jobs-v2/, POST /api/jobs-v2/, GET /api/jobs-v2/{id}, PUT /api/jobs-v2/{id}, DELETE /api/jobs-v2/{id}
 * Side effects : Creates, modifies, or removes job records and associated steps in database
 *
 * Name         : stepsApi
 * Type         : API client object
 * Purpose      : Provides type-safe CRUD operations for job steps, including a specialized patchStatus()
 *                method for workflow progression. All operations are scoped to a specific job and
 *                maintain proper sequence ordering for workflow integrity.
 * Parameters   : All methods take jobId first, then stepId for individual operations. create() takes StepCreate data,
 *                update() takes StepUpdate data, patchStatus() takes StepStatus enum value
 * Returns      : list()
 */

import apiClient from './client'

// ─── Types ────────────────────────────────────────────────────────────────────

export type ResourceType    = 'machine' | 'helper'
export type SchedPriority   = 'critical' | 'urgent' | 'low'
export type SchedShift      = 'morning' | 'evening'
export type SchedJobStatus  = 'pending' | 'scheduled' | 'in_progress' | 'complete'
export type StepType        = 'regular' | 'setup'
export type StepStatus      = 'pending' | 'ready' | 'in_progress' | 'complete'

export interface SchedResource {
  id:          number
  tenant_id:   number
  name:        string
  type:        ResourceType
  shift_start: string   // "HH:MM:SS"
  shift_end:   string
  created_at:  string
}

export interface SchedStep {
  id:                   number
  job_id:               number
  sequence_order:       number
  step_type:            StepType
  duration_minutes:     number
  status:               StepStatus
  required_machine_ids: number[]
  required_helper_ids:  number[]
  reserve_machine_id:   number | null
  is_setup_active:      boolean
  created_at:           string
  updated_at:           string
}

export interface SchedJob {
  id:              number
  tenant_id:       number
  name:            string
  priority:        SchedPriority
  expected_profit: number | null
  deadline:        string
  shift:           SchedShift
  lock_status:     boolean
  status:          SchedJobStatus
  steps:           SchedStep[]
  created_at:      string
  updated_at:      string
}

export interface ResourceCreate {
  name:        string
  type:        ResourceType
  shift_start?: string
  shift_end?:   string
}

export interface ResourceUpdate {
  name?:        string
  shift_start?: string
  shift_end?:   string
}

export interface JobCreate {
  name:             string
  priority:         SchedPriority
  expected_profit?: number | null
  deadline:         string
  shift:            SchedShift
  lock_status?:     boolean
}

export interface JobUpdate extends Partial<JobCreate> {
  status?: SchedJobStatus
}

export interface StepCreate {
  step_type:             StepType
  duration_minutes:      number
  required_machine_ids?: number[]
  required_helper_ids?:  number[]
  reserve_machine_id?:   number | null
}

export interface StepUpdate {
  step_type?:             StepType
  duration_minutes?:      number
  required_machine_ids?:  number[]
  required_helper_ids?:   number[]
  reserve_machine_id?:    number | null
}

export interface StepStatusPatch {
  status: StepStatus
}


// ─── Resources API ────────────────────────────────────────────────────────────

export const resourcesApi = {
  list:   (type?: ResourceType) =>
    apiClient.get<SchedResource[]>('/api/resources/', { params: type ? { type } : {} }),
  create: (data: ResourceCreate) =>
    apiClient.post<SchedResource>('/api/resources/', data),
  update: (id: number, data: ResourceUpdate) =>
    apiClient.put<SchedResource>(`/api/resources/${id}`, data),
  delete: (id: number) =>
    apiClient.delete(`/api/resources/${id}`),
}


// ─── Jobs API ─────────────────────────────────────────────────────────────────

export const schedJobsApi = {
  list:   (status?: SchedJobStatus) =>
    apiClient.get<SchedJob[]>('/api/jobs-v2/', { params: status ? { status } : {} }),
  create: (data: JobCreate) =>
    apiClient.post<SchedJob>('/api/jobs-v2/', data),
  get:    (id: number) =>
    apiClient.get<SchedJob>(`/api/jobs-v2/${id}`),
  update: (id: number, data: JobUpdate) =>
    apiClient.put<SchedJob>(`/api/jobs-v2/${id}`, data),
  delete: (id: number) =>
    apiClient.delete(`/api/jobs-v2/${id}`),
}


// ─── Steps API ────────────────────────────────────────────────────────────────

export const stepsApi = {
  list:   (jobId: number) =>
    apiClient.get<SchedStep[]>(`/api/jobs-v2/${jobId}/steps/`),
  create: (jobId: number, data: StepCreate) =>
    apiClient.post<SchedStep>(`/api/jobs-v2/${jobId}/steps/`, data),
  get:    (jobId: number, stepId: number) =>
    apiClient.get<SchedStep>(`/api/jobs-v2/${jobId}/steps/${stepId}`),
  update: (jobId: number, stepId: number, data: StepUpdate) =>
    apiClient.put<SchedStep>(`/api/jobs-v2/${jobId}/steps/${stepId}`, data),
  delete: (jobId: number, stepId: number) =>
    apiClient.delete(`/api/jobs-v2/${jobId}/steps/${stepId}`),
  patchStatus: (jobId: number, stepId: number, status: StepStatus) =>
    apiClient.patch<SchedStep>(
      `/api/jobs-v2/${jobId}/steps/${stepId}/status`,
      { status }
    ),
}
