// src/scheduler/useScheduler.ts - Version 2.0
// Branch: both
//
// FILE PURPOSE
// State machine and API calls for the Auto-Schedule toolbar button.
// v2.0: Eliminated markDirty() - button state is now derived directly from
// the jobs query on every render. No manual signalling required.
//
// WHAT THIS FILE DOES
// 1. Subscribes to the ['jobs'] TanStack Query cache to watch job state
// 2. Computes SchedulerStatus automatically from job data on every render:
//    - No jobs or all jobs completed/stopped -> greyed-clean
//    - All active jobs locked                -> greyed-locked
//    - Any active unlocked job exists        -> active (needs scheduling)
//    - After a run with no conflicts         -> greyed-clean
//    - After a run with conflicts            -> warn
// 3. Exposes runScheduler() to POST /api/scheduler/run and update state
// 4. Builds a SchedulerRunSummary from the engine response for the result panel
//
// KEY EXPORTS
// - useScheduler()       - the hook, used only by SchedulerContext.tsx
// - SchedulerStatus      - union type for button state
// - ConflictEntry        - one unresolved scheduler conflict
// - ResolvedEntry        - one successfully scheduled step
// - SchedulerRunSummary  - full summary shown in the result panel
//
// WHO CALLS THIS FILE
// - src/scheduler/SchedulerContext.tsx - wraps this hook in a context provider
//
// INTERN NOTES
// - markDirty() is REMOVED. Do not add it back. Any file that previously
//   called markDirty() after a job mutation no longer needs to do so.
//   The button updates automatically because it reads from the ['jobs'] cache
//   which TanStack Query keeps fresh after every mutation invalidation.
// - lastRanAt tracks the timestamp of the most recent scheduler run.
//   After a successful run the status becomes greyed-clean. If a job is then
//   edited (cache invalidated -> re-render), status recomputes to active.
// - The hook intentionally does NOT expose markDirty. If you feel the urge
//   to add it back, read the INTERN NOTES section above first.

import { useState, useCallback, useMemo } from 'react'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'
import { JOBS, SCHEDULER } from '../api/api_endpoints'

// =============================================================================
// TYPES
// =============================================================================

// Button states - maps directly to the visual states in SchedulerToolbar.tsx
export type SchedulerStatus =
  | 'active'          // Active jobs exist and are not all locked - run needed
  | 'warn'            // Last run completed but had unresolved conflicts
  | 'greyed-clean'    // No active jobs, or last run was clean with no conflicts
  | 'greyed-locked'   // All active jobs are locked - nothing to schedule

// One unresolved conflict returned by the scheduler engine
export interface ConflictEntry {
  job_id:         number
  step_id:        number
  sequence_order: number
  reason:         string
}

// One successfully scheduled step returned by the scheduler engine
export interface ResolvedEntry {
  job_id:               number
  step_id:              number
  assigned_machine_ids: number[]
  assigned_helper_ids:  number[]
  scheduled_start:      string
  scheduled_end:        string
}

// Per-job summary built from resolved entries - shown in ResultSummaryPanel
export interface ScheduledJobSummary {
  job_id:         number
  job_name:       string
  step_count:     number
  earliest_start: string
  latest_end:     string
  // True when scheduler moved the job's dates from original request
  // False when job was scheduled on its original requested dates
  dates_changed:  boolean
}

// Full run summary shown in the result panel after scheduler completes
export interface SchedulerRunSummary {
  total_jobs_attempted: number
  jobs_fully_scheduled: number
  jobs_with_conflicts:  number
  scheduled:            ScheduledJobSummary[]
  conflicted_job_ids:   number[]
}

// Minimal job shape needed for status computation
// Matches the shape returned by GET /api/jobs/
interface JobForStatus {
  id:                   number
  name:                 string
  status:               string
  is_locked:            boolean
  original_start_date?: string | null
  original_end_date?:   string | null
}

// Internal run result stored after each scheduler execution
interface LastRunResult {
  at:        Date
  conflicts: ConflictEntry[]
  summary:   SchedulerRunSummary
}

// =============================================================================
// HELPERS
// =============================================================================

// Jobs whose status counts as "active" for scheduling purposes
const ACTIVE_STATUSES = new Set(['Draft', 'Scheduled', 'In Progress', 'Pending Assignment'])

/**
 * Compute button status from current job list and last run result.
 *
 * Priority order (highest to lowest):
 *   1. greyed-locked  - all active jobs are locked
 *   2. warn           - last run had conflicts
 *   3. greyed-clean   - no active jobs exist
 *   4. active         - active unlocked jobs exist and need scheduling
 *
 * Args:
 *   jobs    - current job list from TanStack Query cache
 *   lastRun - result of the most recent scheduler run, or null if never run
 *   running - whether a run is currently in progress
 */
function computeStatus(
  jobs: JobForStatus[],
  lastRun: LastRunResult | null,
  running: boolean,
): SchedulerStatus {
  // While a run is in progress keep showing active so button stays visible
  if (running) return 'active'

  const activeJobs = jobs.filter(j => ACTIVE_STATUSES.has(j.status))

  // No schedulable jobs at all
  if (activeJobs.length === 0) return 'greyed-clean'

  // All active jobs are locked - nothing for scheduler to do
  if (activeJobs.every(j => j.is_locked)) return 'greyed-locked'

  // If last run had conflicts stay in warn state so user sees the conflict panel
  if (lastRun && lastRun.conflicts.length > 0) return 'warn'

  // If last run was clean stay grey until a job changes.
  // TanStack Query invalidates ['jobs'] after any mutation causing a re-render
  // which recomputes this function - returning active again automatically.
  if (lastRun && lastRun.conflicts.length === 0) return 'greyed-clean'

  // No run yet and active unlocked jobs exist - needs scheduling
  return 'active'
}

// =============================================================================
// HOOK
// =============================================================================

export function useScheduler() {
  const qc = useQueryClient()

  // Run state - separate from job cache
  const [running, setRunning] = useState(false)
  const [error,   setError]   = useState<string | null>(null)
  const [lastRun, setLastRun] = useState<LastRunResult | null>(null)

  // Subscribe to the jobs cache so status recomputes on every job mutation.
  // This does NOT make an extra network request - it reads from the existing
  // ['jobs'] cache that Jobs.tsx and Dashboard.tsx already populate.
  // staleTime 0 ensures we always recompute when cache is invalidated.
  const { data: jobs = [] } = useQuery<JobForStatus[]>({
    queryKey: ['jobs'],
    queryFn:  () => apiClient.get(JOBS.list).then(r => r.data),
    staleTime: 0,
  })

  // Status is derived - never stored in useState.
  // Recomputes automatically on every render when jobs or lastRun changes.
  const status: SchedulerStatus = useMemo(
    () => computeStatus(jobs, lastRun, running),
    [jobs, lastRun, running],
  )

  // Convenience values derived from lastRun - no duplication of state
  const conflicts: ConflictEntry[]            = lastRun?.conflicts ?? []
  const summary:   SchedulerRunSummary | null = lastRun?.summary   ?? null
  const lastRunAt: Date | null                = lastRun?.at         ?? null

  /**
   * POST /api/scheduler/run and store the result.
   *
   * Args:
   *   scheduleDate - optional ISO date string passed to the engine.
   *                  Defaults to today if omitted.
   */
  const runScheduler = useCallback(async (scheduleDate?: string) => {
    setRunning(true)
    setError(null)

    try {
      const body = scheduleDate ? { schedule_date: scheduleDate } : {}
      const { data } = await apiClient.post(SCHEDULER.run, body)

      const newConflicts: ConflictEntry[] = data.unresolved ?? []
      const resolved:     ResolvedEntry[] = data.resolved   ?? []

      // Build per-job name map from cached jobs
      const cachedJobs = qc.getQueryData<JobForStatus[]>(['jobs']) ?? []
      const jobNameMap: Record<number, string> = Object.fromEntries(
        cachedJobs.map(j => [j.id, j.name])
      )

      const conflictedIds = new Set(newConflicts.map(c => c.job_id))

      // Group resolved entries by job_id
      const byJob: Record<number, ResolvedEntry[]> = {}
      for (const entry of resolved) {
        if (!byJob[entry.job_id]) byJob[entry.job_id] = []
        byJob[entry.job_id].push(entry)
      }

      // Build per-job summary for jobs that resolved without conflict
      const scheduled: ScheduledJobSummary[] = Object.entries(byJob)
        .filter(([jobIdStr]) => !conflictedIds.has(Number(jobIdStr)))
        .map(([jobIdStr, entries]) => {
          const jobId  = Number(jobIdStr)
          const starts = entries.map(e => e.scheduled_start).sort()
          const ends   = entries.map(e => e.scheduled_end).sort()
          // Detect if scheduler moved dates by comparing to original_end_date
          const jobData = cachedJobs.find(j => j.id === jobId)
          const origEnd   = jobData?.original_end_date   ?? null
          const origStart = jobData?.original_start_date ?? null
          const newStart  = starts[0].split('T')[0]
          const newEnd    = ends[ends.length - 1].split('T')[0]
          const datesChanged = !!(
            (origStart && origStart !== newStart) ||
            (origEnd   && origEnd   !== newEnd)
          )
          return {
            job_id:         jobId,
            job_name:       jobNameMap[jobId] ?? `Job #${jobId}`,
            step_count:     entries.length,
            earliest_start: starts[0],
            latest_end:     ends[ends.length - 1],
            dates_changed:  datesChanged,
          }
        })

      const runSummary: SchedulerRunSummary = {
        total_jobs_attempted: Object.keys(byJob).length + conflictedIds.size,
        jobs_fully_scheduled: scheduled.length,
        jobs_with_conflicts:  conflictedIds.size,
        scheduled,
        conflicted_job_ids: [...conflictedIds],
      }

      setLastRun({ at: new Date(), conflicts: newConflicts, summary: runSummary })

      // Refresh related queries so the rest of the UI reflects the new schedule
      qc.invalidateQueries({ queryKey: ['sched-jobs'] })
      qc.invalidateQueries({ queryKey: ['schedule-entries'] })
      qc.invalidateQueries({ queryKey: ['jobs'] })

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Scheduler error'
      setError(msg)
    } finally {
      setRunning(false)
    }
  }, [qc])

  return {
    status,
    conflicts,
    lastRun:     lastRunAt,
    running,
    error,
    summary,
    runScheduler,
    // markDirty and checkAllLocked are intentionally NOT returned.
    // Status derives automatically from job data. No manual signalling needed.
  }
}
