// frontend/src/components/usePlanLimits.ts
//
// PURPOSE
// Hook + types for the free-plan limit surface. Split out of
// PlanLimitGuard.tsx in v6.3.2.1 so that file has only component exports
// (LimitedButton, PlanLimitBanner, RawMaterialLimitHint) and Vite Fast
// Refresh works without a full-page reload on save.
//
// CALLED BY (3 sites)
// - pages/Jobs.tsx, pages/Employees.tsx, pages/Machines.tsx — anywhere a
//   page needs to know which resources are at the free-plan cap.
//
// CALLS INTO
// - @tanstack/react-query (useQuery for /api/dashboard/plan-limits)
// - apiClient (axios)
// - DASHBOARD endpoint constant

import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'
import { DASHBOARD } from '../api/api_endpoints'

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
