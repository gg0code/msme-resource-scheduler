// frontend/src/components/onboarding/useOnboarding.ts
//
// PURPOSE
// Hook + type + the React Context object for the onboarding tour-stop
// surface. Split out of OnboardingContext.tsx in v6.3.2.1 so the Provider
// file has only component exports and Vite Fast Refresh works without a
// full-page reload on save.
//
// CALLED BY
// - components/onboarding/CoachMark.tsx (reads seenStops)
// - components/onboarding/TourButton.tsx (calls resetTour)
// - components/onboarding/GettingStarted.tsx (reads isNewUser)
// - components/onboarding/index.ts barrel re-exports useOnboarding from here
//
// CALLS INTO
// - React's createContext + useContext primitives only.

import { createContext, useContext } from 'react'

// -- Types --------------------------------------------------------------------
export interface OnboardingContextValue {
  seenStops: Set<string>
  markSeen:    (stopId: string) => void
  resetTour:   () => void
  isSeen:      (stopId: string) => boolean
  isNewUser:   boolean   // true if user has never completed onboarding
}

// -- Context object -----------------------------------------------------------
// Lives here (not in OnboardingContext.tsx) so the Provider file stays
// component-only for Vite Fast Refresh.
export const OnboardingContext = createContext<OnboardingContextValue | null>(null)

// -- Hook ---------------------------------------------------------------------
export function useOnboarding(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext)
  if (!ctx) {
    throw new Error('useOnboarding must be used inside <OnboardingProvider>')
  }
  return ctx
}
