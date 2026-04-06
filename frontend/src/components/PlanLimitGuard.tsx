// src/components/PlanLimitGuard.tsx
// Shared hook + components for plan limit enforcement across all pages.
// Usage:
//   const { planLimits, isReached, getInfo } = usePlanLimits()
//   <LimitedButton resource="jobs" planLimits={planLimits} onClick={...}>New Job</LimitedButton>
//   <PlanLimitBanner resource="jobs" planLimits={planLimits} />

import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'
import { Lock } from 'lucide-react'
import type { ReactNode } from 'react'
import { DASHBOARD } from '../api/api_endpoints'

const CONTACT_EMAIL = 'abc@abc.com'
const CONTACT_PHONE = '+91 999 99 99 999'

// -- Types ---------------------------------------------------------------------
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

// -- Hook ----------------------------------------------------------------------
export function usePlanLimits() {
  const { data: planLimits, isLoading } = useQuery<PlanLimits>({
    queryKey: ['plan-limits'],
    queryFn: () => apiClient.get(DASHBOARD.planLimits).then(r => r.data),
    staleTime: 30_000,
  })

  const isReached = (resource: string) =>
    planLimits?.limits?.[resource]?.reached ?? false

  const getInfo = (resource: string): ResourceLimit =>
    planLimits?.limits?.[resource] ?? { limit: null, current: 0, reached: false, unlimited: true }

  return { planLimits, isLoading, isReached, getInfo }
}

// -- Upgrade hint --------------------------------------------------------------
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

// -- Inline banner (shown below header when limit reached) ---------------------
interface BannerProps {
  resource: string
  planLimits: PlanLimits | undefined
  label?: string        // e.g. "jobs", "employees" - defaults to resource
}

export function PlanLimitBanner({ resource, planLimits, label }: BannerProps) {
  const info = planLimits?.limits?.[resource]
  if (!info?.reached) return null
  const displayLabel = label ?? resource

  return (
    <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm">
      <Lock size={15} className="text-amber-500 mt-0.5 flex-shrink-0" />
      <p className="text-amber-800">
        <span className="font-semibold">Free plan limit reached</span> - you have used{' '}
        <span className="font-semibold">{info.current}/{info.limit}</span> {displayLabel}.{' '}
        For unconstrained working, <UpgradeHint />
      </p>
    </div>
  )
}

// -- Raw materials inline limit hint (inside wizard) ---------------------------
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

// -- Button wrapper -------------------------------------------------------------
interface LimitedButtonProps {
  resource: string
  planLimits: PlanLimits | undefined
  onClick?: () => void
  children: ReactNode
  className?: string           // applied when NOT limited
  disabledClassName?: string   // applied when limited
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
