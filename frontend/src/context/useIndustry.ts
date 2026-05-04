// frontend/src/context/useIndustry.ts
//
// PURPOSE
// Hooks (useIndustry, useLabels) + IndustryContextValue type + the React
// Context object for the industry surface. Split out of IndustryContext.tsx
// in v6.3.2.1 so the Provider file has only component exports and Vite
// Fast Refresh works without a full-page reload on save.
//
// CALLED BY (14 sites)
// - components/Layout.tsx, components/AICopilot.tsx, components/common/CsvImport.tsx
// - components/onboarding/GettingStarted.tsx
// - pages/Jobs.tsx, pages/Dashboard.tsx, pages/Employees.tsx, pages/GanttPage.tsx
// - pages/Machines.tsx, pages/Skills.tsx, pages/Availability.tsx
// - context/IndustryContext.tsx (the Provider file imports the context object)
//
// CALLS INTO
// - React's createContext + useContext primitives only.
// - Type imports from ../config/industries.

import { createContext, useContext } from 'react'
import type { IndustryConfig, IndustryLabels, IndustryPickers } from '../config/industries'

// -- Context type -------------------------------------------------------------
export interface IndustryContextValue {
  config:       IndustryConfig
  labels:       IndustryLabels
  industryType: string
}

// -- Context object -----------------------------------------------------------
// Lives here (not in IndustryContext.tsx) so the Provider file stays
// component-only for Vite Fast Refresh.
export const IndustryContext = createContext<IndustryContextValue | null>(null)

// -- Hooks --------------------------------------------------------------------
export function useIndustry(): IndustryContextValue {
  const ctx = useContext(IndustryContext)
  if (!ctx) throw new Error('useIndustry must be used inside <IndustryProvider>')
  return ctx
}

export function useLabels(): IndustryLabels {
  return useIndustry().labels
}

// v6.3.10 — bootstrap UI trim. Returns the industry's one-tap picker
// suggestions (skills + machineTypes) for the trimmed Employee / Machine forms.
export function usePickers(): IndustryPickers {
  return useIndustry().config.pickers
}
