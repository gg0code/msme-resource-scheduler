// src/data/aiTools.ts — V3.1
// 50 pre-built AI prompts organised by category
// Each tool fires as a chat message when clicked

export interface AITool {
  id: string
  icon: string
  label: string
  prompt: string
  category: string
}

export const AI_TOOL_CATEGORIES = [
  { id: 'reporting',   label: 'Reporting',   icon: '📊' },
  { id: 'scheduling',  label: 'Scheduling',  icon: '📅' },
  { id: 'people',      label: 'People',      icon: '👷' },
  { id: 'cost',        label: 'Cost',        icon: '💰' },
  { id: 'alerts',      label: 'Alerts',      icon: '⚠️' },
  { id: 'whatif',      label: 'What-If',     icon: '🔮' },
  { id: 'machines',    label: 'Machines',    icon: '⚙️' },
  { id: 'jobs',        label: 'Jobs',        icon: '📋' },
]

export const AI_TOOLS: AITool[] = [
  // ── Reporting ──────────────────────────────────────────────────────────────
  {
    id: 'r1', category: 'reporting', icon: '💰',
    label: 'Revenue this month',
    prompt: 'What is my total revenue and order book value for this month?',
  },
  {
    id: 'r2', category: 'reporting', icon: '📈',
    label: 'Profit summary',
    prompt: 'Give me a profit margin summary across all active jobs this month.',
  },
  {
    id: 'r3', category: 'reporting', icon: '🪙',
    label: 'Raw material cost',
    prompt: 'What is my total raw material cost this month? Show breakdown by job.',
  },
  {
    id: 'r4', category: 'reporting', icon: '📦',
    label: 'Order book value',
    prompt: 'What is my total order book value including all scheduled and draft jobs?',
  },
  {
    id: 'r5', category: 'reporting', icon: '📊',
    label: 'Daily shop summary',
    prompt: "Give me today's complete shop floor summary.",
  },
  {
    id: 'r6', category: 'reporting', icon: '🏆',
    label: 'Most profitable job',
    prompt: 'Which job has the highest profit margin this month?',
  },
  {
    id: 'r7', category: 'reporting', icon: '📉',
    label: 'Least profitable job',
    prompt: 'Which job has the lowest profit margin or is likely running at a loss?',
  },

  // ── Scheduling ─────────────────────────────────────────────────────────────
  {
    id: 's1', category: 'scheduling', icon: '⚠️',
    label: 'Scheduling conflicts',
    prompt: 'Are there any scheduling conflicts or resource clashes next week?',
  },
  {
    id: 's2', category: 'scheduling', icon: '📅',
    label: 'Busiest day this month',
    prompt: 'Which day this month has the most jobs running simultaneously?',
  },
  {
    id: 's3', category: 'scheduling', icon: '🔄',
    label: 'Reschedule suggestions',
    prompt: 'Which delayed jobs should I reschedule and what dates do you suggest?',
  },
  {
    id: 's4', category: 'scheduling', icon: '🚦',
    label: 'Jobs not started',
    prompt: 'Which jobs are still in Draft or Scheduled status but should have started by now?',
  },
  {
    id: 's5', category: 'scheduling', icon: '📌',
    label: 'Critical jobs status',
    prompt: 'What is the status of all Critical priority jobs?',
  },
  {
    id: 's6', category: 'scheduling', icon: '🗓️',
    label: 'Jobs due this week',
    prompt: 'Which jobs are due to complete this week?',
  },
  {
    id: 's7', category: 'scheduling', icon: '⏰',
    label: 'Overdue jobs',
    prompt: 'Which jobs are past their end date and still not completed?',
  },

  // ── People ─────────────────────────────────────────────────────────────────
  {
    id: 'p1', category: 'people', icon: '🙋',
    label: 'Who is free today',
    prompt: 'Which employees are available and not assigned to any job today?',
  },
  {
    id: 'p2', category: 'people', icon: '🏆',
    label: 'Top performer',
    prompt: 'Who is the top performing employee this month based on job assignments?',
  },
  {
    id: 'p3', category: 'people', icon: '⏰',
    label: 'Overtime this month',
    prompt: 'Which employees have the most hours assigned this month?',
  },
  {
    id: 'p4', category: 'people', icon: '👥',
    label: 'Most utilised employee',
    prompt: 'Which employee is most utilised this week?',
  },
  {
    id: 'p5', category: 'people', icon: '😴',
    label: 'Idle employees',
    prompt: 'Which employees have no job assignments this week?',
  },
  {
    id: 'p6', category: 'people', icon: '🔧',
    label: 'Employee by skill',
    prompt: 'List employees grouped by their primary skill or department.',
  },
  {
    id: 'p7', category: 'people', icon: '📆',
    label: 'Availability tomorrow',
    prompt: 'Who is available tomorrow and what is their current assignment status?',
  },

  // ── Cost ───────────────────────────────────────────────────────────────────
  {
    id: 'c1', category: 'cost', icon: '💰',
    label: 'Most expensive job',
    prompt: 'Which job has the highest total cost including employee, machine and raw material costs?',
  },
  {
    id: 'c2', category: 'cost', icon: '🪙',
    label: 'RM cost breakdown',
    prompt: 'Show me raw material cost breakdown for all jobs this month.',
  },
  {
    id: 'c3', category: 'cost', icon: '👷',
    label: 'Employee cost this month',
    prompt: 'What is my total employee cost across all jobs this month?',
  },
  {
    id: 'c4', category: 'cost', icon: '⚙️',
    label: 'Machine cost this month',
    prompt: 'What is my total machine running cost across all jobs this month?',
  },
  {
    id: 'c5', category: 'cost', icon: '📊',
    label: 'Cost vs revenue',
    prompt: 'Compare total cost versus total revenue for this month. Am I profitable?',
  },
  {
    id: 'c6', category: 'cost', icon: '🏭',
    label: 'Misc cost summary',
    prompt: 'What are the miscellaneous costs across all jobs this month?',
  },
  {
    id: 'c7', category: 'cost', icon: '💹',
    label: 'Best margin job',
    prompt: 'Which job has the best profit margin percentage?',
  },

  // ── Alerts ─────────────────────────────────────────────────────────────────
  {
    id: 'a1', category: 'alerts', icon: '🔴',
    label: 'All alerts today',
    prompt: 'What are all the alerts and issues I should know about today?',
  },
  {
    id: 'a2', category: 'alerts', icon: '⚠️',
    label: 'Delayed jobs',
    prompt: 'Which jobs are delayed or at risk of missing their deadline?',
  },
  {
    id: 'a3', category: 'alerts', icon: '🚨',
    label: 'Critical + not started',
    prompt: 'Are there any Critical priority jobs that have not been started yet?',
  },
  {
    id: 'a4', category: 'alerts', icon: '📉',
    label: 'Low profit jobs',
    prompt: 'Which jobs have a profit margin below 10%? These need attention.',
  },
  {
    id: 'a5', category: 'alerts', icon: '🔧',
    label: 'Unassigned jobs',
    prompt: 'Which jobs have no employees or machines assigned yet?',
  },
  {
    id: 'a6', category: 'alerts', icon: '📦',
    label: 'No raw materials',
    prompt: 'Which jobs have no raw materials added yet?',
  },
  {
    id: 'a7', category: 'alerts', icon: '⏳',
    label: 'Ending in 3 days',
    prompt: 'Which jobs are ending in the next 3 days?',
  },

  // ── What-If ────────────────────────────────────────────────────────────────
  {
    id: 'w1', category: 'whatif', icon: '🔮',
    label: 'If top employee is absent',
    prompt: 'If my most utilised employee is absent tomorrow, which jobs will be affected?',
  },
  {
    id: 'w2', category: 'whatif', icon: '⚙️',
    label: 'If key machine breaks',
    prompt: 'If the most used machine breaks down today, which jobs will be impacted?',
  },
  {
    id: 'w3', category: 'whatif', icon: '📅',
    label: 'New urgent job feasibility',
    prompt: 'If I take a new urgent job starting tomorrow for 7 days, do I have enough resources?',
  },
  {
    id: 'w4', category: 'whatif', icon: '💰',
    label: 'Revenue if all jobs complete',
    prompt: 'What would my total revenue be if all current jobs complete on time?',
  },
  {
    id: 'w5', category: 'whatif', icon: '🔄',
    label: 'Swap job priorities',
    prompt: 'What happens to the schedule if I change all High priority jobs to Critical?',
  },
  {
    id: 'w6', category: 'whatif', icon: '📦',
    label: 'RM cost increase impact',
    prompt: 'If raw material costs increase by 15%, which jobs would become unprofitable?',
  },

  // ── Machines ───────────────────────────────────────────────────────────────
  {
    id: 'm1', category: 'machines', icon: '✅',
    label: 'Free machines today',
    prompt: 'Which machines are free and available today?',
  },
  {
    id: 'm2', category: 'machines', icon: '🔄',
    label: 'Busy machines today',
    prompt: 'Which machines are currently busy and which jobs are they on?',
  },
  {
    id: 'm3', category: 'machines', icon: '📊',
    label: 'Machine utilisation',
    prompt: 'What is the utilisation rate of each machine this month?',
  },
  {
    id: 'm4', category: 'machines', icon: '😴',
    label: 'Idle machines',
    prompt: 'Which machines have been idle for more than 3 days?',
  },
  {
    id: 'm5', category: 'machines', icon: '💰',
    label: 'Machine cost analysis',
    prompt: 'Which machine has generated the most cost this month?',
  },

  // ── Jobs ───────────────────────────────────────────────────────────────────
  {
    id: 'j1', category: 'jobs', icon: '▶️',
    label: 'Running jobs',
    prompt: 'Which jobs are currently running? Show status and progress.',
  },
  {
    id: 'j2', category: 'jobs', icon: '📋',
    label: 'All jobs summary',
    prompt: 'Give me a summary of all jobs grouped by status.',
  },
  {
    id: 'j3', category: 'jobs', icon: '🏭',
    label: 'Jobs by customer',
    prompt: 'List all jobs grouped by customer name.',
  },
  {
    id: 'j4', category: 'jobs', icon: '💰',
    label: 'Highest value job',
    prompt: 'Which job has the highest order value?',
  },
  {
    id: 'j5', category: 'jobs', icon: '📅',
    label: 'Jobs starting next week',
    prompt: 'Which jobs are scheduled to start next week?',
  },
  {
    id: 'j6', category: 'jobs', icon: '✅',
    label: 'Completed this month',
    prompt: 'Which jobs were completed this month and what was the total value?',
  },
]
