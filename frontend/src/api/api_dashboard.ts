/**
```typescript
/**
 * FILE PURPOSE
 * This file defines the TypeScript types and API client functions for fetching dashboard data
 * in the ZetaOps Copilot web application. It was introduced in v4-dev and serves as the frontend's
 * interface to the /api/dashboard/ backend endpoint, providing rich job information with cost
 * breakdowns, conflict detection, and summary statistics for the main dashboard screen.
 * 
 * WHAT THIS FILE DOES — step by step
 * 1. Defines the CostBreakdown interface for detailed financial calculations per job
 * 2. Defines the DashboardJob interface representing a job with all dashboard-relevant fields
 * 3. Defines the DashboardData interface for the complete dashboard API response structure
 * 4. Exports a dashboardApi object with a single get() method to fetch dashboard data
 * 5. The get() method makes an HTTP GET request and returns a typed Promise of DashboardData
 * 
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 * 
 * Name         : CostBreakdown
 * Type         : TypeScript interface
 * Purpose      : Defines the structure for cost and profit calculations on jobs. Contains both
 *                individual cost components (employee, machine, material, misc) and derived
 *                totals (total_cost, profit). Used for both tentative (scheduled) and actual
 *                (completed) financial breakdowns.
 * Parameters   : N/A (interface)
 * Returns      : N/A (interface)
 * Calls        : N/A (interface)
 * DB/API       : N/A (interface)
 * Side effects : N/A (interface)
 * 
 * Name         : DashboardJob
 * Type         : TypeScript interface
 * Purpose      : Represents a job as displayed on the dashboard with all necessary fields for
 *                rendering job cards, status indicators, conflict warnings, and financial summaries.
 *                Includes both scheduled data (tentative costs) and actual execution data when
 *                jobs are completed. Contains resource assignments and timing information.
 * Parameters   : N/A (interface)
 * Returns      : N/A (interface)
 * Calls        : N/A (interface)
 * DB/API       : N/A (interface)
 * Side effects : N/A (interface)
 * 
 * Name         : DashboardData
 * Type         : TypeScript interface
 * Purpose      : Defines the complete response structure from the /api/dashboard/ endpoint.
 *                Contains high-level metrics (total jobs, available resources), job status
 *                summaries, upcoming job previews, and the full array of DashboardJob objects
 *                for detailed rendering on the dashboard.
 * Parameters   : N/A (interface)
 * Returns      : N/A (interface)
 * Calls        : N/A (interface)
 * DB/API       : N/A (interface)
 * Side effects : N/A (interface)
 * 
 * Name         : dashboardApi.get
 * Type         : function
 * Purpose      : Fetches complete dashboard data from the backend. Makes an authenticated HTTP
 *                request to /api/dashboard/ and returns the parsed response. This is the single
 *                entry point for dashboard data and includes all jobs, metrics, and summaries
 *                needed to render the main dashboard screen.
 * Parameters   : None
 * Returns      : Promise<DashboardData> - A promise that resolves to the complete dashboard data
 *                structure including job arrays, metrics, and financial breakdowns
 * Calls        : apiClient.get() from ./client.ts
 * DB/API       : HTTP GET to /api/dashboard/ (handled by backend dashboard router)
 * Side effects : None (read-only operation)
 * 
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Dashboard.tsx (main dashboard page component)
 * - frontend/src/components/DashboardStats.tsx (dashboard metrics display)
 * - frontend/src/components/JobList.tsx (job listing with dashboard data)
 * - Any other dashboard-related components that need job summaries and metrics
 * 
 * IMPORTS EXPLAINED
 * - apiClient from './client': The configured Axios instance with authentication, base URL,
 *   and tenant scoping that handles all HTTP requests to the ZetaOps backend API.
 * 
 * INTERN NOTES
 * - Easiest thing to break: Changing field names in interfaces without updating the backend
 *   response structure - this will cause runtime TypeScript errors and dashboard display issues
 * - Non-obvious design decision: CostBreakdown appears twice in DashboardJob (tentative vs actual)
 *   because jobs show estimated costs during planning and real costs after completion
 * - Most common mistake: Forgetting that nullable fields like actual_cost and actual_breakdown
 *   are only populated for completed jobs - always check for null before using these values
 * - Design principle #1: This file only handles data fetching and typing - it contains no business
 *   logic, the backend engine computes all costs, conflicts, and scheduling data
 * - What to check if behaving unexpectedly: Verify the backend /api/dashboard/ endpoint response
 *   matches these interfaces exactly, especially conflict_reasons array and cost breakdown fields
 * - Not applicable to v5-whatsapp: This file exists in both branches and handles standard web
 *   dashboard functionality separate from WhatsApp features
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
  get: () => apiClient.get<DashboardData>('/api/dashboard/').then(r => r.data),
}
