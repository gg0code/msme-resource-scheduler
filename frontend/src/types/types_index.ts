// Shared TypeScript interfaces — single source of truth for all pages

export interface Skill {
  id: number
  name: string
  category: string
  is_premium: boolean
  description: string | null
}

export interface EmployeeSkill {
  id: number
  skill_id: number
  skill_level: string
}

export interface Employee {
  id: number
  full_name: string
  department: string | null
  employment_type: string
  base_availability_pct: number
  status: string
  contact_number: string | null
  join_date: string | null
  hourly_rate: number | null
  overtime_rate: number | null
  skills: EmployeeSkill[]
}

export interface MachineSkillReq {
  id: number
  skill_id: number
  min_skill_level: string
  employees_required: number
}

export interface Machine {
  id: number
  name: string
  machine_type: string | null
  base_availability_pct: number
  location_bay: string | null
  status: string
  hourly_rate: number | null
  skill_requirements: MachineSkillReq[]
}

export interface SkillReq {
  id?: number
  skill_id: number
  min_skill_level: string
  employees_required: number
}

export interface RawMaterial {
  name: string
  quantity: number
  unit: string
  unit_cost: number
}

export interface AssignedEmployee {
  id: number
  full_name: string
  department: string | null
}

export interface AssignedMachine {
  id: number
  name: string
  machine_type: string | null
}

export interface Job {
  id: number
  name: string
  customer: string | null
  description: string | null
  start_date: string
  end_date: string
  estimated_hours_per_day: number
  tentative_profit: number | null
  order_value: number | null
  misc_cost: number | null
  priority: string
  status: string
  notes: string | null
  skill_requirements: (SkillReq & { id: number })[]
  raw_materials: RawMaterial[]
  assigned_employees: AssignedEmployee[]
  assigned_machines: AssignedMachine[]
  timer_status: 'idle' | 'running' | 'paused' | 'ended'
  actual_start_at: string | null
  actual_end_at: string | null
  paused_seconds: number
  timer_log: { event: string; timestamp: string }[]
  created_at: string | null
}

export interface DashboardData {
  total_active_jobs: number
  available_machines: number
  available_employees: number
  jobs_by_status: Record<string, number>
  upcoming_jobs_this_week: {
    id: number; name: string; start_date: string; end_date: string
    priority: string; status: string; tentative_profit: number | null
  }[]
}

export interface AvailabilityOverride {
  id: number
  employee_id: number | null
  machine_id: number | null
  date_from: string
  date_to: string
  availability_pct: number
  reason: string | null
}

export interface ImportResult {
  rows_imported: number
  rows_failed: number
  errors: string[]
}
