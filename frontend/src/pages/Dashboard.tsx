/**
 * frontend/src/pages/Dashboard.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * The main dashboard — the first page users see after login. Shows KPI cards
 * (active jobs, order book value, estimated profit, available resources), a jobs
 * status summary, upcoming jobs, and a live job list with cost breakdowns and
 * conflict indicators. Data fetches every 30 seconds automatically. The most
 * data-dense page in the application.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Fetches dashboard data via useDashboard() hook (auto-refetches every 30s).
 * 2. Renders 4 KPI cards using industry labels (kpiJobs, kpiOrderBook, kpiProfit).
 * 3. Renders jobs-by-status summary (Draft, Scheduled, In Progress, Completed).
 * 4. Renders upcoming jobs this week as a horizontal scroll list.
 * 5. Renders the full job list: each job shows timer controls, cost breakdown,
 *    conflict badge, assigned resources, and action buttons.
 * 6. Timer controls call timerApi (start/pause/resume/stop) and invalidate cache.
 * 7. End Job button opens EndJobModal for final cost confirmation.
 * 8. Industry-aware labels throughout (kpiJobs, kpiOrderBook, kpiProfit).
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — registered as /dashboard route (protected)
 *
 * INTERN NOTES
 * - Dashboard fetches everything in one call (GET /api/dashboard/) — not separate
 *   calls per section. This keeps the dashboard fast. The backend aggregates all data.
 * - Design Principle 1: conflict detection, cost calculations, and status icons are
 *   all pre-computed by the backend. Dashboard only renders them.
 * - The 30-second refetch (refetchInterval in useDashboard) keeps the shop floor
 *   status live during the workday. Do not increase this interval.
 * - useDashboard() uses queryKey ['dashboard'] — delete mutations in hooks_index.ts
 *   invalidate this key so dashboard stays current after deletions.
 */
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import {
  Pause,
  AlertCircle,
  Loader2,
  Clock,
  CalendarDays,
  Zap,
  BriefcaseBusiness,
} from 'lucide-react'
import apiClient from '../api/client'
import { useLabels } from '../context/IndustryContext'
import { CoachMark } from '../components/onboarding'
import timerApi from '../api/api_timer'
import EndJobModal from '../components/EndJobModal'
import type { DashboardData, DashboardJob } from '../api/api_dashboard'
import GettingStarted from '../components/onboarding/GettingStarted'
import EmptyState from '../components/EmptyState'

// ─── Poll interval ─────────────────────────────────────────────────────────
// Change this value to adjust how often dashboard checks for conflict resolution.
// Unit: milliseconds. Default: 30 seconds.
const POLL_INTERVAL_MS = 30_000

// ─── Helpers ───────────────────────────────────────────────────────────────
function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  return `₹${Math.round(n).toLocaleString('en-IN')}`
}

function getWeekNumber(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNum = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  return Math.ceil((((date.valueOf() - yearStart.valueOf()) / 86400000) + 1) / 7)
}

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

const priorityColour: Record<string, string> = {
  Critical: 'bg-red-100 text-red-700',
  High: 'bg-orange-100 text-orange-700',
  Medium: 'bg-yellow-100 text-yellow-700',
  Low: 'bg-gray-100 text-gray-600',
}

// ─── Status Icon ───────────────────────────────────────────────────────────
function StatusIcon({ icon }: { icon: string }) {
  if (icon === 'in_progress') {
    return (
      <span className="inline-flex items-center justify-center w-5 h-5">
        <svg viewBox="0 0 20 20" fill="none" className="w-5 h-5">
          <path d="M5 4l11 6-11 6V4z" fill="#16a34a" />
        </svg>
      </span>
    )
  }
  const dot: Record<string, string> = {
    ready: 'bg-green-500',
    conflict: 'bg-amber-500',   // amber = skill gap (most common); real conflicts shown red in card
    completed: 'bg-blue-500',
    stopped: 'bg-gray-900',
  }
  const color = dot[icon] ?? 'bg-gray-400'
  const blink = icon === 'ready' ? 'animate-pulse' : ''
  return (
    <span className={`inline-block w-3 h-3 rounded-full ${color} ${blink} flex-shrink-0`} />
  )
}

// ─── Cost Grid ─────────────────────────────────────────────────────────────
function CostGrid({ job }: { job: DashboardJob }) {
  return (
    <div className="grid grid-cols-2 gap-2 mt-2">
      <div className="bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
        <p className="text-xs text-amber-600 font-medium">Tentative Cost</p>
        <p className="text-sm font-bold text-amber-800">{fmt(job.tentative_cost)}</p>
      </div>
      <div className={`border rounded-lg px-3 py-2 ${job.tentative_profit >= 0 ? 'bg-green-50 border-green-100' : 'bg-red-50 border-red-100'}`}>
        <p className={`text-xs font-medium ${job.tentative_profit >= 0 ? 'text-green-600' : 'text-red-500'}`}>
          Tentative Profit
        </p>
        <div className="flex items-center gap-1">
          {job.tentative_profit >= 0
            ? <TrendingUp size={12} className="text-green-600" />
            : <TrendingDown size={12} className="text-red-500" />
          }
          <p className={`text-sm font-bold ${job.tentative_profit >= 0 ? 'text-green-700' : 'text-red-600'}`}>
            {fmt(job.tentative_profit)}
          </p>
        </div>
      </div>

      {job.actual_cost != null && (
        <>
          <div className="bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
            <p className="text-xs text-blue-600 font-medium">Actual Cost</p>
            <p className="text-sm font-bold text-blue-800">{fmt(job.actual_cost)}</p>
          </div>
          <div className={`border rounded-lg px-3 py-2 ${(job.actual_profit ?? 0) >= 0 ? 'bg-emerald-50 border-emerald-100' : 'bg-red-50 border-red-100'}`}>
            <p className={`text-xs font-medium ${(job.actual_profit ?? 0) >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
              Actual Profit
            </p>
            <div className="flex items-center gap-1">
              {(job.actual_profit ?? 0) >= 0
                ? <TrendingUp size={12} className="text-emerald-600" />
                : <TrendingDown size={12} className="text-red-500" />
              }
              <p className={`text-sm font-bold ${(job.actual_profit ?? 0) >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                {fmt(job.actual_profit)}
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Job Card ──────────────────────────────────────────────────────────────
interface JobCardProps {
  job: DashboardJob
  onAction: (jobId: number, action: 'start' | 'pause' | 'resume' | 'stop' | 'end') => void
  actionLoading: Record<string, boolean>
}

function JobCard({ job, onAction, actionLoading }: JobCardProps) {
  const [expanded, setExpanded] = useState(false)
  const labels = useLabels()
  const [jobDetail, setJobDetail] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const loading = actionLoading[job.id] ?? false

  // Fetch full job detail when expanded (to get assigned_employees/machines)
  useEffect(() => {
    if (!expanded || jobDetail) return
    setDetailLoading(true)
    apiClient.get(`/api/jobs/${job.id}`)
      .then(r => setJobDetail(r.data))
      .catch(() => {})
      .finally(() => setDetailLoading(false))
  }, [expanded, job.id, jobDetail])
  const t = job.timer_status

  const canStart = t === 'idle' && !job.has_conflict && job.status !== 'Completed' && job.status !== 'Stopped'
  const canPause = t === 'running'
  const canResume = t === 'paused'
  const canStop = t === 'running' || t === 'paused'
  const canEnd = t === 'running' || t === 'paused'
  const isDone = job.status === 'Completed' || job.status === 'Stopped'

  return (
    <div className={`bg-white rounded-xl border shadow-sm overflow-hidden transition-all ${
      job.has_conflict ? 'border-red-200' : 'border-gray-200'
    }`}>
      {/* Main row */}
      <div className="px-4 py-3">
        <div className="flex items-start gap-3">
          {/* Status icon */}
          <div className="mt-0.5">
            <StatusIcon icon={job.status_icon} />
          </div>

          {/* Job info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-semibold text-gray-900 truncate">{job.name}</span>
              {job.customer && (
                <span className="text-xs text-gray-400">· {job.customer}</span>
              )}
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${priorityColour[job.priority] ?? 'bg-gray-100 text-gray-600'}`}>
                {job.priority}
              </span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                {job.status}
              </span>
            </div>

            {/* Dates */}
            <p className="text-xs text-gray-400 mt-0.5">
              {job.start_date} → {job.end_date}
            </p>

            {/* Conflict warning — split skill gaps from scheduling conflicts */}
            {job.has_conflict && (() => {
              const reason = job.conflict_reasons[0] ?? ''
              const isSkillGap = reason.toLowerCase().includes('skill') ||
                                 reason.toLowerCase().includes('qualified') ||
                                 reason.toLowerCase().includes('no one assigned')
              return isSkillGap ? (
                <div className="mt-1.5 flex items-start gap-1.5 text-xs text-amber-700 bg-amber-50 rounded-lg px-2 py-1.5">
                  <AlertCircle size={12} className="mt-0.5 flex-shrink-0 text-amber-500" />
                  <span>{reason || 'Skill gap — assign qualified staff'}</span>
                </div>
              ) : (
                <div className="mt-1.5 flex items-start gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg px-2 py-1.5">
                  <AlertCircle size={12} className="mt-0.5 flex-shrink-0" />
                  <span>{reason || 'Scheduling conflict — check resource assignments'}</span>
                </div>
              )
            })()}

            {/* Cost grid */}
            <CostGrid job={job} />
          </div>

          {/* Controls */}
          {!isDone && (
            <div className="flex items-center gap-1 flex-shrink-0">
              {/* Start */}
              <button
                onClick={() => onAction(job.id, 'start')}
                disabled={!canStart || loading}
                title={job.has_conflict ? 'Resolve conflicts to start' : 'Start job'}
                className={`p-1.5 rounded-lg transition-colors ${
                  canStart && !loading
                    ? 'text-green-600 hover:bg-green-50'
                    : 'text-gray-300 cursor-not-allowed'
                }`}
              >
                <Play size={16} fill={canStart ? '#16a34a' : '#d1d5db'} />
              </button>

              {/* Pause */}
              {canPause && (
                <button
                  onClick={() => onAction(job.id, 'pause')}
                  disabled={loading}
                  title="Pause job"
                  className="p-1.5 rounded-lg text-yellow-600 hover:bg-yellow-50 transition-colors"
                >
                  <Pause size={16} />
                </button>
              )}

              {/* Resume */}
              {canResume && (
                <button
                  onClick={() => onAction(job.id, 'resume')}
                  disabled={loading}
                  title="Resume job"
                  className="p-1.5 rounded-lg text-green-600 hover:bg-green-50 transition-colors"
                >
                  <RotateCcw size={16} />
                </button>
              )}

              {/* End (complete) */}
              {canEnd && (
                <button
                  onClick={() => onAction(job.id, 'end')}
                  disabled={loading}
                  title="End job (complete)"
                  className="p-1.5 rounded-lg text-blue-600 hover:bg-blue-50 transition-colors"
                >
                  <CheckCircle2 size={16} />
                </button>
              )}

              {/* Stop early (black cross) */}
              {canStop && (
                <button
                  onClick={() => onAction(job.id, 'stop')}
                  disabled={loading}
                  title="Stop job early"
                  className="p-1.5 rounded-lg text-gray-900 hover:bg-gray-100 transition-colors"
                >
                  <Square size={15} />
                </button>
              )}

              {loading && <Loader2 size={14} className="animate-spin text-gray-400 ml-1" />}
            </div>
          )}

          {/* Expand toggle */}
          <button
            onClick={() => setExpanded(e => !e)}
            className="text-gray-300 hover:text-gray-500 transition-colors ml-1"
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 py-3 bg-gray-50 text-xs text-gray-600 space-y-1.5">
          {detailLoading && (
            <div className="flex items-center gap-2 text-gray-400 py-1">
              <Loader2 size={12} className="animate-spin" /> Loading details...
            </div>
          )}
          <div className="flex gap-2">
            <span className="text-gray-400 w-24">{labels.employees}</span>
            <span>{(jobDetail?.assigned_employees ?? job.assigned_employees ?? []).map((e: { full_name: string }) => e.full_name).join(', ') || 'None'}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-gray-400 w-24">{labels.machines}</span>
            <span>{(jobDetail?.assigned_machines ?? job.assigned_machines ?? []).map((m: { name: string }) => m.name).join(', ') || 'None'}</span>
          </div>
          {job.actual_start_at && (
            <div className="flex gap-2">
              <span className="text-gray-400 w-24">Started</span>
              <span>{new Date(job.actual_start_at).toLocaleString('en-IN')}</span>
            </div>
          )}
          {job.actual_end_at && (
            <div className="flex gap-2">
              <span className="text-gray-400 w-24">Ended</span>
              <span>{new Date(job.actual_end_at).toLocaleString('en-IN')}</span>
            </div>
          )}
          {/* Full cost breakdown */}
          {job.tentative_breakdown && (
            <div className="mt-2 pt-2 border-t border-gray-200">
              <p className="font-medium text-gray-500 mb-1">Tentative Breakdown</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
                <span className="text-gray-400">Employee Cost</span><span>{fmt(job.tentative_breakdown.employee_cost)}</span>
                <span className="text-gray-400">Machine Cost</span><span>{fmt(job.tentative_breakdown.machine_cost)}</span>
                <span className="text-gray-400">Materials</span><span>{fmt(job.tentative_breakdown.material_cost)}</span>
                <span className="text-gray-400">Misc</span><span>{fmt(job.tentative_breakdown.misc_cost)}</span>
                <span className="text-gray-400">Hours</span><span>{job.tentative_breakdown.hours} hrs</span>
              </div>
            </div>
          )}
          {job.actual_breakdown && (
            <div className="mt-2 pt-2 border-t border-gray-200">
              <p className="font-medium text-gray-500 mb-1">Actual Breakdown</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
                <span className="text-gray-400">Employee Cost</span><span>{fmt(job.actual_breakdown.employee_cost)}</span>
                <span className="text-gray-400">Machine Cost</span><span>{fmt(job.actual_breakdown.machine_cost)}</span>
                <span className="text-gray-400">Materials</span><span>{fmt(job.actual_breakdown.material_cost)}</span>
                <span className="text-gray-400">Misc</span><span>{fmt(job.actual_breakdown.misc_cost)}</span>
                <span className="text-gray-400">Hours</span><span>{job.actual_breakdown.hours} hrs</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Collapsible Section ───────────────────────────────────────────────────
interface SectionProps {
  title: string
  count: number
  colorClass: string
  icon?: ReactNode
  defaultOpen?: boolean
  children: ReactNode
}
function CollapsibleSection({ title, count, colorClass, icon, defaultOpen = true, children }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section>
      <button
        onClick={() => setOpen(o => !o)}
        className={`w-full flex items-center justify-between px-3 py-2 rounded-lg mb-2 transition-colors hover:bg-gray-50 ${open ? 'bg-gray-50' : 'bg-white border border-gray-200'}`}
      >
        <span className={`text-sm font-semibold flex items-center gap-2 ${colorClass}`}>
          {icon}
          {title} <span className="text-xs font-normal opacity-70">({count})</span>
        </span>
        {open ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
      </button>
      {open && <div className="space-y-2">{children}</div>}
    </section>
  )
}
export default function Dashboard() {
  const navigate = useNavigate()
  const labels = useLabels()
  const [now, setNow] = useState(new Date())
  const [data, setData] = useState<DashboardData | null>(null)
  const [loadingData, setLoadingData] = useState(true)
  const [dataError, setDataError] = useState(false)
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({})
  const [endModalJobId, setEndModalJobId] = useState<number | null>(null)
  const [empCount,  setEmpCount]  = useState(0)
  const [machCount, setMachCount] = useState(0)

  // Live clock
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  // Fetch dashboard data
  const fetchData = useCallback(() => {
    apiClient.get('/api/dashboard/')
      .then(r => { setData(r.data); setDataError(false) })
      .catch(() => setDataError(true))
      .finally(() => setLoadingData(false))
    apiClient.get('/api/employees/').then(r => setEmpCount(r.data?.length ?? 0)).catch(() => {})
    apiClient.get('/api/machines/').then(r => setMachCount(r.data?.length ?? 0)).catch(() => {})
  }, [])

  useEffect(() => {
    fetchData()
    // Auto-poll every POLL_INTERVAL_MS to detect conflict resolution
    // and keep timer states in sync across users.
    const interval = setInterval(fetchData, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchData])

  const setLoading = (jobId: number, val: boolean) =>
    setActionLoading(prev => ({ ...prev, [jobId]: val }))

  const handleAction = async (jobId: number, action: 'start' | 'pause' | 'resume' | 'stop' | 'end') => {
    if (action === 'end') {
      setEndModalJobId(jobId)
      return
    }
    setLoading(jobId, true)
    try {
      if (action === 'start') await timerApi.start(jobId)
      else if (action === 'pause') await timerApi.pause(jobId)
      else if (action === 'resume') await timerApi.resume(jobId)
      else if (action === 'stop') await timerApi.stop(jobId)
      fetchData()
    } catch (e: unknown) {
      alert((e as {response?:{data?:{detail?:string}}})?.response?.data?.detail ?? `Failed to ${action} job`)
    } finally {
      setLoading(jobId, false)
    }
  }

  const handleEndConfirm = async (employeeIds: number[], machineIds: number[]) => {
    if (!endModalJobId) return
    setLoading(endModalJobId, true)
    try {
      await timerApi.end(endModalJobId, { employee_ids: employeeIds, machine_ids: machineIds })
      setEndModalJobId(null)
      fetchData()
    } finally {
      setLoading(endModalJobId, false)
    }
  }

  const timeStr = now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const dateStr = `${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`
  const weekNo = getWeekNumber(now)

  if (loadingData) return (
    <div className="flex items-center gap-2 text-gray-500 mt-10 justify-center">
      <Loader2 className="animate-spin" size={20} />Loading dashboard...
    </div>
  )
  if (dataError) return (
    <div className="flex items-center gap-2 text-red-500 mt-10 justify-center">
      <AlertCircle size={20} />Failed to load dashboard.
    </div>
  )

  const jobs = data?.jobs ?? []
  const activeJobs = jobs.filter(j => j.timer_status === 'running')
  const pausedJobs = jobs.filter(j => j.timer_status === 'paused')
  const conflictJobs = jobs.filter(j => j.has_conflict && j.timer_status !== 'running' && j.timer_status !== 'paused')
  const readyJobs = jobs.filter(j => j.timer_status === 'idle' && !j.has_conflict && j.status !== 'Completed' && j.status !== 'Stopped')
  const doneJobs = jobs.filter(j => j.status === 'Completed' || j.status === 'Stopped')

  const endModalJob = endModalJobId ? jobs.find(j => j.id === endModalJobId) : null

  const cards = [
    { label: labels.kpiJobs, value: data!.total_active_jobs, icon: BriefcaseBusiness, colour: 'text-blue-600', bg: 'bg-blue-50' },
    { label: `Available ${labels.machines}`, value: data!.available_machines, icon: Factory, colour: 'text-green-600', bg: 'bg-green-50' },
    { label: `Available ${labels.employees}`, value: data!.available_employees, icon: Users, colour: 'text-purple-600', bg: 'bg-purple-50' },
  ]

  return (
    <div className="space-y-6" style={{ fontFamily: "'DM Sans', sans-serif" }}>
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Dashboard</h2>
          <p className="text-sm text-gray-500 mt-0.5">Live {labels.jobs.toLowerCase()} board — auto-refreshes every 30s</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl px-5 py-3 flex items-center gap-5 text-sm shadow-sm">
          <div className="flex items-center gap-2 text-gray-700">
            <Clock size={15} className="text-blue-500" />
            <span className="font-mono font-bold text-lg tracking-widest">{timeStr}</span>
          </div>
          <div className="w-px h-8 bg-gray-200" />
          <div className="flex items-center gap-2 text-gray-700">
            <CalendarDays size={15} className="text-blue-500" />
            <div>
              <p className="font-semibold text-gray-800">{dateStr}</p>
              <p className="text-xs text-gray-400">Week {weekNo} · {now.getFullYear()}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <CoachMark id="dashboard-kpis" title="Your shop floor at a glance" description="KPI cards show active jobs, order book value, profit, and conflicts in real time." position="bottom" step={1} totalSteps={3}>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {cards.map(({ label, value, icon: Icon, colour, bg }) => (
            <div key={label} className="bg-white rounded-xl border border-gray-200 p-5 flex items-center gap-4">
              <div className={`${bg} p-3 rounded-lg`}><Icon className={colour} size={22} /></div>
              <div>
                <p className="text-2xl font-bold text-gray-800">{value}</p>
                <p className="text-sm text-gray-500">{label}</p>
              </div>
            </div>
          ))}
        </div>
      </CoachMark>


        {/* Getting Started checklist — V3.8 */}
      <GettingStarted
        employeeCount={empCount}
        machineCount={machCount}
        jobCount={jobs.length}
        assignedJobCount={jobs.filter(j =>
          (j.assigned_employees?.length ?? 0) > 0 && (j.assigned_machines?.length ?? 0) > 0
        ).length}
        activeJobCount={jobs.filter(j =>
          j.status === 'In Progress' || j.status === 'Completed'
        ).length}
      />

      {/* Smart Alerts */}
      <CoachMark id="dashboard-conflicts" title="Smart Alerts" description="Real-time alerts for conflicts, overdue jobs, idle shop floor and more." position="bottom" step={2} totalSteps={3}>
        {(() => {
          const today = new Date(); today.setHours(0,0,0,0)
          const activeJobs = jobs.filter(j => j.status !== 'Completed' && j.status !== 'Stopped' && j.status !== 'Cancelled')

          // Build typed alerts
          type AlertType = 'error' | 'warning' | 'info' | 'success'
          const allAlerts: { type: AlertType; emoji: string; msg: string }[] = []

          // Split conflicted jobs into skill gaps vs real scheduling conflicts
          const conflicted = activeJobs.filter(j => j.has_conflict)
          const skillGapJobs = conflicted.filter(j => {
            const r = (j.conflict_reasons?.[0] ?? '').toLowerCase()
            return r.includes('skill') || r.includes('qualified') || r.includes('no one assigned')
          })
          const realConflictJobs = conflicted.filter(j => !skillGapJobs.includes(j))

          // 🟡 Skill gaps — amber (action: assign qualified staff)
          if (skillGapJobs.length) allAlerts.push({
            type: 'warning', emoji: '🟡',
            msg: `${skillGapJobs.length} job${skillGapJobs.length > 1 ? 's have' : ' has'} skill gaps — assign qualified staff: ${skillGapJobs.slice(0,2).map(j => j.name).join(', ')}${skillGapJobs.length > 2 ? ` +${skillGapJobs.length - 2} more` : ''}`
          })

          // 🔴 Real scheduling conflicts — red (action: change dates or reassign resource)
          if (realConflictJobs.length) allAlerts.push({
            type: 'error', emoji: '🔴',
            msg: `${realConflictJobs.length} job${realConflictJobs.length > 1 ? 's have' : ' has'} scheduling conflicts: ${realConflictJobs.slice(0,2).map(j => j.name).join(', ')}${realConflictJobs.length > 2 ? ` +${realConflictJobs.length - 2} more` : ''}`
          })

          // 🔴 Overdue jobs (past end date, not complete)
          const overdue = activeJobs.filter(j => {
            if (!j.end_date) return false
            const end = new Date(j.end_date); end.setHours(0,0,0,0)
            return end < today && j.status !== 'Completed' && j.status !== 'Stopped'
          })
          if (overdue.length) allAlerts.push({
            type: 'error', emoji: '⏰',
            msg: `${overdue.length} overdue job${overdue.length > 1 ? 's' : ''}: ${overdue.slice(0,2).map(j => j.name).join(', ')}${overdue.length > 2 ? ` +${overdue.length - 2} more` : ''}`
          })

          // 🟡 Ending within 3 days (not started or still running)
          const endingSoon = activeJobs.filter(j => {
            if (!j.end_date || j.status === 'Completed' || j.status === 'Stopped') return false
            const end = new Date(j.end_date); end.setHours(0,0,0,0)
            const diff = Math.ceil((end.getTime() - today.getTime()) / 86400000)
            return diff >= 0 && diff <= 3
          })
          if (endingSoon.length) allAlerts.push({
            type: 'warning', emoji: '⚠️',
            msg: `${endingSoon.length} job${endingSoon.length > 1 ? 's' : ''} ending within 3 days: ${endingSoon.slice(0,2).map(j => j.name).join(', ')}${endingSoon.length > 2 ? ` +${endingSoon.length - 2} more` : ''}`
          })

          // 🟡 Critical jobs not started
          const critNotStarted = activeJobs.filter(j =>
            j.priority === 'Critical' && (j.status === 'Draft' || j.status === 'Scheduled') && j.timer_status === 'idle'
          )
          if (critNotStarted.length) allAlerts.push({
            type: 'warning', emoji: '🚨',
            msg: `${critNotStarted.length} Critical job${critNotStarted.length > 1 ? 's' : ''} not started: ${critNotStarted.slice(0,2).map(j => j.name).join(', ')}`
          })

          // 🟡 Idle shop floor
          const running = jobs.filter(j => j.timer_status === 'running')
          if (running.length === 0 && jobs.length > 0) allAlerts.push({
            type: 'warning', emoji: '😴',
            msg: `No ${labels.jobs.toLowerCase()} currently running — floor is idle`
          })

          // ✅ All clear
          if (allAlerts.length === 0) allAlerts.push({
            type: 'success', emoji: '✅',
            msg: 'All clear — no alerts today!'
          })

          const bgMap: Record<AlertType, string> = {
            error:   'bg-red-50 border-l-4 border-l-red-400',
            warning: 'bg-amber-50 border-l-4 border-l-amber-400',
            info:    'bg-blue-50 border-l-4 border-l-blue-400',
            success: 'bg-green-50 border-l-4 border-l-green-400',
          }
          const textMap: Record<AlertType, string> = {
            error: 'text-red-700', warning: 'text-amber-700',
            info: 'text-blue-700', success: 'text-green-700',
          }

          return (
            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
              <div className="px-4 py-2.5 border-b border-gray-100 flex items-center gap-2">
                <Zap size={14} className="text-amber-500" />
                <span className="text-sm font-semibold text-gray-700">Smart Alerts</span>
                <span className={`ml-2 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                  allAlerts.some(a => a.type === 'error') ? 'bg-red-100 text-red-600'
                  : allAlerts.some(a => a.type === 'warning') ? 'bg-amber-100 text-amber-600'
                  : 'bg-green-100 text-green-600'
                }`}>
                  {allAlerts.filter(a => a.type !== 'success').length || '✓'}
                </span>
                <span className="ml-auto text-[10px] text-gray-400 uppercase tracking-wide">Live</span>
              </div>
              <div className="divide-y divide-gray-50">
                {allAlerts.map((a, i) => (
                  <div key={i} className={`flex items-start gap-3 px-4 py-2.5 ${bgMap[a.type]}`}>
                    <span className="mt-0.5 shrink-0 text-sm">{a.emoji}</span>
                    <p className={`text-xs leading-relaxed font-medium ${textMap[a.type]}`}>{a.msg}</p>
                  </div>
                ))}
              </div>
            </div>
          )
        })()}
      </CoachMark>

      {/* Legend */}
      <div className="flex items-center gap-5 text-xs text-gray-500 bg-white border border-gray-100 rounded-xl px-4 py-2.5 flex-wrap">
        <span className="font-medium text-gray-400 uppercase tracking-wide text-xs">Legend</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse inline-block" />Ready to start</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />Skill gap</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" />Scheduling conflict</span>
        <span className="flex items-center gap-1.5">
          <svg viewBox="0 0 16 16" className="w-3.5 h-3.5"><path d="M3 2l10 6-10 6V2z" fill="#16a34a" /></svg>In progress
        </span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block" />Completed</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-gray-900 inline-block" />Stopped early</span>
      </div>

      {/* Running jobs */}
      {activeJobs.length > 0 && (
        <CollapsibleSection
          title={`Running ${labels.jobs}`}
          count={activeJobs.length}
          colorClass="text-green-700"
          defaultOpen={true}
          icon={<span className="w-2 h-2 rounded-full bg-green-500 animate-pulse inline-block" />}
        >
          {activeJobs.map(j => (
            <JobCard key={j.id} job={j} onAction={handleAction} actionLoading={actionLoading} />
          ))}
        </CollapsibleSection>
      )}

      {/* Jobs needing attention — split skill gaps from scheduling conflicts */}
      {conflictJobs.length > 0 && (() => {
        const skillGapSection = conflictJobs.filter(j => {
          const r = (j.conflict_reasons?.[0] ?? '').toLowerCase()
          return r.includes('skill') || r.includes('qualified') || r.includes('no one assigned')
        })
        const realConflictSection = conflictJobs.filter(j => !skillGapSection.includes(j))
        return (
          <>
            {skillGapSection.length > 0 && (
              <CollapsibleSection
                title={`Needs Attention — Skill Gaps`}
                count={skillGapSection.length}
                colorClass="text-amber-600"
                defaultOpen={true}
                icon={<AlertCircle size={14} className="text-amber-500" />}
              >
                {skillGapSection.map(j => (
                  <JobCard key={j.id} job={j} onAction={handleAction} actionLoading={actionLoading} />
                ))}
              </CollapsibleSection>
            )}
            {realConflictSection.length > 0 && (
              <CollapsibleSection
                title="Needs Attention — Scheduling Conflicts"
                count={realConflictSection.length}
                colorClass="text-red-600"
                defaultOpen={true}
                icon={<AlertCircle size={14} />}
              >
                {realConflictSection.map(j => (
                  <JobCard key={j.id} job={j} onAction={handleAction} actionLoading={actionLoading} />
                ))}
              </CollapsibleSection>
            )}
          </>
        )
      })()}

      {/* Paused jobs */}
      {pausedJobs.length > 0 && (
        <CollapsibleSection
          title={`Paused ${labels.jobs}`}
          count={pausedJobs.length}
          colorClass="text-yellow-700"
          defaultOpen={true}
          icon={<Pause size={13} />}
        >
          {pausedJobs.map(j => (
            <JobCard key={j.id} job={j} onAction={handleAction} actionLoading={actionLoading} />
          ))}
        </CollapsibleSection>
      )}

      {/* Pending (idle, no conflict) */}
      {readyJobs.length > 0 && (
        <CollapsibleSection
          title={`Ready to Start`}
          count={readyJobs.length}
          colorClass="text-gray-700"
          defaultOpen={true}
          icon={<span className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse inline-block" />}
        >
          {readyJobs.map(j => (
            <JobCard key={j.id} job={j} onAction={handleAction} actionLoading={actionLoading} />
          ))}
        </CollapsibleSection>
      )}

      {/* Completed / Stopped */}
      {doneJobs.length > 0 && (
        <CollapsibleSection
          title={`Completed / Stopped`}
          count={doneJobs.length}
          colorClass="text-gray-500"
          defaultOpen={false}
        >
          {doneJobs.map(j => (
            <JobCard key={j.id} job={j} onAction={handleAction} actionLoading={actionLoading} />
          ))}
        </CollapsibleSection>
      )}

      {jobs.length === 0 && (
        <EmptyState
          icon={<BriefcaseBusiness size={32} />}
          title={`No ${labels.jobs.toLowerCase()} yet`}
          description={`Create your first ${labels.job.toLowerCase()} to start tracking production. Assign ${labels.employees.toLowerCase()} and ${labels.machines.toLowerCase()} to get a full picture.`}
          actionLabel="Create First Job"
          onAction={() => navigate('/jobs')}
        />
      )}

      {/* End Job Modal */}
      {endModalJobId && endModalJob && (
        <EndJobModal
          jobId={endModalJobId}
          jobName={endModalJob.name}
          onConfirm={handleEndConfirm}
          onClose={() => setEndModalJobId(null)}
        />
      )}
    </div>
  )
}