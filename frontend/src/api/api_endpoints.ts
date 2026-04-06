// frontend/src/api/api_endpoints.ts - Version 1.0
// Branch: both
//
// FILE PURPOSE
// Single source of truth for ALL backend API paths used in this frontend.
// No file anywhere in the project should hardcode an API path string.
// All paths must be imported from here.
//
// WHAT THIS FILE DOES
// 1. Defines every static and parameterised backend route as a typed constant
// 2. Exports a DEV-mode health check that fires on app load in development
//    to immediately surface any dead routes in the browser console
//
// RULES
// - Never hardcode '/api/...' anywhere else in the project
// - Static paths: string constants
// - Parameterised paths: arrow functions returning strings
// - Auth paths have no /api/ prefix (auth router registered without prefix)
// - WhatsApp paths use /api/v1/whatsapp/ (router self-prefixes)
//
// WHO CALLS THIS FILE
// - Every file in src/ that makes an apiClient or fetch call
//
// INTERN NOTES
// - If a backend route changes, update it here ONLY - TypeScript propagates
// - Health check only runs in DEV (import.meta.env.DEV) - never in production
// - HEALTH_CHECK_ROUTES contains only GET routes safe to call without side effects

import apiClient from './client'

// =============================================================================
// AUTH  (no /api/ prefix - auth router registered bare)
// =============================================================================
export const AUTH = {
  login:    '/auth/login',
  register: '/auth/register',
  refresh:  '/auth/refresh',
  logout:   '/auth/logout',
  me:       '/auth/me',
} as const

// =============================================================================
// DASHBOARD
// =============================================================================
export const DASHBOARD = {
  root:       '/api/dashboard/',
  planLimits: '/api/dashboard/plan-limits',
} as const

// =============================================================================
// JOBS
// =============================================================================
export const JOBS = {
  list:               '/api/jobs/',
  create:             '/api/jobs/',
  detail:             (id: number) => `/api/jobs/${id}`,
  update:             (id: number) => `/api/jobs/${id}`,
  delete:             (id: number) => `/api/jobs/${id}`,
  timer:              (id: number) => `/api/jobs/${id}/timer`,
  scanTokens:         (id: number) => `/api/jobs/${id}/scan-tokens`,
  steps:              (jobId: number) => `/api/jobs/${jobId}/steps`,
  step:               (jobId: number, stepId: number) => `/api/jobs/${jobId}/steps/${stepId}`,
  stepStatus:         (jobId: number, stepId: number) => `/api/jobs/${jobId}/steps/${stepId}/status`,
  stepResources:      (jobId: number, stepId: number) => `/api/jobs/${jobId}/steps/${stepId}/resources`,
  stepResource:       (jobId: number, stepId: number, resourceId: number) => `/api/jobs/${jobId}/steps/${stepId}/resources/${resourceId}`,
  useJobResources:    (jobId: number, stepId: number) => `/api/jobs/${jobId}/steps/${stepId}/use-job-resources`,
  resourceAvailability: (jobId: number) => `/api/jobs/${jobId}/resource-availability`,
  materialEstimate:   (jobId: number) => `/api/jobs/${jobId}/material-estimate`,
  scheduleSuggestions:(jobId: number) => `/api/jobs/${jobId}/schedule-suggestions`,
} as const

// =============================================================================
// TIMER
// =============================================================================
export const TIMER = {
  start:   (jobId: number) => `/api/timer/${jobId}/start`,
  pause:   (jobId: number) => `/api/timer/${jobId}/pause`,
  resume:  (jobId: number) => `/api/timer/${jobId}/resume`,
  stop:    (jobId: number) => `/api/timer/${jobId}/stop`,
  end:     (jobId: number) => `/api/timer/${jobId}/end`,
  summary: (jobId: number) => `/api/timer/${jobId}/summary`,
  outage:  (jobId: number) => `/api/timer/${jobId}/outage`,
} as const

// =============================================================================
// EMPLOYEES
// =============================================================================
export const EMPLOYEES = {
  list:   '/api/employees/',
  create: '/api/employees/',
  detail: (id: number) => `/api/employees/${id}`,
  update: (id: number) => `/api/employees/${id}`,
  delete: (id: number) => `/api/employees/${id}`,
} as const

// =============================================================================
// MACHINES
// =============================================================================
export const MACHINES = {
  list:   '/api/machines/',
  create: '/api/machines/',
  detail: (id: number) => `/api/machines/${id}`,
  update: (id: number) => `/api/machines/${id}`,
  delete: (id: number) => `/api/machines/${id}`,
} as const

// =============================================================================
// SKILLS
// =============================================================================
export const SKILLS = {
  list:   '/api/skills/',
  create: '/api/skills/',
  update: (id: number) => `/api/skills/${id}`,
  delete: (id: number) => `/api/skills/${id}`,
} as const

// =============================================================================
// ASSIGNMENTS
// =============================================================================
export const ASSIGNMENTS = {
  create:          '/api/assignments/',
  check:           (jobId: number) => `/api/assignments/check/${jobId}`,
  byEmployee:      (employeeId: number) => `/api/assignments/employee/${employeeId}`,
  byMachine:       (machineId: number) => `/api/assignments/machine/${machineId}`,
  delete:          (id: number) => `/api/assignments/${id}`,
  allocation:      (jobId: number) => `/api/assignments/${jobId}/allocation`,
} as const

// =============================================================================
// AVAILABILITY (overrides)
// =============================================================================
export const AVAILABILITY = {
  list:   '/api/availability/',
  create: '/api/availability/',
  update: (id: number) => `/api/availability/${id}`,
  delete: (id: number) => `/api/availability/${id}`,
} as const

// =============================================================================
// UNAVAILABILITY (leaves + downtimes)
// =============================================================================
export const UNAVAILABILITY = {
  employeeLeaves:      (employeeId: number) => `/api/unavailability/employees/${employeeId}/leaves`,
  employeeLeave:       (employeeId: number, leaveId: number) => `/api/unavailability/employees/${employeeId}/leaves/${leaveId}`,
  machineDowntimes:    (machineId: number) => `/api/unavailability/machines/${machineId}/downtimes`,
  machineDowntime:     (machineId: number, downtimeId: number) => `/api/unavailability/machines/${machineId}/downtimes/${downtimeId}`,
} as const

// =============================================================================
// IMPORT / CSV
// =============================================================================
export const IMPORT = {
  employees:        '/api/import/employees',
  machines:         '/api/import/machines',
  skills:           '/api/import/skills',
  template:         (resource: string) => `/api/import/template/${resource}`,
} as const

// =============================================================================
// GANTT
// =============================================================================
export const GANTT = {
  list: '/api/gantt/',
} as const

// =============================================================================
// SCHEDULER
// =============================================================================
export const SCHEDULER = {
  run:     '/api/scheduler/run',
  entries: '/api/scheduler/entries',
} as const

// =============================================================================
// SCAN
// =============================================================================
export const SCAN = {
  verify:  (token: string) => `/api/scan/verify?token=${encodeURIComponent(token)}`,
  execute: '/api/scan/execute',
} as const

// =============================================================================
// AI COPILOT
// =============================================================================
export const AI = {
  greeting: '/api/ai/greeting',
  usage:    '/api/ai/usage',
  chat:     '/api/ai/chat',
} as const

// =============================================================================
// FEATURES
// =============================================================================
export const FEATURES = {
  flags: '/api/features',
} as const

// =============================================================================
// WHATSAPP  (router self-prefixes with /api/v1/whatsapp)
// =============================================================================
export const WHATSAPP = {
  linkPhone:          '/api/v1/whatsapp/link-phone',
  linkedPhones:       '/api/v1/whatsapp/linked-phones',
  deactivatePhone:    (id: number) => `/api/v1/whatsapp/linked-phones/${id}/deactivate`,
  simulate:           '/api/v1/whatsapp/simulate',
  simulateVoice:      '/api/v1/whatsapp/simulate-voice',
  triggerDevAlerts:   '/api/v1/whatsapp/trigger-dev-alerts',
  webhook:            '/api/v1/whatsapp/webhook',
} as const

// =============================================================================
// DEV-MODE HEALTH CHECK
// Fires once on app load in development only.
// Hits every safe GET endpoint and logs any that return non-2xx.
// Never runs in production (import.meta.env.DEV is false after vite build).
// =============================================================================
const HEALTH_CHECK_ROUTES: string[] = [
  DASHBOARD.root,
  DASHBOARD.planLimits,
  JOBS.list,
  EMPLOYEES.list,
  MACHINES.list,
  SKILLS.list,
  AVAILABILITY.list,
  GANTT.list,
  FEATURES.flags,
  AI.greeting,
  AI.usage,
  SCHEDULER.entries,
]

export function runDevHealthCheck(): void {
  if (!import.meta.env.DEV) return

  console.groupCollapsed('[ZetaOps] API Health Check - checking all routes...')

  Promise.allSettled(
    HEALTH_CHECK_ROUTES.map(path =>
      apiClient.get(path)
        .then(() => ({ path, ok: true }))
        .catch((err: unknown) => {
          const status = (err as { response?: { status?: number } })?.response?.status
          return { path, ok: false, status }
        })
    )
  ).then(results => {
    let allOk = true
    results.forEach(r => {
      if (r.status === 'fulfilled') {
        const { path, ok, status } = r.value as { path: string; ok: boolean; status?: number }
        if (ok) {
          console.log(`%c OK  ${path}`, 'color: #16a34a')
        } else {
          allOk = false
          console.error(`%c DEAD ${path} - HTTP ${status ?? 'no response'}`, 'color: #dc2626')
        }
      }
    })
    if (allOk) {
      console.log('%c All routes healthy', 'color: #16a34a; font-weight: bold')
    } else {
      console.warn('%c Some routes are dead - check backend registration in main.py', 'color: #d97706; font-weight: bold')
    }
    console.groupEnd()
  })
}
