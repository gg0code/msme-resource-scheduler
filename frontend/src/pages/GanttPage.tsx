// src/pages/GanttPage.tsx — V2.1
// Added: Day / Week / Month zoom toggle
// Day view  : 30px per day (detailed)
// Week view : 10px per day (~3x zoom out)
// Month view:  4px per day (~7x zoom out, full picture)

import { useEffect, useRef, useState } from 'react'
import { fetchGanttData } from '../api/api_gantt'
import type { GanttJob } from '../api/api_gantt'
import { CoachMark } from '../components/onboarding'

// ─── Constants ───────────────────────────────────────────────────────────────
const ROW_H    = 52
const LABEL_W  = 220
const HEADER_H = 56

const ZOOM_COL_W: Record<string, number> = {
  day:   30,
  week:  10,
  month:  4,
}

const JOB_COLORS = [
  '#0369a1', '#7c3aed', '#c2410c', '#0f766e',
  '#be185d', '#4d7c0f', '#4338ca', '#b45309',
]
const PRIORITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 }

// ─── Helpers ─────────────────────────────────────────────────────────────────
const getJobColor = (idx: number) => JOB_COLORS[idx % JOB_COLORS.length]

function parseDate(s?: string): Date | null {
  if (!s) return null
  const d = new Date(s)
  return isNaN(d.getTime()) ? null : d
}
function daysBetween(a: Date, b: Date) {
  return Math.floor((b.getTime() - a.getTime()) / 86400000)
}
function addDays(d: Date, n: number) {
  const r = new Date(d); r.setDate(r.getDate() + n); return r
}
function isSameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}
function isWeekend(d: Date) { return d.getDay() === 0 || d.getDay() === 6 }
function formatDate(d: Date) {
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
}
function monthLabel(d: Date) {
  return d.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })
}
function shortMonth(d: Date) {
  return d.toLocaleDateString('en-IN', { month: 'short' })
}

// ─── Status dot SVG (on bar) ─────────────────────────────────────────────────
function StatusDotSvg({ icon, x, y }: { icon: string; x: number; y: number }) {
  const cy = y + ROW_H / 2
  const cx = x + 8
  if (icon === 'in_progress')
    return <polygon points={`${cx-4},${cy-5} ${cx+6},${cy} ${cx-4},${cy+5}`} fill="#fff" opacity={0.9} />
  const colors: Record<string, string> = {
    ready: '#86efac', conflict: '#c4b5fd', completed: '#93c5fd', stopped: '#1f2937',
    delayed: '#fca5a5', at_risk: '#fcd34d',
  }
  return <circle cx={cx} cy={cy} r={4} fill={colors[icon] ?? '#e5e7eb'} opacity={0.95} />
}

// ─── Blink dot (label column) ────────────────────────────────────────────────
function BlinkDot({ icon }: { icon: string }) {
  if (icon === 'in_progress')
    return <svg viewBox="0 0 12 12" className="w-3 h-3 flex-shrink-0"><polygon points="1,1 11,6 1,11" fill="#16a34a"/></svg>
  const map: Record<string, string> = {
    ready: 'bg-green-500 animate-pulse', conflict: 'bg-violet-600',
    completed: 'bg-blue-500', stopped: 'bg-gray-900',
    delayed: 'bg-red-500 animate-pulse', at_risk: 'bg-amber-400 animate-pulse',
  }
  return <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 inline-block ${map[icon] ?? 'bg-gray-300'}`} />
}

// ─── Timer badge icons on bar ─────────────────────────────────────────────
function TimerBadges({ job, x, y, barW }: { job: GanttJob; x: number; y: number; barW: number }) {
  // Only show if bar is wide enough (>90px)
  if (barW < 90) return null
  const t = job.timer_status ?? 'idle'
  const s = job.status

  // Pick which badges to show based on state
  const badges: { icon: string; color: string; title: string }[] = []
  if (t === 'idle' && s !== 'Completed' && s !== 'Stopped')
    badges.push({ icon: '▶', color: '#16a34a', title: 'Ready to Start' })
  if (t === 'running')
    badges.push({ icon: '⏸', color: '#ca8a04', title: 'Running — can Pause' })
  if (t === 'paused')
    badges.push({ icon: '↺', color: '#2563eb', title: 'Paused — can Resume' })
  if (t === 'running' || t === 'paused') {
    badges.push({ icon: '✕', color: '#111827', title: 'Stop' })
    badges.push({ icon: '●', color: '#2563eb', title: 'End' })
  }

  const badgeW = 16
  const gap = 3
  const totalW = badges.length * (badgeW + gap) - gap
  // Right-align badges inside bar with 6px margin
  const startX = x + barW - totalW - 8

  return (
    <>
      {badges.map((b, i) => {
        const bx = startX + i * (badgeW + gap)
        return (
          <g key={i}>
            <rect x={bx} y={y + ROW_H/2 - 9} width={badgeW} height={18} rx={3}
              fill="rgba(0,0,0,0.25)" />
            <text x={bx + badgeW/2} y={y + ROW_H/2 + 5}
              fill={b.color} fontSize={9} fontWeight={700}
              textAnchor="middle" style={{ userSelect: 'none' }}>
              {b.icon}
            </text>
          </g>
        )
      })}
    </>
  )
}
type ZoomLevel = 'day' | 'week' | 'month'
type FilterPriority = 'all' | 'high' | 'medium' | 'low'

export default function GanttPage() {
  const [jobs, setJobs]               = useState<GanttJob[]>([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState<string | null>(null)
  const [activeTab, setActiveTab]     = useState<TabType>('jobs')
  const [zoom, setZoom]               = useState<ZoomLevel>('day')
  const [filterPriority, setFilterPriority] = useState<FilterPriority>('all')
  const [filterStatus, setFilterStatus]     = useState<string>('all')
  const [selectedJob, setSelectedJob] = useState<GanttJob | null>(null)
  const [conflictPanelOpen, setConflictPanelOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const COL_W = ZOOM_COL_W[zoom]

  const today = new Date(); today.setHours(0, 0, 0, 0)
  // Range: current month start → 2 months ahead end
  const rangeStart = new Date(today.getFullYear(), today.getMonth(), 1)
  const rangeEnd   = new Date(today.getFullYear(), today.getMonth() + 2, 0)
  const totalDays  = daysBetween(rangeStart, rangeEnd) + 1
  const days       = Array.from({ length: totalDays }, (_, i) => addDays(rangeStart, i))

  useEffect(() => {
    fetchGanttData()
      .then(setJobs)
      .catch(e => setError(e?.message ?? 'Failed to load'))
      .finally(() => setLoading(false))
  }, [])

  // Scroll to today on load or zoom change
  useEffect(() => {
    if (!loading && scrollRef.current) {
      const offset = daysBetween(rangeStart, today) * COL_W - 80
      scrollRef.current.scrollLeft = Math.max(0, offset)
    }
  }, [loading, zoom])

  const scrollToToday = () => {
    if (scrollRef.current) {
      const offset = daysBetween(rangeStart, today) * COL_W - 80
      scrollRef.current.scrollLeft = Math.max(0, offset)
    }
  }

  const STATUSES = ['All', 'In Progress', 'Scheduled', 'Draft', 'Completed', 'Paused']

  const filtered = jobs
    .filter(j => filterPriority === 'all' || j.priority?.toLowerCase() === filterPriority)
    .filter(j => filterStatus === 'all' || j.status === filterStatus)
    .sort((a, b) => {
      const pa = PRIORITY_ORDER[a.priority?.toLowerCase() ?? 'low'] ?? 2
      const pb = PRIORITY_ORDER[b.priority?.toLowerCase() ?? 'low'] ?? 2
      return pa - pb
    })

  const colorMap: Record<number, string> = {}
  jobs.forEach((j, i) => { colorMap[j.id] = getJobColor(i) })

  // Build machine groups
  const machineGroups: Record<string, GanttJob[]> = {}
  if (activeTab === 'machines') {
    filtered.forEach(job => {
      const machines = job.assigned_machines.length ? job.assigned_machines : ['Unassigned']
      machines.forEach(m => {
        if (!machineGroups[m]) machineGroups[m] = []
        machineGroups[m].push(job)
      })
    })
  }

  const conflicting  = filtered.filter(j => j.has_conflict)
  const chartHeight  = activeTab === 'jobs'
    ? filtered.length * ROW_H
    : Object.values(machineGroups).reduce((acc, arr) => acc + (1 + arr.length) * ROW_H, 0)

  // ── Header rows ─────────────────────────────────────────────────────────────
  // Month sub-header (always shown)
  const monthGroups = days.reduce((acc: { label: string; count: number }[], d) => {
    const m = monthLabel(d)
    if (!acc.length || acc[acc.length - 1].label !== m) acc.push({ label: m, count: 1 })
    else acc[acc.length - 1].count++
    return acc
  }, [])

  // Day labels — shown in day/week view; in month view show week numbers instead
  const renderDayHeader = () => {
    if (zoom === 'month') {
      // Show one cell per week with "W{n}" label
      return days.filter((_, i) => i % 7 === 0).map((d, i) => {
        const wStart = i * 7
        const wEnd   = Math.min(wStart + 7, totalDays)
        const w      = (wEnd - wStart) * COL_W
        return (
          <div key={i} style={{ width: w, minWidth: w }}
            className="flex items-center justify-center border-r border-gray-100 flex-shrink-0 text-xs text-gray-400">
            {shortMonth(d)} {d.getDate()}
          </div>
        )
      })
    }
    return days.map((d, i) => (
      <div key={i} style={{ width: COL_W, minWidth: COL_W }}
        className={`flex items-center justify-center border-r flex-shrink-0 ${
          isWeekend(d) ? 'bg-gray-100 border-gray-200' : 'border-gray-100'
        } ${isSameDay(d, today) ? 'bg-blue-50' : ''}`}>
        <span className={`text-xs ${isSameDay(d, today) ? 'font-bold text-blue-600' : isWeekend(d) ? 'text-gray-400' : 'text-gray-500'}`}>
          {zoom === 'week' ? (d.getDate() % 7 === 1 || d.getDate() === 1 ? d.getDate() : '') : d.getDate()}
        </span>
      </div>
    ))
  }

  // ── Bar renderer ─────────────────────────────────────────────────────────────
  const renderBar = (job: GanttJob, rowY: number) => {
    const start = parseDate(job.start_date)
    const end   = parseDate(job.end_date)
    if (!start || !end) return null
    if (end < rangeStart || start > rangeEnd) return null

    const clampedStart = start < rangeStart ? rangeStart : start
    const clampedEnd   = end   > rangeEnd   ? rangeEnd   : end
    const x = daysBetween(rangeStart, clampedStart) * COL_W
    const w = (daysBetween(clampedStart, clampedEnd) + 1) * COL_W - 2
    if (w <= 0) return null

    // Health colour logic
    const isComplete  = ['Completed', 'Cancelled', 'Stopped'].includes(job.status ?? '')
    const isConflict  = job.has_conflict
    const isDelayed   = !isComplete && end < today
    const daysLeft    = daysBetween(today, end)
    const isAtRisk    = !isDelayed && !isConflict && !isComplete
                        && daysLeft <= 3 && daysLeft >= 0
                        && ['Draft', 'Scheduled'].includes(job.status ?? '')
    const isSelected = selectedJob?.id === job.id
    const color     = isConflict ? '#7c3aed'
                    : isDelayed  ? '#ef4444'
                    : isAtRisk   ? '#f59e0b'
                    : colorMap[job.id]
    const strokeClr = isSelected ? '#1d4ed8' : isConflict ? '#6d28d9' : isDelayed ? '#dc2626' : isAtRisk ? '#d97706' : 'transparent'
    const textColor = '#ffffff'

    return (
      <g key={job.id} onClick={() => setSelectedJob(selectedJob?.id === job.id ? null : job)}
        style={{ cursor: 'pointer' }}>
        <rect x={x+1} y={rowY+10} width={w} height={ROW_H-20} rx={5}
          fill={color}
          stroke={strokeClr}
          strokeWidth={isSelected ? 2 : isConflict || isDelayed || isAtRisk ? 1.5 : 0} opacity={0.95}
        />
        {w > 16 && <StatusDotSvg icon={job.status_icon ?? 'ready'} x={x} y={rowY} />}
        {w > 50 && (
          <text x={x+20} y={rowY + ROW_H/2 + 5} fill={textColor} fontSize={11} fontWeight={600}>
            {job.name.length > Math.floor((w-22)/7)
              ? job.name.slice(0, Math.floor((w-22)/7)) + '…'
              : job.name}
          </text>
        )}
        {w > 90 && <TimerBadges job={job} x={x+1} y={rowY} barW={w} />}
      </g>
    )
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64 gap-2">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      <span className="text-gray-500 text-sm">Loading Gantt…</span>
    </div>
  )
  if (error) return (
    <div className="m-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">⚠️ {error}</div>
  )

  return (
    <div className="flex flex-col h-full bg-white" style={{ fontFamily: "'DM Sans', sans-serif" }}>

      {/* ── Header ── */}
      <div className="px-6 pt-5 pb-3 border-b border-gray-100">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <CoachMark id="gantt-timeline" title="Production Timeline" description="See all jobs on a visual calendar. Each bar is one job. Hover for details." position="bottom" step={1} totalSteps={2}>
            <div>
              <h1 className="text-xl font-semibold text-gray-900">Production Schedule</h1>
              <p className="text-xs text-gray-400 mt-0.5">{monthLabel(rangeStart)} — {monthLabel(rangeEnd)}</p>
            </div>
          </CoachMark>

          <div className="flex items-center gap-2">
            {/* Zoom toggle */}
            <div className="flex items-center bg-gray-100 rounded-lg p-0.5 gap-0.5">
              {(['day', 'week', 'month'] as ZoomLevel[]).map(z => (
                <button key={z} onClick={() => setZoom(z)}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors capitalize ${
                    zoom === z ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                  }`}>
                  {z}
                </button>
              ))}
            </div>

            <button onClick={scrollToToday}
              className="px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-md hover:bg-blue-100 transition-colors">
              Today
            </button>
          </div>
        </div>

        {/* Tabs + legend row */}
        <div className="flex items-center justify-between mt-3 flex-wrap gap-2">
          <div className="flex gap-1">
            {(['jobs', 'machines'] as TabType[]).map(tab => (
              <button key={tab} onClick={() => { setActiveTab(tab); setSelectedJob(null) }}
                className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors capitalize ${
                  activeTab === tab ? 'bg-gray-900 text-white' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                }`}>
                {tab === 'jobs' ? 'Jobs' : 'Machines'}
              </button>
            ))}
          </div>
          {/* Health legend */}
          <div className="flex items-center gap-3 text-[11px] text-gray-500">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block bg-green-500 opacity-80"/><span>On track</span></span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block bg-amber-400 opacity-80"/><span>At risk</span></span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block bg-red-500 opacity-80"/><span>Delayed</span></span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block bg-violet-600 opacity-80"/><span>Conflict</span></span>
          </div>
        </div>
      </div>

      {/* ── Conflict pill (compact, click to open panel) ── */}
      {conflicting.length > 0 && (
        <div className="px-6 mt-3">
          <button
            onClick={() => setConflictPanelOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-xs font-semibold text-red-700 hover:bg-red-100 transition-colors group"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"/>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"/>
            </span>
            {conflicting.length} conflict{conflicting.length > 1 ? 's' : ''} detected
            <span className="text-red-400 group-hover:text-red-600 ml-1">→ View details</span>
          </button>
        </div>
      )}

      {/* ── Conflict floating panel ── */}
      {conflictPanelOpen && (
        <>
          {/* Backdrop — click to close */}
          <div
            className="fixed inset-0 z-40 bg-black/20"
            onClick={() => setConflictPanelOpen(false)}
          />
          {/* Slide-in panel from right */}
          <div className="fixed top-0 right-0 h-full w-96 z-50 bg-white shadow-2xl border-l border-gray-200 flex flex-col">
            {/* Panel header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 bg-red-50">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"/>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500"/>
                </span>
                <h3 className="font-bold text-red-700 text-sm">
                  {conflicting.length} Conflict{conflicting.length > 1 ? 's' : ''} Detected
                </h3>
              </div>
              <button
                onClick={() => setConflictPanelOpen(false)}
                className="w-7 h-7 flex items-center justify-center rounded-full text-gray-400 hover:text-gray-700 hover:bg-gray-100 text-lg font-bold"
              >
                ✕
              </button>
            </div>
            {/* Panel body — scrollable */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
              {conflicting.map(j => (
                <div key={j.id} className="bg-red-50 border border-red-200 rounded-xl p-3">
                  <div className="flex items-start gap-2 mb-1.5">
                    <span className="text-red-500 text-xs mt-0.5 shrink-0">⚠</span>
                    <span className="text-xs font-bold text-red-700 leading-tight">{j.name}</span>
                  </div>
                  <ul className="space-y-1 pl-4">
                    {(j.conflict_reasons.length > 0 ? j.conflict_reasons : ['Resource double-booked']).map((r, i) => (
                      <li key={i} className="text-xs text-red-600 flex items-start gap-1.5">
                        <span className="text-red-300 shrink-0 mt-0.5">•</span>
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
            {/* Panel footer */}
            <div className="px-5 py-3 border-t border-gray-100 bg-gray-50">
              <p className="text-xs text-gray-400">Go to Jobs page to reassign resources or change dates.</p>
            </div>
          </div>
        </>
      )}

      {/* ── Filters ── */}
      <div className="px-6 py-3 border-b border-gray-100 space-y-2">
        {/* Priority row */}
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide w-14">Priority</span>
          <div className="flex gap-1.5 flex-wrap">
            {(['all', 'high', 'medium', 'low'] as FilterPriority[]).map(p => (
              <button key={p} onClick={() => setFilterPriority(p)}
                className={`px-3 py-1 text-xs font-medium rounded-full border transition-colors capitalize ${
                  filterPriority === p
                    ? p === 'high'   ? 'bg-red-100 text-red-700 border-red-300'
                    : p === 'medium' ? 'bg-yellow-100 text-yellow-700 border-yellow-300'
                    : p === 'low'    ? 'bg-green-100 text-green-700 border-green-300'
                    : 'bg-gray-900 text-white border-gray-900'
                    : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'
                }`}>
                {p === 'all' ? 'All' : p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>
        </div>
        {/* Status row */}
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide w-14">Status</span>
          <div className="flex gap-1.5 flex-wrap">
            {STATUSES.map(s => {
              const val = s === 'All' ? 'all' : s
              const active = filterStatus === val
              const colour = active
                ? s === 'In Progress' ? 'bg-purple-100 text-purple-700 border-purple-300'
                : s === 'Scheduled'   ? 'bg-blue-100 text-blue-700 border-blue-300'
                : s === 'Draft'       ? 'bg-gray-200 text-gray-700 border-gray-400'
                : s === 'Completed'   ? 'bg-teal-100 text-teal-700 border-teal-300'
                : s === 'Paused'      ? 'bg-orange-100 text-orange-700 border-orange-300'
                : 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'
              return (
                <button key={s} onClick={() => setFilterStatus(val)}
                  className={`px-3 py-1 text-xs font-medium rounded-full border transition-colors ${colour}`}>
                  {s}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* ── Chart ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Label column — scrolls vertically in sync */}
        <div className="flex-shrink-0 border-r border-gray-200 flex flex-col" style={{ width: LABEL_W }}>
          <div className="border-b border-gray-200 bg-gray-50 flex items-end px-3 pb-2 flex-shrink-0" style={{ height: HEADER_H }}>
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
              {activeTab === 'jobs' ? 'Job' : 'Machine / Job'}
            </span>
          </div>
          <div className="overflow-y-auto flex-1" id="gantt-label-scroll" onScroll={e => {
            const chart = document.getElementById('gantt-chart-scroll')
            if (chart) chart.scrollTop = (e.target as HTMLElement).scrollTop
          }}>
            <div style={{ height: chartHeight }}>
            {activeTab === 'jobs'
              ? filtered.map(job => (
                  <div key={job.id} onClick={() => setSelectedJob(selectedJob?.id === job.id ? null : job)}
                    style={{ height: ROW_H }}
                    className={`flex items-center gap-2 px-3 border-b border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors ${selectedJob?.id === job.id ? 'bg-blue-50' : ''}`}>
                    <BlinkDot icon={job.status_icon ?? 'ready'} />
                    <span className="text-xs font-medium truncate"
                      style={{ color: job.has_conflict ? '#991b1b' : '#1f2937' }}
                      title={job.name}>
                      {job.has_conflict && '⚠️ '}{job.name}
                    </span>
                  </div>
                ))
              : Object.entries(machineGroups).map(([machine, machineJobs]) => (
                  <div key={machine}>
                    <div style={{ height: ROW_H }} className="flex items-center px-3 border-b border-gray-200 bg-gray-50">
                      <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide truncate">🔧 {machine}</span>
                    </div>
                    {machineJobs.map(job => (
                      <div key={job.id} onClick={() => setSelectedJob(selectedJob?.id === job.id ? null : job)}
                        style={{ height: ROW_H }}
                        className={`flex items-center gap-2 pl-6 pr-3 border-b border-gray-100 cursor-pointer hover:bg-gray-50 ${selectedJob?.id === job.id ? 'bg-blue-50' : ''}`}>
                        <BlinkDot icon={job.status_icon ?? 'ready'} />
                        <span className="text-xs font-medium truncate"
                          style={{ color: job.has_conflict ? '#991b1b' : '#374151' }}
                          title={job.name}>
                          {job.has_conflict && '⚠️ '}{job.name}
                        </span>
                      </div>
                    ))}
                  </div>
                ))
            }
            </div>
          </div>
        </div>

        {/* Scrollable chart — horizontal AND vertical */}
        <div ref={scrollRef} id="gantt-chart-scroll" className="flex-1 overflow-x-auto overflow-y-auto" onScroll={e => {
          const label = document.getElementById('gantt-label-scroll')
          if (label) label.scrollTop = (e.target as HTMLElement).scrollTop
        }}>
          <div style={{ width: totalDays * COL_W }}>

            {/* Date header */}
            <div className="sticky top-0 bg-gray-50 border-b border-gray-200 z-10" style={{ height: HEADER_H }}>
              {/* Month row */}
              <div className="flex" style={{ height: 22 }}>
                {monthGroups.map(({ label, count }, i) => (
                  <div key={i} style={{ width: count * COL_W }}
                    className="flex items-center px-2 border-r border-gray-200 flex-shrink-0 overflow-hidden">
                    <span className="text-xs font-semibold text-gray-500 truncate">{label}</span>
                  </div>
                ))}
              </div>
              {/* Day/week row */}
              <div className="flex" style={{ height: HEADER_H - 22 }}>
                {renderDayHeader()}
              </div>
            </div>

            {/* SVG body */}
            <svg width={totalDays * COL_W} height={chartHeight} style={{ display: 'block' }}>
              {/* Background shading */}
              {days.map((d, i) => (
                <rect key={i} x={i * COL_W} y={0} width={COL_W} height={chartHeight}
                  fill={isSameDay(d, today) ? 'rgba(59,130,246,0.05)' : isWeekend(d) ? 'rgba(0,0,0,0.025)' : 'transparent'}
                />
              ))}

              {/* Row separators */}
              {activeTab === 'jobs' && filtered.map((_, i) => (
                <line key={i} x1={0} y1={(i+1)*ROW_H} x2={totalDays*COL_W} y2={(i+1)*ROW_H}
                  stroke="#f3f4f6" strokeWidth={1} />
              ))}

              {/* Bars — Jobs */}
              {activeTab === 'jobs' && filtered.map((job, i) => renderBar(job, i * ROW_H))}

              {/* Bars — Machines */}
              {activeTab === 'machines' && (() => {
                let y = 0
                return Object.entries(machineGroups).map(([, machineJobs]) => {
                  y += ROW_H  // header row
                  return machineJobs.map(job => {
                    const bar = renderBar(job, y)
                    y += ROW_H
                    return bar
                  })
                })
              })()}

              {/* Today line */}
              {today >= rangeStart && today <= rangeEnd && (
                <line
                  x1={daysBetween(rangeStart, today) * COL_W + COL_W/2} y1={0}
                  x2={daysBetween(rangeStart, today) * COL_W + COL_W/2} y2={chartHeight}
                  stroke="#3b82f6" strokeWidth={1.5} strokeDasharray="4 3" opacity={0.7}
                />
              )}
            </svg>
          </div>
        </div>
      </div>

      {/* ── Detail panel ── */}
      {selectedJob && (
        <div className="border-t border-gray-200 bg-white px-6 py-4 shadow-inner">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <BlinkDot icon={selectedJob.status_icon ?? 'ready'} />
              <div>
                <h3 className="text-sm font-semibold text-gray-900">{selectedJob.name}</h3>
                {selectedJob.customer && <p className="text-xs text-gray-400">{selectedJob.customer}</p>}
              </div>
              {selectedJob.has_conflict && (
                <span className="px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700 rounded-full">⚠️ Conflict</span>
              )}
            </div>
            <button onClick={() => setSelectedJob(null)} className="text-gray-400 hover:text-gray-600 text-lg leading-none">×</button>
          </div>
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-1.5 text-xs">
            <div className="flex gap-2"><span className="text-gray-400 w-20">Dates</span>
              <span>{selectedJob.start_date ? formatDate(new Date(selectedJob.start_date)) : '—'} → {selectedJob.end_date ? formatDate(new Date(selectedJob.end_date)) : '—'}</span></div>
            <div className="flex gap-2"><span className="text-gray-400 w-20">Status</span><span className="capitalize">{selectedJob.status || '—'}</span></div>
            <div className="flex gap-2"><span className="text-gray-400 w-20">Priority</span>
              <span className={`capitalize font-medium ${selectedJob.priority?.toLowerCase() === 'high' ? 'text-red-600' : selectedJob.priority?.toLowerCase() === 'medium' ? 'text-yellow-600' : 'text-green-600'}`}>
                {selectedJob.priority || '—'}
              </span>
            </div>
            <div className="flex gap-2"><span className="text-gray-400 w-20">Employees</span><span>{selectedJob.assigned_employees.join(', ') || 'None'}</span></div>
            <div className="flex gap-2"><span className="text-gray-400 w-20">Machines</span><span>{selectedJob.assigned_machines.join(', ') || 'None'}</span></div>
            {selectedJob.tentative_cost != null && (
              <div className="flex gap-2"><span className="text-gray-400 w-20">Est. Cost</span><span>₹{Math.round(selectedJob.tentative_cost).toLocaleString('en-IN')}</span></div>
            )}
            {selectedJob.tentative_profit != null && (
              <div className="flex gap-2"><span className="text-gray-400 w-20">Est. Profit</span>
                <span className={selectedJob.tentative_profit >= 0 ? 'text-green-600 font-medium' : 'text-red-500 font-medium'}>
                  ₹{Math.round(selectedJob.tentative_profit).toLocaleString('en-IN')}
                </span>
              </div>
            )}
          </div>
          {selectedJob.has_conflict && selectedJob.conflict_reasons.length > 0 && (
            <div className="mt-3 p-2.5 bg-red-50 border border-red-100 rounded-lg">
              <p className="text-xs font-semibold text-red-700 mb-1">Conflict Details</p>
              <ul className="space-y-0.5">{selectedJob.conflict_reasons.map((r, i) => <li key={i} className="text-xs text-red-600">• {r}</li>)}</ul>
            </div>
          )}
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center flex-1 text-gray-400 gap-2 py-16">
          <span className="text-3xl">📋</span>
          <p className="text-sm">No jobs match the current filters</p>
        </div>
      )}
    </div>
  )
}
