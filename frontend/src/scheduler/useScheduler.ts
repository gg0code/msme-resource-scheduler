// src/scheduler/useScheduler.ts — Prompt 2 Part D
// Hook: state machine + API calls for the scheduler toolbar

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
