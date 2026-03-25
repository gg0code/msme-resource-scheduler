// src/data/aiTools.ts — v4.0.8
// 50 pre-built AI prompts — industry-aware via IndustryLabels
// Call getAITools(labels) to get prompts in the right terminology

import type { IndustryLabels } from '../config/industries/types'

export interface AITool {
  id:       string
  icon:     string
  label:    string
  prompt:   string
  category: string
}

export const AI_TOOL_CATEGORIES = [
  { id: 'reporting',  label: 'Reporting',  icon: '📊' },
  { id: 'scheduling', label: 'Scheduling', icon: '📅' },
  { id: 'people',     label: 'People',     icon: '👷' },
  { id: 'cost',       label: 'Cost',       icon: '💰' },
  { id: 'alerts',     label: 'Alerts',     icon: '⚠️' },
  { id: 'whatif',     label: 'What-If',    icon: '🔮' },
  { id: 'machines',   label: 'Machines',   icon: '⚙️' },
  { id: 'jobs',       label: 'Jobs',       icon: '📋' },
]

/**
 * Returns 50 pre-built AI tool prompts using industry-specific terminology.
 * Pass labels from useLabels() to get the right terms per industry.
 *
 * Example:
 *   Chemical  → "batch orders", "operators", "reactors", "batch inputs"
 *   Printing  → "jobs", "operators", "machines", "raw materials"
 *   Field Svc → "service jobs", "technicians", "vehicles/tools", "parts"
 */
export function getAITools(labels: IndustryLabels): AITool[] {
  const j  = labels.jobs.toLowerCase()         // jobs / batch orders / service jobs
  const jo = labels.job.toLowerCase()          // job / batch order / service job
  const e  = labels.employees.toLowerCase()    // operators / technicians / fabricators
  const eo = labels.employee.toLowerCase()     // operator / technician / fabricator
  const m  = labels.machines.toLowerCase()     // machines / reactors / work centers
  const mo = labels.machine.toLowerCase()      // machine / reactor / work center
  const mat= labels.materials.toLowerCase()    // raw materials / batch inputs / BOM items

  return [
    // ── Reporting ────────────────────────────────────────────────────────────
    {
      id: 'r1', category: 'reporting', icon: '💰',
      label: 'Revenue this month',
      prompt: `What is my total revenue and order book value for this month?`,
    },
    {
      id: 'r2', category: 'reporting', icon: '📈',
      label: 'Profit summary',
      prompt: `Give me a profit margin summary across all active ${j} this month.`,
    },
    {
      id: 'r3', category: 'reporting', icon: '🪙',
      label: `${labels.materials} cost`,
      prompt: `What is my total ${mat} cost this month? Show breakdown by ${jo}.`,
    },
    {
      id: 'r4', category: 'reporting', icon: '📦',
      label: 'Order book value',
      prompt: `What is my total order book value including all scheduled and draft ${j}?`,
    },
    {
      id: 'r5', category: 'reporting', icon: '📊',
      label: 'Daily summary',
      prompt: `Give me today's complete ${jo} summary — running ${j}, available ${m}, alerts.`,
    },
    {
      id: 'r6', category: 'reporting', icon: '🏆',
      label: `Most profitable ${jo}`,
      prompt: `Which ${jo} has the highest profit margin this month?`,
    },
    {
      id: 'r7', category: 'reporting', icon: '📉',
      label: `Least profitable ${jo}`,
      prompt: `Which ${jo} has the lowest profit margin or is likely running at a loss?`,
    },

    // ── Scheduling ───────────────────────────────────────────────────────────
    {
      id: 's1', category: 'scheduling', icon: '⚠️',
      label: 'Scheduling conflicts',
      prompt: `Are there any scheduling conflicts or resource clashes next week?`,
    },
    {
      id: 's2', category: 'scheduling', icon: '📅',
      label: 'Busiest day this month',
      prompt: `Which day this month has the most ${j} running simultaneously?`,
    },
    {
      id: 's3', category: 'scheduling', icon: '🔄',
      label: 'Reschedule suggestions',
      prompt: `Which delayed ${j} should I reschedule and what dates do you suggest?`,
    },
    {
      id: 's4', category: 'scheduling', icon: '🚦',
      label: `${labels.jobs} not started`,
      prompt: `Which ${j} are still in Draft or Scheduled status but should have started by now?`,
    },
    {
      id: 's5', category: 'scheduling', icon: '📌',
      label: `Critical ${j} status`,
      prompt: `What is the status of all Critical priority ${j}?`,
    },
    {
      id: 's6', category: 'scheduling', icon: '🗓️',
      label: `${labels.jobs} due this week`,
      prompt: `Which ${j} are due to complete this week?`,
    },
    {
      id: 's7', category: 'scheduling', icon: '⏰',
      label: `Overdue ${j}`,
      prompt: `Which ${j} are past their end date and still not completed?`,
    },

    // ── People ───────────────────────────────────────────────────────────────
    {
      id: 'p1', category: 'people', icon: '🙋',
      label: `Free ${e} today`,
      prompt: `Which ${e} are available and not assigned to any ${jo} today?`,
    },
    {
      id: 'p2', category: 'people', icon: '🏆',
      label: 'Top performer',
      prompt: `Who is the top performing ${eo} this month based on ${jo} assignments?`,
    },
    {
      id: 'p3', category: 'people', icon: '⏰',
      label: 'Overtime this month',
      prompt: `Which ${e} have the most hours assigned this month?`,
    },
    {
      id: 'p4', category: 'people', icon: '👥',
      label: `Most utilised ${eo}`,
      prompt: `Which ${eo} is most utilised this week?`,
    },
    {
      id: 'p5', category: 'people', icon: '😴',
      label: `Idle ${e}`,
      prompt: `Which ${e} have no ${jo} assignments this week?`,
    },
    {
      id: 'p6', category: 'people', icon: '🔧',
      label: `${labels.employees} by skill`,
      prompt: `List ${e} grouped by their primary skill or department.`,
    },
    {
      id: 'p7', category: 'people', icon: '📆',
      label: 'Availability tomorrow',
      prompt: `Which ${e} are available tomorrow and what is their current assignment status?`,
    },

    // ── Cost ─────────────────────────────────────────────────────────────────
    {
      id: 'c1', category: 'cost', icon: '💰',
      label: `Most expensive ${jo}`,
      prompt: `Which ${jo} has the highest total cost including ${eo}, ${mo} and ${mat} costs?`,
    },
    {
      id: 'c2', category: 'cost', icon: '🪙',
      label: `${labels.materials} breakdown`,
      prompt: `Show me ${mat} cost breakdown for all ${j} this month.`,
    },
    {
      id: 'c3', category: 'cost', icon: '👷',
      label: `${labels.employee} cost this month`,
      prompt: `What is my total ${eo} cost across all ${j} this month?`,
    },
    {
      id: 'c4', category: 'cost', icon: '⚙️',
      label: `${labels.machine} cost this month`,
      prompt: `What is my total ${mo} running cost across all ${j} this month?`,
    },
    {
      id: 'c5', category: 'cost', icon: '📊',
      label: 'Cost vs revenue',
      prompt: `Compare total cost versus total revenue for this month. Am I profitable?`,
    },
    {
      id: 'c6', category: 'cost', icon: '🏭',
      label: 'Misc cost summary',
      prompt: `What are the miscellaneous costs across all ${j} this month?`,
    },
    {
      id: 'c7', category: 'cost', icon: '💹',
      label: `Best margin ${jo}`,
      prompt: `Which ${jo} has the best profit margin percentage?`,
    },

    // ── Alerts ───────────────────────────────────────────────────────────────
    {
      id: 'a1', category: 'alerts', icon: '🔴',
      label: 'All alerts today',
      prompt: `What are all the alerts and issues I should know about today?`,
    },
    {
      id: 'a2', category: 'alerts', icon: '⚠️',
      label: `Delayed ${j}`,
      prompt: `Which ${j} are delayed or at risk of missing their deadline?`,
    },
    {
      id: 'a3', category: 'alerts', icon: '🚨',
      label: `Critical + not started`,
      prompt: `Are there any Critical priority ${j} that have not been started yet?`,
    },
    {
      id: 'a4', category: 'alerts', icon: '📉',
      label: `Low profit ${j}`,
      prompt: `Which ${j} have a profit margin below 10%? These need attention.`,
    },
    {
      id: 'a5', category: 'alerts', icon: '🔧',
      label: `Unassigned ${j}`,
      prompt: `Which ${j} have no ${e} or ${m} assigned yet?`,
    },
    {
      id: 'a6', category: 'alerts', icon: '📦',
      label: `No ${mat}`,
      prompt: `Which ${j} have no ${mat} added yet?`,
    },
    {
      id: 'a7', category: 'alerts', icon: '⏳',
      label: `Ending in 3 days`,
      prompt: `Which ${j} are ending in the next 3 days?`,
    },

    // ── What-If ──────────────────────────────────────────────────────────────
    {
      id: 'w1', category: 'whatif', icon: '🔮',
      label: `If top ${eo} is absent`,
      prompt: `If my most utilised ${eo} is absent tomorrow, which ${j} will be affected?`,
    },
    {
      id: 'w2', category: 'whatif', icon: '⚙️',
      label: `If key ${mo} breaks`,
      prompt: `If the most used ${mo} breaks down today, which ${j} will be impacted?`,
    },
    {
      id: 'w3', category: 'whatif', icon: '📅',
      label: `New urgent ${jo} feasibility`,
      prompt: `If I take a new urgent ${jo} starting tomorrow for 7 days, do I have enough resources?`,
    },
    {
      id: 'w4', category: 'whatif', icon: '💰',
      label: `Revenue if all ${j} complete`,
      prompt: `What would my total revenue be if all current ${j} complete on time?`,
    },
    {
      id: 'w5', category: 'whatif', icon: '🔄',
      label: 'Swap priorities',
      prompt: `What happens to the schedule if I change all High priority ${j} to Critical?`,
    },
    {
      id: 'w6', category: 'whatif', icon: '📦',
      label: `${labels.materials} cost increase`,
      prompt: `If ${mat} costs increase by 15%, which ${j} would become unprofitable?`,
    },

    // ── Machines ─────────────────────────────────────────────────────────────
    {
      id: 'm1', category: 'machines', icon: '✅',
      label: `Free ${m} today`,
      prompt: `Which ${m} are free and available today?`,
    },
    {
      id: 'm2', category: 'machines', icon: '🔄',
      label: `Busy ${m} today`,
      prompt: `Which ${m} are currently busy and which ${j} are they on?`,
    },
    {
      id: 'm3', category: 'machines', icon: '📊',
      label: `${labels.machine} utilisation`,
      prompt: `What is the utilisation rate of each ${mo} this month?`,
    },
    {
      id: 'm4', category: 'machines', icon: '😴',
      label: `Idle ${m}`,
      prompt: `Which ${m} have been idle for more than 3 days?`,
    },
    {
      id: 'm5', category: 'machines', icon: '💰',
      label: `${labels.machine} cost analysis`,
      prompt: `Which ${mo} has generated the most cost this month?`,
    },

    // ── Jobs ─────────────────────────────────────────────────────────────────
    {
      id: 'j1', category: 'jobs', icon: '▶️',
      label: `Running ${j}`,
      prompt: `Which ${j} are currently running? Show status and progress.`,
    },
    {
      id: 'j2', category: 'jobs', icon: '📋',
      label: `All ${j} summary`,
      prompt: `Give me a summary of all ${j} grouped by status.`,
    },
    {
      id: 'j3', category: 'jobs', icon: '🏭',
      label: `${labels.jobs} by customer`,
      prompt: `List all ${j} grouped by customer name.`,
    },
    {
      id: 'j4', category: 'jobs', icon: '💰',
      label: `Highest value ${jo}`,
      prompt: `Which ${jo} has the highest order value?`,
    },
    {
      id: 'j5', category: 'jobs', icon: '📅',
      label: `${labels.jobs} starting next week`,
      prompt: `Which ${j} are scheduled to start next week?`,
    },
    {
      id: 'j6', category: 'jobs', icon: '✅',
      label: `Completed this month`,
      prompt: `Which ${j} were completed this month and what was the total value?`,
    },
  ]
}

// Keep backward compat export for any code still importing AI_TOOLS directly
// Components should migrate to getAITools(labels)
export const AI_TOOLS = getAITools({
  job: 'job', jobs: 'Jobs',
  employee: 'employee', employees: 'Employees',
  machine: 'machine', machines: 'Machines',
  material: 'Raw Material', materials: 'Raw Materials',
  skill: 'Skill', skills: 'Skills',
  step: 'Step', steps: 'Steps',
  jobsPageTitle: 'Jobs', jobsPageSubtitle: 'Production job board',
  employeesPageTitle: 'Employees', machinesPageTitle: 'Machines',
  jobNamePlaceholder: '', jobTypePlaceholder: '',
  newJobButton: 'New Job',
  kpiJobs: 'Active Jobs', kpiOrderBook: 'Order Book', kpiProfit: 'Est. Profit',
})
