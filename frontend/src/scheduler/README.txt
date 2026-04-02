AUTO-GENERATED - frontend/src/scheduler/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/scheduler/
PURPOSE: Auto-scheduler state machine, context provider, and toolbar button.

FILES
  useScheduler.ts       - State machine hook. Manages scheduler status, conflicts,
                          run summary. Calls POST /api/scheduler/run.
                          Exports: useScheduler, SchedulerStatus, ConflictEntry,
                          SchedulerRunSummary, ScheduledJobSummary. Branch: both.
  SchedulerContext.tsx  - Thin context wrapper around useScheduler. Provides
                          scheduler state to the whole app via useSchedulerContext().
                          Branch: both.
  SchedulerToolbar.tsx  - Header bar button. Shows scheduler status, triggers runs,
                          displays result summary. Feature-flagged (flags.scheduler).
                          Branch: both.

ARCHITECTURE NOTES
useScheduler.ts contains all logic. SchedulerContext.tsx wraps it in React context so
any component can access scheduler state without prop-drilling. SchedulerToolbar.tsx is
the only UI entry point - it reads from context and renders the button + result panel.
Jobs.tsx calls markDirty() after mutations to signal the scheduler needs a re-run.
The backend engine (backend/app/scheduler/engine.py) is pure Python - this folder
only calls it and processes the response.

DESIGN PRINCIPLES
Principle 1: runScheduler() calls the backend. No scheduling logic runs client-side.
Principle 6: The backend reads from Job/JobStep tables. The summary here reflects that.
Principle 8: SchedulerToolbar returns null when flags.scheduler is false.

DEPENDENCIES
  This folder imports from:
    ../api/client.ts           - apiClient for POST /api/scheduler/run
    ../context/FeatureFlags.tsx - useFeatureFlags() in SchedulerToolbar
    @tanstack/react-query      - useQueryClient for cache invalidation and job names

  This folder is imported by:
    frontend/src/App.tsx               - SchedulerProvider wraps authenticated routes
    frontend/src/components/Layout.tsx - SchedulerToolbar in header bar
    frontend/src/pages/Jobs.tsx        - useSchedulerContext for markDirty

GOTCHAS
1. markDirty() must be called in Jobs.tsx after every job mutation (create, update,
   delete, lock toggle). If the toolbar stays gray after a change, a mutation is
   missing its markDirty() call in onSuccess.
2. greyed-locked triggers when ALL jobs have lock_status=true. One unlocked job
   reverts to active state. This check happens in checkAllLocked() called from Jobs.tsx.
3. Job names in the run summary come from the TanStack Query ['jobs'] cache.
   If cache is cold, names show as "Job #123". This is acceptable - the cache
   warms immediately after the jobs list loads.
