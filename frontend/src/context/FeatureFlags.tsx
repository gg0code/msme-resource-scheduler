/**
 * frontend/src/context/FeatureFlags.tsx — v4.0.9
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Fetches feature flags from the backend once on app load and makes them
 * available to every component via the useFeatureFlags() hook. Feature flags
 * control which nav items and features are visible to the tenant. Introduced
 * in v3.7, updated in v4.0.9 to add the whatsapp flag for v5. Sits inside
 * AuthProvider in App.tsx — flags are tenant-specific and require auth.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines FeatureFlags interface with all 7 flag keys.
 * 2. Defines DEFAULT_FLAGS — all false — used until the API responds.
 * 3. FeatureFlagProvider: calls GET /api/features via TanStack Query,
 *    5-minute cache, retry 2 times.
 * 4. Provides flags (or DEFAULT_FLAGS if loading/error) to all descendants.
 * 5. useFeatureFlags(): hook returning the current FeatureFlags object.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : FeatureFlagProvider
 * Type         : React component
 * Purpose      : Fetches and provides feature flags. Renders children immediately
 *                with DEFAULT_FLAGS (all false) while loading — no loading spinner,
 *                no blocked render. Flags arrive within 1-2 seconds.
 * Parameters   : { children: ReactNode }
 * Returns      : JSX.Element
 * Calls        : apiClient.get('/api/features')
 * DB/API       : GET /api/features — returns FEATURE_FLAGS dict from backend
 * Side effects : none
 *
 * Name         : useFeatureFlags
 * Type         : React hook
 * Purpose      : Returns current FeatureFlags object. Returns DEFAULT_FLAGS
 *                if called outside provider (no throw — safe default).
 * Parameters   : none
 * Returns      : FeatureFlags
 * Calls        : useContext(FeatureFlagContext)
 * DB/API       : none
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — wraps protected routes in FeatureFlagProvider
 * - frontend/src/components/Layout.tsx — useFeatureFlags() for nav items
 * - frontend/src/components/AICopilot.tsx — useFeatureFlags()
 * - Any component that conditionally renders based on a feature flag
 *
 * IMPORTS EXPLAINED
 * - createContext, useContext, ReactNode from 'react': context API.
 * - useQuery from '@tanstack/react-query': fetches and caches flags.
 * - apiClient from '../api/client': authenticated Axios instance.
 *
 * INTERN NOTES
 * - All flags default to false. This means features are hidden until the backend
 *   responds — never shown then hidden. This prevents UI flicker.
 * - staleTime: 5 minutes means flags are cached for the session. If you change
 *   flags in the backend, the frontend picks them up within 5 minutes (or on
 *   window focus, which triggers a background refetch).
 * - The whatsapp flag (v5.0) is safe to include in v4-dev — it defaults to false
 *   so nothing renders until it is explicitly enabled on the backend.
 * - Design Principle 8: This is the frontend source of truth for feature gating.
 *   Always check flags before rendering gated features — never hardcode true.
 * - If flags are not loading: check that GET /api/features is registered in
 *   main.py and returns a JSON dict. The backend route is in routers/features.py.
 */

// src/context/FeatureFlags.tsx — v4.0.9
import { createContext, useContext, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'

export interface FeatureFlags {
  scheduler:         boolean
  gantt:             boolean
  qr_scan:           boolean
  step_intelligence: boolean
  csv_import:        boolean
  ai_copilot:        boolean
  whatsapp:          boolean
}

const DEFAULT_FLAGS: FeatureFlags = {
  scheduler:         false,
  gantt:             false,
  qr_scan:           false,
  step_intelligence: false,
  csv_import:        false,
  ai_copilot:        false,
  whatsapp:          false,
}

const FeatureFlagContext = createContext<FeatureFlags>(DEFAULT_FLAGS)

export function FeatureFlagProvider({ children }: { children: ReactNode }) {
  const { data: flags } = useQuery<FeatureFlags>({
    queryKey: ['features'],
    queryFn: () => apiClient.get('/api/features').then(r => r.data),
    staleTime: 5 * 60 * 1000,
    retry: 2,
  })

  return (
    <FeatureFlagContext.Provider value={flags ?? DEFAULT_FLAGS}>
      {children}
    </FeatureFlagContext.Provider>
  )
}

export function useFeatureFlags(): FeatureFlags {
  return useContext(FeatureFlagContext)
}
