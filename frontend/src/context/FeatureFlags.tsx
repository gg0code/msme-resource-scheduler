// src/context/FeatureFlags.tsx - v4.0.9
//
// Fetches feature flags from /api/features once on app load.
// Makes them available everywhere via the FeatureFlagContext (consumed by
// useFeatureFlags() in ./useFeatureFlags.ts).
//
// v6.3.2.1: Hook + interface + DEFAULT_FLAGS + the React Context object live
// in ./useFeatureFlags.ts so this file has only the Provider component and
// Vite Fast Refresh hot-swaps cleanly on save.
//
// No auth needed - flags are public UI visibility controls.

import { type ReactNode, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'
import { FEATURES, runDevHealthCheck } from '../api/api_endpoints'
import { FeatureFlagContext, DEFAULT_FLAGS, type FeatureFlags } from './useFeatureFlags'

// -- Provider ---------------------------------------------------------------
export function FeatureFlagProvider({ children }: { children: ReactNode }) {
  // Fire dev health check once on first provider mount
  useEffect(() => { runDevHealthCheck() }, [])
  const { data: flags } = useQuery<FeatureFlags>({
    queryKey: ['features'],
    queryFn: () => apiClient.get(FEATURES.flags).then(r => r.data),
    // Flags rarely change - cache for the session, refetch on window focus
    staleTime: 5 * 60 * 1000,   // 5 minutes
    retry: 2,
  })

  return (
    <FeatureFlagContext.Provider value={flags ?? DEFAULT_FLAGS}>
      {children}
    </FeatureFlagContext.Provider>
  )
}
