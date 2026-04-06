// src/scheduler/SchedulerContext.tsx - Version 2.0
// Branch: both
//
// FILE PURPOSE
// Provides useScheduler() state to the whole app via React context.
// v2.0: Removed markDirty and checkAllLocked from context interface.
// These no longer exist - scheduler status is derived automatically.
//
// WHAT THIS FILE DOES
// 1. Wraps useScheduler() in a React context
// 2. Exposes the context via useSchedulerContext() hook
// 3. SchedulerProvider wraps <Layout> in App.tsx
//
// WHO CALLS THIS FILE
// - src/App.tsx                    - renders <SchedulerProvider>
// - src/scheduler/SchedulerToolbar - reads status, conflicts, runScheduler
// - Any component needing scheduler state
//
// INTERN NOTES
// - Do not add markDirty back to this context. See useScheduler.ts.
// - Do not add checkAllLocked back. Lock state is computed from job data.
// - If you need to trigger a scheduler state change, invalidate ['jobs']
//   in TanStack Query and the status will recompute automatically.

import { createContext, useContext } from 'react'
import type { ReactNode } from 'react'
import { useScheduler } from './useScheduler'
import type { SchedulerStatus, ConflictEntry, SchedulerRunSummary } from './useScheduler'

// Re-export types so callers import from one place
export type { ConflictEntry, SchedulerRunSummary }

interface SchedulerContextValue {
  status:      SchedulerStatus
  conflicts:   ConflictEntry[]
  lastRun:     Date | null
  running:     boolean
  error:       string | null
  summary:     SchedulerRunSummary | null
  runScheduler: (scheduleDate?: string) => Promise<void>
}

const SchedulerContext = createContext<SchedulerContextValue | null>(null)

export function SchedulerProvider({ children }: { children: ReactNode }) {
  const scheduler = useScheduler()
  return (
    <SchedulerContext.Provider value={scheduler}>
      {children}
    </SchedulerContext.Provider>
  )
}

export function useSchedulerContext(): SchedulerContextValue {
  const ctx = useContext(SchedulerContext)
  if (!ctx) throw new Error('useSchedulerContext must be used inside <SchedulerProvider>')
  return ctx
}
