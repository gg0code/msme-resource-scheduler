// src/scheduler/SchedulerContext.tsx - Version 2.1 (v6.3.2.1)
// Branch: both
//
// FILE PURPOSE
// Provides useScheduler() state to the whole app via React context.
// v2.0: Removed markDirty and checkAllLocked from context interface.
// These no longer exist - scheduler status is derived automatically.
// v2.1 / v6.3.2.1: Hook + types + context object live in
// ./useSchedulerContext.ts so this file has only the Provider component
// and Vite Fast Refresh hot-swaps it cleanly on save.
//
// WHAT THIS FILE DOES
// 1. Wraps useScheduler() in a React context
// 2. SchedulerProvider wraps <Layout> in App.tsx
//
// WHO CALLS THIS FILE
// - src/App.tsx                    - renders <SchedulerProvider>
// - src/scheduler/SchedulerToolbar - reads status, conflicts, runScheduler
//   (via useSchedulerContext from ./useSchedulerContext)
//
// INTERN NOTES
// - Do not add markDirty back to this context. See useScheduler.ts.
// - Do not add checkAllLocked back. Lock state is computed from job data.
// - If you need to trigger a scheduler state change, invalidate ['jobs']
//   in TanStack Query and the status will recompute automatically.

import type { ReactNode } from 'react'
import { useScheduler } from './useScheduler'
import { SchedulerContext } from './useSchedulerContext'

export function SchedulerProvider({ children }: { children: ReactNode }) {
  const scheduler = useScheduler()
  return (
    <SchedulerContext.Provider value={scheduler}>
      {children}
    </SchedulerContext.Provider>
  )
}
