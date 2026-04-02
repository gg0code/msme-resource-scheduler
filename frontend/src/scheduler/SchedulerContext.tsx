/**
 * frontend/src/scheduler/SchedulerContext.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Thin context wrapper around useScheduler(). Makes the scheduler state machine
 * available to any component without prop-drilling. SchedulerProvider wraps the
 * authenticated route group in App.tsx. Any component that needs to trigger a
 * scheduler run or read its status imports useSchedulerContext().
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines SchedulerContextValue interface (matches useScheduler() return shape).
 * 2. Creates SchedulerContext with null default.
 * 3. SchedulerProvider: calls useScheduler(), wraps children in Context.Provider.
 * 4. useSchedulerContext(): returns context value, throws if outside provider.
 * 5. Re-exports ConflictEntry and SchedulerRunSummary types for consumers.
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — SchedulerProvider wraps the authenticated route group
 * - frontend/src/scheduler/SchedulerToolbar.tsx — useSchedulerContext()
 * - frontend/src/pages/Jobs.tsx — useSchedulerContext() for markDirty, runScheduler
 *
 * INTERN NOTES
 * - This file is intentionally thin — all logic lives in useScheduler.ts.
 * - useSchedulerContext() throws if called outside SchedulerProvider. If you see
 *   the throw error in dev: check App.tsx provider nesting order.
 * - Re-exported types (ConflictEntry, SchedulerRunSummary) allow consumers to import
 *   from this file instead of from useScheduler.ts directly.
 */

// Provides useScheduler() state to the whole app via context
// Wrap <Layout> (or <App>) with <SchedulerProvider>

import { createContext, useContext } from 'react'
import type { ReactNode } from 'react'
import { useScheduler } from './useScheduler'
import type { SchedulerStatus, ConflictEntry, SchedulerRunSummary } from './useScheduler'
export type { ConflictEntry, SchedulerRunSummary }

interface SchedulerContextValue {
  status:         SchedulerStatus
  conflicts:      ConflictEntry[]
  lastRun:        Date | null
  running:        boolean
  error:          string | null
  summary:        SchedulerRunSummary | null
  markDirty:      () => void
  checkAllLocked: (jobs: { lock_status: boolean }[]) => void
  runScheduler:   (scheduleDate?: string) => Promise<void>
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
