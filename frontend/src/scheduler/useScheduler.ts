// src/scheduler/useScheduler.ts — v3.9.5
// Hook: state machine + API calls for the scheduler toolbar
// v3.9.5: captures resolved jobs and builds a result summary after each run

import { useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

export type SchedulerStatus =
  | 'active'          // dirty - needs run
  | 'warn'            // ran, has conflicts
  | 'greyed-clean'    // ran, no conflicts
  | 'greyed-locked'   // all jobs locked

export interface ConflictEntry {
  job_id:         number
  step_id:        number
  sequence_order: number
  reason:         string
}

// One resolved job entry returned by the scheduler engine
export interface ResolvedEntry {
  job_id:               number
  step_id:              number
  assigned_machine_ids: number[]
  assigned_helper_ids:  number[]
  scheduled_start:      string
  scheduled_end:        string
}

// Per-job summary built from resolved entries
export interface ScheduledJobSummary {
  job_id:         number
  job_name:       string
  step_count:     number
  earliest_start: string
  latest_end:     string
}

// Full run summary shown after scheduler completes
export interface SchedulerRunSummary {
  total_jobs_attempted: number
  jobs_fully_scheduled: number
  jobs_with_conflicts:  number
  scheduled:            ScheduledJobSummary[]
  conflicted_job_ids:   number[]
}

interface SchedulerState {
  status:    SchedulerStatus
  conflicts: ConflictEntry[]
  lastRun:   Date | null
  running:   boolean
  error:     string | null
  summary:   SchedulerRunSummary | null
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useScheduler() {
  const qc = useQueryClient()

  const [state, setState] = useState<SchedulerState>({
    status:    'greyed-clean',
    conflicts: [],
    lastRun:   null,
    running:   false,
    error:     null,
    summary:   null,
  })

  /** Call after any job/step create, update, delete, or lock toggle */
  const markDirty = useCallback(() => {
    setState(s => ({
      ...s,
      // Don't override greyed-locked — all-locked is a data-driven state
      status: s.status === 'greyed-locked' ? 'greyed-locked' : 'active',
    }))
  }, [])

  /** Mark all-locked state (called when jobs list changes) */
  const checkAllLocked = useCallback((jobs: { lock_status: boolean }[]) => {
    if (jobs.length > 0 && jobs.every(j => j.lock_status)) {
      setState(s => ({ ...s, status: 'greyed-locked' }))
    } else {
      setState(s => {
        if (s.status === 'greyed-locked') return { ...s, status: 'active' }
        return s
      })
    }
  }, [])

  /** POST /api/scheduler/run → update status and build result summary */
  const runScheduler = useCallback(async (scheduleDate?: string) => {
    setState(s => ({ ...s, running: true, error: null, summary: null }))
    try {
      const body = scheduleDate ? { schedule_date: scheduleDate } : {}
      const { data } = await apiClient.post('/api/scheduler/run', body)

      const conflicts: ConflictEntry[]  = data.unresolved ?? []
      const resolved:  ResolvedEntry[]  = data.resolved   ?? []

      // Build per-job summary from resolved entries
      // Group resolved steps by job_id to find earliest start and latest end
      const cachedJobs = qc.getQueryData<{ id: number; name: string }[]>(['jobs']) ?? []
      const jobNameMap: Record<number, string> = Object.fromEntries(cachedJobs.map(j => [j.id, j.name]))
      const conflictedIds = new Set(conflicts.map(c => c.job_id))

      const byJob: Record<number, ResolvedEntry[]> = {}
      for (const entry of resolved) {
        if (!byJob[entry.job_id]) byJob[entry.job_id] = []
        byJob[entry.job_id].push(entry)
      }

      const scheduled: ScheduledJobSummary[] = Object.entries(byJob)
        .filter(([jobIdStr]) => !conflictedIds.has(Number(jobIdStr)))
        .map(([jobIdStr, entries]) => {
          const jobId = Number(jobIdStr)
          const starts = entries.map(e => e.scheduled_start).sort()
          const ends   = entries.map(e => e.scheduled_end).sort()
          return {
            job_id:         jobId,
            job_name:       jobNameMap[jobId] ?? `Job #${jobId}`,
            step_count:     entries.length,
            earliest_start: starts[0],
            latest_end:     ends[ends.length - 1],
          }
        })

      const summary: SchedulerRunSummary = {
        total_jobs_attempted: Object.keys(byJob).length + conflictedIds.size,
        jobs_fully_scheduled: scheduled.length,
        jobs_with_conflicts:  conflictedIds.size,
        scheduled,
        conflicted_job_ids: [...conflictedIds],
      }

      setState({
        status:    conflicts.length > 0 ? 'warn' : 'greyed-clean',
        conflicts,
        lastRun:   new Date(),
        running:   false,
        error:     null,
        summary,
      })

      // Refresh schedule entries + jobs in all active queries
      qc.invalidateQueries({ queryKey: ['sched-jobs'] })
      qc.invalidateQueries({ queryKey: ['schedule-entries'] })
      qc.invalidateQueries({ queryKey: ['jobs'] })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Scheduler error'
      setState(s => ({ ...s, running: false, error: msg, status: 'active', summary: null }))
    }
  }, [qc])

  return {
    ...state,
    markDirty,
    checkAllLocked,
    runScheduler,
  }
}
