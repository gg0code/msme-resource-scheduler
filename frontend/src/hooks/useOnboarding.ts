// src/hooks/useOnboarding.ts — V3.8
//
// Manages the Getting Started checklist state in localStorage.
// Checklist is derived from real app data — no manual marking needed.
// Auto-dismisses permanently once all 5 steps are complete.
//
// Steps:
//   1. add_employee    — at least 1 employee exists
//   2. add_machine     — at least 1 machine exists
//   3. create_job      — at least 1 job exists
//   4. assign_resources — at least 1 job has employees + machines assigned
//   5. mark_in_progress — at least 1 job has status In Progress or Completed

import { useState, useEffect } from 'react'

const STORAGE_KEY = 'msme_onboarding_dismissed'

export interface OnboardingState {
  dismissed: boolean
  steps: {
    add_employee:      boolean
    add_machine:       boolean
    create_job:        boolean
    assign_resources:  boolean
    mark_in_progress:  boolean
  }
  completedCount: number
  allComplete: boolean
  dismiss: () => void
}

interface OnboardingInput {
  employeeCount:    number
  machineCount:     number
  jobCount:         number
  assignedJobCount: number   // jobs with both employee + machine assigned
  activeJobCount:   number   // jobs with status In Progress or Completed
}

export function useOnboarding(input: OnboardingInput): OnboardingState {
  const [dismissed, setDismissed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })

  const steps = {
    add_employee:     input.employeeCount    > 0,
    add_machine:      input.machineCount     > 0,
    create_job:       input.jobCount         > 0,
    assign_resources: input.assignedJobCount > 0,
    mark_in_progress: input.activeJobCount   > 0,
  }

  const completedCount = Object.values(steps).filter(Boolean).length
  const allComplete    = completedCount === 5

  // Auto-dismiss permanently once all steps complete
  useEffect(() => {
    if (allComplete && !dismissed) {
      try {
        localStorage.setItem(STORAGE_KEY, 'true')
      } catch { /* ignore */ }
      // Small delay so user sees the completed state before it disappears
      const t = setTimeout(() => setDismissed(true), 2000)
      return () => clearTimeout(t)
    }
  }, [allComplete, dismissed])

  function dismiss() {
    try {
      localStorage.setItem(STORAGE_KEY, 'true')
    } catch { /* ignore */ }
    setDismissed(true)
  }

  return { dismissed, steps, completedCount, allComplete, dismiss }
}
