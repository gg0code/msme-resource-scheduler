// src/context/IndustryContext.tsx - v4.0.7 / v6.3.2.1
//
// Loads the industry config and applies a theme class to <body>
// so CSS variables in index.css take effect for full theme switching.
//
// v6.3.2.1: Hooks (useIndustry, useLabels) + IndustryContextValue type +
// the React Context object live in ./useIndustry.ts. This file exports
// only the Provider so Vite Fast Refresh hot-swaps it cleanly on save.
//
// Usage:
//   const labels = useLabels()           // from ./useIndustry
//   const { config } = useIndustry()     // from ./useIndustry

import { useMemo, useEffect } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from '../auth/useAuth'
import { getIndustryConfig } from '../config/industries'
import { IndustryContext } from './useIndustry'

// -- Provider ------------------------------------------------------------------

const INDUSTRY_TYPES = ['printing', 'manufacturing', 'fabrication', 'chemical', 'field_service']

export function IndustryProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  // AuthUser.industry_type is declared in auth/useAuth.ts (added v4.0.2);
  // the previous (user as any) cast was dead defensive code from before that.
  const industryType = user?.industry_type ?? 'printing'

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
