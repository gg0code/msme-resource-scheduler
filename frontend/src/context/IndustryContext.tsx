// frontend/src/context/IndustryContext.tsx - v4.0.7
// Loads industry config, applies theme-{industry} class to body.
// Provides useIndustry() and useLabels() hooks.

import { createContext, useContext, useMemo, useEffect } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from '../auth/AuthContext'
import { getIndustryConfig } from '../config/industries'
import type { IndustryConfig, IndustryLabels } from '../config/industries'

// -- Context type --------------------------------------------------------------

interface IndustryContextValue {
  config:       IndustryConfig
  labels:       IndustryLabels
  industryType: string
}

const IndustryContext = createContext<IndustryContextValue | null>(null)

// -- Provider ------------------------------------------------------------------

const INDUSTRY_TYPES = ['printing', 'manufacturing', 'fabrication', 'chemical', 'field_service']

export function IndustryProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const industryType = (user as any)?.industry_type ?? 'printing'

  const config = useMemo(
    () => getIndustryConfig(industryType),
    [industryType]
  )

  // v4.0.7 - apply theme-{industry} class to <body>
  // index.css defines CSS variables per class (brand-primary, brand-sidebar-bg etc)
  useEffect(() => {
    INDUSTRY_TYPES.forEach(t => document.body.classList.remove(`theme-${t}`))
    document.body.classList.add(`theme-${industryType}`)
    return () => {
      document.body.classList.remove(`theme-${industryType}`)
    }
  }, [industryType])

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

// -- Hooks ---------------------------------------------------------------------

export function useIndustry(): IndustryContextValue {
  const ctx = useContext(IndustryContext)
  if (!ctx) throw new Error('useIndustry must be used inside <IndustryProvider>')
  return ctx
}

export function useLabels(): IndustryLabels {
  return useIndustry().labels
}
