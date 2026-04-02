/**
 * frontend/src/components/PlanLimitGuard.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Provides shared plan limit enforcement UI across all resource management pages.
 * The free plan caps employees at 10, jobs at 20, machines at 10, skills at 20,
 * and raw materials per job at a configurable limit. This file contains a hook
 * (usePlanLimits) and three components (PlanLimitBanner, RawMaterialLimitHint,
 * LimitedButton) that any page can use to consistently enforce and communicate
 * these limits. Introduced in v3.7 and updated in v4.0.9. Sits in the shared
 * components layer — called from Jobs, Employees, Machines, and Skills pages.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines ResourceLimit and PlanLimits TypeScript interfaces matching the
 *    backend /dashboard/plan-limits response shape.
 * 2. Exports usePlanLimits() hook that fetches plan limits from the backend
 *    using TanStack Query with a 30-second cache.
 * 3. usePlanLimits returns planLimits data, isLoading, isReached(resource) helper,
 *    and getInfo(resource) helper.
 * 4. Exports PlanLimitBanner — an amber warning banner shown below page headers
 *    when a resource limit is reached.
 * 5. Exports RawMaterialLimitHint — a small inline hint inside the job wizard
 *    showing raw material count vs limit.
 * 6. Exports LimitedButton — a button wrapper that disables itself and shows a
 *    lock icon when the resource limit is reached.
 * 7. Internal UpgradeHint renders the contact email and phone as clickable links.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : usePlanLimits
 * Type         : React hook
 * Purpose      : Fetches current plan limits and usage counts from the backend.
 *                Returns helpers to check if a specific resource limit is reached.
 *                Used by every resource management page to gate create actions.
 * Parameters   : none
 * Returns      : { planLimits, isLoading, isReached(resource), getInfo(resource) }
 * Calls        : apiClient.get('/dashboard/plan-limits')
 * DB/API       : GET /dashboard/plan-limits (note: no /api/ prefix — special route)
 * Side effects : none — read only, cached 30s
 *
 * Name         : PlanLimitBanner
 * Type         : React component
 * Purpose      : Amber warning banner displayed when a resource limit is reached.
 *                Returns null (renders nothing) if limit is not reached — safe to
 *                always render without conditional logic in the parent.
 * Parameters   : resource: string — e.g. 'jobs', 'employees'
 *                planLimits: PlanLimits | undefined
 *                label?: string — display name e.g. "jobs" (defaults to resource key)
 * Returns      : JSX.Element | null
 * Calls        : UpgradeHint
 * DB/API       : none
 * Side effects : none
 *
 * Name         : RawMaterialLimitHint
 * Type         : React component
 * Purpose      : Inline hint inside the job raw materials wizard showing used/limit.
 *                Turns amber with a lock icon when the count reaches the limit.
 * Parameters   : current: number — current raw material count
 *                planLimits: PlanLimits | undefined
 * Returns      : JSX.Element | null (null if plan is unlimited)
 * Calls        : UpgradeHint (when limit reached)
 * DB/API       : none
 * Side effects : none
 *
 * Name         : LimitedButton
 * Type         : React component
 * Purpose      : A button that automatically disables itself when the resource limit
 *                is reached, shows a lock icon, and displays the limit details in
 *                the title tooltip. Drop-in replacement for plain buttons on pages
 *                that have plan limit enforcement.
 * Parameters   : resource: string, planLimits: PlanLimits | undefined,
 *                onClick?: () => void, children: ReactNode,
 *                className?: string, disabledClassName?: string
 * Returns      : JSX.Element — button element, disabled or enabled
 * Calls        : nothing
 * DB/API       : none
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Jobs.tsx — LimitedButton, PlanLimitBanner, usePlanLimits
 * - frontend/src/pages/Employees.tsx — LimitedButton, PlanLimitBanner, usePlanLimits
 * - frontend/src/pages/Machines.tsx — LimitedButton, PlanLimitBanner, usePlanLimits
 * - frontend/src/pages/Skills.tsx — LimitedButton, PlanLimitBanner, usePlanLimits
 *
 * IMPORTS EXPLAINED
 * - useQuery from '@tanstack/react-query': Fetches and caches plan limits with
 *   automatic background refetch after 30 seconds.
 * - apiClient from '../api/client': Authenticated Axios instance for the plan limits call.
 * - Lock from 'lucide-react': Lock icon shown on disabled buttons and banners.
 * - ReactNode from 'react': Type for the children prop in LimitedButton.
 *
 * INTERN NOTES
 * - The /dashboard/plan-limits endpoint has NO /api/ prefix — this is the one exception
 *   to Design Principle 4 in the frontend. The backend route is registered differently.
 *   Do not add /api/ to this URL.
 * - CONTACT_EMAIL and CONTACT_PHONE are hardcoded strings. Update them when the
 *   business contact changes — they appear in every plan limit message shown to users.
 * - PlanLimitBanner returns null when limit is not reached. Always render it without
 *   a conditional wrapper — the component handles its own visibility.
 * - LimitedButton accepts className and disabledClassName props so each page can
 *   match its own button styling. The defaults are standard blue/gray Tailwind classes.
 * - Design Principle 8: Plan limits are a form of feature gating enforced at both
 *   backend (HTTP 402) and frontend (this file). Both layers must be respected.
 * - If usePlanLimits returns undefined planLimits: the fetch likely failed because
 *   the user is not authenticated or the /dashboard/plan-limits route is not registered.
 *   Check backend main.py for the dashboard router registration.
 */

import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'
import { Lock } from 'lucide-react'
import type { ReactNode } from 'react'

const CONTACT_EMAIL = 'abc@abc.com'
const CONTACT_PHONE = '+91 999 99 99 999'

// ── Types ─────────────────────────────────────────────────────────────────────
export interface ResourceLimit {
  limit: number | null
  current: number
  reached: boolean
  unlimited: boolean
}

export interface PlanLimits {
  plan: string
  limits: Record<string, ResourceLimit>
}

// ── Hook ──────────────────────────────────────────────────────────────────────
export function usePlanLimits() {
  const { data: planLimits, isLoading } = useQuery<PlanLimits>({
    queryKey: ['plan-limits'],
    queryFn: () => apiClient.get('/dashboard/plan-limits').then(r => r.data),
    staleTime: 30_000,
  })

  const isReached = (resource: string) =>
    planLimits?.limits?.[resource]?.reached ?? false

  const getInfo = (resource: string): ResourceLimit =>
    planLimits?.limits?.[resource] ?? { limit: null, current: 0, reached: false, unlimited: true }

  return { planLimits, isLoading, isReached, getInfo }
}

// ── Upgrade hint ──────────────────────────────────────────────────────────────
function UpgradeHint() {
  return (
    <span className="text-gray-500">
      Contact{' '}
      <a href={`mailto:${CONTACT_EMAIL}`} className="text-blue-600 hover:underline font-medium">
        {CONTACT_EMAIL}
      </a>
      {' '}or{' '}
      <a href={`tel:${CONTACT_PHONE.replace(/\s/g, '')}`} className="text-blue-600 hover:underline font-medium">
        {CONTACT_PHONE}
      </a>
      {' '}to upgrade.
    </span>
  )
}

// ── Inline banner (shown below header when limit reached) ─────────────────────
interface BannerProps {
  resource: string
  planLimits: PlanLimits | undefined
  label?: string
}

export function PlanLimitBanner({ resource, planLimits, label }: BannerProps) {
  const info = planLimits?.limits?.[resource]
  if (!info?.reached) return null
  const displayLabel = label ?? resource

  return (
    <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm">
      <Lock size={15} className="text-amber-500 mt-0.5 flex-shrink-0" />
      <p className="text-amber-800">
        <span className="font-semibold">Free plan limit reached</span> — you have used{' '}
        <span className="font-semibold">{info.current}/{info.limit}</span> {displayLabel}.{' '}
        For unconstrained working, <UpgradeHint />
      </p>
    </div>
  )
}

// ── Raw materials inline limit hint (inside wizard) ───────────────────────────
interface RawMatLimitProps {
  current: number
  planLimits: PlanLimits | undefined
}

export function RawMaterialLimitHint({ current, planLimits }: RawMatLimitProps) {
  const info = planLimits?.limits?.['raw_materials']
  if (!info || info.unlimited) return null

  const reached = current >= (info.limit ?? Infinity)
  return (
    <div className={`text-xs px-3 py-1.5 rounded-lg flex items-center gap-1.5 ${
      reached ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-gray-50 text-gray-500'
    }`}>
      {reached ? <Lock size={11} /> : null}
      {reached
        ? <>Free plan: {current}/{info.limit} materials used. <UpgradeHint /></>
        : <>{current}/{info.limit} materials (free plan)</>
      }
    </div>
  )
}

// ── Button wrapper ─────────────────────────────────────────────────────────────
interface LimitedButtonProps {
  resource: string
  planLimits: PlanLimits | undefined
  onClick?: () => void
  children: ReactNode
  className?: string
  disabledClassName?: string
}

export function LimitedButton({
  resource, planLimits, onClick, children,
  className = 'flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg transition-colors',
  disabledClassName = 'flex items-center gap-2 bg-gray-200 text-gray-400 text-sm px-4 py-2 rounded-lg cursor-not-allowed',
}: LimitedButtonProps) {
  const info = planLimits?.limits?.[resource]
  const reached = info?.reached ?? false

  return (
    <button
      onClick={reached ? undefined : onClick}
      disabled={reached}
      title={reached
        ? `Free plan limit reached (${info?.current}/${info?.limit}). Contact ${CONTACT_EMAIL} or ${CONTACT_PHONE} to upgrade.`
        : undefined}
      className={reached ? disabledClassName : className}
    >
      {reached && <Lock size={13} />}
      {children}
    </button>
  )
}
