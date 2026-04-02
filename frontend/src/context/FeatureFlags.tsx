// frontend/src/context/FeatureFlags.tsx - v4.0.9
// Fetches feature flags from /api/features, provides via useFeatureFlags().
// All flags default to false until API responds. Cached 5 minutes.

import { createContext, useContext, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'

// -- Types ------------------------------------------------------------------
export interface FeatureFlags {
  scheduler:         boolean
  gantt:             boolean
  qr_scan:           boolean
  step_intelligence: boolean
  csv_import:        boolean
  ai_copilot:        boolean
  whatsapp:          boolean   // v5.0 - WhatsApp Copilot nav item
}

// All flags default to false - safe until the API responds
const DEFAULT_FLAGS: FeatureFlags = {
  scheduler:         false,
  gantt:             false,
  qr_scan:           false,
  step_intelligence: false,
  csv_import:        false,
  ai_copilot:        false,
  whatsapp:          false,   // v5.0
}

// -- Context ----------------------------------------------------------------
const FeatureFlagContext = createContext<FeatureFlags>(DEFAULT_FLAGS)

// -- Provider ---------------------------------------------------------------
export function FeatureFlagProvider({ children }: { children: ReactNode }) {
  const { data: flags } = useQuery<FeatureFlags>({
    queryKey: ['features'],
    queryFn: () => apiClient.get('/api/features').then(r => r.data),
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

// -- Hook -------------------------------------------------------------------
export function useFeatureFlags(): FeatureFlags {
  return useContext(FeatureFlagContext)
}
