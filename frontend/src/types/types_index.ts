// src/types/types_index.ts
// -----------------------------------------------------------------------------
// Single source of truth for all shared domain interfaces.
// Industry config types live in src/config/industries/types.ts - do not
// duplicate them here. Import from there if needed.
//
// Rules:
//   - All optional fields use T | null (never undefined) - matches FastAPI JSON
//   - Arrays that may be missing from API use optional ?: [] pattern
//   - No implicit any - every field explicitly typed
// -----------------------------------------------------------------------------

// -- Team & Roles (v6.3.3) ----------------------------------------------------
// Mirrors backend app/schemas/team.py shapes. The Role string is
// loose (string, not the Role union from auth/useAuth.ts) so the API
// can return roles the client doesn't yet know about without breaking.

// v6.3.5 status pill enum - mirrors backend WhatsAppStatus literal.
export type WhatsAppStatus = 'active' | 'invited' | 'disconnected' | 'none'

// v6.3.5 invite channel - mirrors backend InviteChannel literal. Optional on
// the request so v6.3.3 callers (passing only email_or_phone) keep working.
export type InviteChannel = 'whatsapp' | 'desktop'

export interface TeamMember {
  id:               number
  // v6.3.5: synthesised invite-*@invite.zetaops.com emails surface as null
  // so the UI can render the "(unnamed)" empty state.
  email:            string | null
  phone_e164:       string | null
  role:             string
  is_active:        boolean
  is_top_tier:      boolean
  created_via:      string
  // v6.3.5 additions.
  whatsapp_status:  WhatsAppStatus
  name:             string | null
}

export interface InviteRequest {
  email_or_phone: string
  role:           string
  // v6.3.5 additions - optional for back-compat with the v6.3.3 inline form.
  channel?:       InviteChannel
  consent_given?: boolean
  name?:          string | null
}

export interface InviteResponse {
  member:        TeamMember
  temp_password: string | null
}

export interface RoleChangeRequest {
  role: string
}

// -- Skills -------------------------------------------------------------------

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

// -- Employees -----------------------------------------------------------------

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

// -- Machines ------------------------------------------------------------------

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

// -- Jobs ----------------------------------------------------------------------

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

// -- Dashboard -----------------------------------------------------------------

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
  // Optional - may be missing from dashboard API response,
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

// -- Availability --------------------------------------------------------------

export interface AvailabilityOverride {
  id:               number
  employee_id:      number | null
  machine_id:       number | null
  date_from:        string
  date_to:          string
  availability_pct: number
  reason:           string | null
}

// -- Import --------------------------------------------------------------------

export interface ImportResult {
  rows_imported: number
  rows_failed:   number
  errors:        string[]
}

// -- Job Steps -----------------------------------------------------------------

export interface JobStep {
  id:               number
  job_id:           number
  sequence_no:      number
  name:             string
  step_type:        string
  duration_minutes: number
  status:           'locked' | 'ready' | 'in_progress' | 'complete'
}

// -- Plan Limits ---------------------------------------------------------------

export interface PlanLimits {
  employees_used:  number
  employees_limit: number | null
  machines_used:   number
  machines_limit:  number | null
  jobs_used:       number
  jobs_limit:      number | null
  plan:            string
}
