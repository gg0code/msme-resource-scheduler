/**
 * FILE PURPOSE
 * This file provides the API client interface for fetching job data specifically formatted
 * for the Production Timeline (Gantt chart) visualization. It was introduced in v4-dev as
 * part of the core scheduling frontend and sits in the API layer between React components
 * and the FastAPI backend. This module handles the transformation of raw job data into a
 * Gantt-optimized format that includes visual status indicators, conflict detection, and
 * timeline-specific metadata required for the Production Timeline page.
 * 
 * WHAT THIS FILE DOES - step by step
 * 1. Imports the shared apiClient instance from './client' for authenticated HTTP requests
 * 2. Defines the GanttJob TypeScript interface that exactly matches the backend schema
 * 3. Specifies all job properties needed for Gantt chart rendering including dates, assignments, and conflicts
 * 4. Exports the fetchGanttData() async function that calls the backend /api/gantt/ endpoint
 * 5. Returns a Promise containing an array of GanttJob objects ready for timeline visualization
 * 
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 * 
 * Name         : GanttJob
 * Type         : TypeScript interface
 * Purpose      : Defines the exact shape of job data optimized for Gantt chart display. This interface
 *                includes visual status indicators, conflict detection flags, and financial estimates
 *                that are pre-computed by the backend for efficient frontend rendering.
 * Parameters   : N/A (interface definition)
 * Returns      : N/A (interface definition)
 * Calls        : N/A (interface definition)
 * DB/API       : N/A (interface definition)
 * Side effects : N/A (interface definition)
 * 
 * Name         : fetchGanttData
 * Type         : async function
 * Purpose      : Fetches all jobs from the backend formatted specifically for Gantt chart display.
 *                This function retrieves tenant-scoped job data with pre-computed conflict detection,
 *                resource assignments, and visual status indicators. The backend handles all business
 *                logic including conflict analysis and cost calculations.
 * Parameters   : None - uses current user's tenant context from JWT token in apiClient
 * Returns      : Promise<GanttJob[]> - Array of jobs with Gantt-specific formatting including
 *                start/end dates, assigned resources, conflict flags, and visual status indicators
 * Calls        : apiClient.get() from './client' which handles JWT authentication and tenant scoping
 * DB/API       : Makes GET request to /api/gantt/ endpoint on the FastAPI backend
 * Side effects : None - pure data fetching function with no mutations or side effects
 * 
 * WHO CALLS THIS FILE
 * - frontend/src/pages/ProductionTimeline.tsx (main Gantt chart page component)
 * - Any other components that need to display Gantt chart visualizations of job schedules
 * 
 * IMPORTS EXPLAINED
 * - apiClient from './client': The configured Axios instance that handles JWT token authentication,
 *   automatic token refresh, tenant scoping, and base URL configuration for all API calls.
 * 
 * INTERN NOTES
 * - Easiest thing to break: Modifying the GanttJob interface without updating the backend schema
 *   will cause runtime type mismatches and break the Production Timeline page rendering
 * - Non-obvious design decision: The status_icon field uses string literals instead of enums because
 *   it needs to match exactly with the backend's computed status logic and frontend icon mapping
 * - Most common mistake: Adding new fields to GanttJob without ensuring the backend /api/gantt/
 *   endpoint returns those fields, causing undefined values in the frontend components
 * - Design principle #1: This implements "Engine computes, AI only narrates" - all conflict detection,
 *   status computation, and cost calculations are done by backend logic, not frontend
 * - What to check if unexpected behavior: Verify the backend /api/gantt/ endpoint returns data
 *   matching the GanttJob interface, check network tab for API errors, and ensure JWT token is valid
 * - N/A for v5-whatsapp merging concerns as this file exists in v4-dev production branch
 */

import apiClient from './client'

export interface GanttJob {
  id: number
  name: string
  customer: string | null
  start_date: string | null
  end_date: string | null
  priority: string | null
  status: string | null
  timer_status: string | null
  assigned_employees: string[]
  assigned_machines: string[]
  has_conflict: boolean
  conflict_reasons: string[]
  /** 'ready' | 'conflict' | 'in_progress' | 'completed' | 'stopped' */
  status_icon: string
  tentative_cost: number | null
  tentative_profit: number | null
}

export async function fetchGanttData(): Promise<GanttJob[]> {
  const res = await apiClient.get<GanttJob[]>('/api/gantt/')
  return res.data
}
