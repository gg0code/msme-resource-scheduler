// src/api/scheduling.ts — Prompt 1 frontend API layer

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
