/**
 * FILE PURPOSE
 * This React hook manages the state machine and API interactions for the scheduler toolbar component
 * in ZetaOps Copilot. Introduced in v4-dev as part of the scheduler UI redesign, it sits in the
 * frontend architecture as a custom hook that bridges between the React UI state and the backend
 * scheduler engine. It tracks whether the schedule is dirty (needs re-running), has conflicts,
 * or is locked, and provides functions to trigger scheduler runs via the FastAPI backend.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines TypeScript interfaces for scheduler state and conflict data structures
 * 2. Creates a SchedulerStatus union type representing the four possible scheduler states
 * 3. Exports a useScheduler hook that manages internal state using React useState
 * 4. Provides a markDirty function to transition the scheduler to 'active' when jobs change
 * 5. Provides a checkAllLocked function to detect when all jobs are locked and update state
 * 6. Provides a runScheduler function that calls the backend API and updates state based on results
 * 7. Handles error states and loading states during scheduler execution
 * 8. Invalidates React Query caches to refresh UI after successful scheduler runs
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : useScheduler
 * Type         : React hook
 * Purpose      : Custom hook that manages scheduler state machine and provides functions to interact
 *                with the backend scheduler API. Tracks dirty state, conflicts, loading state, and
 *                provides callbacks for common scheduler operations like marking dirty and running.
 * Parameters   : none
 * Returns      : Object containing current state (status, conflicts, lastRun, running, error) plus
 *                three callback functions (markDirty, checkAllLocked, runScheduler)
 * Calls        : apiClient.post() from '../api/client', useQueryClient() from TanStack Query
 * DB/API       : Makes POST request to /api/scheduler/run endpoint with optional schedule_date
 * Side effects : Updates React state, invalidates React Query caches for 'sched-jobs' and
 *                'schedule-entries' queryKeys after successful runs
 *
 * Name         : markDirty
 * Type         : function (callback)
 * Purpose      : Transitions scheduler state to 'active' to indicate schedule needs re-running.
 *                Preserves 'greyed-locked' state when all jobs are locked since that's data-driven.
 * Parameters   : none
 * Returns      : void
 * Calls        : setState (React state setter)
 * DB/API       : none
 * Side effects : Updates local component state to mark scheduler as needing to run
 *
 * Name         : checkAllLocked
 * Type         : function (callback)
 * Purpose      : Evaluates whether all jobs are locked and updates scheduler state accordingly.
 *                Transitions to 'greyed-locked' when all jobs locked, or back to 'active' when unlocked.
 * Parameters   : jobs: Array of objects with lock_status boolean property
 * Returns      : void
 * Calls        : setState (React state setter), Array.every() method
 * DB/API       : none
 * Side effects : Updates scheduler state based on job lock status analysis
 *
 * Name         : runScheduler
 * Type         : function (callback, async)
 * Purpose      : Executes the backend scheduler engine by calling the FastAPI endpoint, processes
 *                the response to extract conflicts, and updates state to reflect results. Handles
 *                both success and error cases, including cache invalidation after success.
 * Parameters   : scheduleDate?: string (optional ISO date string for scheduling target date)
 * Returns      : Promise<void>
 * Calls        : apiClient.post(), qc.invalidateQueries() twice for different query keys
 * DB/API       : POST /api/scheduler/run with optional schedule_date in request body
 * Side effects : Sets running state, updates conflicts and status, invalidates React Query caches
 *
 * WHO CALLS THIS FILE
 * - frontend/src/components/SchedulerToolbar.tsx (primary consumer of this hook)
 * - frontend/src/pages/SchedulePage.tsx (uses hook for scheduler controls integration)
 * - frontend/src/components/JobsList.tsx (calls markDirty when jobs are modified)
 *
 * IMPORTS EXPLAINED
 * - useState, useCallback from 'react': React hooks for managing local state and memoizing callbacks
 * - useQueryClient from '@tanstack/react-query': Provides access to React Query cache for invalidation
 * - apiClient from '../api/client': Axios instance configured with JWT auth and base URL for API calls
 *
 * INTERN NOTES
 * - Easiest thing to break: forgetting to call markDirty() after job operations, leaving scheduler
 *   in stale 'greyed-clean' state when it should show 'active' requiring re-run
 * - Non-obvious design decision: 'greyed-locked' state is preserved during markDirty() because
 *   when all jobs are locked, the scheduler shouldn't run regardless of other changes
 * - Most common mistake: not handling the async nature of runScheduler() or forgetting to check
 *   the 'running' state before allowing multiple concurrent scheduler executions
 * - This implements design principle #1: the hook only calls the backend engine API and displays
 *   results, it never attempts to perform scheduling logic in the frontend
 * - If scheduler behaves unexpectedly: check network tab for API errors, verify React Query cache
 *   invalidation is working, and confirm job lock states are being passed correctly to checkAllLocked
 * - Not applicable to v5-whatsapp: this file exists in v4-dev only and scheduler UI is unchanged in v5
 */

import { useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

export type SchedulerStatus =
  | 'active'          // dirty — needs run
  | 'warn'            // ran, has conflicts
  | 'greyed-clean'    // ran, no conflicts
  | 'greyed-locked'   // all jobs locked

export interface ConflictEntry {
  job_id:         number
  step_id:        number
  sequence_order: number
  reason:         string
}

interface SchedulerState {
  status:    SchedulerStatus
  conflicts: ConflictEntry[]
  lastRun:   Date | null
  running:   boolean
  error:     string | null
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useScheduler() {
  const qc = useQueryClient()

  const [state, setState] = useState<SchedulerState>({
    status:    'active',
    conflicts: [],
    lastRun:   null,
    running:   false,
    error:     null,
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

  /** POST /api/scheduler/run → update status based on result */
  const runScheduler = useCallback(async (scheduleDate?: string) => {
    setState(s => ({ ...s, running: true, error: null }))
    try {
      const body = scheduleDate ? { schedule_date: scheduleDate } : {}
      const { data } = await apiClient.post('/api/scheduler/run', body)

      const conflicts: ConflictEntry[] = data.unresolved ?? []

      setState({
        status:    conflicts.length > 0 ? 'warn' : 'greyed-clean',
        conflicts,
        lastRun:   new Date(),
        running:   false,
        error:     null,
      })

      // Refresh schedule entries + jobs in all active queries
      qc.invalidateQueries({ queryKey: ['sched-jobs'] })
      qc.invalidateQueries({ queryKey: ['schedule-entries'] })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Scheduler error'
      setState(s => ({ ...s, running: false, error: msg, status: 'active' }))
    }
  }, [qc])

  return {
    ...state,
    markDirty,
    checkAllLocked,
    runScheduler,
  }
}
