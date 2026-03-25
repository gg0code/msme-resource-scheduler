// src/context/IndustryContext.tsx — v4.0.2
//
// Loads the industry config for the logged-in tenant and makes it
// available everywhere via useIndustry() and useLabels() hooks.
//
// How it works:
//   1. Reads industry_type from the authenticated user (via /auth/me)
//   2. Loads the matching IndustryConfig from the config files
//   3. Injects it into all child components via context
//
// Usage:
//   const labels = useLabels()
//   <h1>{labels.jobsPageTitle}</h1>  → "Jobs" | "Production Orders" | etc
//
//   const { config } = useIndustry()
//   <span>{config.branding.productName}</span>  → "PrintFlow Scheduler" | etc
//
// Wrap inside <AuthProvider> and <FeatureFlagProvider> in App.tsx.
// Industry config is loaded once per session — no refetch needed.

import { createContext, useContext, useMemo } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from '../auth/AuthContext'
import { getIndustryConfig } from '../config/industries'
import type { IndustryConfig, IndustryLabels } from '../config/industries'

// ── Context type ──────────────────────────────────────────────────────────────

interface IndustryContextValue {
  config:       IndustryConfig
  labels:       IndustryLabels
  industryType: string
}

// ── Context ───────────────────────────────────────────────────────────────────

const IndustryContext = createContext<IndustryContextValue | null>(null)

// ── Provider ──────────────────────────────────────────────────────────────────

export function IndustryProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  // industry_type comes from the authenticated user object (added in v4.0.2)
  // Falls back to 'printing' if not set — safe for existing tenants
  const industryType = (user as any)?.industry_type ?? 'printing'

  const config = useMemo(
    () => getIndustryConfig(industryType),
    [industryType]
  )

  return (
    <IndustryContext.Provider value={{
      config,
      labels:       config.labels,
      industryType,
    }}>
      {children}
    </IndustryContext.Provider>
  )
}

// ── Hooks ─────────────────────────────────────────────────────────────────────

/**
 * Returns the full industry config including branding and labels.
 * Use when you need branding info (product name, color, icon).
 */
export function useIndustry(): IndustryContextValue {
  const ctx = useContext(IndustryContext)
  if (!ctx) throw new Error('useIndustry must be used inside <IndustryProvider>')
  return ctx
}

/**
 * Returns just the labels object — the most commonly used hook.
 * Use in any component that displays entity names or page titles.
 *
 * Example:
 *   const labels = useLabels()
 *   <h2>{labels.jobs}</h2>  → "Jobs" or "Production Orders"
 */
export function useLabels(): IndustryLabels {
  return useIndustry().labels
}
