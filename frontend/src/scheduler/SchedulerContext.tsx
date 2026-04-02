// src/scheduler/SchedulerContext.tsx
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
