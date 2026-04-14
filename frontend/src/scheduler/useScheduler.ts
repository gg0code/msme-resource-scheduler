// src/scheduler/useScheduler.ts - Version 2.2
// Branch: both
//
// FILE PURPOSE
// State machine and API calls for the Auto-Schedule toolbar button.
// v2.0: Eliminated markDirty() - button state is now derived directly from
// the jobs query on every render. No manual signalling required.
// v2.1: Fixed two bugs in runScheduler - newConflicts -> raw, Conflicts -> conflicts
//       Added job-change detection via prevJobsRef so button reactivates after edits.
// v2.2: Fixed suppressClearRef so scheduler result panel is not immediately cleared
//       by the jobs re-fetch that the scheduler itself triggers.
//       Fixed dates_changed to compare against start_date on first run (when
//       original_start_date is null in cache).
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
// - markDirty() is REMOVED. Do not add it back.
// - suppressClearRef: set to true before invalidating ['jobs'] after a run.
//   The first jobs signature change after a run is caused by the scheduler
//   itself updating dates — we must NOT clear lastRun on that change.
//   It resets to false on the second change (a real user edit).
// - datesChanged uses start_date as fallback when original_start_date is null.
//   original_start_date is only set by the backend after dates actually change.
//   On the very first run it is null in the cache, so we compare against
//   start_date (the user's requested date before the scheduler ran).

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'
import { JOBS, SCHEDULER } from '../api/api_endpoints'

// =============================================================================
// TYPES
// =============================================================================

export type SchedulerStatus =
  | 'active'
  | 'warn'
  | 'greyed-clean'
  | 'greyed-locked'

export interface ConflictEntry {
  job_id:         number
  step_id:        number
  sequence_order: number
  reason:         string
}

export interface ResolvedEntry {
  job_id:               number
  step_id:              number
  assigned_machine_ids: number[]
  assigned_helper_ids:  number[]
  scheduled_start:      string
  scheduled_end:        string
}

export interface ScheduledJobSummary {
  job_id:         number
  job_name:       string
  step_count:     number
  earliest_start: string
  latest_end:     string
  dates_changed:  boolean
}

export interface SchedulerRunSummary {
  total_jobs_attempted: number
  jobs_fully_scheduled: number
  jobs_with_conflicts:  number
  scheduled:            ScheduledJobSummary[]
  conflicted_job_ids:   number[]
}

// start_date and end_date added in v2.2 — needed for dates_changed on first
// scheduler run when original_start_date is still null in the cache
interface JobForStatus {
  id:                   number
  name:                 string
  status:               string
  is_locked:            boolean
  start_date?:          string | null
  end_date?:            string | null
  original_start_date?: string | null
  original_end_date?:   string | null
}

interface LastRunResult {
  at:        Date
  conflicts: ConflictEntry[]
  summary:   SchedulerRunSummary
}

// =============================================================================
// HELPERS
// =============================================================================

const ACTIVE_STATUSES = new Set(['Draft', 'Scheduled', 'In Progress', 'Pending Assignment'])

function computeStatus(
  jobs: JobForStatus[],
  lastRun: LastRunResult | null,
  running: boolean,
): SchedulerStatus {
  if (running) return 'active'

  const activeJobs = jobs.filter(j => ACTIVE_STATUSES.has(j.status))

  if (activeJobs.length === 0) return 'greyed-clean'
  if (activeJobs.every(j => j.is_locked)) return 'greyed-locked'
  if (lastRun && lastRun.conflicts.length > 0) return 'warn'
  if (lastRun && lastRun.conflicts.length === 0) return 'greyed-clean'

  return 'active'
}

// =============================================================================
// HOOK
// =============================================================================

export function useScheduler() {
  const qc = useQueryClient()

  const [running, setRunning] = useState(false)
  const [error,   setError]   = useState<string | null>(null)
  const [lastRun, setLastRun] = useState<LastRunResult | null>(null)

  const { data: jobs = [] } = useQuery<JobForStatus[]>({
    queryKey: ['jobs'],
    queryFn:  () => apiClient.get(JOBS.list).then(r => r.data),
    staleTime: 0,
  })

  // --- Job change detection --------------------------------------------------
  // Clears lastRun when a user edits a job so the button reactivates.
  //
  // suppressClearRef: the scheduler itself invalidates ['jobs'] after a run,
  // which triggers a signature change. That change must NOT clear lastRun or
  // the result panel would be wiped immediately after opening.
  // suppressClearRef is set true before invalidation. The first signature
  // change is skipped. The second change (real user edit) clears normally.
  const prevJobsRef      = useRef<string>('')
  const suppressClearRef = useRef<boolean>(false)

  const jobsSignature = jobs
    .map(j => `${j.id}:${j.is_locked}:${j.status}`)
    .join(',')

  useEffect(() => {
    if (prevJobsRef.current && prevJobsRef.current !== jobsSignature) {
      if (suppressClearRef.current) {
        suppressClearRef.current = false  // Scheduler-caused change — skip
      } else {
        setLastRun(null)                  // Real user edit — reactivate button
      }
    }
    prevJobsRef.current = jobsSignature
  }, [jobsSignature])

  // --------------------------------------------------------------------------

  const status: SchedulerStatus = useMemo(
    () => computeStatus(jobs, lastRun, running),
    [jobs, lastRun, running],
  )

  const conflicts: ConflictEntry[]            = lastRun?.conflicts ?? []
  const summary:   SchedulerRunSummary | null = lastRun?.summary   ?? null
  const lastRunAt: Date | null                = lastRun?.at         ?? null

  const runScheduler = useCallback(async (scheduleDate?: string) => {
    setRunning(true)
    setError(null)

    try {
      const body = scheduleDate ? { schedule_date: scheduleDate } : {}
      const { data } = await apiClient.post(SCHEDULER.run, body)

      // raw = full list (one entry per synthetic day-step)
      // conflicts = deduplicated to one entry per job for the conflict panel
      // conflictedIds uses raw so counts remain accurate
      const raw: ConflictEntry[] = data.unresolved ?? []
      const seen = new Set<number>()
      const conflicts = raw.filter(c => {
        if (seen.has(c.job_id)) return false
        seen.add(c.job_id)
        return true
      })

      const resolved: ResolvedEntry[] = data.resolved ?? []

      // Capture cached jobs BEFORE invalidation — these are the pre-run values.
      // start_date here is the user's requested date before the scheduler moved it.
      // original_start_date may be null on the first run (set by backend only
      // after dates actually change). We fall back to start_date as the
      // comparator so dates_changed is accurate on both first and later runs.
      const cachedJobs = qc.getQueryData<JobForStatus[]>(['jobs']) ?? []
      const jobNameMap: Record<number, string> = Object.fromEntries(
        cachedJobs.map(j => [j.id, j.name])
      )

      const conflictedIds = new Set(raw.map(c => c.job_id))

      const byJob: Record<number, ResolvedEntry[]> = {}
      for (const entry of resolved) {
        if (!byJob[entry.job_id]) byJob[entry.job_id] = []
        byJob[entry.job_id].push(entry)
      }

      const scheduled: ScheduledJobSummary[] = Object.entries(byJob)
        .filter(([jobIdStr]) => !conflictedIds.has(Number(jobIdStr)))
        .map(([jobIdStr, entries]) => {
          const jobId  = Number(jobIdStr)
          const starts = entries.map(e => e.scheduled_start).sort()
          const ends   = entries.map(e => e.scheduled_end).sort()

          const jobData = cachedJobs.find(j => j.id === jobId)

          // Use original_start_date if already set (re-run scenario).
          // Fall back to start_date on first run when original is null.
          const comparStart = jobData?.original_start_date ?? jobData?.start_date ?? null
          const comparEnd   = jobData?.original_end_date   ?? jobData?.end_date   ?? null
          const newStart    = starts[0].split('T')[0]
          const newEnd      = ends[ends.length - 1].split('T')[0]

          const datesChanged = !!(
            (comparStart && comparStart !== newStart) ||
            (comparEnd   && comparEnd   !== newEnd)
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

      setLastRun({ at: new Date(), conflicts: conflicts, summary: runSummary })

      // Set suppress BEFORE invalidating so the re-fetch signature change
      // does not immediately clear the result we just stored above.
      suppressClearRef.current = true

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
  }
}
