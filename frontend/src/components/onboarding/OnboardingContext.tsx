// frontend/src/components/onboarding/OnboardingContext.tsx
// Tracks seen tour stops per user in localStorage.
// Provides markSeen, resetTour, isSeen, isNewUser via useOnboarding().

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { useAuth } from '../../auth/AuthContext'

// -- Types ---------------------------------------------------------------------

interface OnboardingContextValue {
  seenStops: Set<string>
  markSeen:    (stopId: string) => void
  resetTour:   () => void
  isSeen:      (stopId: string) => boolean
  isNewUser:   boolean   // true if user has never completed onboarding
}

// -- Helpers -------------------------------------------------------------------

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
    // corrupted data - start fresh
  }
  return new Set()
}

function saveSeenStops(userId: number, stops: Set<string>): void {
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify([...stops]))
  } catch {
    // storage full or unavailable - fail silently
  }
}

// -- Context -------------------------------------------------------------------

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

  // isNewUser - true if the user has seen fewer than 2 stops (hasn't really started)
  const isNewUser = seenStops.size < 2

  return (
    <OnboardingContext.Provider value={{ seenStops, markSeen, resetTour, isSeen, isNewUser }}>
      {children}
    </OnboardingContext.Provider>
  )
}

// -- Hook ----------------------------------------------------------------------

export function useOnboarding(): OnboardingContextValue {
  const ctx = useContext(OnboardingContext)
  if (!ctx) {
    throw new Error('useOnboarding must be used inside <OnboardingProvider>')
  }
  return ctx
}
