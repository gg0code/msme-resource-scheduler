/**
 * frontend/src/context/IndustryContext.tsx — v4.0.7
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Loads the industry-specific configuration for the logged-in tenant and applies
 * a CSS theme class to <body> so all CSS variables take effect. Provides the
 * config and labels to all descendant components via useIndustry() and useLabels()
 * hooks. Introduced in v4.0.2, refactored in v4.0.7 to use body CSS classes
 * instead of inline styles. Sits inside AuthProvider in App.tsx — requires user
 * to be logged in to know industry_type.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Reads user.industry_type from useAuth().
 * 2. Calls getIndustryConfig(industryType) to load the matching IndustryConfig.
 * 3. Memoises the config so it only recomputes when industryType changes.
 * 4. useEffect: removes all theme-* classes from <body>, adds theme-{industryType}.
 *    This triggers CSS variable substitution from index.css for sidebar, brand colours etc.
 * 5. Provides config, labels, and industryType via IndustryContext.
 * 6. useIndustry(): returns full IndustryContextValue, throws if outside provider.
 * 7. useLabels(): convenience hook returning just config.labels.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : IndustryProvider
 * Type         : React component
 * Purpose      : Loads industry config, applies body theme class, provides context.
 * Parameters   : { children: ReactNode }
 * Returns      : JSX.Element
 * Calls        : useAuth(), getIndustryConfig(), document.body.classList
 * DB/API       : none — config is local static data
 * Side effects : adds/removes CSS class on document.body
 *
 * Name         : useLabels
 * Type         : React hook
 * Purpose      : Shortcut hook returning IndustryLabels. Used by almost every
 *                page and component that displays resource names (jobs, employees etc).
 * Parameters   : none
 * Returns      : IndustryLabels
 * Calls        : useIndustry()
 * DB/API       : none
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — wraps protected routes in IndustryProvider
 * - frontend/src/components/Layout.tsx — useIndustry() for config, useLabels() for nav
 * - frontend/src/components/AICopilot.tsx — useLabels() for suggestion text
 * - frontend/src/components/onboarding/GettingStarted.tsx — useLabels() for step text
 * - frontend/src/components/common/CsvImport.tsx — useLabels() for modal title
 * - All pages — useLabels() for page titles and button labels
 *
 * IMPORTS EXPLAINED
 * - createContext, useContext, useMemo, useEffect from 'react': context, memoisation,
 *   body class side effect.
 * - ReactNode from 'react': children prop type.
 * - useAuth from '../auth/AuthContext': reads user.industry_type.
 * - getIndustryConfig from '../config/industries': loads the config object.
 * - IndustryConfig, IndustryLabels from '../config/industries': TypeScript types.
 *
 * INTERN NOTES
 * - (user as any)?.industry_type is a deliberate cast. The AuthUser interface does
 *   define industry_type but TypeScript may not narrow it correctly here. If you
 *   update AuthUser in AuthContext.tsx, remove the cast.
 * - The theme class effect cleanup (return () => classList.remove) runs on unmount
 *   and on industryType change. This ensures no stale theme classes accumulate.
 * - INDUSTRY_TYPES array must match the keys in INDUSTRY_CONFIGS in index.ts.
 *   If you add a new industry, update both.
 * - Design Principle 11: useIndustry() throws if called outside IndustryProvider.
 *   useLabels() is a thin wrapper — it never returns null.
 * - If the sidebar shows the wrong colour: check that IndustryProvider is mounted
 *   above Layout in App.tsx and that user.industry_type is set on the tenant.
 */

// src/context/IndustryContext.tsx — v4.0.7
import { createContext, useContext, useMemo, useEffect } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from '../auth/AuthContext'
import { getIndustryConfig } from '../config/industries'
import type { IndustryConfig, IndustryLabels } from '../config/industries'

interface IndustryContextValue {
  config:       IndustryConfig
  labels:       IndustryLabels
  industryType: string
}

const IndustryContext = createContext<IndustryContextValue | null>(null)

const INDUSTRY_TYPES = ['printing', 'manufacturing', 'fabrication', 'chemical', 'field_service']

export function IndustryProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const industryType = (user as any)?.industry_type ?? 'printing'

  const config = useMemo(
    () => getIndustryConfig(industryType),
    [industryType]
  )

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

export function useIndustry(): IndustryContextValue {
  const ctx = useContext(IndustryContext)
  if (!ctx) throw new Error('useIndustry must be used inside <IndustryProvider>')
  return ctx
}

export function useLabels(): IndustryLabels {
  return useIndustry().labels
}
