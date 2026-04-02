/**
 * FILE PURPOSE
 * This is the TypeScript API client layer for the ZetaOps Copilot dashboard functionality,
 * introduced in v4-dev and serving as the frontend's interface to retrieve comprehensive
 * dashboard data from the backend. It sits between React dashboard components and the
 * backend FastAPI /api/dashboard/ endpoint, providing type-safe access to job status
 * summaries, resource availability, and detailed job information with cost breakdowns.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Imports the shared apiClient from './client' which handles authentication and tenant scoping
 * 2. Defines CostBreakdown interface for detailed financial breakdowns (employee, machine, material costs)
 * 3. Defines DashboardJob interface representing a job with all dashboard-relevant fields
 * 4. Defines DashboardData interface representing the complete dashboard response structure
 * 5. Exports dashboardApi object containing the single 'get' method for fetching dashboard data
 * 6. The get method makes an authenticated HTTP GET request to /api/dashboard/ and returns typed data
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 * 
 * CostBreakdown (Interface)
 * Name         : CostBreakdown
 * Type         : TypeScript interface
 * Purpose      : Defines the structure for detailed cost analysis of jobs, breaking down expenses
 *                into categories (labor, equipment, materials, misc) and calculating profit margins.
 *                Used for both tentative (planned) and actual (completed) cost tracking.
 * Parameters   : Not applicable (interface)
 * Returns      : Not applicable (interface)
 * Calls        : Not applicable (interface)
 * DB/API       : Not applicable (interface)
 * Side effects : Not applicable (interface)
 *
 * DashboardJob (Interface)
 * Name         : DashboardJob
 * Type         : TypeScript interface
 * Purpose      : Comprehensive job representation for dashboard display, including scheduling data,
 *                timer information, conflict detection, resource assignments, and dual cost tracking
 *                (tentative vs actual). Provides all data needed for job cards and status indicators.
 * Parameters   : Not applicable (interface)
 * Returns      : Not applicable (interface)
 * Calls        : Not applicable (interface)
 * DB/API       : Not applicable (interface)
 * Side effects : Not applicable (interface)
 *
 * DashboardData (Interface)
 * Name         : DashboardData
 * Type         : TypeScript interface
 * Purpose      : Top-level dashboard data structure containing summary statistics, resource availability
 *                counts, job status distributions, upcoming job previews, and the complete jobs array.
 *                Represents the entire payload from the backend dashboard endpoint.
 * Parameters   : Not applicable (interface)
 * Returns      : Not applicable (interface)
 * Calls        : Not applicable (interface)
 * DB/API       : Not applicable (interface)
 * Side effects : Not applicable (interface)
 *
 * dashboardApi.get (Function)
 * Name         : dashboardApi.get
 * Type         : Async function
 * Purpose      : Fetches complete dashboard data from the backend, including job summaries, resource
 *                availability, and detailed job information. Handles authentication automatically through
 *                apiClient and returns strongly-typed data for dashboard components to consume.
 * Parameters   : None
 * Returns      : Promise<DashboardData> - Complete dashboard dataset with jobs, summaries, and statistics
 * Calls        : apiClient.get() from './client' which handles JWT tokens and tenant scoping
 * DB/API       : HTTP GET to /api/dashboard/ endpoint on backend FastAPI server
 * Side effects : None (read-only operation)
 *
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Dashboard.tsx (main dashboard page component)
 * - frontend/src/components/DashboardSummary.tsx (summary statistics component)
 * - frontend/src/components/JobStatusCards.tsx (job listing components)
 * - Any other dashboard-related components that need job status or resource availability data
 *
 * IMPORTS EXPLAINED
 * - apiClient from './client': The shared Axios instance that handles JWT authentication, 
 *   automatic token refresh, tenant scoping headers, and base URL configuration for all API calls.
 *
 * INTERN NOTES
 * - Easiest thing to break without realising: Changing field names in interfaces without updating
 *   the backend schemas - TypeScript won't catch mismatches between frontend/backend until runtime
 * - Non-obvious design decision and why: Dual cost tracking (tentative vs actual) allows showing
 *   planned costs during job execution and actual costs after completion without data loss
 * - Most common mistake when editing: Adding new fields to interfaces without ensuring the backend
 *   dashboard endpoint actually returns those fields, causing undefined values in components
 * - Which design principle this file implements: Principle #2 (tenant scoping) - all data is
 *   automatically scoped by tenant through the apiClient authentication headers
 * - What to check if this file behaves unexpectedly: Verify the backend /api/dashboard/ endpoint
 *   is returning data matching these interfaces, check authentication tokens, and ensure tenant_id
 *   filtering is working correctly on the backend
 * - Not applicable (v4-dev file): This file exists in the stable production branch and doesn't
 *   require special v5-whatsapp merge considerations
 */

```
 */

import apiClient from './client'

export interface CostBreakdown {
  hours: number
  employee_cost: number
  machine_cost: number
  material_cost: number
  misc_cost: number
  total_cost: number
  order_value: number
  profit: number
}

export interface DashboardJob {
  id: number
  name: string
  customer?: string
  priority: string
  status: string
  timer_status: string
  start_date: string | null
  end_date: string | null
  actual_start_at: string | null
  actual_end_at: string | null
  paused_seconds: number
  has_conflict: boolean
  conflict_reasons: string[]
  status_icon: string
  assigned_employees: { id: number; full_name: string }[]
  assigned_machines: { id: number; name: string }[]
  tentative_cost: number
  tentative_profit: number
  tentative_breakdown: CostBreakdown
  actual_cost: number | null
  actual_profit: number | null
  actual_breakdown: CostBreakdown | null
  order_value: number | null
}

export interface DashboardData {
  total_active_jobs: number
  available_machines: number
  available_employees: number
  jobs_by_status: Record<string, number>
  upcoming_jobs_this_week: {
    id: number
    name: string
    start_date: string
    end_date: string
    priority: string
    status: string
  }[]
  jobs: DashboardJob[]
}

export const dashboardApi = {
  get: () => apiClient.get<DashboardData>('/dashboard/').then(r => r.data),
}
