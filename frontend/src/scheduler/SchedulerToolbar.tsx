// src/scheduler/SchedulerToolbar.tsx — Prompt 2 Part D
//
// States:
//   active        → blue pulsing "Auto-Schedule" button + dirty banner
//   warn          → amber "Review Conflicts (n)" button + conflict slide-panel
//   greyed-clean  → disabled grey button, tooltip "Schedule is up to date."
//   greyed-locked → disabled grey button, tooltip "All jobs are locked…"

import { useState } from 'react'
import {
  Zap, AlertTriangle, CheckCircle, Lock,
  X, Clock, Loader2, RotateCcw,
} from 'lucide-react'
import { useSchedulerContext } from './SchedulerContext'
import type { ConflictEntry } from './useScheduler'
import { schedJobsApi } from '../api/scheduling'
import { useQueryClient } from '@tanstack/react-query'

// ─── Priority badge ───────────────────────────────────────────────────────────

const PRIORITY_BADGE: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 border border-red-200',
  urgent:   'bg-amber-100 text-amber-700 border border-amber-200',
  low:      'bg-gray-100 text-gray-600 border border-gray-200',
}

// ─── Conflict panel ───────────────────────────────────────────────────────────

function ConflictPanel({
  conflicts,
  jobMap,
  onClose,
  onLockJob,
}: {
  conflicts:  ConflictEntry[]
  jobMap:     Record<number, { name: string; priority: string }>
  onClose:    () => void
  onLockJob:  (jobId: number) => void
}) {
  // Group by job
  const grouped: Record<number, ConflictEntry[]> = {}
  for (const c of conflicts) {
    grouped[c.job_id] = grouped[c.job_id] ?? []
    grouped[c.job_id].push(c)
  }

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-40 bg-black/20"
        onClick={onClose}
      />

      {/* Slide-in panel from right */}
      <div className="fixed top-0 right-0 h-full w-96 bg-white shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 bg-amber-50">
          <div className="flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-600" />
            <span className="font-semibold text-gray-900">
              {conflicts.length} Conflict{conflicts.length !== 1 ? 's' : ''}
            </span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {Object.entries(grouped).map(([jobIdStr, items]) => {
            const jobId = Number(jobIdStr)
            const job   = jobMap[jobId]
            return (
              <div key={jobId} className="border border-gray-200 rounded-xl overflow-hidden">
                {/* Job header */}
                <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-gray-900">
                      {job?.name ?? `Job #${jobId}`}
                    </span>
                    {job?.priority && (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${PRIORITY_BADGE[job.priority] ?? ''}`}>
                        {job.priority}
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => onLockJob(jobId)}
                    className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100 transition-colors"
                    title="Lock this job to prevent re-scheduling"
                  >
                    <Lock size={12} /> Lock
                  </button>
                </div>

                {/* Conflict rows */}
                <div className="divide-y divide-gray-100">
                  {items.map(c => (
                    <div key={c.step_id} className="px-4 py-3">
                      <div className="text-xs text-gray-500 mb-1 font-medium">
                        Step {c.sequence_order}
                      </div>
                      <div className="font-mono text-xs text-red-700 bg-red-50 border border-red-200 rounded px-2 py-1.5 leading-relaxed">
                        {c.reason}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        <div className="px-5 py-3 border-t border-gray-100 text-xs text-gray-400">
          Locking a job preserves its current schedule window.
        </div>
      </div>
    </>
  )
}

// ─── Result summary panel ────────────────────────────────────────────────────

function ResultSummaryPanel({
  summary,
  jobMap,
  onClose,
}: {
  summary: import('./useScheduler').SchedulerRunSummary
  jobMap:  Record<number, { name: string; priority: string }>
  onClose: () => void
}) {
  const fmt = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      <div className="fixed top-0 right-0 h-full w-96 bg-white shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 bg-blue-50">
          <div className="flex items-center gap-2">
            <CheckCircle size={18} className="text-blue-600" />
            <span className="font-semibold text-gray-900">Auto-Schedule Complete</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
            <X size={18} />
          </button>
        </div>

        {/* Stats bar */}
        <div className="grid grid-cols-3 divide-x divide-gray-100 border-b border-gray-200 bg-gray-50 shrink-0">
          <div className="text-center px-3 py-3">
            <div className="text-xl font-bold text-blue-600">{summary.total_jobs_attempted}</div>
            <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-0.5">Attempted</div>
          </div>
          <div className="text-center px-3 py-3">
            <div className="text-xl font-bold text-green-600">{summary.jobs_fully_scheduled}</div>
            <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-0.5">Scheduled</div>
          </div>
          <div className="text-center px-3 py-3">
            <div className={`text-xl font-bold ${summary.jobs_with_conflicts > 0 ? 'text-amber-600' : 'text-gray-300'}`}>
              {summary.jobs_with_conflicts}
            </div>
            <div className="text-[10px] text-gray-400 uppercase tracking-wide mt-0.5">Conflicts</div>
          </div>
        </div>

        {/* Scheduled jobs list */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {summary.scheduled.length === 0 && summary.jobs_with_conflicts === 0 && (
            <p className="text-sm text-gray-400 italic text-center py-8">No jobs were processed.</p>
          )}

          {summary.scheduled.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                <CheckCircle size={11} className="text-green-500"/> Scheduled
              </p>
              <div className="space-y-2">
                {summary.scheduled.map(job => (
                  <div key={job.job_id} className="border border-green-200 bg-green-50 rounded-xl px-4 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-gray-800 truncate">{job.job_name}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {job.step_count} step{job.step_count !== 1 ? 's' : ''} scheduled
                        </p>
                      </div>
                      <span className="text-[10px] font-bold text-green-700 bg-green-100 px-2 py-0.5 rounded-full shrink-0">
                        Done
                      </span>
                    </div>
                    <div className="mt-2 flex items-center gap-1.5 text-xs text-green-700">
                      <Clock size={11}/>
                      {fmt(job.earliest_start)} → {fmt(job.latest_end)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {summary.jobs_with_conflicts > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                <AlertTriangle size={11} className="text-amber-500"/> Could not schedule
              </p>
              <div className="space-y-2">
                {summary.conflicted_job_ids.map(jobId => (
                  <div key={jobId} className="border border-amber-200 bg-amber-50 rounded-xl px-4 py-3">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold text-gray-800">
                        {jobMap[jobId]?.name ?? `Job #${jobId}`}
                      </p>
                      <span className="text-[10px] font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
                        Conflict
                      </span>
                    </div>
                    <p className="text-xs text-amber-700 mt-1">
                      Review the conflict details to resolve.
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t border-gray-100 text-xs text-gray-400">
          Jobs page has been refreshed with the latest schedule.
        </div>
      </div>
    </>
  )
}

// ─── Main toolbar component ───────────────────────────────────────────────────

export default function SchedulerToolbar() {
  const {
    status, conflicts, lastRun, running, error,
    runScheduler, summary,
  } = useSchedulerContext()

  const qc = useQueryClient()
  const [panelOpen, setPanelOpen] = useState(false)
  const [summaryOpen, setSummaryOpen] = useState(false)

  // Build a job name/priority map from cached query data
  const cachedJobs = (qc.getQueryData<{ id: number; name: string; priority: string; lock_status: boolean }[]>(['sched-jobs'])) ?? []
  const jobMap = Object.fromEntries(cachedJobs.map(j => [j.id, { name: j.name, priority: j.priority }]))

  async function handleLockJob(jobId: number) {
    await schedJobsApi.update(jobId, { lock_status: true })
    qc.invalidateQueries({ queryKey: ['sched-jobs'] })
    setPanelOpen(false)
  }

  const fmtTime = (d: Date | null) =>
    d ? d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : null

  // ── Button rendering per state ─────────────────────────────────────────────

  if (status === 'greyed-locked') {
    return (
      <div className="flex items-center" title="All jobs are locked. Unlock a job to enable scheduling.">
        <button
          disabled
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-100 text-gray-400 text-sm cursor-not-allowed select-none"
        >
          <Lock size={14} />
          Auto-Schedule
        </button>
      </div>
    )
  }

  if (status === 'greyed-clean') {
    return (
      <>
        <div className="flex items-center gap-2">
          <div title="Schedule is up to date.">
            <button
              disabled
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-100 text-gray-400 text-sm cursor-not-allowed select-none"
            >
              <CheckCircle size={14} />
              Auto-Schedule
            </button>
          </div>
          {lastRun && (
            <span className="text-xs text-gray-400 flex items-center gap-1">
              <Clock size={12} /> {fmtTime(lastRun)}
            </span>
          )}
          {/* Show results link if summary available */}
          {summary && (
            <button
              onClick={() => setSummaryOpen(true)}
              className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1 underline underline-offset-2"
            >
              View results
            </button>
          )}
        </div>
        {summaryOpen && summary && (
          <ResultSummaryPanel
            summary={summary}
            jobMap={jobMap}
            onClose={() => setSummaryOpen(false)}
          />
        )}
      </>
    )
  }

  if (status === 'warn') {
    return (
      <>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPanelOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500 text-white text-sm font-medium hover:bg-amber-600 transition-colors shadow-sm"
          >
            <AlertTriangle size={14} />
            Review Conflicts ({conflicts.length})
          </button>
          {lastRun && (
            <span className="text-xs text-gray-400 flex items-center gap-1">
              <Clock size={12} /> {fmtTime(lastRun)}
            </span>
          )}
        </div>

        {panelOpen && (
          <ConflictPanel
            conflicts={conflicts}
            jobMap={jobMap}
            onClose={() => setPanelOpen(false)}
            onLockJob={handleLockJob}
          />
        )}
      </>
    )
  }

  // Default: 'active' state
  return (
    <>
      <div className="flex items-center gap-2">
        <button
          onClick={async () => {
            await runScheduler()
            // Auto-open summary panel after run completes
            setSummaryOpen(true)
          }}
          disabled={running}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium text-white shadow-sm transition-all
            ${running
              ? 'bg-blue-400 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700 animate-pulse'
            }`}
        >
          {running
            ? <Loader2 size={14} className="animate-spin" />
            : <Zap size={14} />
          }
          {running ? 'Scheduling...' : 'Auto-Schedule'}
        </button>

        {/* Reschedule needed indicator */}
        {!running && (
          <span className="text-xs text-amber-600 flex items-center gap-1 whitespace-nowrap font-medium">
            <RotateCcw size={11}/> Reschedule Needed
          </span>
        )}

        {error && (
          <span className="text-xs text-red-600 whitespace-nowrap">{error}</span>
        )}
      </div>

      {/* Result summary panel — opens automatically after run */}
      {summaryOpen && summary && (
        <ResultSummaryPanel
          summary={summary}
          jobMap={jobMap}
          onClose={() => setSummaryOpen(false)}
        />
      )}
    </>
  )
}
