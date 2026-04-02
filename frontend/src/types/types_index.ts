/**
 * frontend/src/types/types_index.ts
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * The single source of truth for all shared domain TypeScript interfaces in the
 * ZetaOps Copilot frontend. Every interface that is used across more than one file
 * lives here. Industry config types live separately in src/config/industries/types.ts
 * and should never be duplicated here. Introduced in v4.0.9 as part of the TypeScript
 * strict mode enforcement. All API response shapes, domain models, and utility types
 * are defined and exported from this file.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Skill, EmployeeSkill — competency tags and their employee assignments.
 * 2. Employee — full employee record with skills array.
 * 3. MachineSkillReq, Machine — machine with skill requirements.
 * 4. SkillReq, RawMaterial, AssignedEmployee, AssignedMachine — job sub-objects.
 * 5. TentativeBreakdown — cost breakdown shape (tentative and actual).
 * 6. JobConflict — conflict detail from availability check.
 * 7. StartMode, TimerStatus, JobStatus — named union types for job state fields.
 * 8. Job — the full job record with all 30+ fields matching the backend Job model.
 * 9. DashboardJob, DashboardData — dashboard-specific job shape (subset of Job).
 * 10. AvailabilityOverride — availability override record.
 * 11. ImportResult — response shape from bulk CSV/XLSX import endpoints.
 * 12. JobStep — individual production step within a job.
 * 13. PlanLimits — free plan usage counts and limits.
 *
 * RULES (enforced by comments in source)
 * - All optional fields use T | null (never undefined) — matches FastAPI JSON output.
 * - Arrays that may be missing use optional ?: [] pattern (e.g. assigned_employees?).
 * - No implicit any — every field explicitly typed.
 *
 * WHO CALLS THIS FILE
 * - frontend/src/api/api_employees.ts — Employee, ImportResult
 * - frontend/src/api/api_machines.ts  — Machine, ImportResult
 * - frontend/src/api/api_skills.ts    — Skill, ImportResult
 * - frontend/src/api/api_jobs.ts      — Job
 * - frontend/src/api/api_dashboard.ts — DashboardJob, DashboardData (local defs)
 * - frontend/src/api/api_timer.ts     — (uses local CostBreakdown, mirrors TentativeBreakdown)
 * - frontend/src/pages/Jobs.tsx       — Job, RawMaterial, SkillReq, JobStep, all sub-types
 * - frontend/src/pages/Employees.tsx  — Employee, EmployeeSkill
 * - frontend/src/pages/Machines.tsx   — Machine, MachineSkillReq
 * - frontend/src/pages/Dashboard.tsx  — DashboardJob, DashboardData
 * - frontend/src/components/common/CsvImport.tsx — ImportResult
 *
 * INTERN NOTES
 * - Never create a new types file in a random location. Add new shared types here.
 *   Industry config types go in src/config/industries/types.ts only.
 * - The Job interface has 30+ fields — it mirrors the backend Job SQLAlchemy model
 *   exactly. If the backend adds a column, add it here too before using it in any
 *   frontend file.
 * - DashboardJob is a SEPARATE interface from Job — it has fewer fields and some
 *   optional ones (assigned_employees?, assigned_machines?). Do not merge them.
 *   The dashboard API returns DashboardJob; the jobs API returns Job.
 * - StartMode, TimerStatus, JobStatus are named union types. Use these instead of
 *   raw string in any component that reads these fields — tsc will catch typos.
 * - TentativeBreakdown and the CostBreakdown in api_timer.ts are structurally
 *   identical but declared separately. This is intentional — they come from
 *   different endpoints. Do not merge them to avoid import coupling.
 * - Design Principle 11: this file is the most imported file in the project after
 *   client.ts. Any error here causes cascading tsc failures across the entire app.
 *   Always run tsc --noEmit after any change here.
 */
// src/types/types_index.ts
// ─────────────────────────────────────────────────────────────────────────────
// Single source of truth for all shared domain interfaces.
// Industry config types live in src/config/industries/types.ts — do not
// duplicate them here. Import from there if needed.
//
// Rules:
//   - All optional fields use T | null (never undefined) — matches FastAPI JSON
//   - Arrays that may be missing from API use optional ?: [] pattern
//   - No implicit any — every field explicitly typed
// ─────────────────────────────────────────────────────────────────────────────

// ── Skills ───────────────────────────────────────────────────────────────────

export interface Skill {
  id:          number
  name:        string
  category:    string
  is_premium:  boolean
  is_active:   boolean
  description: string | null
}

export interface EmployeeSkill {
  id:          number
  skill_id:    number
  skill_level: string
}

// ── Employees ─────────────────────────────────────────────────────────────────

export interface Employee {
  id:                    number
  full_name:             string
  department:            string | null
  employment_type:       string
  base_availability_pct: number
  status:                string
  contact_number:        string | null
  join_date:             string | null
  hourly_rate:           number | null
  overtime_rate:         number | null
  skills:                EmployeeSkill[]
}

// ── Machines ──────────────────────────────────────────────────────────────────

export interface MachineSkillReq {
  id:                number
  skill_id:          number
  min_skill_level:   string
  employees_required: number
}

export interface Machine {
  id:                    number
  name:                  string
  machine_type:          string | null
  base_availability_pct: number
  location_bay:          string | null
  status:                string
  hourly_rate:           number | null
  skill_requirements:    MachineSkillReq[]
}

// ── Jobs ──────────────────────────────────────────────────────────────────────

export interface SkillReq {
  id?:                number
  skill_id:           number
  min_skill_level:    string
  employees_required: number
}

export interface RawMaterial {
  name:      string
  quantity:  number
  unit:      string
  unit_cost: number
}

export interface AssignedEmployee {
  id:         number
  full_name:  string
  department: string | null
}

export interface AssignedMachine {
  id:           number
  name:         string
  machine_type: string | null
}

export interface TentativeBreakdown {
  employee_cost: number | null
  machine_cost:  number | null
  material_cost: number | null
  misc_cost:     number | null
  total_cost:    number | null
  hours:         number | null
}

export interface JobConflict {
  resource_type: string
  resource_name: string
  reason:        string
}

export type StartMode = 'right_away' | 'pick_a_date' | 'flexible'
export type TimerStatus = 'idle' | 'running' | 'paused' | 'ended'
export type JobStatus =
  | 'Draft'
  | 'Pending Assignment'
  | 'Scheduled'
  | 'In Progress'
  | 'Completed'
  | 'Cancelled'
  | 'Stopped'

export interface Job {
  id:                       number
  name:                     string
  customer:                 string | null
  description:              string | null
  start_date:               string
  end_date:                 string
  earliest_date:            string | null
  latest_date:              string | null
  estimated_hours_per_day:  number
  tentative_profit:         number | null
  order_value:              number | null
  misc_cost:                number | null
  priority:                 string
  status:                   JobStatus
  start_mode:               StartMode
  is_locked:                boolean
  has_conflict:             boolean
  notes:                    string | null
  job_type:                 string | null
  quantity:                 number | null
  invoice_number:           string | null
  payment_status:           string | null
  skill_requirements:       (SkillReq & { id: number })[]
  raw_materials:            RawMaterial[]
  assigned_employees:       AssignedEmployee[]
  assigned_machines:        AssignedMachine[]
  timer_status:             TimerStatus
  timer_log:                { event: string; timestamp: string }[]
  actual_start_at:          string | null
  actual_end_at:            string | null
  actual_hours:             number | null
  paused_seconds:           number
  has_steps:                boolean
  conflicts:                JobConflict[]
  tentative_breakdown:      TentativeBreakdown | null
  actual_breakdown:         TentativeBreakdown | null
  created_at:               string | null
  status_icon:              string
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export interface DashboardJob {
  id:                  number
  name:                string
  customer:            string | null
  priority:            string
  status:              JobStatus
  status_icon:         string
  start_date:          string
  end_date:            string
  has_conflict:        boolean
  timer_status:        TimerStatus
  paused_seconds:      number
  actual_start_at:     string | null
  actual_end_at:       string | null
  tentative_profit:    number | null
  order_value:         number | null
  tentative_breakdown: TentativeBreakdown | null
  actual_breakdown:    TentativeBreakdown | null
  // Optional — may be missing from dashboard API response,
  // fetched on demand via GET /api/jobs/{id} on card expand
  assigned_employees?: AssignedEmployee[]
  assigned_machines?:  AssignedMachine[]
}

export interface DashboardData {
  total_active_jobs:   number
  available_machines:  number
  available_employees: number
  jobs_by_status:      Record<string, number>
  jobs:                DashboardJob[]
}

// ── Availability ──────────────────────────────────────────────────────────────

export interface AvailabilityOverride {
  id:               number
  employee_id:      number | null
  machine_id:       number | null
  date_from:        string
  date_to:          string
  availability_pct: number
  reason:           string | null
}

// ── Import ────────────────────────────────────────────────────────────────────

export interface ImportResult {
  rows_imported: number
  rows_failed:   number
  errors:        string[]
}

// ── Job Steps ─────────────────────────────────────────────────────────────────

export interface JobStep {
  id:               number
  job_id:           number
  sequence_no:      number
  name:             string
  step_type:        string
  duration_minutes: number
  status:           'locked' | 'ready' | 'in_progress' | 'complete'
}

// ── Plan Limits ───────────────────────────────────────────────────────────────

export interface PlanLimits {
  employees_used:  number
  employees_limit: number | null
  machines_used:   number
  machines_limit:  number | null
  jobs_used:       number
  jobs_limit:      number | null
  plan:            string
}
