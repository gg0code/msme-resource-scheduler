/**
 * frontend/src/pages/Jobs.tsx — ~2500 lines
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * The main job management page — the most complex file in the entire frontend.
 * ~2500 lines handling the complete job lifecycle: create, edit, delete, assign
 * resources, manage steps, run scheduler, view resource availability, control
 * timers, print job cards, and receive AI Copilot answers. Every major v4 feature
 * surfaces here. Industry-aware labels throughout via useLabels().
 *
 * WHAT THIS FILE DOES — step by step (major sections)
 * 1. Data: fetches jobs, employees, machines, skills, plan limits, schedule entries.
 * 2. Job list: filterable by status, priority, customer. Each job card is expandable.
 * 3. Create/Edit wizard: multi-step form — basic info → raw materials → skill
 *    requirements → step management → resource assignment.
 * 4. Raw materials: JSON array with name/quantity/unit/unit_cost per item.
 *    Plan limit enforced (RawMaterialLimitHint).
 * 5. Step management: add/reorder/delete JobStep records for a job.
 * 6. Resource assignment: assign employees and machines, shows availability panel
 *    (ResourceAvailabilityResponse) with real-time free_pct and blocking jobs.
 * 7. Scheduler toolbar: triggers POST /api/scheduler/run, shows resolved/unresolved.
 * 8. Material estimate: calls GET /api/jobs/{id}/material-estimate, AI narrates result.
 * 9. Schedule suggestions: calls GET /api/jobs/{id}/schedule-suggestions.
 * 10. Timer controls: start/pause/resume/stop per job via timerApi.
 * 11. End job: opens EndJobModal for final cost confirmation.
 * 12. Print: opens /jobs/:jobId/print in new tab (QR card generation).
 * 13. Plan limits: LimitedButton + PlanLimitBanner for job count enforcement.
 *
 * KEY INTERNAL COMPONENTS (defined inline)
 * - JobWizard — multi-step create/edit modal (~800 lines)
 * - StepManager — step CRUD for a job
 * - ResourcePanel — assignment + availability display
 * - SchedulerResultPanel — shows run_scheduler() output
 * - MaterialEstimatePanel — shows material estimate with confidence score
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — registered as /jobs route (protected)
 *
 * INTERN NOTES
 * - This file is too large to understand all at once. Read it section by section.
 *   Each major section has a comment block starting with ── SectionName ──.
 * - The ['jobs'] query key is used by GettingStarted.tsx for onboarding detection.
 * - Design Principle 1: material estimates, schedule suggestions, and cost
 *   calculations all come from backend endpoints — never computed in this file.
 * - Design Principle 5: resource availability (amber = partial, red = unavailable)
 *   is different from scheduling conflicts (red in Gantt). Both surfaces exist here.
 * - If a job action (assign, step edit etc) seems to have no effect: check that
 *   the mutation's onSuccess is calling qc.invalidateQueries with the right key.
 
import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import {
  getResourceAvailability,
  employeeStatusColor,
  employeeStatusLabel,
  machineStatusLabel,
  type ResourceAvailabilityResponse,
} from '../api/api_resource_availability'
import { CoachMark } from '../components/onboarding'
import { useFeatureFlags } from '../context/FeatureFlags'
import {
  Plus, Pencil, Trash2, Loader2, AlertCircle, CalendarDays, IndianRupee,
  X, Check, Search, ChevronRight, ChevronLeft, ChevronDown, ChevronUp,
  Users, ClipboardCheck, AlertTriangle, UserCheck, Factory,
  Play, Pause, Square, RotateCcw, Clock, Package,
  Lock, Unlock, Zap, Tag, FolderOpen, ListTodo, CheckCircle2, Circle, Wrench,
} from 'lucide-react'
import { usePlanLimits, LimitedButton, PlanLimitBanner, RawMaterialLimitHint } from '../components/PlanLimitGuard'
import { useSchedulerContext } from '../scheduler/SchedulerContext'
import { useLabels } from '../context/IndustryContext'

// ── Types ──────────────────────────────────────────────
interface Skill    { id: number; name: string; is_premium: boolean }
interface Employee { id: number; full_name: string; department: string | null }
interface MachineSkillReq { skill_id: number; min_skill_level: string; employees_required: number }
interface Machine  { id: number; name: string; status: string; location_bay: string | null; skill_requirements: MachineSkillReq[] }
interface SkillReq { id?: number; skill_id: number; min_skill_level: string; employees_required: number }
interface RawMat   { name: string; quantity: number; unit: string; unit_cost: number }
interface AssignedEmployee { id: number; full_name: string; department: string | null; allocation_pct: number | null }
interface AssignedMachine  { id: number; name: string; machine_type: string | null; allocation_pct: number | null }
interface Job {
  id: number; name: string; customer: string | null
  start_date: string; end_date: string; estimated_hours_per_day: number
  tentative_profit: number | null; order_value: number | null; misc_cost: number | null
  priority: string; status: string
  notes: string | null; skill_requirements: (SkillReq & { id: number })[]
  raw_materials: RawMat[]
  assigned_employees: AssignedEmployee[]
  assigned_machines: AssignedMachine[]
  timer_status: 'idle' | 'running' | 'paused' | 'ended'
  actual_start_at: string | null; actual_end_at: string | null
  paused_seconds: number; timer_log: { event: string; timestamp: string }[]
  availability?: AvailResult | null
  // J1.1
  start_mode: 'right_away' | 'pick_a_date' | 'flexible'
  is_locked: boolean
  has_conflict: boolean
  earliest_date: string | null
  latest_date: string | null
  // J1.2
  delivery_date: string | null
  invoice_number: string | null
  invoice_date: string | null
  payment_status: string
  payment_amount: number | null
  payment_date: string | null
  actual_hours: number | null
  cost_overrun: { overrun_pct: number; actual_hours: number; estimated_hours: number } | null
  // v3.9.6
  job_type: string | null
  quantity: number | null
}
interface AvailResult {
  feasible: boolean; feasibility_score: number
  conflicts: { resource_name: string; reason: string; resource_type: string }[]
  available_employees: Record<string, number[]>
}
interface SkillReqInfo {
  id: number; skill_id: number; skill_name: string
  min_skill_level: string; employees_required: number
  available_employee_ids: number[]
}
interface MachineInfo {
  id: number; name: string; machine_type: string | null
  location_bay: string | null; hourly_rate: number | null
  available: boolean; busy_reason: string | null
  skill_requirements: { skill_id: number; skill_name: string; min_skill_level: string; employees_required: number }[]
}
interface EmpInfo {
  id: number; full_name: string; department: string | null
  employment_type: string; hourly_rate: number | null
  available: boolean; busy_reason: string | null
  skills: { skill_id: number; skill_name: string; skill_level: string }[]
}
interface CheckResult {
  job_id: number; feasible: boolean; feasibility_score: number
  conflicts: { resource_type: string; resource_name: string; reason: string }[]
  skill_requirements: SkillReqInfo[]
  machines: MachineInfo[]
  employees: EmpInfo[]
  currently_assigned_employee_ids: number[]
  currently_assigned_machine_ids: number[]
}

// ── Constants ──────────────────────────────────────────
const PRIORITIES  = ['Low','Medium','High','Critical']
const STATUSES    = ['Draft','Pending Assignment','Scheduled','In Progress','Completed','Cancelled']
const LEVELS      = ['Generic','Intermediate','Premium']
const UNITS       = ['pcs','kg','m','l','set','lot']
const START_MODES = [
  { value: 'right_away',  label: 'Right Away',  desc: 'Start today — date locked to today' },
  { value: 'pick_a_date', label: 'Pick a Date', desc: 'Choose start date — locked once set' },
  { value: 'flexible',    label: 'Flexible',    desc: 'Scheduler picks best slot within your range' },
] as const

const priorityColour: Record<string,string> = {
  Critical:'bg-red-100 text-red-700 border-red-200',
  High:'bg-orange-100 text-orange-700 border-orange-200',
  Medium:'bg-yellow-100 text-yellow-700 border-yellow-200',
  Low:'bg-gray-100 text-gray-600 border-gray-200',
}
const statusColour: Record<string,string> = {
  'Scheduled':'bg-green-100 text-green-700','Pending Assignment':'bg-blue-100 text-blue-700',
  'In Progress':'bg-purple-100 text-purple-700','Draft':'bg-gray-100 text-gray-600',
  'Completed':'bg-teal-100 text-teal-700','Cancelled':'bg-red-100 text-red-600',
}
const scoreColour = (s: number) =>
  s === 100 ? { bar:'bg-green-500', text:'text-green-700', bg:'bg-green-50', badge:'bg-green-500', label:'Feasible' }
  : s >= 60  ? { bar:'bg-orange-400', text:'text-orange-700', bg:'bg-orange-50', badge:'bg-orange-400', label:'Partial' }
  : { bar:'bg-red-500', text:'text-red-700', bg:'bg-red-50', badge:'bg-red-500', label:'Conflicts' }

const timerColour: Record<string,string> = {
  idle:'text-gray-400', running:'text-green-600', paused:'text-yellow-600', ended:'text-teal-600'
}

const emptyDetails = () => ({
  name:'', customer:'', notes:'', start_date:'', end_date:'',
  estimated_hours_per_day: 8, tentative_profit:'', order_value:'', misc_cost:'',
  priority:'Medium', status:'Draft',
  start_mode: 'pick_a_date' as const,
  earliest_date:'', latest_date:'',
  delivery_date:'',
  invoice_number:'', invoice_date:'', payment_status:'Unpaid', payment_amount:'', payment_date:'',
  job_type:'', quantity:'',
})
const emptyMat = (): RawMat => ({ name:'', quantity:1, unit:'pcs', unit_cost:0 })

// ── Job ID formatter ───────────────────────────────────
function jobDisplayId(job: Job, prefix?: string | null): string {
  return prefix ? `${prefix}-${job.id}` : `#${job.id}`
}


// ── Availability badge ─────────────────────────────────
function AvailBadge({ result, loading, status }: { result?: AvailResult | null; loading?: boolean; status?: string }) {
  const [showTip, setShowTip] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setShowTip(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])
  if (status === 'Completed') return (
    <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-teal-500 text-white">
      <Check size={10}/> Done
    </span>
  )
  if (status === 'Cancelled') return (
    <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-gray-400 text-white">Cancelled</span>
  )
  if (loading) return <span className="w-3 h-3 rounded-full bg-gray-300 animate-pulse inline-block"/>
  if (!result)  return null
  const c = scoreColour(result.feasibility_score)
  return (
    <div ref={ref} className="relative inline-block">
      <button onClick={() => setShowTip(t => !t)}
        className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold text-white ${c.badge} hover:opacity-80`}
        title="Feasibility shows whether assigned employees and machines are available for this job's dates. Click for details.">
        {result.feasibility_score}% {c.label}
      </button>
      {showTip && (
        <div className="absolute right-0 top-7 z-30 bg-white border border-gray-200 rounded-xl shadow-xl p-3 w-72">
          <div className={`${c.bg} rounded-lg px-3 py-2 mb-2`}>
            <div className="flex items-center justify-between">
              <span className={`text-xs font-bold ${c.text}`}>Availability: {c.label}</span>
              <span className={`text-sm font-black ${c.text}`}>{result.feasibility_score}%</span>
            </div>
            <div className="w-full bg-white/60 rounded-full h-1.5 mt-1">
              <div className={`${c.bar} h-1.5 rounded-full`} style={{ width:`${result.feasibility_score}%` }}/>
            </div>
          </div>
          {result.conflicts.length === 0
            ? <p className="text-xs text-green-600 flex items-center gap-1"><Check size={12}/>All requirements met</p>
            : <>
                <p className="text-xs font-semibold text-gray-600 mb-1">{result.conflicts.length} conflict(s):</p>
                {result.conflicts.slice(0,4).map((c,i) => (
                  <p key={i} className="text-xs text-red-600 mb-0.5">· <span className="font-medium">{c.resource_name}</span>: {c.reason}</p>
                ))}
                {result.conflicts.length > 4 && <p className="text-xs text-gray-400">+{result.conflicts.length-4} more</p>}
              </>
          }
        </div>
      )}
    </div>
  )
}

// ── Conflict badge ─────────────────────────────────────
function ConflictBadge({ reasons }: { reasons?: string[] }) {
  const [show, setShow] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setShow(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])
  return (
    <div ref={ref} className="relative inline-block">
      <button onClick={() => setShow(s => !s)}
        className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-red-100 text-red-700 text-xs font-bold border border-red-200 hover:bg-red-200">
        <AlertTriangle size={10}/> Conflict
      </button>
      {show && (
        <div className="absolute left-0 top-7 z-30 bg-white border border-red-200 rounded-xl shadow-xl p-3 w-64">
          <p className="text-xs font-semibold text-red-700 mb-1 flex items-center gap-1"><AlertTriangle size={11}/>Conflict Details</p>
          {reasons && reasons.length > 0
            ? reasons.map((r,i) => <p key={i} className="text-xs text-red-600 mb-0.5">· {r}</p>)
            : <p className="text-xs text-gray-500">Resource conflict detected — check assignments</p>
          }
          <p className="text-xs text-gray-400 mt-2 border-t pt-2">Resolve conflicts to enable Start</p>
        </div>
      )}
    </div>
  )
}

// ── Timeline progress bar ──────────────────────────────
function TimelineBar({ job }: { job: Job }) {
  if (!job.start_date || !job.end_date) return null
  if (['Completed','Cancelled'].includes(job.status)) return (
    <div className="mt-1.5 w-full bg-gray-100 rounded-full h-1">
      <div className="h-1 rounded-full bg-teal-400 w-full" />
    </div>
  )
  const today  = new Date(); today.setHours(0,0,0,0)
  const start  = new Date(job.start_date)
  const end    = new Date(job.end_date)
  const total  = end.getTime() - start.getTime()
  const elapsed = today.getTime() - start.getTime()
  const pct    = total > 0 ? Math.min(Math.max(elapsed / total * 100, 0), 100) : 0
  const daysLeft = Math.ceil((end.getTime() - today.getTime()) / 86400000)
  const isDelayed   = today > end
  const isAtRisk    = !isDelayed && daysLeft <= 3 && ['Draft','Scheduled','Pending Assignment'].includes(job.status)
  const notStarted  = today < start
  const barColor    = isDelayed ? 'bg-red-500' : isAtRisk ? 'bg-amber-500' : 'bg-blue-400'
  const label       = isDelayed  ? <span className="text-[10px] text-red-500 font-medium">Overdue</span>
                    : isAtRisk   ? <span className="text-[10px] text-amber-600 font-medium">{daysLeft}d left ⚠</span>
                    : notStarted ? <span className="text-[10px] text-gray-400">in {Math.abs(daysLeft)}d</span>
                    : null
  return (
    <div className="mt-1.5">
      <div className="w-full bg-gray-100 rounded-full h-1.5">
        <div className={`h-1.5 rounded-full ${barColor}`} style={{ width: `${notStarted ? 0 : pct}%` }} />
      </div>
      {label && <div className="mt-0.5">{label}</div>}
    </div>
  )
}

// ── Lock badge ─────────────────────────────────────────
function LockBadge({ locked }: { locked: boolean }) {
  if (locked) return (
    <span className="flex items-center gap-0.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded-full">
      <Lock size={9}/> Locked
    </span>
  )
  return (
    <span className="flex items-center gap-0.5 text-xs text-blue-600 bg-blue-50 border border-blue-100 px-1.5 py-0.5 rounded-full">
      <Unlock size={9}/> Flexible
    </span>
  )
}

// ── Timer display ──────────────────────────────────────
function TimerDisplay({ job }: { job: Job }) {
  const [elapsed, setElapsed] = useState('')
  useEffect(() => {
    if (job.timer_status !== 'running' || !job.actual_start_at) { setElapsed(''); return }
    const tick = () => {
      const start = new Date(job.actual_start_at!).getTime()
      const secs  = Math.floor((Date.now() - start) / 1000) - (job.paused_seconds || 0)
      const h = Math.floor(secs/3600), m = Math.floor((secs%3600)/60), s = secs%60
      setElapsed(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`)
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [job.timer_status, job.actual_start_at, job.paused_seconds])
  if (job.timer_status === 'idle') return null
  return (
    <div className={`flex items-center gap-1.5 text-xs font-mono font-semibold ${timerColour[job.timer_status]}`}>
      <Clock size={12}/>
      {job.timer_status === 'running' && elapsed ? elapsed
        : job.timer_status === 'paused' ? 'Paused'
        : job.timer_status === 'ended' && job.actual_start_at && job.actual_end_at
          ? (() => {
              const net = Math.floor((new Date(job.actual_end_at).getTime() - new Date(job.actual_start_at).getTime()) / 1000) - (job.paused_seconds||0)
              return `Done — ${Math.floor(net/3600)}h ${Math.floor((net%3600)/60)}m`
            })()
          : job.timer_status
      }
    </div>
  )
}

// ── Start Mode selector ────────────────────────────────
function StartModeSelector({
  value, onChange, startDate, onStartDateChange, earliestDate, onEarliestChange, latestDate, onLatestChange
}: {
  value: string; onChange: (v: string) => void
  startDate: string; onStartDateChange: (v: string) => void
  earliestDate: string; onEarliestChange: (v: string) => void
  latestDate: string; onLatestChange: (v: string) => void
}) {
  const today = new Date().toISOString().split('T')[0]
  return (
    <div className="space-y-3">
      <label className="block text-xs font-medium text-gray-600 mb-1">Start Mode</label>
      <div className="grid grid-cols-3 gap-2">
        {START_MODES.map(m => (
          <button key={m.value} type="button"
            onClick={() => {
              onChange(m.value)
              if (m.value === 'right_away') onStartDateChange(today)
            }}
            className={`flex flex-col items-start gap-1 p-3 rounded-xl border text-left transition-all ${
              value === m.value
                ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-300'
                : 'border-gray-200 hover:border-blue-200 hover:bg-gray-50'
            }`}>
            <span className={`text-xs font-semibold ${value === m.value ? 'text-blue-700' : 'text-gray-700'}`}>
              {m.label}
            </span>
            <span className="text-xs text-gray-400 leading-tight">{m.desc}</span>
          </button>
        ))}
      </div>
      {value === 'flexible' ? (
        <div className="grid grid-cols-2 gap-3 mt-2">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Earliest Start *</label>
            <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={earliestDate} onChange={e => onEarliestChange(e.target.value)} min={today}/>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Latest Start *</label>
            <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={latestDate} onChange={e => onLatestChange(e.target.value)} min={earliestDate || today}/>
          </div>
        </div>
      ) : (
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Start Date {value === 'right_away' ? '(locked to today)' : '*'}
          </label>
          <input type="date"
            className={`w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              value === 'right_away' ? 'bg-gray-50 text-gray-400 cursor-not-allowed' : ''
            }`}
            value={startDate} onChange={e => onStartDateChange(e.target.value)}
            readOnly={value === 'right_away'} min={value === 'right_away' ? today : undefined}/>
        </div>
      )}
    </div>
  )
}


// ── JobStepsPanel ─────────────────────────────────────────────────────────────
interface JobStep {
  id: number; job_id: number; sequence_no: number; name: string
  step_type: string; duration_minutes: number; status: string
  notes?: string; use_job_resources: boolean; started_at?: string
}

const STEP_TYPE_OPTS = ['setup','production','inspection','packaging','finishing']
const STATUS_ICON: Record<string, React.ReactNode> = {
  locked:      <Lock size={13} className="text-gray-400"/>,
  ready:       <Circle size={13} className="text-blue-500"/>,
  in_progress: <Play size={13} className="text-amber-500"/>,
  complete:    <CheckCircle2 size={13} className="text-green-500"/>,
}
const STATUS_COLOR: Record<string, string> = {
  locked:      'bg-gray-100 text-gray-500',
  ready:       'bg-blue-50 text-blue-600',
  in_progress: 'bg-amber-50 text-amber-700',
  complete:    'bg-green-50 text-green-700',
}

function JobStepsPanel({ jobId, jobStatus }: { jobId: number; jobStatus: string }) {
  const qc = useQueryClient()
  const { markDirty } = useSchedulerContext()
  const isJobDone = ['Completed','Cancelled','completed','cancelled'].includes(jobStatus)
  const [showAdd, setShowAdd] = useState(false)
  const [newStep, setNewStep] = useState({ name: '', step_type: 'production', duration_minutes: 60 })
  const [saving, setSaving] = useState(false)

  const { data: steps = [], isLoading } = useQuery<JobStep[]>({
    queryKey: ['steps', jobId],
    queryFn: () => apiClient.get(`/api/jobs/${jobId}/steps`).then(r => r.data),
  })

  const addStep = async () => {
    if (!newStep.name.trim()) return
    setSaving(true)
    try {
      await apiClient.post(`/api/jobs/${jobId}/steps`, newStep)
      qc.invalidateQueries({ queryKey: ['steps', jobId] })
      setNewStep({ name: '', step_type: 'production', duration_minutes: 60 })
      setShowAdd(false)
    } finally { setSaving(false) }
  }

  const updateStatus = async (stepId: number, status: string) => {
    await apiClient.patch(`/api/jobs/${jobId}/steps/${stepId}/status`, { status })
    qc.invalidateQueries({ queryKey: ['steps', jobId] })
    qc.invalidateQueries({ queryKey: ['jobs'] })
  }

  const deleteStep = async (stepId: number) => {
    await apiClient.delete(`/api/jobs/${jobId}/steps/${stepId}`)
    qc.invalidateQueries({ queryKey: ['steps', jobId] })
  }

  return (
    <div className="border-t border-blue-100 mt-2">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
          <ListTodo size={14} className="text-blue-500"/>
          Steps <span className="text-xs font-normal text-gray-400 ml-1">({steps.length})</span>
        </div>
        {!isJobDone && (
          <button onClick={() => setShowAdd(v => !v)}
            className="text-xs px-2.5 py-1 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 font-medium flex items-center gap-1">
            <Plus size={11}/> Add Step
          </button>
        )}
      </div>

      {/* Add step form */}
      {showAdd && (
        <div className="mx-4 mb-3 p-3 bg-gray-50 rounded-lg border border-gray-200 flex flex-wrap gap-2 items-end">
          <input value={newStep.name} onChange={e => setNewStep(s => ({ ...s, name: e.target.value }))}
            placeholder="Step name" maxLength={100}
            className="flex-1 min-w-[140px] text-xs border border-gray-300 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"/>
          <select value={newStep.step_type} onChange={e => setNewStep(s => ({ ...s, step_type: e.target.value }))}
            className="text-xs border border-gray-300 rounded-lg px-2 py-1.5 bg-white focus:outline-none">
            {STEP_TYPE_OPTS.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <div className="flex items-center gap-1">
            <input type="number" value={newStep.duration_minutes} min={5} max={999}
              onChange={e => setNewStep(s => ({ ...s, duration_minutes: +e.target.value }))}
              className="w-16 text-xs border border-gray-300 rounded-lg px-2 py-1.5 text-center focus:outline-none"/>
            <span className="text-xs text-gray-400">min</span>
          </div>
          <button onClick={addStep} disabled={saving || !newStep.name.trim()}
            className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium">
            {saving ? 'Adding...' : 'Add'}
          </button>
          <button onClick={() => setShowAdd(false)}
            className="text-xs px-2.5 py-1.5 bg-gray-200 text-gray-600 rounded-lg hover:bg-gray-300">
            Cancel
          </button>
        </div>
      )}

      {/* Steps list */}
      {isLoading ? (
        <p className="text-xs text-gray-400 px-4 pb-3">Loading steps...</p>
      ) : steps.length === 0 ? (
        <p className="text-xs text-gray-400 italic px-4 pb-3">
          No steps yet — add steps to track progress within this job.
        </p>
      ) : (
        <div className="px-4 pb-3 space-y-1.5">
          {steps.map((step, idx) => {
            const isLast = idx === steps.length - 1
            const dur = step.duration_minutes < 60
              ? `${step.duration_minutes}m`
              : `${Math.floor(step.duration_minutes/60)}h${step.duration_minutes%60 ? ' '+step.duration_minutes%60+'m' : ''}`
            return (
              <div key={step.id}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs ${step.status === 'locked' ? 'bg-gray-50 border-gray-100 opacity-60' : 'bg-white border-gray-200'}`}>
                <span className="w-5 text-gray-400 font-mono text-center">{step.sequence_no}</span>
                {STATUS_ICON[step.status]}
                <span className={`font-medium flex-1 truncate ${step.status === 'complete' ? 'line-through text-gray-400' : 'text-gray-700'}`}>
                  {step.name}
                </span>
                <span className="text-gray-400 shrink-0">{step.step_type}</span>
                <span className="text-gray-400 shrink-0">{dur}</span>
                <span className={`px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${STATUS_COLOR[step.status]}`}>
                  {step.status.replace('_',' ')}
                </span>
                {!isJobDone && step.status === 'ready' && (
                  <button onClick={() => updateStatus(step.id, 'in_progress')}
                    className="text-xs px-2 py-0.5 bg-amber-500 text-white rounded hover:bg-amber-600 shrink-0">
                    Start
                  </button>
                )}
                {!isJobDone && step.status === 'in_progress' && (
                  <button onClick={() => updateStatus(step.id, 'complete')}
                    className="text-xs px-2 py-0.5 bg-green-600 text-white rounded hover:bg-green-700 shrink-0">
                    Complete
                  </button>
                )}
                {!isJobDone && isLast && step.status !== 'in_progress' && step.status !== 'complete' && (
                  <button onClick={() => deleteStep(step.id)}
                    className="text-gray-300 hover:text-red-400 shrink-0 ml-1">
                    <X size={12}/>
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════
export default function Jobs() {
  const qc = useQueryClient()
  const { markDirty, checkAllLocked } = useSchedulerContext()
  const labels = useLabels()
  const flags = useFeatureFlags() 
  const navigate = useNavigate()
  const today = new Date().toISOString().split('T')[0]

  // Filters
  const [search, setSearch]               = useState('')
  const [filterStatus, setFilterStatus]   = useState('All')
  const [filterPriority, setFilterPriority] = useState('All')
  const [filterFrom, setFilterFrom]       = useState('')
  const [filterTo, setFilterTo]           = useState('')
  const [groupByCustomer, setGroupByCustomer] = useState(false)

  // Availability cache
  const [availCache, setAvailCache]       = useState<Record<number, AvailResult | null | 'loading'>>({})
  const [expandedRow, setExpandedRow]     = useState<number | null>(null)
  const [openMenu,    setOpenMenu]        = useState<number | null>(null)
  const [allocPct,    setAllocPct]        = useState<Record<string, number>>({})
  const [savingAlloc, setSavingAlloc]     = useState(false)
  // v3.9.4 — real-time resource availability per job, fetched on row expand
  const [resAvail,        setResAvail]        = useState<Record<number, ResourceAvailabilityResponse>>({})
  const [resAvailLoading, setResAvailLoading] = useState<Record<number, boolean>>({})

  // Wizard
  const [wizardOpen, setWizardOpen]       = useState(false)
  const [wizardStep, setWizardStep]       = useState(1)
  const [details, setDetails]             = useState(emptyDetails())
  const [skillReqs, setSkillReqs]         = useState<SkillReq[]>([])
  const [rawMats, setRawMats]             = useState<RawMat[]>([])
  const [selectedEmps, setSelectedEmps]   = useState<number[]>([])
  const [selectedMachines, setSelectedMachines] = useState<number[]>([])
  const [wizardCheck, setWizardCheck]     = useState<AvailResult | null>(null)
  const [wizardChecking, setWizardChecking] = useState(false)

  // Edit
  const [editJob, setEditJob]             = useState<Job | null>(null)
  const [editForm, setEditForm]           = useState(emptyDetails())
  const [editSkillReqs, setEditSkillReqs] = useState<SkillReq[]>([])
  const [editRawMats, setEditRawMats]     = useState<RawMat[]>([])

  // Assign drawer
  const [assignJob, setAssignJob]           = useState<Job | null>(null)
  const [assignCheck, setAssignCheck]       = useState<CheckResult | null>(null)
  const [assignChecking, setAssignChecking] = useState(false)
  const [assignEmps, setAssignEmps]         = useState<number[]>([])
  const [assignMachines, setAssignMachines] = useState<number[]>([])
  const [assignError, setAssignError]       = useState('')
  const [assignTab, setAssignTab]           = useState<'machines'|'people'|'extras'>('machines')

  const [deleteId, setDeleteId]           = useState<number | null>(null)
  const [pdfJob,   setPdfJob]             = useState<Job | null>(null)
  const [toast, setToast]                 = useState('')

  const [viewMode, setViewMode] = useState<'list'>('list')

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(''), 3500) }

  // ── Queries ──────────────────────────────────────────
  const { data: jobs = [], isLoading, isError } = useQuery<Job[]>({
    queryKey:['jobs'], queryFn:() => apiClient.get('/api/jobs/').then(r => r.data),
  })
  const { data: skills = [] } = useQuery<Skill[]>({
    queryKey:['skills'], queryFn:() => apiClient.get('/api/skills/').then(r => r.data),
  })
  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey:['employees'], queryFn:() => apiClient.get('/api/employees/').then(r => r.data),
  })
  const { data: machines = [] } = useQuery<Machine[]>({
    queryKey:['machines'], queryFn:() => apiClient.get('/api/machines/').then(r => r.data),
  })
  // Fetch tenant info for job_id_prefix
  const { data: tenantInfo } = useQuery<{ job_id_prefix?: string | null }>({
    queryKey:['tenant-info'],
    queryFn:() => apiClient.get('/auth/me').then(r => r.data?.tenant ?? {}),
  })
  const jobPrefix = tenantInfo?.job_id_prefix ?? null
  const { planLimits } = usePlanLimits()

  const getSkillName = useCallback((id: number) => skills.find(s => s.id === id)?.name ?? `Skill#${id}`, [skills])

  // ── Availability checks ───────────────────────────────
  const runAvailCheck = useCallback(async (jobId: number) => {
    setAvailCache(c => ({ ...c, [jobId]: 'loading' }))
    try {
      const res = await apiClient.get(`/api/assignments/check/${jobId}`)
      setAvailCache(c => ({ ...c, [jobId]: res.data }))
    } catch {
      setAvailCache(c => ({ ...c, [jobId]: null }))
    }
  }, [])

  useEffect(() => {
    jobs.forEach(job => {
      if (!['Completed','Cancelled'].includes(job.status) && availCache[job.id] === undefined) {
        runAvailCheck(job.id)
      }
    })
  }, [jobs, availCache, runAvailCheck])

  // v3.9.5 — keep greyed-locked state in sync with jobs list
  useEffect(() => {
    checkAllLocked(jobs.map(j => ({ lock_status: j.is_locked })))
  }, [jobs, checkAllLocked])

  function openPdfExport(job: Job) { setPdfJob(job) }

  // ── Filters ───────────────────────────────────────────
  const filtered = useMemo(() => jobs.filter(j => {
    const q = search.toLowerCase()
    if (q && !j.name.toLowerCase().includes(q) && !(j.customer ?? '').toLowerCase().includes(q)) return false
    if (filterStatus   !== 'All' && j.status   !== filterStatus)   return false
    if (filterPriority !== 'All' && j.priority !== filterPriority) return false
    if (filterFrom && j.end_date   < filterFrom) return false
    if (filterTo   && j.start_date > filterTo)   return false
    return true
  }), [jobs, search, filterStatus, filterPriority, filterFrom, filterTo])

  // Customer groups
  const customerGroups = useMemo(() => {
    const groups: Record<string, Job[]> = {}
    filtered.forEach(j => {
      const key = j.customer || '(No Customer)'
      if (!groups[key]) groups[key] = []
      groups[key].push(j)
    })
    return groups
  }, [filtered, groupByCustomer])

  // ── Mutations ─────────────────────────────────────────
  const createJob = useMutation({
    mutationFn: (p: object) => apiClient.post('/api/jobs/', p),
    onSuccess: async (res) => {
      const newJobId = res.data.id
      if ((selectedEmps.length > 0 || selectedMachines.length > 0) && newJobId) {
        try { await apiClient.post('/api/assignments/', { job_id:newJobId, employee_ids:selectedEmps, machine_ids:selectedMachines }) }
        catch (err: unknown) {
          const msg = err?.response?.data?.detail || 'Could not assign resources.'
          showToast(msg, 'error') 
        }
      }
      qc.invalidateQueries({queryKey:['jobs']})
      qc.invalidateQueries({queryKey:['dashboard']})
      qc.invalidateQueries({queryKey:['plan-limits']})
      markDirty()  // new job affects schedule
      setTimeout(() => runAvailCheck(newJobId), 500)
      closeWizard()
      showToast('Job created!')
    },
  })

  const updateJob = useMutation({
    mutationFn: ({id,p}:{id:number;p:object}) => apiClient.patch(`/api/jobs/${id}`, p),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({queryKey:['jobs']})
      setEditJob(null)
      runAvailCheck((vars as {id:number}).id)
      // Only mark dirty if scheduling-relevant fields were changed
      const schedFields = new Set(['priority','start_date','end_date','estimated_hours_per_day','start_mode','earliest_date'])
      const changedFields = Object.keys((vars as {p: object}).p ?? {})
      if (changedFields.some(f => schedFields.has(f))) markDirty()
      showToast('Job updated!')
    },
  })

  const toggleLock = useMutation({
    mutationFn: ({id, locked}:{id:number; locked:boolean}) =>
      apiClient.patch(`/api/jobs/${id}`, { is_locked: !locked }),
    onSuccess: () => {
      qc.invalidateQueries({queryKey:['jobs']})
      markDirty()  // lock/unlock affects schedule
    },
  })

  const deleteJobMut = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/jobs/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({queryKey:['jobs']})
      qc.invalidateQueries({queryKey:['dashboard']})
      qc.invalidateQueries({queryKey:['plan-limits']})
      markDirty()  // deleted job affects schedule
      setDeleteId(null)
      showToast('Job deleted!')
    },
  })

  const timerMut = useMutation({
    mutationFn: ({id,action}:{id:number;action:string}) => apiClient.post(`/api/jobs/${id}/timer`, {action}),
    onSuccess: () => {
      qc.invalidateQueries({queryKey:['jobs']})
      qc.invalidateQueries({queryKey:['dashboard']})
    },
  })

  const outageMut = useMutation({
    mutationFn: ({id, action, reason}: {id: number; action: string; reason?: string}) =>
      apiClient.post(`/api/timer/${id}/outage`, {action, reason}),
    onSuccess: () => {
      qc.invalidateQueries({queryKey:['jobs']})
      showToast('Outage logged.')
    },
    onError: (e: unknown) => {
      const msg = (e as {response?:{data?:{detail?:string}}})?.response?.data?.detail ?? 'Failed to log outage'
      showToast(`Error: ${msg}`)
    },
  })

  const assignMut = useMutation({
    mutationFn: (p: object) => apiClient.post('/api/assignments/', p),
    onSuccess: (res) => {
      qc.invalidateQueries({queryKey:['jobs']})
      qc.invalidateQueries({queryKey:['dashboard']})
      markDirty()  // new assignments affect schedule
      if (assignJob) runAvailCheck(assignJob.id)
      setAssignJob(null)
      showToast(`${res.data.assignments.length} resource(s) assigned!`)
    },
    onError: (e: unknown) => {
      const msg = (e as {response?:{data?:{detail?:string}}})?.response?.data?.detail
      setAssignError(msg ?? 'Assignment failed.')
    },
  })

  // ── Wizard helpers ────────────────────────────────────
  function openWizard() {
    setDetails(emptyDetails())
    setSkillReqs([]); setRawMats([]); setSelectedEmps([]); setSelectedMachines([])
    setWizardCheck(null); setWizardStep(1); setWizardOpen(true)
  }
  function closeWizard() { setWizardOpen(false); setWizardStep(1) }

  async function wizardCheckAvail() {
    if (skillReqs.length === 0) { setWizardCheck(null); return }
    setWizardChecking(true); setWizardCheck(null)
    try {
      const empData = await apiClient.get('/api/employees/').then(r => r.data) as (Employee & { skills:{skill_id:number;skill_level:string}[] })[]
      const RANK: Record<string,number> = { Generic:1, Intermediate:2, Premium:3 }
      const newMap: Record<string,number[]> = {}
      skillReqs.forEach((req,i) => {
        newMap[String(i)] = empData.filter(e =>
          e.skills?.some(s => s.skill_id===req.skill_id && RANK[s.skill_level]>=RANK[req.min_skill_level])
        ).map(e => e.id)
      })
      const needed = skillReqs.reduce((s,r)=>s+r.employees_required,0)
      const avail  = skillReqs.reduce((s,_,i)=>s+Math.min(newMap[String(i)]?.length??0,skillReqs[i].employees_required),0)
      setWizardCheck({ feasible:avail>=needed, feasibility_score:needed>0?Math.round((avail/needed)*100):100, conflicts:[], available_employees:newMap })
    } catch(_) {}
    finally { setWizardChecking(false) }
  }

  // Auto-check availability whenever skill requirements change (e.g. machine selected)
  useEffect(() => {
    if (!wizardOpen || wizardStep !== 2) return
    const timer = setTimeout(() => { wizardCheckAvail() }, 400)
    return () => clearTimeout(timer)
  }, [skillReqs, wizardOpen, wizardStep])

  function submitWizard() {
    const isLocked = details.start_mode !== 'flexible'
    createJob.mutate({
      name:details.name, customer:details.customer||null, notes:details.notes||null,
      start_date: details.start_mode === 'flexible' ? (details.earliest_date || details.start_date) : details.start_date,
      end_date:details.end_date,
      estimated_hours_per_day:Number(details.estimated_hours_per_day),
      tentative_profit:details.tentative_profit!==''?Number(details.tentative_profit):null,
      order_value:details.order_value!==''?Number(details.order_value):null,
      misc_cost:details.misc_cost!==''?Number(details.misc_cost):null,
      priority:details.priority,
      status: selectedEmps.length>0||selectedMachines.length>0 ? 'Scheduled' : details.status,
      skill_requirements:skillReqs, raw_materials:rawMats,
      start_mode: details.start_mode,
      is_locked: isLocked,
      earliest_date: details.start_mode === 'flexible' ? (details.earliest_date || null) : null,
      latest_date:   details.start_mode === 'flexible' ? (details.latest_date || null) : null,
      delivery_date: details.delivery_date || null,
      job_type: details.job_type || null,
      quantity: details.quantity !== '' ? Number(details.quantity) : null,
    })
  }

  // ── Edit helpers ──────────────────────────────────────
  function openEdit(job: Job) {
    setEditJob(job)
    setEditForm({
      name:job.name, customer:job.customer??'', notes:job.notes??'',
      start_date:job.start_date, end_date:job.end_date,
      estimated_hours_per_day:job.estimated_hours_per_day,
      tentative_profit:job.tentative_profit!=null?String(job.tentative_profit):'',
      order_value:job.order_value!=null?String(job.order_value):'',
      misc_cost:job.misc_cost!=null?String(job.misc_cost):'',
      priority:job.priority, status:job.status,
      start_mode: job.start_mode ?? 'pick_a_date',
      earliest_date: job.earliest_date ?? '',
      latest_date: job.latest_date ?? '',
      delivery_date: job.delivery_date ?? '',
      invoice_number: job.invoice_number ?? '',
      invoice_date: job.invoice_date ?? '',
      payment_status: job.payment_status ?? 'Unpaid',
      payment_amount: job.payment_amount != null ? String(job.payment_amount) : '',
      payment_date: job.payment_date ?? '',
      job_type: job.job_type ?? '',
      quantity: job.quantity != null ? String(job.quantity) : '',
    })
    setEditSkillReqs(job.skill_requirements.map(r=>({skill_id:r.skill_id,min_skill_level:r.min_skill_level,employees_required:r.employees_required})))
    setEditRawMats(job.raw_materials || [])
  }

  function submitEdit() {
    if (!editJob) return
    const isLocked = editForm.start_mode !== 'flexible'
    updateJob.mutate({ id:editJob.id, p:{
      ...editForm,
      estimated_hours_per_day:Number(editForm.estimated_hours_per_day),
      tentative_profit:editForm.tentative_profit!==''?Number(editForm.tentative_profit):null,
      order_value:editForm.order_value!==''?Number(editForm.order_value):null,
      misc_cost:editForm.misc_cost!==''?Number(editForm.misc_cost):null,
      skill_requirements:editSkillReqs, raw_materials:editRawMats,
      is_locked: isLocked,
      earliest_date: editForm.start_mode === 'flexible' ? (editForm.earliest_date || null) : null,
      latest_date:   editForm.start_mode === 'flexible' ? (editForm.latest_date || null) : null,
      delivery_date: editForm.delivery_date || null,
      invoice_number: editForm.invoice_number || null,
      invoice_date: editForm.invoice_date || null,
      payment_status: editForm.payment_status || 'Unpaid',
      payment_amount: editForm.payment_amount !== '' ? Number(editForm.payment_amount) : null,
      payment_date: editForm.payment_date || null,
      job_type: editForm.job_type || null,
      quantity: editForm.quantity !== '' ? Number(editForm.quantity) : null,
    }})
  }

  // ── Assign drawer ─────────────────────────────────────
  async function openAssign(job: Job) {
    setAssignJob(job); setAssignEmps([]); setAssignMachines([]); setAssignError('')
    setAssignCheck(null); setAssignChecking(true); setAssignTab('machines')
    try {
      const res = await apiClient.get(`/api/assignments/check/${job.id}`)
      const data: CheckResult = res.data
      setAssignEmps(data.currently_assigned_employee_ids)
      setAssignMachines(data.currently_assigned_machine_ids)
      setAssignCheck(data)
    } catch(_) { setAssignCheck(null) }
    finally { setAssignChecking(false) }
  }

  // Cost helpers
  const matTotal = (mats: RawMat[]) => mats.reduce((s,m)=>s+m.quantity*m.unit_cost,0)
  const rawMatLimit = planLimits?.limits?.raw_materials?.limit ?? null
  const rawMatLimitReached = (count: number) => rawMatLimit !== null && count >= rawMatLimit

  const jobCost = (job: Job) => matTotal(job.raw_materials || []) + (job.misc_cost ?? 0)
  const jobProfit = (job: Job) => job.order_value != null ? job.order_value - jobCost(job) : null


  // ── Status badge styles ──────────────────────────────
  const STATUS_STYLE: Record<string,string> = {
    'Draft':              'bg-gray-100 text-gray-500 border-gray-200',
    'Scheduled':          'bg-blue-100 text-blue-700 border-blue-200',
    'Pending Assignment': 'bg-amber-100 text-amber-700 border-amber-200',
    'In Progress':        'bg-purple-100 text-purple-700 border-purple-200',
    'Completed':          'bg-teal-100 text-teal-700 border-teal-200',
    'Cancelled':          'bg-red-100 text-red-500 border-red-200',
  }

  // ── Timer badge styles ────────────────────────────────
  const TIMER_STYLE: Record<string,{label:string;cls:string}> = {
    idle:    { label:'—',       cls:'text-gray-300 bg-gray-50 border-gray-100'       },
    running: { label:'Running', cls:'text-green-700 bg-green-50 border-green-200'    },
    paused:  { label:'Paused',  cls:'text-amber-700 bg-amber-50 border-amber-200'    },
    ended:   { label:'Ended',   cls:'text-teal-600 bg-teal-50 border-teal-200'       },
  }

  // ── Running pulse dot (used in header pill) ──────────
  function RunningDot() {
    return (
      <span className="relative flex h-2 w-2 shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"/>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"/>
      </span>
    )
  }

  // ── Render a single job row ───────────────────────────
  function JobRow({ job }: { job: Job }) {
   
    const avail    = availCache[job.id]
    const aLoading = avail === 'loading'
    const result   = typeof avail === 'object' ? avail : null
    const isExpanded = expandedRow === job.id
    const rawTotal   = matTotal(job.raw_materials || [])
    const totalCost  = jobCost(job)
    const profit     = jobProfit(job)
    const profitPos  = profit != null && profit >= 0
    const displayId  = jobDisplayId(job, jobPrefix)
    const ts         = TIMER_STYLE[job.timer_status] ?? TIMER_STYLE['idle']
    

    // One-liner summary
    const summaryParts = [
      job.assigned_employees.length > 0 ? `${job.assigned_employees.length} people` : 'Unassigned',
      job.assigned_machines.length > 0  ? `${job.assigned_machines.length} machine${job.assigned_machines.length!==1?'s':''}` : 'No machines',
      `${job.estimated_hours_per_day}h/day`,
      job.start_mode === 'flexible' && job.earliest_date
        ? `Flexible ${job.earliest_date}`
        : job.start_date,
      job.is_locked ? '🔒 Locked' : null,
      job.has_conflict ? '⚠ Conflict' : null,
    ].filter(Boolean)

    return (
      <>
        <tr
          onClick={async () => {
            if (isExpanded) {
              setExpandedRow(null)
            } else {
              setExpandedRow(job.id)
              // v3.9.4: fetch real-time resource availability when row expands
              if (!resAvail[job.id]) {
                setResAvailLoading(p => ({ ...p, [job.id]: true }))
                try {
                  const data = await getResourceAvailability(job.id)
                  setResAvail(p => ({ ...p, [job.id]: data }))
                } catch (_) {
                  // silently fall back to static values if fetch fails
                } finally {
                  setResAvailLoading(p => ({ ...p, [job.id]: false }))
                }
              }
            }
          }}
          className={`cursor-pointer group border-b transition-colors
            ${job.has_conflict
              ? isExpanded
                ? 'bg-red-50 border-b-red-200 outline outline-1 outline-red-300'
                : 'bg-red-50/80 hover:bg-red-100/60 border-b-red-100 outline outline-1 outline-dashed outline-red-300'
              : isExpanded
                ? 'bg-blue-50/40 border-b-gray-100'
                : 'hover:bg-gray-50 border-b-gray-100'
            }
          `}
        >
          {/* Chevron — thick, visible, coloured on hover/expanded */}
          <td className="pl-3 pr-1 py-3 w-7">
            <div className={`w-6 h-6 rounded flex items-center justify-center transition-all ${
              isExpanded ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-500 group-hover:bg-blue-100 group-hover:text-blue-600'
            }`}>
              <ChevronRight size={15} strokeWidth={2.8} className={`transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`}/>
            </div>
          </td>

          {/* Job name + customer + priority + status + one-liner */}
          <td className="px-3 py-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-[11px] font-medium text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded shrink-0">{displayId}</span>
              <span className="text-sm font-semibold text-gray-800">{job.name}</span>
              {/* Priority inline */}
              <span className={`text-xs font-semibold px-1.5 py-0.5 rounded border ${priorityColour[job.priority]??''}`}>
                {job.priority}
              </span>
              {/* Status inline */}
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${STATUS_STYLE[job.status]??''}`}>
                {job.status}
              </span>
              {job.has_conflict && <ConflictBadge />}
              {job.cost_overrun && (
                <span title={`Actual ${job.cost_overrun.actual_hours}h vs estimated ${job.cost_overrun.estimated_hours}h (+${job.cost_overrun.overrun_pct}%)`}
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-700 text-xs font-bold border border-orange-200 cursor-help">
                  <Clock size={9}/> +{job.cost_overrun.overrun_pct}% hrs
                </span>
              )}
              <AvailBadge result={result} loading={aLoading} status={job.status}/>
            </div>
            {job.customer && <div className="text-xs text-gray-400 mt-0.5 pl-[26px]">{job.customer}</div>}
            <div className="text-xs text-gray-400 mt-0.5 pl-[26px] font-mono tracking-tight">
              {summaryParts.join('  ·  ')}
            </div>
          </td>

          {/* Timer — full text badge + pulse dot */}
          <td className="px-3 py-3 w-28">
            <div className="flex items-center gap-1.5">
              {job.timer_status === 'running' && <RunningDot/>}
              <span className={`text-xs font-medium px-2 py-1 rounded-full border ${ts.cls}`}>
                {ts.label}
              </span>
            </div>
          </td>

          {/* Timeline */}
          <td className="px-3 py-3 w-44">
            <div className="text-xs font-medium text-gray-700">
              {job.start_mode === 'flexible' && job.earliest_date ? job.earliest_date : job.start_date}
            </div>
            <div className="text-xs text-gray-400">→ {job.end_date} · {job.estimated_hours_per_day}h/d</div>
            {job.delivery_date && (
              <div className="text-xs text-blue-600 mt-0.5">📦 Deliver by {job.delivery_date}</div>
            )}
            {job.actual_hours != null && (
              <div className={`text-xs mt-0.5 font-medium ${job.cost_overrun ? 'text-orange-600' : 'text-teal-600'}`}>
                ✓ Actual: {job.actual_hours}h
              </div>
            )}
            <TimelineBar job={job} />
          </td>

          {/* Actions — compact icon buttons */}
          <td className="px-2 py-3 w-36 whitespace-nowrap" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-1 justify-end">

              {/* Lock / Unlock */}
              <button
                onClick={() => toggleLock.mutate({id:job.id, locked:job.is_locked})}
                title={job.is_locked ? 'Unlock' : 'Lock'}
                className={`w-7 h-7 flex items-center justify-center rounded-md border transition-colors ${
                  job.is_locked
                    ? 'bg-amber-50 border-amber-300 text-amber-600 hover:bg-amber-100'
                    : 'border-gray-200 text-gray-300 hover:text-gray-500 hover:bg-gray-100'
                }`}>
                {job.is_locked ? <Lock size={12}/> : <Unlock size={12}/>}
              </button>

              {!['Completed','Cancelled'].includes(job.status) && (
                <>
                  {/* ▶ Start — idle */}
                  {job.timer_status === 'idle' && (
                    <button
                      onClick={() => !job.has_conflict && timerMut.mutate({id:job.id,action:'start'})}
                      disabled={job.has_conflict}
                      title={job.has_conflict ? 'Resolve conflict to start' : 'Start'}
                      className={`w-7 h-7 flex items-center justify-center rounded-md border transition-colors ${
                        job.has_conflict
                          ? 'border-gray-200 text-gray-300 cursor-not-allowed bg-gray-50'
                          : 'bg-green-600 border-green-600 text-white hover:bg-green-700'
                      }`}>
                      <Play size={12}/>
                    </button>
                  )}
                  {/* ▶ Resume — paused */}
                  {job.timer_status === 'paused' && (
                    <button onClick={()=>timerMut.mutate({id:job.id,action:'resume'})}
                      title="Resume"
                      className="w-7 h-7 flex items-center justify-center rounded-md bg-green-600 border border-green-600 text-white hover:bg-green-700">
                      <Play size={12}/>
                    </button>
                  )}
                  {/* ⏸ Pause — running */}
                  {job.timer_status === 'running' && (
                    <button onClick={()=>timerMut.mutate({id:job.id,action:'pause'})}
                      title="Pause"
                      className="w-7 h-7 flex items-center justify-center rounded-md bg-amber-500 border border-amber-500 text-white hover:bg-amber-600">
                      <Pause size={12}/>
                    </button>
                  )}
                  {/* ■ End — running or paused */}
                  {['running','paused'].includes(job.timer_status) && (
                    <button onClick={()=>timerMut.mutate({id:job.id,action:'end'})}
                      title="End job"
                      className="w-7 h-7 flex items-center justify-center rounded-md bg-gray-700 border border-gray-700 text-white hover:bg-gray-900">
                      <Square size={12}/>
                    </button>
                  )}
                </>
              )}

              {/* ⋯ menu */}
              <div className="relative">
                <button
                  onClick={() => setOpenMenu(openMenu === job.id ? null : job.id)}
                  className="w-7 h-7 flex items-center justify-center rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <circle cx="3" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/><circle cx="13" cy="8" r="1.5"/>
                  </svg>
                </button>
                {openMenu === job.id && (
                  <div className="absolute right-0 top-8 z-50 bg-white border border-gray-200 rounded-lg shadow-xl py-1 min-w-[148px]"
                       onClick={e => e.stopPropagation()}>
                    {!['Completed','Cancelled','In Progress'].includes(job.status) && job.timer_status === 'idle' && (
                      <button onClick={()=>{openAssign(job);setOpenMenu(null)}}
                        className="w-full text-left px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-2">
                        <ClipboardCheck size={11}/> Assign
                      </button>
                    )}
                    <button onClick={()=>{openEdit(job);setOpenMenu(null)}}
                      className="w-full text-left px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 flex items-center gap-2">
                      <Pencil size={11}/> Edit
                    </button>
                    {['running','paused'].includes(job.timer_status) && (() => {
                      const lastOutageEvent = [...(job.timer_log||[])].reverse().find(e => e.event === 'outage_start' || e.event === 'outage_end')
                      const hasActiveOutage = lastOutageEvent?.event === 'outage_start'
                      return hasActiveOutage ? (
                        <button onClick={()=>{outageMut.mutate({id:job.id,action:'end'});setOpenMenu(null)}}
                          className="w-full text-left px-3 py-1.5 text-xs text-green-700 hover:bg-green-50 flex items-center gap-2">
                          <Check size={11}/> End Outage
                        </button>
                      ) : (
                        <button onClick={()=>{outageMut.mutate({id:job.id,action:'start'});setOpenMenu(null)}}
                          className="w-full text-left px-3 py-1.5 text-xs text-amber-700 hover:bg-amber-50 flex items-center gap-2">
                          <AlertTriangle size={11}/> Log Outage
                        </button>
                      )
                    })()}
                    {job.status === 'Completed' && (
                      <button onClick={()=>{openPdfExport(job);setOpenMenu(null)}}
                        className="w-full text-left px-3 py-1.5 text-xs text-blue-700 hover:bg-blue-50 flex items-center gap-2">
                        <Package size={11}/> Export PDF
                      </button>
                    )}
                    <div className="border-t border-gray-100 my-0.5"/>
                    <button onClick={()=>{setDeleteId(job.id);setOpenMenu(null)}}
                      className="w-full text-left px-3 py-1.5 text-xs text-red-500 hover:bg-red-50 flex items-center gap-2">
                      <Trash2 size={11}/> Delete
                    </button>
                  </div>
                )}
              </div>
            </div>
          </td>
        </tr>

        {/* ── Expanded detail row ── */}
        {isExpanded && (
          <tr key={`${job.id}-detail`}>
            <td colSpan={5} className="bg-blue-50/40 border-b border-blue-100 px-4 py-4">
              <div className="border-2 border-blue-300 rounded-xl overflow-hidden shadow-md bg-white">

              {/* Cost summary bar */}
              <div className="flex items-stretch gap-0 bg-gray-50 border-b border-blue-100 overflow-hidden divide-x divide-gray-100">
                {[
                  { label: 'Order Value', value: job.order_value != null ? `₹${job.order_value.toLocaleString('en-IN')}` : '—', cls: 'text-gray-800' },
                  { label: 'RM Cost',     value: `₹${rawTotal.toLocaleString('en-IN')}`,                 cls: 'text-red-500'   },
                  { label: 'Misc / OH',   value: `₹${(job.misc_cost??0).toLocaleString('en-IN')}`,       cls: 'text-red-400'   },
                  { label: 'Total Cost',  value: `₹${totalCost.toLocaleString('en-IN')}`,                cls: 'text-red-600 font-black' },
                  { label: 'Profit',
                    value: profit != null ? `${profitPos?'+':''}₹${Math.abs(profit).toLocaleString('en-IN')}` : '—',
                    cls: profit != null ? (profitPos ? 'text-green-600 font-black' : 'text-red-600 font-black') : 'text-gray-400'
                  },
                ].map(({ label, value, cls }) => (
                  <div key={label} className="flex-1 text-center px-4 py-3">
                    <div className="text-xs text-gray-400 mb-1">{label}</div>
                    <div className={`text-sm font-bold ${cls}`}>{value}</div>
                  </div>
                ))}
              </div>

              {/* 3-col detail */}
              <div className="grid grid-cols-3 gap-4 p-4">

                {/* Raw Materials */}
                <div>
                  <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                    <Package size={11} className="text-orange-500"/> {labels.materials}
                  </p>
                  {(job.raw_materials||[]).length === 0
                    ? <p className="text-xs text-gray-400 italic">None specified</p>
                    : <div className="space-y-1.5">
                        {job.raw_materials.map((m,i) => (
                          <div key={i} className="flex items-center justify-between text-xs bg-white rounded-lg border border-gray-100 px-3 py-1.5">
                            <div>
                              <span className="font-medium text-gray-700">{m.name}</span>
                              <span className="text-gray-400 ml-1.5">{m.quantity}{m.unit}</span>
                            </div>
                            <span className="font-semibold text-gray-800 shrink-0 ml-2">₹{(m.quantity*m.unit_cost).toLocaleString('en-IN')}</span>
                          </div>
                        ))}
                      </div>
                  }
                </div>

                {/* People & Machines — v3.9.4: real-time availability */}
                <div>
                  <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                    <Users size={11} className="text-blue-500"/> People & Machines
                  </p>
                  {job.assigned_employees.length === 0 && job.assigned_machines.length === 0
                    ? <div className="rounded-xl border border-dashed border-amber-200 bg-amber-50 px-4 py-3 text-center">
                        <p className="text-xs text-amber-600 font-medium mb-1">No resources assigned yet</p>
                        <p className="text-xs text-amber-500">Click <strong>Assign</strong> below to add employees and machines to this job.</p>
                      </div>
                    : <>
                        {/* Loading spinner while fetching availability */}
                        {resAvailLoading[job.id] && (
                          <div className="flex items-center gap-1.5 text-xs text-gray-400 mb-2">
                            <Loader2 size={11} className="animate-spin"/> Checking availability...
                          </div>
                        )}
                        {/* No dates set message */}
                        {resAvail[job.id]?.error === 'no_dates' && (
                          <p className="text-xs text-gray-400 italic mb-2">
                            Set start and end dates to see real-time availability.
                          </p>
                        )}
                        {/* Employees */}
                        {job.assigned_employees.map(e => {
                          const key      = `e-${job.id}-${e.id}`
                          const val      = allocPct[key] ?? (e.allocation_pct ?? 100)
                          const empAvail = resAvail[job.id]?.employees?.find(ea => ea.employee_id === e.id)
                          const dotColor = empAvail ? employeeStatusColor(empAvail.status) : '#60a5fa'
                          const subtitle = empAvail ? employeeStatusLabel(empAvail) : ''
                          const displayPct = empAvail ? Math.round(empAvail.free_pct) : val
                          return (
                            <div key={e.id} className="flex items-start gap-2 mb-1.5 bg-white rounded-lg border border-gray-100 px-3 py-1.5">
                              <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style={{ backgroundColor: dotColor }}/>
                              <div className="flex-1 min-w-0">
                                <span className="text-xs text-gray-700">{e.full_name}</span>
                                {subtitle && (
                                  <p className="text-xs mt-0.5" style={{ color: dotColor }}>{subtitle}</p>
                                )}
                              </div>
                              <input type="range" min={10} max={100} step={5} value={val}
                                onChange={ev => setAllocPct(p => ({...p, [key]: Number(ev.target.value)}))}
                                className="w-16 mt-1" style={{ accentColor: dotColor }}/>
                              <span className="text-xs font-semibold w-8 text-right mt-1" style={{ color: dotColor }}>
                                {displayPct}%
                              </span>
                            </div>
                          )
                        })}
                        {/* Machines */}
                        {job.assigned_machines.map(m => {
                          const key      = `m-${job.id}-${m.id}`
                          const val      = allocPct[key] ?? (m.allocation_pct ?? 100)
                          const machAvail = resAvail[job.id]?.machines?.find(ma => ma.machine_id === m.id)
                          const isBusy   = machAvail ? !machAvail.is_free : false
                          const dotColor = isBusy ? '#A32D2D' : '#a855f7'
                          const statusText = machAvail ? machineStatusLabel(machAvail) : ''
                          return (
                            <div key={m.id} className="flex items-start gap-2 mb-1.5 bg-white rounded-lg border border-gray-100 px-3 py-1.5">
                              <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style={{ backgroundColor: dotColor }}/>
                              <div className="flex-1 min-w-0">
                                <span className="text-xs text-gray-700 truncate block" title={m.name}>{m.name}</span>
                                {statusText && (
                                  <p className="text-xs mt-0.5" style={{ color: dotColor }}>{statusText}</p>
                                )}
                              </div>
                              <input type="range" min={10} max={100} step={5} value={val}
                                onChange={ev => setAllocPct(p => ({...p, [key]: Number(ev.target.value)}))}
                                className="w-16 mt-1" style={{ accentColor: dotColor }}/>
                              <span className="text-xs font-semibold w-8 text-right mt-1" style={{ color: dotColor }}>
                                {val}%
                              </span>
                            </div>
                          )
                        })}
                        {(job.assigned_employees.length > 0 || job.assigned_machines.length > 0) && (
                          <button
                            disabled={savingAlloc}
                            onClick={async () => {
                              setSavingAlloc(true)
                              try {
                                const patches = [
                                  ...job.assigned_employees.map(e => ({
                                    type:'employee', resource_id: e.id,
                                    allocation_pct: allocPct[`e-${job.id}-${e.id}`] ?? (e.allocation_pct ?? 100)
                                  })),
                                  ...job.assigned_machines.map(m => ({
                                    type:'machine', resource_id: m.id,
                                    allocation_pct: allocPct[`m-${job.id}-${m.id}`] ?? (m.allocation_pct ?? 100)
                                  })),
                                ]
                                await apiClient.patch(`/api/assignments/${job.id}/allocation`, { allocations: patches })
                                qc.invalidateQueries({ queryKey: ['jobs'] })
                                // Refresh availability after saving allocation
                                const updated = await getResourceAvailability(job.id)
                                setResAvail(p => ({ ...p, [job.id]: updated }))
                              } catch(_) {}
                              setSavingAlloc(false)
                            }}
                            className="flex items-center gap-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-2.5 py-1.5 mt-1 disabled:opacity-50">
                            {savingAlloc ? <Loader2 size={11} className="animate-spin"/> : <Check size={11}/>} Save Allocation
                          </button>
                        )}

                        {/* Skill requirements coverage — shows which skills are met vs missing */}
                        {(() => {
                          const checkResult = typeof availCache[job.id] === 'object'
                                    ? availCache[job.id] as {
                                        skill_requirements?: {
                                          skill_id: number
                                          min_skill_level: string
                                          employees_required: number
                                          available_employee_ids?: number[]
                                        }[]
                                      }
                                    : null
                          const skillReqs = checkResult?.skill_requirements ?? []
                          if (skillReqs.length === 0) return null
                          return (
                            <div className="mt-3 pt-3 border-t border-gray-100">
                              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                                <ClipboardCheck size={11} className="text-blue-400"/> Skill Coverage
                              </p>
                              <div className="space-y-1.5">
                                {skillReqs.map((req: { skill_id: number; min_skill_level: string; employees_required: number; id?: number; available_employee_ids?: number[] }) => {
                                  // Count how many assigned employees actually cover this skill
                                  const assignedIds = job.assigned_employees.map(e => e.id)
                                  const coveredCount = (req.available_employee_ids ?? [])
                                    .filter((id: number) => assignedIds.includes(id)).length
                                  const needed   = req.employees_required
                                  const covered  = Math.min(coveredCount, needed)
                                  const isMet    = covered >= needed
                                  const isPartial = covered > 0 && covered < needed
                                  const dotColor = isMet ? '#1D9E75' : isPartial ? '#BA7517' : '#A32D2D'
                                  const statusLabel = isMet
                                    ? `${covered}/${needed} assigned`
                                    : isPartial
                                    ? `${covered}/${needed} — need ${needed - covered} more`
                                    : `0/${needed} — nobody assigned`
                                  return (
                                    <div key={req.id} className="flex items-center gap-2 bg-white rounded-lg border border-gray-100 px-3 py-1.5">
                                      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: dotColor }}/>
                                      <div className="flex-1 min-w-0">
                                        <span className="text-xs text-gray-700">{req.skill_name}</span>
                                        <span className="text-xs text-gray-400 ml-1.5">{req.min_skill_level}</span>
                                      </div>
                                      <span className="text-xs font-semibold shrink-0" style={{ color: dotColor }}>
                                        {statusLabel}
                                      </span>
                                    </div>
                                  )
                                })}
                                {!checkResult?.feasible && (
                                  <p className="text-xs text-amber-600 mt-1.5 flex items-center gap-1">
                                    <AlertTriangle size={10}/> Click <strong>Assign</strong> to add qualified staff
                                  </p>
                                )}
                              </div>
                            </div>
                          )
                        })()}
                      </>
                  }
                </div>

                {/* Scheduling + notes */}
                <div>
                  <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                    <Zap size={11} className="text-blue-400"/> Scheduling
                  </p>
                  <div className="text-xs space-y-1.5 mb-3">
                    {[
                      ['Mode',     (job.start_mode||'pick_a_date').replace(/_/g,' ')],
                      ['Lock',     job.is_locked ? '🔒 Locked' : '🔓 Flexible'],
                      ['Hours/day',`${job.estimated_hours_per_day}h`],
                      ['Job ID',   displayId],
                    ].map(([k,v]) => (
                      <div key={k} className="flex justify-between bg-white rounded-lg border border-gray-100 px-3 py-1.5">
                        <span className="text-gray-400">{k}</span>
                        <span className="font-medium text-gray-700">{v}</span>
                      </div>
                    ))}
                    {job.start_mode === 'flexible' && job.earliest_date && (
                      <div className="flex justify-between bg-white rounded-lg border border-gray-100 px-3 py-1.5">
                        <span className="text-gray-400">Range</span>
                        <span className="text-blue-600 font-medium">{job.earliest_date} → {job.latest_date||'?'}</span>
                      </div>
                    )}
                  </div>
                  {result && result.conflicts.length > 0 && (() => {
                    // Split conflicts into skill gaps (employee) vs real scheduling conflicts (machine)
                    const skillGaps  = result.conflicts.filter(c => c.resource_type === 'employee')
                    const realConflicts = result.conflicts.filter(c => c.resource_type !== 'employee')
                    return (
                      <>
                        {/* Skill Gaps — amber, action: assign qualified staff */}
                        {skillGaps.length > 0 && (
                          <div className="mb-2 bg-amber-50 rounded-lg border border-amber-200 px-3 py-2">
                            <p className="text-xs font-semibold text-amber-700 mb-1.5 flex items-center gap-1">
                              <AlertTriangle size={10}/> Skill Gaps
                            </p>
                            {skillGaps.map((c, i) => {
                              // Parse "Skill: X (need N, found M)" into friendlier format
                              const nameMatch  = c.resource_name.match(/Skill:\s*(.+?)\s*\(/)
                              const needMatch  = c.resource_name.match(/need\s*(\d+)/)
                              const foundMatch = c.resource_name.match(/found\s*(\d+)/)
                              const skillName  = nameMatch?.[1]  ?? c.resource_name
                              const need       = needMatch?.[1]  ?? '?'
                              const found      = foundMatch?.[1] ?? '0'
                              return (
                                <div key={i} className="text-xs text-amber-700 mb-1 flex items-start gap-1.5">
                                  <span className="shrink-0 mt-0.5">·</span>
                                  <span>
                                    <span className="font-medium">{skillName}</span>
                                    {' '}— need {need}, only {found} qualified {found === '0' ? 'assigned' : 'available'}
                                  </span>
                                </div>
                              )
                            })}
                            <p className="text-xs text-amber-600 mt-1.5 flex items-center gap-1 border-t border-amber-100 pt-1.5">
                              <ClipboardCheck size={10}/> Click <strong className="mx-0.5">Assign</strong> to add staff with these skills
                            </p>
                          </div>
                        )}
                        {/* Real scheduling conflicts — red, action: change dates or reassign resource */}
                        {realConflicts.length > 0 && (
                          <div className="mb-2 bg-red-50 rounded-lg border border-red-200 px-3 py-2">
                            <p className="text-xs font-semibold text-red-600 mb-1.5 flex items-center gap-1">
                              <AlertTriangle size={10}/> Scheduling Conflicts
                            </p>
                            {realConflicts.map((c, i) => (
                              <div key={i} className="text-xs text-red-600 mb-1 flex items-start gap-1.5">
                                <span className="shrink-0 mt-0.5">·</span>
                                <span><span className="font-medium">{c.resource_name}</span>: {c.reason}</span>
                              </div>
                            ))}
                            <p className="text-xs text-red-500 mt-1.5 flex items-center gap-1 border-t border-red-100 pt-1.5">
                              <AlertTriangle size={10}/> Change job dates or reassign the conflicting resource
                            </p>
                          </div>
                        )}
                      </>
                    )
                  })()}
                  {/* Invoice & payment */}
                  {(job.invoice_number || job.payment_status !== 'Unpaid') && (
                    <div className="mb-3">
                      <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1.5 flex items-center gap-1">
                        <IndianRupee size={11} className="text-green-600"/> Invoice
                      </p>
                      <div className="text-xs space-y-1">
                        {job.invoice_number && (
                          <div className="flex justify-between bg-white rounded-lg border border-gray-100 px-3 py-1.5">
                            <span className="text-gray-400">Invoice#</span>
                            <span className="font-medium text-gray-700">{job.invoice_number}</span>
                          </div>
                        )}
                        <div className="flex justify-between bg-white rounded-lg border border-gray-100 px-3 py-1.5">
                          <span className="text-gray-400">Payment</span>
                          <span className={`font-semibold ${job.payment_status==='Paid'?'text-green-600':job.payment_status==='Partial'?'text-amber-600':'text-red-500'}`}>
                            {job.payment_status}
                            {job.payment_amount != null && ` · ₹${job.payment_amount.toLocaleString('en-IN')}`}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                  {job.notes && (
                    <div className="text-xs bg-yellow-50 border border-yellow-200 rounded-lg px-3 py-2 text-gray-600 italic">
                      📝 {job.notes}
                    </div>
                  )}
                </div>
              </div>

              {/* Steps Panel V3.7 gated  */}
              {flags.step_intelligence && (<JobStepsPanel jobId={job.id} jobStatus={job.status} />)}

              {/* Action buttons */}
              <div className="flex gap-2 mt-4 pt-3 border-t border-blue-100 px-4 pb-4">
                <button onClick={()=>openEdit(job)}
                  className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium flex items-center gap-1.5">
                  <Pencil size={11}/> Edit
                </button>
                {!['Completed','Cancelled'].includes(job.status) && (
                  <button onClick={()=>openAssign(job)}
                    className="text-xs px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 font-medium flex items-center gap-1.5">
                    <ClipboardCheck size={11}/> Assign
                  </button>
                )}
                <button onClick={()=>toggleLock.mutate({id:job.id, locked:job.is_locked})}
                  className="text-xs px-3 py-1.5 bg-amber-50 text-amber-700 rounded-lg hover:bg-amber-100 border border-amber-200 font-medium flex items-center gap-1.5">
                  {job.is_locked ? <><Lock size={11}/> Unlock</> : <><Unlock size={11}/> Lock</>}
                </button>
                {flags.qr_scan && (<button
                  onClick={() => navigate(`/jobs/${job.id}/print`)}
                  className="text-xs px-3 py-1.5 bg-purple-50 text-purple-700 rounded-lg hover:bg-purple-100 border border-purple-200 font-medium flex items-center gap-1.5">
                  <Package size={11}/> Print Job Card
                </button>
                )}
                <button onClick={()=>setDeleteId(job.id)}
                  className="text-xs px-3 py-1.5 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 border border-red-100 font-medium flex items-center gap-1.5 ml-auto">
                  <Trash2 size={11}/> Delete
                </button>
              </div>
              </div>{/* end border wrapper */}
            </td>
          </tr>
        )}
      </>
    )
  }
  // ── Main render ───────────────────────────────────────
  return (
    <div className="space-y-0">

      {/* ── Page Header ─────────────────────────────────── */}
      <div className="bg-white border-b border-gray-200 px-1 py-4 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{labels.jobsPageTitle}</h2>
            <p className="text-xs text-gray-400 mt-0.5">{labels.jobsPageSubtitle}</p>
          </div>
          <div className="flex items-center gap-2">
            <CoachMark id="jobs-new" title="Create your first job" description="Pick a machine — skills are auto-suggested. Set dates and assign your team." position="bottom" step={1} totalSteps={3}>
              <LimitedButton resource="jobs" planLimits={planLimits} onClick={openWizard}>
                <Plus size={16}/> {labels.newJobButton}
              </LimitedButton>
            </CoachMark>
          </div>
        </div>

        {/* Summary pills */}
        {(() => {
          const totalOV     = jobs.reduce((s,j) => s + (j.order_value??0), 0)
          const totalProfit = jobs.reduce((s,j) => s + (jobProfit(j)??0), 0)
          const conflicts   = jobs.filter(j => j.has_conflict).length
          const running     = jobs.filter(j => j.timer_status === 'running').length
          return (
            <div className="flex gap-3 flex-wrap">
              <div className="flex items-center gap-2.5 bg-blue-50 border border-blue-100 rounded-xl px-4 py-2.5">
                <span className="text-2xl font-bold text-blue-700">{jobs.length}</span>
                <span className="text-xs text-blue-500 font-medium leading-tight">{labels.kpiJobs}</span>
              </div>
              <div className="flex items-center gap-2.5 bg-slate-50 border border-slate-100 rounded-xl px-4 py-2.5">
                <span className="text-lg font-bold text-slate-700 flex items-center gap-0.5"><IndianRupee size={16}/>{totalOV.toLocaleString('en-IN')}</span>
                <span className="text-xs text-slate-400 font-medium leading-tight">{labels.kpiOrderBook}</span>
              </div>
              <div className="flex items-center gap-2.5 bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-2.5">
                <span className={`text-lg font-bold flex items-center gap-0.5 ${totalProfit>=0?'text-emerald-700':'text-red-600'}`}>
                  {totalProfit>=0?'+':''}<IndianRupee size={16}/>{Math.abs(totalProfit).toLocaleString('en-IN')}
                </span>
                <span className="text-xs text-emerald-500 font-medium leading-tight">Est.<br/>Profit</span>
              </div>
              {conflicts > 0 && (
                <div className="flex items-center gap-2.5 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5">
                  <span className="text-2xl font-bold text-red-600">{conflicts}</span>
                  <span className="text-xs text-red-400 font-medium leading-tight">⚠<br/>Conflicts</span>
                </div>
              )}
              {running > 0 && (
                <div className="flex items-center gap-2.5 bg-green-50 border border-green-200 rounded-xl px-4 py-2.5">
                  <span className="relative flex h-3 w-3 shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"/>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"/>
                  </span>
                  <span className="text-2xl font-bold text-green-600 ml-1">{running}</span>
                  <span className="text-xs text-green-500 font-medium leading-tight">Now<br/>Running</span>
                </div>
              )}
            </div>
          )
        })()}
      </div>

      <PlanLimitBanner resource="jobs" planLimits={planLimits} label="jobs" />
      {toast && (
        <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-sm mt-3">
          <Check size={15}/>{toast}
        </div>
      )}



      {/* ── Toolbar ─────────────────────────────────────── */}
      <div className="bg-white border-b border-gray-100 py-3 flex items-center gap-3 flex-wrap">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400"/>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search jobs or customers…"
            className="pl-7 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg w-52 focus:outline-none focus:ring-2 focus:ring-blue-300 bg-gray-50"
          />
        </div>
        <div className="flex gap-0.5 bg-gray-100 rounded-lg p-1">
          {(['All',...STATUSES]).map(s => {
            const count = s === 'All' ? jobs.length : jobs.filter(j => j.status === s).length
            return (
              <button key={s} onClick={() => setFilterStatus(s)}
                className={`text-xs px-3 py-1 rounded-md font-medium transition-colors flex items-center gap-1.5
                  ${filterStatus === s ? 'bg-white shadow text-gray-800' : 'text-gray-500 hover:text-gray-700'}`}>
                {s}
                <span className={`text-xs rounded-full px-1.5 font-bold
                  ${filterStatus === s ? 'bg-blue-100 text-blue-600' : 'bg-gray-200 text-gray-400'}`}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>
        <select value={filterPriority} onChange={e => setFilterPriority(e.target.value)}
          className="text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-300 text-gray-600">
          <option value="All">All Priorities</option>
          {PRIORITIES.map(p => <option key={p}>{p}</option>)}
        </select>
        <button
          onClick={() => setGroupByCustomer(g => !g)}
          className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors ${
            groupByCustomer ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'
          }`}>
          <FolderOpen size={12}/> By Customer
        </button>
        <div className="flex items-center gap-1.5 ml-auto">
          <span className="text-xs text-gray-400">From</span>
          <input type="date" className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs bg-gray-50" value={filterFrom} onChange={e=>setFilterFrom(e.target.value)}/>
          <span className="text-gray-300">→</span>
          <input type="date" className="border border-gray-200 rounded-lg px-2 py-1.5 text-xs bg-gray-50" value={filterTo} onChange={e=>setFilterTo(e.target.value)}/>
          {(search||filterStatus!=='All'||filterPriority!=='All'||filterFrom||filterTo) && (
            <button onClick={()=>{setSearch('');setFilterStatus('All');setFilterPriority('All');setFilterFrom('');setFilterTo('')}}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 border border-gray-200 rounded-lg px-2 py-1.5 bg-white">
              <X size={11}/> Clear
            </button>
          )}
        </div>
      </div>

      {isLoading && <div className="flex items-center gap-2 text-gray-500 justify-center py-10"><Loader2 className="animate-spin" size={18}/>Loading jobs...</div>}
      {isError   && <div className="flex items-center gap-2 text-red-500 justify-center py-10"><AlertCircle size={18}/>Failed to load jobs.</div>}

      {/* ── Table ───────────────────────────────────────── */}
      {!isLoading && !isError && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden mt-4">
          <div className="overflow-x-auto scrollbar-thin" style={{overflowX:'auto', WebkitOverflowScrolling:'touch'}}>
            <table className="w-full text-sm table-fixed">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500 font-semibold uppercase tracking-wide">
                  <th className="w-8 px-4 py-3"/>
                  <th className="text-left px-3 py-3 w-auto">Job / Customer</th>
                  <th className="text-left px-3 py-3 w-28">Timer</th>
                  <th className="text-left px-3 py-3 w-44">Timeline</th>
                  <th className="text-right px-2 py-3 w-36">Actions</th>
                </tr>
              </thead>
              <tbody>
                {!groupByCustomer
                  ? filtered.map(job => <JobRow key={job.id} job={job}/>)
                  : Object.entries(customerGroups).map(([customer, cJobs]) => (
                      <React.Fragment key={`grp-${customer}`}>
                        <tr className="bg-gray-100">
                          <td colSpan={5} className="px-4 py-2">
                            <div className="flex items-center gap-2 text-xs font-semibold text-gray-600 uppercase tracking-wide">
                              <FolderOpen size={12} className="text-blue-500"/>
                              {customer}
                              <span className="font-normal text-gray-400">({cJobs.length} job{cJobs.length!==1?'s':''})</span>
                            </div>
                          </td>
                        </tr>
                        {cJobs.map(job => <JobRow key={job.id} job={job}/>)}
                      </React.Fragment>
                    ))
                }
                {filtered.length === 0 && (
                  <tr><td colSpan={5} className="text-center text-gray-400 py-10 text-sm">No jobs match your filters.</td></tr>
                )}
              </tbody>
              {filtered.length > 0 && (() => {
                const totalOV     = filtered.reduce((s,j) => s + (j.order_value??0), 0)
                const totalCosts  = filtered.reduce((s,j) => s + jobCost(j), 0)
                const totalProfit = totalOV - totalCosts
                return (
                  <tfoot>
                    <tr className="bg-gray-50 border-t-2 border-gray-200">
                      <td colSpan={5} className="px-4 py-2.5 text-xs text-gray-400">
                        <span className="font-semibold text-gray-600">{filtered.length}</span> job{filtered.length!==1?'s':''} shown
                        {filtered.filter(j=>j.status==='In Progress').length > 0 && (
                          <span className="ml-3 text-green-600">· <span className="font-semibold">{filtered.filter(j=>j.status==='In Progress').length}</span> in progress</span>
                        )}
                        {filtered.filter(j=>j.has_conflict).length > 0 && (
                          <span className="ml-3 text-red-500 font-semibold">· ⚠ {filtered.filter(j=>j.has_conflict).length} conflict{filtered.filter(j=>j.has_conflict).length>1?'s':''}</span>
                        )}
                      </td>
                    </tr>
                  </tfoot>
                )
              })()}
            </table>
          </div>

        </div>
      )}

      {/* ══ NEW JOB WIZARD ══════════════════════════════════ */}
      {wizardOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div>
                <h3 className="font-bold text-gray-800">{labels.newJobButton}</h3>
                <div className="flex items-center gap-2 mt-1">
                  {[`${labels.job} Details`,`${labels.machines} & People`,`${labels.materials} & Confirm`].map((label,i)=>(
                    <div key={i} className="flex items-center gap-1.5">
                      <span className={`w-5 h-5 rounded-full text-xs flex items-center justify-center font-bold ${wizardStep>i+1?'bg-green-500 text-white':wizardStep===i+1?'bg-blue-600 text-white':'bg-gray-200 text-gray-400'}`}>
                        {wizardStep>i+1?'✓':i+1}
                      </span>
                      <span className={`text-xs ${wizardStep===i+1?'text-blue-600 font-medium':'text-gray-400'}`}>{label}</span>
                      {i<2 && <ChevronRight size={12} className="text-gray-300"/>}
                    </div>
                  ))}
                </div>
              </div>
              <button onClick={closeWizard}><X size={18} className="text-gray-400 hover:text-gray-600"/></button>
            </div>

            {/* Step 1: Details + Start Mode */}
            {wizardStep===1 && (
              <div className="p-6 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Job Name *</label>
                    <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.name} onChange={e=>setDetails({...details,name:e.target.value})} placeholder="e.g. CNC Shaft Machining"/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Customer</label>
                    <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.customer} onChange={e=>setDetails({...details,customer:e.target.value})} placeholder="e.g. Tata Motors"/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Order Value (₹)</label>
                    <input type="number" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="Total contract / order value"
                      value={details.order_value} onChange={e=>setDetails({...details,order_value:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Misc / Overhead Cost (₹)</label>
                    <input type="number" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g. transport, consumables"
                      value={details.misc_cost} onChange={e=>setDetails({...details,misc_cost:e.target.value})}/>
                  </div>
                </div>

                {/* Start Mode selector */}
                <div className="border border-gray-200 rounded-xl p-4 bg-gray-50">
                  <StartModeSelector
                    value={details.start_mode}
                    onChange={v => setDetails({...details, start_mode: v as typeof details.start_mode})}
                    startDate={details.start_date}
                    onStartDateChange={v => setDetails({...details, start_date:v})}
                    earliestDate={details.earliest_date}
                    onEarliestChange={v => setDetails({...details, earliest_date:v})}
                    latestDate={details.latest_date}
                    onLatestChange={v => setDetails({...details, latest_date:v})}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">End Date *</label>
                    <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.end_date} onChange={e=>setDetails({...details,end_date:e.target.value})}/>
                    <p className="text-xs text-gray-400 mt-1">The date by which production must be complete.</p>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Delivery Date (optional)</label>
                    <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.delivery_date} onChange={e=>setDetails({...details,delivery_date:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Hours / Day</label>
                    <input type="number" min="1" max="24" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.estimated_hours_per_day} onChange={e=>setDetails({...details,estimated_hours_per_day:Number(e.target.value)})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Priority</label>
                    <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.priority} onChange={e=>setDetails({...details,priority:e.target.value})}>
                      {PRIORITIES.map(p=><option key={p}>{p}</option>)}
                    </select>
                    <p className="text-xs text-gray-400 mt-1">Critical and High priority jobs are scheduled first.</p>
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                    <textarea className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                      rows={2} value={details.notes} onChange={e=>setDetails({...details,notes:e.target.value})}/>
                  </div>
                  {/* v3.9.6 — Job Type + Quantity */}
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Job Type</label>
                    <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g. Corrugated Box, Label…"
                      value={details.job_type} onChange={e=>setDetails({...details,job_type:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Quantity</label>
                    <input type="number" min={0} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="Units to produce"
                      value={details.quantity} onChange={e=>setDetails({...details,quantity:e.target.value})}/>
                  </div>
                </div>

                <div className="flex gap-2 pt-2">
                  <button
                    onClick={()=>{ if(details.name&&details.end_date&&(details.start_mode==='flexible'?details.earliest_date:details.start_date)) setWizardStep(2) }}
                    disabled={!details.name || !details.end_date || (details.start_mode==='flexible' ? !details.earliest_date : !details.start_date)}
                    className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm py-2.5 rounded-xl font-medium">
                    Next — {labels.skills} & People <ChevronRight size={15}/>
                  </button>
                  <button onClick={closeWizard} className="px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-xl">Cancel</button>
                </div>
              </div>
            )}

            {/* Step 2: Machines → Skills → People (same as before) */}
            {wizardStep===2 && (
              <div className="p-6 space-y-5">
                <div>
                  <h4 className="font-semibold text-gray-700 flex items-center gap-2 mb-1">
                    <Factory size={15} className="text-green-600"/> Step 1 — Select {labels.machines}
                  </h4>
                  <p className="text-xs text-gray-400 mb-3">Selecting a machine auto-adds its skill requirements below.</p>
                  {machines.filter(m=>m.status==='Operational').length === 0
                    ? <p className="text-xs text-gray-400 italic">No operational machines found.</p>
                    : <div className="grid grid-cols-2 gap-2">
                        {machines.filter(m=>m.status==='Operational').map(m=>{
                          const sel = selectedMachines.includes(m.id)
                          return (
                            <button key={m.id} type="button"
                              onClick={()=>{
                                if (sel) {
                                  setSelectedMachines(p=>p.filter(x=>x!==m.id))
                                  setSkillReqs(prev => prev.filter(r => !(r as SkillReq & {fromMachine?:number}).fromMachine === m.id))
                                } else {
                                  setSelectedMachines(p=>[...p,m.id])
                                  const newReqs = (m.skill_requirements||[]).map(sr=>({...sr, fromMachine: m.id}))
                                  setSkillReqs(prev=>{
                                    const merged = [...prev]
                                    newReqs.forEach(nr=>{
                                      const exists = merged.find(r=>r.skill_id===nr.skill_id && r.min_skill_level===nr.min_skill_level)
                                      if (exists) exists.employees_required = Math.max(exists.employees_required, nr.employees_required)
                                      else merged.push(nr)
                                    })
                                    return merged
                                  })
                                }
                                setWizardCheck(null)
                              }}
                              className={`flex flex-col items-start gap-1 p-3 rounded-xl border text-left transition-all ${
                                sel ? 'border-green-500 bg-green-50 ring-1 ring-green-300' : 'border-gray-200 hover:border-green-300 hover:bg-gray-50'
                              }`}>
                              <div className="flex items-center gap-2 w-full">
                                <Factory size={14} className={sel?'text-green-600':'text-gray-400'}/>
                                <span className="text-sm font-medium text-gray-800 truncate">{m.name}</span>
                                {sel && <Check size={13} className="text-green-600 ml-auto shrink-0"/>}
                              </div>
                              {m.location_bay && <span className="text-xs text-gray-400 pl-5">Bay: {m.location_bay}</span>}
                            </button>
                          )
                        })}
                      </div>
                  }
                </div>
                <hr className="border-gray-100"/>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-semibold text-gray-700 flex items-center gap-2"><Users size={15} className="text-blue-500"/> Step 2 — Skill Requirements</h4>
                    <button onClick={()=>setSkillReqs(r=>[...r,{skill_id:skills[0]?.id??0,min_skill_level:'Generic',employees_required:1}])}
                      className="flex items-center gap-1.5 text-xs text-blue-600 border border-blue-200 rounded-lg px-3 py-1.5">
                      <Plus size={12}/> Add Skill
                    </button>
                  </div>
                  {skillReqs.length===0
                    ? <div className="border-2 border-dashed border-gray-200 rounded-xl p-4 text-center text-xs text-gray-400">Select a machine above or click "Add Skill".</div>
                    : skillReqs.map((req,i)=>(
                        <div key={i} className={`mb-2 rounded-xl border ${(req as SkillReq & {fromMachine?:number}).fromMachine?'bg-green-50 border-green-200':'bg-gray-50 border-gray-200'}`}>
                          <div className="flex gap-2 items-center p-3">
                            <select className="flex-1 border border-gray-300 rounded-lg px-2 py-1.5 text-sm bg-white"
                              value={req.skill_id} onChange={e=>setSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,skill_id:Number(e.target.value)}:s))}>
                              {skills.map(s=><option key={s.id} value={s.id}>{s.name}{s.is_premium?' ⭐':''}</option>)}
                            </select>
                            <select className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm bg-white"
                              value={req.min_skill_level} onChange={e=>setSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,min_skill_level:e.target.value}:s))}>
                              {LEVELS.map(l=><option key={l}>{l}</option>)}
                            </select>
                            <span className="text-xs text-gray-500">×</span>
                            <input type="number" min="1" className="w-14 border border-gray-300 rounded-lg px-2 py-1.5 text-sm bg-white"
                              value={req.employees_required} onChange={e=>setSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,employees_required:Number(e.target.value)}:s))}/>
                            <button onClick={()=>setSkillReqs(r=>r.filter((_,idx)=>idx!==i))} className="text-red-400 hover:text-red-600"><X size={14}/></button>
                          </div>
                          {/* Per-skill availability feedback */}
                          {(() => {
                            const available = wizardCheck?.available_employees?.[String(i)]?.length ?? null
                            if (wizardChecking) return <div className="px-3 pb-2 text-xs text-gray-400 flex items-center gap-1"><Loader2 size={10} className="animate-spin"/>Checking...</div>
                            if (available === null) return null
                            const ok = available >= req.employees_required
                            return (
                              <div className={`px-3 pb-2 text-xs font-medium flex items-center gap-1 ${ok ? 'text-green-700' : 'text-red-600'}`}>
                                {ok ? <Check size={11}/> : <AlertTriangle size={11}/>}
                                Need {req.employees_required} · <span className="font-bold">{available} available</span>
                                {!ok && <span className="font-normal text-red-500 ml-1">— add staff or lower level</span>}
                              </div>
                            )
                          })()}
                        </div>
                      ))
                  }
                </div>
                {skillReqs.length>0 && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-gray-700 flex items-center gap-2"><UserCheck size={15} className="text-purple-500"/> Step 3 — Available People</h4>
                      {wizardChecking && <span className="flex items-center gap-1 text-xs text-gray-400"><Loader2 size={11} className="animate-spin"/>Checking...</span>}
                    </div>
                    {wizardCheck && !wizardChecking && (
                      <div className={`${scoreColour(wizardCheck.feasibility_score).bg} rounded-lg px-4 py-2.5 flex items-center justify-between`}>
                        <span className={`text-sm font-semibold ${scoreColour(wizardCheck.feasibility_score).text}`}>
                          {wizardCheck.feasible ? '✓ All requirements can be met' : '⚠ Some requirements cannot be fully met'}
                        </span>
                        <span className={`text-lg font-black ${scoreColour(wizardCheck.feasibility_score).text}`}>{wizardCheck.feasibility_score}%</span>
                      </div>
                    )}
                  </div>
                )}
                <div className="flex gap-2">
                  <button onClick={()=>setWizardStep(1)} className="flex items-center gap-1.5 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-xl"><ChevronLeft size={15}/>Back</button>
                  <button onClick={()=>setWizardStep(3)} className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm py-2.5 rounded-xl font-medium">
                    Next — {labels.materials} & Confirm <ChevronRight size={15}/>
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Raw Materials + Confirm */}
            {wizardStep===3 && (
              <div className="p-6 space-y-5">
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h4 className="font-semibold text-gray-700 flex items-center gap-1.5"><Package size={15} className="text-orange-500"/>{labels.materials}</h4>
                      <p className="text-xs text-gray-400">Add materials needed for this job.</p>
                    </div>
                    <button onClick={()=>setRawMats(m=>[...m,emptyMat()])}
                      disabled={rawMatLimitReached(rawMats.length)}
                      className={`flex items-center gap-1.5 text-xs border rounded-lg px-3 py-1.5 ${rawMatLimitReached(rawMats.length)?'text-gray-400 border-gray-200 cursor-not-allowed':'text-orange-600 border-orange-200 hover:bg-orange-50'}`}>
                      <Plus size={12}/> Add Material
                    </button>
                  </div>
                  <RawMaterialLimitHint current={rawMats.length} planLimits={planLimits} />
                  {rawMats.length===0 && <div className="border-2 border-dashed border-gray-200 rounded-xl p-4 text-center text-sm text-gray-400">No raw materials added yet.</div>}
                  {rawMats.map((mat,i)=>(
                    <div key={i} className="grid grid-cols-12 gap-2 mb-2 items-center">
                      <input className="col-span-4 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" placeholder="Material name" value={mat.name} onChange={e=>setRawMats(m=>m.map((r,idx)=>idx===i?{...r,name:e.target.value}:r))}/>
                      <input type="number" min="0" step="0.1" className="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" placeholder="Qty" value={mat.quantity} onChange={e=>setRawMats(m=>m.map((r,idx)=>idx===i?{...r,quantity:Number(e.target.value)}:r))}/>
                      <select className="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" value={mat.unit} onChange={e=>setRawMats(m=>m.map((r,idx)=>idx===i?{...r,unit:e.target.value}:r))}>
                        {UNITS.map(u=><option key={u}>{u}</option>)}
                      </select>
                      <input type="number" min="0" className="col-span-3 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" placeholder="Unit cost ₹" value={mat.unit_cost} onChange={e=>setRawMats(m=>m.map((r,idx)=>idx===i?{...r,unit_cost:Number(e.target.value)}:r))}/>
                      <button onClick={()=>setRawMats(m=>m.filter((_,idx)=>idx!==i))} className="col-span-1 text-red-400 hover:text-red-600 flex justify-center"><X size={14}/></button>
                    </div>
                  ))}
                  {rawMats.length>0 && <div className="text-right text-sm font-semibold text-orange-700 mt-2">Total Materials: ₹{matTotal(rawMats).toLocaleString('en-IN')}</div>}
                </div>
                <div className="bg-gray-50 rounded-xl p-4 text-sm space-y-1.5">
                  <p className="font-semibold text-gray-700 mb-2">Confirm Details</p>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div><span className="text-gray-500">Job:</span> <span className="font-medium">{details.name}</span></div>
                    <div><span className="text-gray-500">Customer:</span> <span className="font-medium">{details.customer||'—'}</span></div>
                    <div><span className="text-gray-500">Schedule:</span> <span className="font-medium capitalize">{details.start_mode.replace(/_/g,' ')}</span></div>
                    <div><span className="text-gray-500">Priority:</span> <span className={`px-2 py-0.5 rounded-full font-medium border ${priorityColour[details.priority]??''}`}>{details.priority}</span></div>
                    <div><span className="text-gray-500">Lock:</span> <span className="font-medium">{details.start_mode === 'flexible' ? 'Flexible (scheduler can move)' : 'Locked (fixed date)'}</span></div>
                  </div>
                  {selectedEmps.length>0 && <p className="text-xs text-green-700 mt-1">· {selectedEmps.length} employee(s) will be assigned</p>}
                  {selectedMachines.length>0 && <p className="text-xs text-green-700">· {selectedMachines.length} machine(s) will be assigned</p>}
                  {rawMats.length>0 && <p className="text-xs text-orange-700">· {rawMats.length} raw material(s) — ₹{matTotal(rawMats).toLocaleString('en-IN')}</p>}
                  {selectedEmps.length===0&&selectedMachines.length===0 && (
                    <p className="text-xs text-yellow-600 flex items-center gap-1 mt-1"><AlertTriangle size={11}/>No resources selected — can assign later.</p>
                  )}
                </div>
                <div className="flex gap-2">
                  <button onClick={()=>setWizardStep(2)} className="flex items-center gap-1.5 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-xl"><ChevronLeft size={15}/>Back</button>
                  <button onClick={submitWizard} disabled={createJob.isPending}
                    className="flex-1 flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-sm py-2.5 rounded-xl font-medium">
                    {createJob.isPending ? <><Loader2 className="animate-spin" size={15}/>Creating...</> : <><Check size={15}/>{selectedEmps.length>0||selectedMachines.length>0?'Create Job & Assign':'Create Job'}</>}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}


      {/* ══ ASSIGN DRAWER ══════════════════════════════════ */}
      {assignJob && (
        <div className="fixed inset-0 bg-black/40 z-50 flex justify-end">
          <div className="bg-white w-full max-w-lg h-full shadow-2xl flex flex-col">
            <div className="px-5 py-4 border-b border-gray-200 flex items-start justify-between shrink-0">
              <div>
                <p className="font-bold text-gray-800">Assign Resources</p>
                <p className="text-xs text-blue-600 font-medium mt-0.5">{assignJob.name}</p>
                <p className="text-xs text-gray-400">{assignJob.start_date} → {assignJob.end_date}</p>
              </div>
              <button onClick={()=>setAssignJob(null)}><X size={18} className="text-gray-400 hover:text-gray-600"/></button>
            </div>
            <div className="flex border-b border-gray-200 shrink-0 bg-gray-50">
              {(['machines','people','extras'] as const).map(tab => (
                <button key={tab} onClick={()=>setAssignTab(tab)}
                  className={`flex-1 py-3 text-xs font-semibold border-b-2 transition-colors ${assignTab===tab?'border-blue-600 text-blue-600 bg-white':'border-transparent text-gray-500 hover:text-gray-700'}`}>
                  {tab === 'machines' ? `🔧 ${labels.machines}` : tab === 'people' ? '👷 Skilled People' : '➕ Extra People'}
                </button>
              ))}
            </div>
            {assignChecking && <div className="flex-1 flex items-center justify-center"><Loader2 className="animate-spin" size={18} /></div>}
            {!assignChecking && !assignCheck && <div className="flex-1 flex items-center justify-center"><p className="text-sm text-red-400">Failed to load availability data.</p></div>}
            {assignCheck && !assignChecking && (
              <div className="flex-1 overflow-y-auto">
                <div className={`${scoreColour(assignCheck.feasibility_score).bg} px-5 py-2.5 flex items-center justify-between`}>
                  <span className={`text-xs font-semibold ${scoreColour(assignCheck.feasibility_score).text}`}>
                    {assignCheck.feasible ? '✓ All requirements can be met' : '⚠ Some requirements cannot be fully met'}
                  </span>
                  <span className={`text-base font-black ${scoreColour(assignCheck.feasibility_score).text}`}>{assignCheck.feasibility_score}%</span>
                </div>
                {assignTab === 'machines' && (
                  <div className="p-5 space-y-3">
                    {assignCheck.machines.length === 0
                      ? <p className="text-sm text-gray-400 italic">No operational machines available.</p>
                      : assignCheck.machines.map(m => {
                          const sel = assignMachines.includes(m.id)
                          return (
                            <div key={m.id}
                              onClick={() => !m.available && !sel ? null : setAssignMachines(p => p.includes(m.id) ? p.filter(x=>x!==m.id) : [...p, m.id])}
                              className={`rounded-xl border p-3 cursor-pointer transition-all ${sel?'border-green-500 bg-green-50 ring-1 ring-green-300':!m.available?'border-gray-100 bg-gray-50 opacity-60 cursor-not-allowed':'border-gray-200 hover:border-green-300'}`}>
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <Factory size={14} className={sel?'text-green-600':'text-gray-400'}/>
                                  <span className="text-sm font-semibold text-gray-800">{m.name}</span>
                                  {sel && <Check size={13} className="text-green-600"/>}
                                </div>
                                {!m.available
                                  ? <span className="text-xs text-red-500 bg-red-50 px-2 py-0.5 rounded-full">{m.busy_reason}</span>
                                  : <span className="text-xs text-green-600 bg-green-100 px-2 py-0.5 rounded-full">Available</span>
                                }
                              </div>
                            </div>
                          )
                        })
                    }
                  </div>
                )}
                {assignTab === 'people' && (
                  <div className="p-5 space-y-4">
                    {assignCheck.skill_requirements.length === 0
                      ? <p className="text-sm text-gray-400 italic">No skill requirements. Go to Extras tab.</p>
                      : assignCheck.skill_requirements.map(req => {
                          const sel = req.available_employee_ids.filter(id => assignEmps.includes(id)).length
                          return (
                            <div key={req.id} className="border border-gray-200 rounded-xl overflow-hidden">
                              <div className="bg-gray-50 px-3 py-2 flex items-center justify-between border-b border-gray-100">
                                <span className="text-xs font-semibold text-gray-800">{req.skill_name} · {req.min_skill_level}</span>
                                <span className={`text-xs font-bold ${sel>=req.employees_required?'text-green-600':'text-orange-600'}`}>{sel}/{req.employees_required}</span>
                              </div>
                              <div className="p-2 space-y-1">
                                {req.available_employee_ids.length === 0
                                  ? <p className="text-xs text-red-500 italic p-2">No qualified employees available.</p>
                                  : req.available_employee_ids.map(empId => {
                                      const emp = assignCheck.employees.find(e => e.id === empId)
                                      if (!emp) return null
                                      return (
                                        <label key={empId} className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer text-xs transition-colors ${assignEmps.includes(empId)?'border-blue-400 bg-blue-50':'border-transparent hover:bg-gray-50'}`}>
                                          <input type="checkbox" checked={assignEmps.includes(empId)}
                                            onChange={() => setAssignEmps(p => p.includes(empId) ? p.filter(e=>e!==empId) : [...p,empId])} className="rounded"/>
                                          <span className="font-medium text-gray-800">{emp.full_name}</span>
                                          {emp.department && <span className="text-gray-400">{emp.department}</span>}
                                          {emp.hourly_rate != null && <span className="ml-auto text-gray-400">₹{emp.hourly_rate}/hr</span>}
                                        </label>
                                      )
                                    })
                                }
                              </div>
                            </div>
                          )
                        })
                    }
                  </div>
                )}
                {assignTab === 'extras' && (
                  <div className="p-5 space-y-3">
                    <p className="text-xs text-gray-500">Add helpers or support staff without specific skills.</p>
                    {assignCheck.employees.filter(e => e.available).map(emp => (
                      <label key={emp.id} className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border cursor-pointer text-xs transition-colors ${assignEmps.includes(emp.id)?'border-blue-400 bg-blue-50':'border-gray-200 hover:bg-gray-50'}`}>
                        <input type="checkbox" checked={assignEmps.includes(emp.id)}
                          onChange={() => setAssignEmps(p => p.includes(emp.id) ? p.filter(e=>e!==emp.id) : [...p,emp.id])} className="rounded"/>
                        <span className="font-medium text-gray-800">{emp.full_name}</span>
                        {emp.department && <span className="text-gray-400">{emp.department}</span>}
                      </label>
                    ))}
                  </div>
                )}
                {assignError && (
                  <div className="mx-5 mb-3 flex items-center gap-2 text-red-600 bg-red-50 border border-red-200 rounded-xl px-3 py-2.5 text-xs">
                    <AlertCircle size={14}/>{assignError}
                  </div>
                )}
              </div>
            )}
            <div className="px-5 py-4 border-t border-gray-200 shrink-0">
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-3">
                <span><Factory size={11} className="inline text-green-600 mr-0.5"/><strong className="text-green-700">{assignMachines.length}</strong> machines</span>
                <span>·</span>
                <span><Users size={11} className="inline text-blue-500 mr-0.5"/><strong className="text-blue-700">{assignEmps.length}</strong> people</span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={()=>assignMut.mutate({job_id:assignJob.id,employee_ids:assignEmps,machine_ids:assignMachines})}
                  disabled={assignMut.isPending||(assignEmps.length===0&&assignMachines.length===0)}
                  className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm py-2.5 rounded-xl font-medium">
                  {assignMut.isPending ? <><Loader2 className="animate-spin" size={15}/>Saving...</> : <><ClipboardCheck size={15}/>Confirm Assignment</>}
                </button>
                <button onClick={()=>setAssignJob(null)} className="px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-xl">Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══ EDIT MODAL ══════════════════════════════════════ */}
      {editJob && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h3 className="font-bold text-gray-800">Edit Job — {jobDisplayId(editJob, jobPrefix)}</h3>
              <button onClick={()=>setEditJob(null)}><X size={18} className="text-gray-400 hover:text-gray-600"/></button>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Job Name</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.name} onChange={e=>setEditForm({...editForm,name:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Customer</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.customer} onChange={e=>setEditForm({...editForm,customer:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Order Value (₹)</label>
                  <input type="number" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.order_value} onChange={e=>setEditForm({...editForm,order_value:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Misc / Overhead (₹)</label>
                  <input type="number" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.misc_cost} onChange={e=>setEditForm({...editForm,misc_cost:e.target.value})}/>
                </div>
              </div>
              {/* Start Mode in edit */}
              <div className="border border-gray-200 rounded-xl p-4 bg-gray-50">
                <StartModeSelector
                  value={editForm.start_mode}
                  onChange={v => setEditForm({...editForm, start_mode: v as typeof editForm.start_mode})}
                  startDate={editForm.start_date}
                  onStartDateChange={v => setEditForm({...editForm, start_date:v})}
                  earliestDate={editForm.earliest_date}
                  onEarliestChange={v => setEditForm({...editForm, earliest_date:v})}
                  latestDate={editForm.latest_date}
                  onLatestChange={v => setEditForm({...editForm, latest_date:v})}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">End Date</label>
                  <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.end_date} onChange={e=>setEditForm({...editForm,end_date:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Priority</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.priority} onChange={e=>setEditForm({...editForm,priority:e.target.value})}>
                    {PRIORITIES.map(p=><option key={p}>{p}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.status} onChange={e=>setEditForm({...editForm,status:e.target.value})}>
                    {STATUSES.map(s=><option key={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Delivery Date</label>
                  <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.delivery_date} onChange={e=>setEditForm({...editForm,delivery_date:e.target.value})}/>
                </div>
              </div>
              {/* Invoice & Payment */}
              <div className="border border-gray-200 rounded-xl p-4 bg-gray-50 space-y-3">
                <p className="text-xs font-semibold text-gray-600 flex items-center gap-1.5"><IndianRupee size={12} className="text-green-600"/>Invoice & Payment</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Invoice Number</label>
                    <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g. INV-2024-001"
                      value={editForm.invoice_number} onChange={e=>setEditForm({...editForm,invoice_number:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Invoice Date</label>
                    <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={editForm.invoice_date} onChange={e=>setEditForm({...editForm,invoice_date:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Payment Status</label>
                    <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={editForm.payment_status} onChange={e=>setEditForm({...editForm,payment_status:e.target.value})}>
                      {['Unpaid','Partial','Paid'].map(s=><option key={s}>{s}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Amount Received (₹)</label>
                    <input type="number" min="0" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="0"
                      value={editForm.payment_amount} onChange={e=>setEditForm({...editForm,payment_amount:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Payment Date</label>
                    <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={editForm.payment_date} onChange={e=>setEditForm({...editForm,payment_date:e.target.value})}/>
                  </div>
                  {/* v3.9.6 */}
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Job Type</label>
                    <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g. Corrugated Box, Label…"
                      value={editForm.job_type} onChange={e=>setEditForm({...editForm,job_type:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Quantity</label>
                    <input type="number" min={0} className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="Units to produce"
                      value={editForm.quantity} onChange={e=>setEditForm({...editForm,quantity:e.target.value})}/>
                  </div>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-gray-600">Skill Requirements</label>
                  <button onClick={()=>setEditSkillReqs(r=>[...r,{skill_id:skills[0]?.id??0,min_skill_level:'Generic',employees_required:1}])}
                    className="text-xs text-blue-600 flex items-center gap-1"><Plus size={12}/>Add</button>
                </div>
                {editSkillReqs.map((req,i)=>(
                  <div key={i} className="flex gap-2 mb-2 items-center">
                    <select className="flex-1 border border-gray-300 rounded-lg px-2 py-1.5 text-xs"
                      value={req.skill_id} onChange={e=>setEditSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,skill_id:Number(e.target.value)}:s))}>
                      {skills.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                    <select className="border border-gray-300 rounded-lg px-2 py-1.5 text-xs"
                      value={req.min_skill_level} onChange={e=>setEditSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,min_skill_level:e.target.value}:s))}>
                      {LEVELS.map(l=><option key={l}>{l}</option>)}
                    </select>
                    <input type="number" min="1" className="w-16 border border-gray-300 rounded-lg px-2 py-1.5 text-xs"
                      value={req.employees_required} onChange={e=>setEditSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,employees_required:Number(e.target.value)}:s))}/>
                    <button onClick={()=>setEditSkillReqs(r=>r.filter((_,idx)=>idx!==i))} className="text-red-400 hover:text-red-600"><X size={14}/></button>
                  </div>
                ))}
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-gray-600 flex items-center gap-1"><Package size={12} className="text-orange-500"/>{labels.materials}</label>
                  <div className="flex items-center gap-2">
                    <RawMaterialLimitHint current={editRawMats.length} planLimits={planLimits} />
                    <button onClick={()=>setEditRawMats(m=>[...m,emptyMat()])} disabled={rawMatLimitReached(editRawMats.length)}
                      className={`text-xs flex items-center gap-1 ${rawMatLimitReached(editRawMats.length)?'text-gray-300 cursor-not-allowed':'text-orange-600'}`}>
                      <Plus size={12}/>Add
                    </button>
                  </div>
                </div>
                {editRawMats.map((mat,i)=>(
                  <div key={i} className="grid grid-cols-12 gap-2 mb-2 items-center">
                    <input className="col-span-4 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" placeholder="Material" value={mat.name} onChange={e=>setEditRawMats(m=>m.map((r,idx)=>idx===i?{...r,name:e.target.value}:r))}/>
                    <input type="number" className="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" value={mat.quantity} onChange={e=>setEditRawMats(m=>m.map((r,idx)=>idx===i?{...r,quantity:Number(e.target.value)}:r))}/>
                    <select className="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" value={mat.unit} onChange={e=>setEditRawMats(m=>m.map((r,idx)=>idx===i?{...r,unit:e.target.value}:r))}>
                      {UNITS.map(u=><option key={u}>{u}</option>)}
                    </select>
                    <input type="number" className="col-span-3 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" value={mat.unit_cost} onChange={e=>setEditRawMats(m=>m.map((r,idx)=>idx===i?{...r,unit_cost:Number(e.target.value)}:r))}/>
                    <button onClick={()=>setEditRawMats(m=>m.filter((_,idx)=>idx!==i))} className="col-span-1 text-red-400 hover:text-red-600 flex justify-center"><X size={14}/></button>
                  </div>
                ))}
                {editRawMats.length>0 && <div className="text-right text-xs font-semibold text-orange-700">Total: ₹{matTotal(editRawMats).toLocaleString('en-IN')}</div>}
              </div>
            </div>
            <div className="flex gap-2 px-6 pb-6">
              <button onClick={submitEdit} disabled={!editForm.name||updateJob.isPending}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm py-2.5 rounded-lg font-medium">
                {updateJob.isPending?'Saving...':'Update Job'}
              </button>
              <button onClick={()=>setEditJob(null)} className="px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-lg">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* ══ JOB REPORT / PDF EXPORT MODAL ══════════════════ */}
      {pdfJob && (() => {
        const job = pdfJob
        const rawTotal  = matTotal(job.raw_materials || [])
        const totalCost = jobCost(job)
        const profit    = jobProfit(job)
        const displayId = jobDisplayId(job, jobPrefix)
        const duration  = job.start_date && job.end_date
          ? Math.max((new Date(job.end_date).getTime() - new Date(job.start_date).getTime()) / 86400000 + 1, 1)
          : null
        const estHours  = duration ? duration * job.estimated_hours_per_day : null
        const overrunPct = job.actual_hours && estHours
          ? Math.round(((job.actual_hours - estHours) / estHours) * 100)
          : null
        return (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] overflow-y-auto">
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 no-print">
                <div>
                  <h3 className="font-bold text-gray-800">Job Report — {displayId}</h3>
                  <p className="text-xs text-gray-400 mt-0.5">Preview before printing</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => window.print()}
                    className="flex items-center gap-1.5 text-sm font-medium px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700">
                    <Package size={14}/> Print / Save PDF
                  </button>
                  <button onClick={() => setPdfJob(null)}><X size={18} className="text-gray-400 hover:text-gray-600"/></button>
                </div>
              </div>

              {/* Printable content */}
              <div id="job-report-print" className="p-6 space-y-5">
                {/* Job header */}
                <div className="flex items-start justify-between border-b border-gray-200 pb-4">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-500">{displayId}</span>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${STATUS_STYLE[job.status]??''}`}>{job.status}</span>
                    </div>
                    <h2 className="text-xl font-bold text-gray-900">{job.name}</h2>
                    {job.customer && <p className="text-sm text-gray-500 mt-0.5">Customer: {job.customer}</p>}
                  </div>
                  <div className="text-right text-xs text-gray-400">
                    <p>Generated: {new Date().toLocaleDateString('en-IN')}</p>
                    {job.invoice_number && <p className="font-semibold text-gray-700 mt-0.5">Invoice: {job.invoice_number}</p>}
                  </div>
                </div>

                {/* Dates & hours */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-gray-50 rounded-xl border border-gray-200 p-3 text-center">
                    <p className="text-xs text-gray-400 mb-1">Start → End</p>
                    <p className="text-sm font-semibold text-gray-800">{job.start_date} → {job.end_date}</p>
                  </div>
                  {job.delivery_date && (
                    <div className="bg-blue-50 rounded-xl border border-blue-200 p-3 text-center">
                      <p className="text-xs text-blue-400 mb-1">Delivery Date</p>
                      <p className="text-sm font-semibold text-blue-700">{job.delivery_date}</p>
                    </div>
                  )}
                  <div className={`rounded-xl border p-3 text-center ${overrunPct != null && overrunPct > 10 ? 'bg-orange-50 border-orange-200' : 'bg-green-50 border-green-200'}`}>
                    <p className="text-xs text-gray-400 mb-1">Actual Hours</p>
                    <p className={`text-sm font-semibold ${overrunPct != null && overrunPct > 10 ? 'text-orange-700' : 'text-green-700'}`}>
                      {job.actual_hours != null ? `${job.actual_hours}h` : '—'}
                      {estHours != null && <span className="text-xs font-normal text-gray-400 ml-1">/ est. {estHours}h</span>}
                    </p>
                    {overrunPct != null && overrunPct > 10 && (
                      <p className="text-xs text-orange-600 mt-0.5">+{overrunPct}% overrun</p>
                    )}
                  </div>
                </div>

                {/* Cost summary */}
                <div>
                  <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">Cost Summary</p>
                  <div className="overflow-hidden rounded-xl border border-gray-200 divide-y divide-gray-100">
                    {[
                      ['Order Value', job.order_value != null ? `₹${job.order_value.toLocaleString('en-IN')}` : '—', ''],
                      [labels.materials, `₹${rawTotal.toLocaleString('en-IN')}`, 'text-red-500'],
                      ['Misc / Overhead', `₹${(job.misc_cost??0).toLocaleString('en-IN')}`, 'text-red-400'],
                      ['Total Cost', `₹${totalCost.toLocaleString('en-IN')}`, 'text-red-600 font-black'],
                      ['Profit', profit != null ? `${profit>=0?'+':''}₹${Math.abs(profit).toLocaleString('en-IN')}` : '—', profit != null ? (profit>=0 ? 'text-green-600 font-black' : 'text-red-600 font-black') : ''],
                    ].map(([label, value, cls]) => (
                      <div key={label} className="flex justify-between px-4 py-2 text-sm">
                        <span className="text-gray-500">{label}</span>
                        <span className={cls || 'font-medium text-gray-800'}>{value}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Assignments */}
                {(job.assigned_employees.length > 0 || job.assigned_machines.length > 0) && (
                  <div>
                    <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">Resources Used</p>
                    <div className="grid grid-cols-2 gap-3">
                      {job.assigned_employees.length > 0 && (
                        <div>
                          <p className="text-xs font-semibold text-blue-700 mb-1.5">Employees</p>
                          {job.assigned_employees.map(e => (
                            <div key={e.id} className="flex items-center gap-2 text-xs bg-blue-50 rounded-lg px-3 py-1.5 mb-1">
                              <span className="w-1.5 h-1.5 rounded-full bg-blue-400"/>
                              <span className="font-medium text-gray-700">{e.full_name}</span>
                              {e.allocation_pct != null && e.allocation_pct < 100 && (
                                <span className="text-gray-400 ml-auto">{e.allocation_pct}%</span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                      {job.assigned_machines.length > 0 && (
                        <div>
                          <p className="text-xs font-semibold text-purple-700 mb-1.5">Machines</p>
                          {job.assigned_machines.map(m => (
                            <div key={m.id} className="flex items-center gap-2 text-xs bg-purple-50 rounded-lg px-3 py-1.5 mb-1">
                              <span className="w-1.5 h-1.5 rounded-full bg-purple-400"/>
                              <span className="font-medium text-gray-700">{m.name}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Raw materials table */}
                {(job.raw_materials||[]).length > 0 && (
                  <div>
                    <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">{labels.materials}</p>
                    <table className="w-full text-xs border border-gray-200 rounded-xl overflow-hidden">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="text-left px-3 py-2 text-gray-500 font-semibold">Material</th>
                          <th className="text-right px-3 py-2 text-gray-500 font-semibold">Qty</th>
                          <th className="text-right px-3 py-2 text-gray-500 font-semibold">Unit</th>
                          <th className="text-right px-3 py-2 text-gray-500 font-semibold">Unit Cost</th>
                          <th className="text-right px-3 py-2 text-gray-500 font-semibold">Total</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {job.raw_materials.map((m, i) => (
                          <tr key={i} className="bg-white">
                            <td className="px-3 py-2 font-medium text-gray-700">{m.name}</td>
                            <td className="px-3 py-2 text-right text-gray-600">{m.quantity}</td>
                            <td className="px-3 py-2 text-right text-gray-400">{m.unit}</td>
                            <td className="px-3 py-2 text-right text-gray-600">₹{m.unit_cost.toLocaleString('en-IN')}</td>
                            <td className="px-3 py-2 text-right font-semibold text-gray-800">₹{(m.quantity*m.unit_cost).toLocaleString('en-IN')}</td>
                          </tr>
                        ))}
                        <tr className="bg-orange-50">
                          <td colSpan={4} className="px-3 py-2 font-semibold text-orange-700">Total Materials</td>
                          <td className="px-3 py-2 text-right font-bold text-orange-700">₹{rawTotal.toLocaleString('en-IN')}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Invoice & payment */}
                {(job.invoice_number || job.payment_status !== 'Unpaid') && (
                  <div>
                    <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">Invoice & Payment</p>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {job.invoice_number && (
                        <div className="bg-gray-50 rounded-lg border border-gray-200 px-3 py-2 flex justify-between">
                          <span className="text-gray-400">Invoice#</span>
                          <span className="font-semibold">{job.invoice_number}</span>
                        </div>
                      )}
                      {job.invoice_date && (
                        <div className="bg-gray-50 rounded-lg border border-gray-200 px-3 py-2 flex justify-between">
                          <span className="text-gray-400">Invoice Date</span>
                          <span className="font-semibold">{job.invoice_date}</span>
                        </div>
                      )}
                      <div className="bg-gray-50 rounded-lg border border-gray-200 px-3 py-2 flex justify-between">
                        <span className="text-gray-400">Payment</span>
                        <span className={`font-semibold ${job.payment_status==='Paid'?'text-green-600':job.payment_status==='Partial'?'text-amber-600':'text-red-500'}`}>
                          {job.payment_status}
                          {job.payment_amount != null && ` — ₹${job.payment_amount.toLocaleString('en-IN')}`}
                        </span>
                      </div>
                      {job.payment_date && (
                        <div className="bg-gray-50 rounded-lg border border-gray-200 px-3 py-2 flex justify-between">
                          <span className="text-gray-400">Payment Date</span>
                          <span className="font-semibold">{job.payment_date}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {job.notes && (
                  <div className="bg-yellow-50 border border-yellow-200 rounded-xl px-4 py-3 text-sm text-gray-600 italic">
                    📝 {job.notes}
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      })()}

      {/* Delete confirm */}
      {deleteId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 shadow-xl w-80 space-y-4">
            <h3 className="font-bold text-gray-800">Delete Job?</h3>
            <p className="text-sm text-gray-600">This permanently deletes the job and all its assignments.</p>
            <div className="flex gap-2">
              <button onClick={()=>deleteJobMut.mutate(deleteId)} className="flex-1 bg-red-600 hover:bg-red-700 text-white text-sm py-2 rounded-lg">{deleteJobMut.isPending?'Deleting...':'Yes, Delete'}</button>
              <button onClick={()=>setDeleteId(null)} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2 rounded-lg">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}