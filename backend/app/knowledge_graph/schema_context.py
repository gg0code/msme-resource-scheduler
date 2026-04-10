# schema_context.py - Version 1.0
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Describes the ZetaOps database schema in plain English so the AI (Llama 3.3)
# can generate accurate answers grounded in real field names and relationships.
#
# WITHOUT THIS FILE: AI guesses field names, gets them wrong, hallucinates
#   relationships. "Who is free today?" might query a non-existent field.
#
# WITH THIS FILE: AI knows Employee.full_name, EmployeeSkill -> Skill.name,
#   Job.status valid values, etc. Answers become grounded and accurate.
#
# WHO CALLS THIS FILE
#   app/knowledge_graph/context_builder.py - imports SCHEMA_CONTEXT constant
#
# WHAT THIS FILE CALLS
#   Nothing. Pure constant — no imports, no DB calls, no side effects.
#
# KEY DESIGN DECISIONS
#   1. INDUSTRY-AGNOSTIC — describes DB structure only, not industry norms.
#      Industry-specific knowledge lives in rag_data/_templates/{industry}/.
#      This file is the same for a printing tenant and a fabrication tenant.
#   2. PLAIN ENGLISH, NOT SQL — Llama reads English better than DDL.
#      We say "full_name (text, never null)" not "VARCHAR(150) NOT NULL".
#   3. VALID VALUES ARE EXPLICIT — for every status/enum field we list
#      every allowed value so the AI never invents one.
#   4. RELATIONSHIPS ARE NAMED — "Employee.skills is a list of EmployeeSkill
#      rows, each linking to one Skill" is clearer than FK notation.
#   5. TENANT ISOLATION IS HIGHLIGHTED — the AI must know that every query
#      MUST filter by tenant_id. Cross-tenant data leaks are a security bug.
#   6. UPDATE THIS FILE IN THE SAME COMMIT as any migration that adds a
#      table, column, or changes a valid value. Never let schema drift.
#      Current migration head: 023 (v5.16 source + worker_type fields)

# ---------------------------------------------------------------------------
# SCHEMA_CONTEXT — injected into every AI system prompt via context_builder.py
# ---------------------------------------------------------------------------
# This string is appended to the system prompt so the AI knows the exact
# database structure before answering any question.
# Keep it under ~2000 tokens to leave room for conversation history.

SCHEMA_CONTEXT: str = """
--- ZETAOPS DATABASE SCHEMA (read before answering any data question) ---

TENANT ISOLATION RULE (mandatory, no exceptions):
Every table below has a tenant_id column. Every query you suggest or explain
MUST filter by tenant_id. Never return or reference data from another tenant.
Cross-tenant data access is a security vulnerability, not a style issue.

--- TABLE: tenants ---
One row per factory / business using ZetaOps.
Fields:
  id            (integer, primary key)
  name          (text) — business name e.g. "Sharma Printers"
  plan          (text) — subscription plan: 'free' | 'starter' | 'pro'
  industry_type (text) — vertical: 'printing' | 'manufacturing' |
                          'fabrication' | 'field_service'
  created_at    (datetime, UTC)

--- TABLE: users ---
One row per person who can log into ZetaOps web app.
Fields:
  id            (integer, primary key)
  tenant_id     (integer, FK to tenants.id)
  email         (text, unique)
  role          (text) — 'owner' | 'manager' | 'operator'
  industry_type (text) — copied from tenant at registration
  is_active     (boolean)

--- TABLE: employees ---
Workers at the factory. Can be entered manually (Day 1 table),
captured via WhatsApp conversation, or synced from ERP (v7.0).
Fields:
  id                    (integer, primary key)
  tenant_id             (integer, FK to tenants.id — always filter by this)
  full_name             (text, never null) — e.g. "Suresh Patel"
                         NOTE: the field is full_name, NOT name
  status                (text) — 'Active' | 'Inactive'
                         NOTE: capital A and I — always check exact case
  employment_type       (text) — 'Full-time' | 'Part-time' | 'Contract'
  worker_type           (text, v5.16+) — 'permanent' | 'contractor'
  source                (text, v5.16+) — how record was created:
                         'manual' | 'whatsapp' | 'erp_sync'
  base_availability_pct (float) — default 100.0 (percentage 0-100)
  hourly_rate           (float, nullable) — INR per hour
  overtime_rate         (float, nullable) — INR per hour
  department            (text, nullable)
  contact_number        (text, nullable)
  join_date             (date, nullable)
  created_at            (datetime, UTC)

SKILLS: Employee does NOT have a skill column directly.
Skills are stored in the employee_skills table (see below).
To find "who has skill X": join employees -> employee_skills -> skills.

--- TABLE: employee_skills ---
Many-to-many link between employees and skills.
One row per employee-skill pair.
Fields:
  id          (integer, primary key)
  employee_id (integer, FK to employees.id)
  tenant_id   (integer, FK to tenants.id)
  skill_id    (integer, FK to skills.id)
  skill_level (text) — 'Generic' | 'Beginner' | 'Intermediate' | 'Expert'

To find an employee's skills:
  SELECT s.name FROM skills s
  JOIN employee_skills es ON es.skill_id = s.id
  WHERE es.employee_id = <employee_id>
  AND es.tenant_id = <tenant_id>

--- TABLE: skills ---
Master list of skills for a tenant.
Fields:
  id          (integer, primary key)
  tenant_id   (integer, FK to tenants.id)
  name        (text) — e.g. "Flexo Printing", "Die Cutting", "Welding"
  category    (text) — e.g. "production", "quality", "maintenance"
  is_active   (boolean)

--- TABLE: machines ---
Equipment / work centers in the factory.
Fields:
  id                    (integer, primary key)
  tenant_id             (integer, FK to tenants.id)
  name                  (text) — e.g. "Heidelberg Press 1", "CNC Lathe 2"
  machine_type          (text) — e.g. "offset_press", "cnc_lathe", "welding"
  status                (text) — 'Operational' | 'Maintenance' | 'Breakdown'
  base_availability_pct (float) — default 100.0
  source                (text, v5.16+) — 'manual' | 'whatsapp' | 'erp_sync'
  hourly_rate           (float, nullable) — INR per hour
  created_at            (datetime, UTC)

--- TABLE: jobs ---
Production orders / work orders. The central entity.
Fields:
  id                  (integer, primary key)
  tenant_id           (integer, FK to tenants.id)
  name                (text) — e.g. "Corporate Brochure - Infosys"
  status              (text) — 'pending' | 'in_progress' | 'completed' |
                       'cancelled' | 'on_hold'
                       NOTE: all lowercase, no capitals
  priority            (text) — 'low' | 'medium' | 'high' | 'critical'
  start_date          (date, nullable)
  end_date            (date, nullable)
  original_start_date (date, nullable) — set when job is rescheduled
  original_end_date   (date, nullable) — set when job is rescheduled
  is_locked           (boolean) — True means scheduler cannot move this job
  order_value         (float, nullable) — INR, customer invoice amount
  misc_cost           (float, nullable) — INR, other costs
  customer_name       (text, nullable)
  notes               (text, nullable)
  timer_status        (text) — 'not_started' | 'running' | 'paused' | 'stopped'
  created_at          (datetime, UTC)

CONFLICT DETECTION: A job has a conflict when the count of its rows in
schedule_entries is less than the number of days between start_date and
end_date. There is NO has_conflict column on the jobs table — never use it.

--- TABLE: job_assignments ---
Links a job to the employee(s) and machine(s) working on it.
One row per job-resource link.
Fields:
  id              (integer, primary key)
  job_id          (integer, FK to jobs.id)
  tenant_id       (integer, FK to tenants.id)
  employee_id     (integer, FK to employees.id, nullable)
  machine_id      (integer, FK to machines.id, nullable)
  allocation_pct  (float) — percentage of resource time allocated (0-100)

Note: either employee_id or machine_id is set, not both (usually).

--- TABLE: schedule_entries ---
One row per scheduled working day per job (created by the scheduler engine).
Fields:
  id                    (integer, primary key)
  job_id                (integer, FK to jobs.id)
  tenant_id             (integer, FK to tenants.id)
  scheduled_date        (date) — the day this entry covers
  assigned_machine_ids  (array of integers) — machine IDs working this day
  assigned_helper_ids   (array of integers) — employee IDs working this day

--- TABLE: phone_tenant_map ---
Maps a WhatsApp phone number to a ZetaOps tenant and user.
Fields:
  id            (integer, primary key)
  phone_number  (text, E.164 format) — e.g. "+919876543210"
  tenant_id     (integer, FK to tenants.id)
  user_id       (integer, FK to users.id)
  phone_role    (text) — role of this phone:
                 'owner' | 'manager' | 'operator'
  is_active     (boolean)
  consent_given (boolean)
  display_name  (text, nullable) — human label e.g. "Factory Manager"
  industry_type (text, nullable) — copied from tenant

--- TABLE: employee_leaves (unavailability) ---
Records planned or actual absences for employees.
Fields:
  id          (integer, primary key)
  tenant_id   (integer, FK to tenants.id)
  employee_id (integer, FK to employees.id)
  start_date  (date)
  end_date    (date)
  reason      (text, nullable)

--- TABLE: machine_downtimes (unavailability) ---
Records planned maintenance or breakdowns for machines.
Fields:
  id          (integer, primary key)
  tenant_id   (integer, FK to tenants.id)
  machine_id  (integer, FK to machines.id)
  start_date  (date)
  end_date    (date)
  reason      (text, nullable)

--- KEY RELATIONSHIPS SUMMARY ---
Tenant -> Users (one-to-many)
Tenant -> Employees (one-to-many)
Tenant -> Machines (one-to-many)
Tenant -> Jobs (one-to-many)
Employee -> EmployeeSkills -> Skills (many-to-many via employee_skills)
Job -> JobAssignments -> Employee/Machine (many-to-many via job_assignments)
Job -> ScheduleEntries (one-to-many, one per working day)
Employee -> EmployeeLeaves (one-to-many)
Machine -> MachineDowntimes (one-to-many)
PhoneTenantMap -> Tenant (many-to-one)

--- END OF SCHEMA ---
"""
