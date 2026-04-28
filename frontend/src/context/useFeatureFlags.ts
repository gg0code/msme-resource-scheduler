// frontend/src/context/useFeatureFlags.ts
//
// PURPOSE
// Hook + types + default values for the feature-flag surface. Split out of
// FeatureFlags.tsx in v6.3.2.1 so the Provider file has only component
// exports and Vite Fast Refresh works without a full-page reload on save.
//
// CALLED BY
// - components/Layout.tsx, pages/Jobs.tsx, pages/Employees.tsx,
//   pages/Machines.tsx — anywhere UI is gated on a feature flag.
//
// CALLS INTO
// - React's createContext + useContext primitives only. The Provider in
//   ./FeatureFlags.tsx is what actually fetches /api/features and supplies
//   the flag values via this context.

import { createContext, useContext } from 'react'

// -- Types --------------------------------------------------------------------
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
export const DEFAULT_FLAGS: FeatureFlags = {
  scheduler:         false,
  gantt:             false,
  qr_scan:           false,
  step_intelligence: false,
  csv_import:        false,
  ai_copilot:        false,
  whatsapp:          false,   // v5.0
}

// -- Context object -----------------------------------------------------------
// Lives here (not in FeatureFlags.tsx) so the Provider file stays
// component-only for Vite Fast Refresh.
export const FeatureFlagContext = createContext<FeatureFlags>(DEFAULT_FLAGS)

// -- Hook ---------------------------------------------------------------------
export function useFeatureFlags(): FeatureFlags {
  return useContext(FeatureFlagContext)
}
