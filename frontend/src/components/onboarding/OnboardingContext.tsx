/**
 * frontend/src/components/onboarding/OnboardingContext.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * The state management layer for the user onboarding tour system. Tracks which
 * tour stops the user has seen, persists that state per-user in localStorage, and
 * exposes markSeen/resetTour/isSeen helpers to any component via the useOnboarding
 * hook. Sits at the root of the onboarding sub-system — every other onboarding file
 * (CoachMark, GettingStarted, TourButton) depends on this context.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines OnboardingContextValue interface with seenStops, markSeen, resetTour,
 *    isSeen, and isNewUser.
 * 2. storageKey() — returns per-user localStorage key: 'onboarding_{userId}'.
 * 3. loadSeenStops() — reads and parses the Set<string> from localStorage.
 * 4. saveSeenStops() — serialises Set to JSON array and writes to localStorage.
 * 5. OnboardingProvider: loads seenStops on mount (and when user changes).
 * 6. markSeen(stopId): adds a stop ID to the set, persists immediately.
 * 7. resetTour(): removes the localStorage key, clears state to empty Set.
 * 8. isSeen(stopId): returns boolean from seenStops.
 * 9. isNewUser: true if fewer than 2 stops have been seen.
 * 10. useOnboarding(): hook that throws if called outside provider.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : OnboardingProvider
 * Type         : React component
 * Purpose      : Context provider that manages seen-stops state and exposes
 *                the full onboarding API to all descendants.
 * Parameters   : { children: ReactNode }
 * Returns      : JSX.Element
 * Calls        : loadSeenStops (on mount), saveSeenStops (on markSeen)
 * DB/API       : none — localStorage only
 * Side effects : reads/writes localStorage
 *
 * Name         : useOnboarding
 * Type         : React hook
 * Purpose      : Public API for consuming onboarding state. Returns seenStops,
 *                markSeen, resetTour, isSeen, isNewUser.
 * Parameters   : none
 * Returns      : OnboardingContextValue
 * Calls        : useContext(OnboardingContext)
 * DB/API       : none
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/components/onboarding/index.ts — re-exports OnboardingProvider and useOnboarding
 * - frontend/src/App.tsx — wraps authenticated routes in OnboardingProvider
 * - frontend/src/components/onboarding/CoachMark.tsx — calls isSeen, markSeen
 * - frontend/src/components/onboarding/GettingStarted.tsx — calls resetTour
 * - frontend/src/components/onboarding/TourButton.tsx — calls resetTour
 *
 * IMPORTS EXPLAINED
 * - createContext, useCallback, useContext, useEffect, useState, ReactNode from 'react':
 *   Core React hooks for context creation, state, and memoisation.
 * - useAuth from '../../auth/AuthContext': Reads user.id to namespace localStorage keys
 *   per user — different users on the same browser don't share tour state.
 *
 * INTERN NOTES
 * - localStorage keys are per-user: 'onboarding_{userId}'. If user.id is undefined
 *   (not logged in), seenStops is an empty Set and no writes happen.
 * - saveSeenStops uses try/catch silently — localStorage can be full or disabled in
 *   private browsing. The tour will still work in-session, just won't persist.
 * - isNewUser (seenStops.size < 2) is a heuristic — it means the user has clicked
 *   "Got it" on fewer than 2 coach marks. Used by other components to decide whether
 *   to show extra help. The threshold of 2 is intentional.
 * - Design Principle 3 (no secrets in storage) applies here too — only stop IDs
 *   (strings like 'employees', 'jobs') are stored, never tokens or PII.
 * - If the tour resets unexpectedly: check that user.id is stable. If it changes
 *   between renders, useEffect re-runs and overwrites seenStops.
 */

// Tracks which tour stops the user has seen, persisted per-user in localStorage.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { useAuth } from '../../auth/AuthContext'

// ── Types ─────────────────────────────────────────────────────────────────────

interface OnboardingContextValue {
  seenStops: Set<string>
  markSeen:    (stopId: string) => void
  resetTour:   () => void
  isSeen:      (stopId: string) => boolean
  isNewUser:   boolean   // true if user has never completed onboarding
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function storageKey(userId: number): string {
  return `onboarding_${userId}`
}

function loadSeenStops(userId: number): Set<string> {
  try {
    const raw = localStorage.getItem(storageKey(userId))
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return new Set<string>(parsed)
  } catch {
    // corrupted data — start fresh
  }
  return new Set()
}

function saveSeenStops(userId: number, stops: Set<string>): void {
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify([...stops]))
  } catch {
    // storage full or unavailable — fail silently
  }
}

// ── Context ───────────────────────────────────────────────────────────────────

const OnboardingContext = createContext<OnboardingContextValue | null>(null)

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [seenStops, setSeenStops] = useState<Set<string>>(new Set())

  // Reload from localStorage whenever the logged-in user changes
  useEffect(() => {
    if (user) {
      setSeenStops(loadSeenStops(user.id))
    } else {
      setSeenStops(new Set())
    }
  }, [user?.id])

  const markSeen = useCallback(
    (stopId: string) => {
      if (!user) return
      setSeenStops((prev) => {
        const next = new Set(prev)
        next.add(stopId)
        saveSeenStops(user.id, next)
        return next
      })
    },
    [user],
  )

  const resetTour = useCallback(() => {
    if (!user) return
    try {
      localStorage.removeItem(storageKey(user.id))
    } catch {
      // ignore
    }
    setSeenStops(new Set())
  }, [user])

  const isSeen = useCallback(
    (stopId: string) => seenStops.has(stopId),
    [seenStops],
  )

  // isNewUser — true if the user has seen fewer than 2 stops (hasn't really started)
  const isNewUser = seenStops.size < 2

  return (
    <OnboardingContext.Provider value={{ seenStops, markSeen, resetTour, isSeen, isNewUser }}>
      {children}
    </OnboardingContext.Provider>
  )
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useOnboarding(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext)
  if (!ctx) {
    throw new Error('useOnboarding must be used inside <OnboardingProvider>')
  }
  return ctx
}
