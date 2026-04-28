// frontend/src/scheduler/useSchedulerContext.ts
//
// PURPOSE
// Hook + types + the React Context object for the scheduler surface.
// Split out of SchedulerContext.tsx in v6.3.2.1 so the Provider file has
// only component exports and Vite Fast Refresh works without a full-page
// reload on save.
//
// CALLED BY (2 sites)
// - scheduler/SchedulerToolbar.tsx — reads status, conflicts, runScheduler.
// - The Provider file ./SchedulerContext.tsx imports the context object.
//
// CALLS INTO
// - React's createContext + useContext primitives.
// - Type imports from ./useScheduler.

import { createContext, useContext } from 'react'
import type { SchedulerStatus, ConflictEntry, SchedulerRunSummary } from './useScheduler'

// Re-export so callers can import these types from one place
export type { ConflictEntry, SchedulerRunSummary }

export interface SchedulerContextValue {
  status:      SchedulerStatus
  conflicts:   ConflictEntry[]
  lastRun:     Date | null
  running:     boolean
  error:       string | null
  summary:     SchedulerRunSummary | null
  runScheduler: (scheduleDate?: string) => Promise<void>
}

// Context object lives here so the Provider file stays component-only
// for Vite Fast Refresh.
export const SchedulerContext = createContext<SchedulerContextValue | null>(null)

export function useSchedulerContext(): SchedulerContextValue {
  const ctx = useContext(SchedulerContext)
  if (!ctx) throw new Error('useSchedulerContext must be used inside <SchedulerProvider>')
  return ctx
}
