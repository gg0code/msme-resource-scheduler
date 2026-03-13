// src/pages/SchedJobsPage.tsx — V3.1
// markDirty() wired into create, update, delete, lock toggle
// checkAllLocked() called after every jobs list change

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Plus, Pencil, Trash2, Lock, Unlock, ChevronDown, ChevronRight,
  Loader2, AlertCircle, Printer, Layers,
} from 'lucide-react'
import { schedJobsApi } from '../api/scheduling'
import type {
  SchedJob, SchedStep, SchedPriority,
  SchedJobStatus, SchedShift, JobCreate,
} from '../api/scheduling'
import { useSchedulerContext } from '../scheduler/SchedulerContext'

// ─── Colour maps ──────────────────────────────────────────────────────────────

const PRIORITY_BADGE: Record<SchedPriority, string> = {
  critical: 'bg-red-100 text-red-700 border border-red-200',
  urgent:   'bg-amber-100 text-amber-700 border border-amber-200',
  low:      'bg-gray-100 text-gray-600 border border-gray-200',
}

const STATUS_BADGE: Record<SchedJobStatus, string> = {
  pending:     'bg-gray-100 text-gray-600',
  scheduled:   'bg-blue-100 text-blue-700',
  in_progress: 'bg-amber-100 text-amber-700',
  complete:    'bg-green-100 text-green-700',
}

const STEP_STATUS_BADGE: Record<string, string> = {
  pending:     'bg-gray-100 text-gray-500',
  ready:       'bg-blue-100 text-blue-700',
  in_progress: 'bg-amber-100 text-amber-700',
  complete:    'bg-green-100 text-green-700',
}

const fmtDate = (d: string) =>
  new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })

const fmtProfit = (n: number | null) =>
  n == null ? '—' : `₹${n.toLocaleString('en-IN')}`

// ─── Inline steps ─────────────────────────────────────────────────────────────

function InlineSteps({ steps }: { steps: SchedStep[] }) {
  if (!steps.length)
    return <div className="px-6 py-3 text-sm text-gray-400 italic">No steps yet.</div>
  return (
    <div className="px-6 py-3 bg-gray-50 border-t border-gray-100">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-400 uppercase tracking-wide">
            <th className="text-left pb-1 w-8">Seq</th>
            <th className="text-left pb-1">Type</th>
            <th className="text-left pb-1">Duration</th>
            <th className="text-left pb-1">Status</th>
          </tr>
        </thead>
        <tbody>
          {steps.map(s => (
            <tr key={s.id} className={s.step_type === 'setup' ? 'bg-amber-50' : ''}>
              <td className="py-0.5 font-mono">{s.sequence_order}</td>
              <td className="py-0.5">
                <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                  s.step_type === 'setup' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'
                }`}>{s.step_type}</span>
                {s.is_setup_active && <span className="ml-1 text-amber-600 text-xs">⛓</span>}
              </td>
              <td className="py-0.5">{s.duration_minutes} min</td>
              <td className="py-0.5">
                <span className={`px-1.5 py-0.5 rounded text-xs ${STEP_STATUS_BADGE[s.status]}`}>
                  {s.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Job modal ────────────────────────────────────────────────────────────────

const EMPTY_FORM: JobCreate = {
  name: '', priority: 'low', expected_profit: null,
  deadline: '', shift: 'morning', lock_status: false,
}

function JobModal({
  initial, onClose, onSave,
}: {
  initial?: SchedJob
  onClose: () => void
  onSave:  (data: JobCreate) => void
}) {
  const [form, setForm] = useState<JobCreate>(
    initial ? {
      name: initial.name, priority: initial.priority,
      expected_profit: initial.expected_profit,
      deadline: initial.deadline.split('T')[0],
      shift: initial.shift, lock_status: initial.lock_status,
    } : EMPTY_FORM
  )
  const set = (k: keyof JobCreate, v: unknown) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-semibold mb-4">{initial ? 'Edit Job' : 'New Scheduling Job'}</h2>
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Job Name *</label>
            <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.name}
              onChange={e => set('name', e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Priority</label>
              <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.priority}
                onChange={e => set('priority', e.target.value)}>
                <option value="critical">Critical</option>
                <option value="urgent">Urgent</option>
                <option value="low">Low</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Shift</label>
              <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.shift}
                onChange={e => set('shift', e.target.value as SchedShift)}>
                <option value="morning">Morning</option>
                <option value="evening">Evening</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Deadline *</label>
              <input type="date" className="w-full border rounded-lg px-3 py-2 text-sm"
                value={form.deadline} onChange={e => set('deadline', e.target.value)} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Profit (₹)</label>
              <input type="number" className="w-full border rounded-lg px-3 py-2 text-sm"
                value={form.expected_profit ?? ''}
                onChange={e => set('expected_profit', e.target.value ? Number(e.target.value) : null)} />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border hover:bg-gray-50">Cancel</button>
          <button
            onClick={() => { if (form.name && form.deadline) onSave(form) }}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700"
          >
            {initial ? 'Save Changes' : 'Create Job'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function SchedJobsPage() {
  const qc = useQueryClient()
  const { markDirty, checkAllLocked } = useSchedulerContext()

  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [editJob,    setEditJob]    = useState<SchedJob | null | 'new'>(null)
  const [deleteId,   setDeleteId]   = useState<number | null>(null)

  const { data: jobs = [], isLoading, error } = useQuery({
    queryKey: ['sched-jobs'],
    queryFn: () => schedJobsApi.list().then(r => r.data),
  })

  // Keep all-locked state in sync whenever jobs list changes
  useEffect(() => { checkAllLocked(jobs) }, [jobs, checkAllLocked])

  const invalidate = () => qc.invalidateQueries({ queryKey: ['sched-jobs'] })

  const createMut = useMutation({
    mutationFn: (d: JobCreate) => schedJobsApi.create(d),
    onSuccess: () => { invalidate(); setEditJob(null); markDirty() },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, d }: { id: number; d: JobCreate }) => schedJobsApi.update(id, d),
    onSuccess: () => { invalidate(); setEditJob(null); markDirty() },
  })
  const deleteMut = useMutation({
    mutationFn: (id: number) => schedJobsApi.delete(id),
    onSuccess: () => { invalidate(); setDeleteId(null); markDirty() },
  })
  const lockMut = useMutation({
    mutationFn: ({ id, lock }: { id: number; lock: boolean }) =>
      schedJobsApi.update(id, { lock_status: lock }),
    onSuccess: () => { invalidate(); markDirty() },
  })

  if (isLoading) return (
    <div className="flex items-center justify-center h-64 text-gray-500">
      <Loader2 className="animate-spin mr-2" size={20} /> Loading jobs…
    </div>
  )
  if (error) return (
    <div className="flex items-center gap-2 text-red-600 p-4">
      <AlertCircle size={18} /> Failed to load jobs.
    </div>
  )

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Scheduling Jobs</h1>
          <p className="text-sm text-gray-500 mt-0.5">{jobs.length} job{jobs.length !== 1 ? 's' : ''}</p>
        </div>
        <button onClick={() => setEditJob('new')}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
          <Plus size={16} /> New Job
        </button>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-600 w-8"></th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Job Name</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Priority</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Deadline</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Profit</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Shift</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Steps</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Lock</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {jobs.length === 0 && (
              <tr><td colSpan={10} className="text-center py-10 text-gray-400">No jobs yet.</td></tr>
            )}
            {jobs.map(job => (
              <>
                <tr key={job.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <button onClick={() => setExpandedId(expandedId === job.id ? null : job.id)}
                      className="text-gray-400 hover:text-gray-700">
                      {expandedId === job.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </button>
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900">{job.name}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${PRIORITY_BADGE[job.priority]}`}>
                      {job.priority}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{fmtDate(job.deadline)}</td>
                  <td className="px-4 py-3 text-gray-600">{fmtProfit(job.expected_profit)}</td>
                  <td className="px-4 py-3 text-gray-600 capitalize">{job.shift}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE[job.status]}`}>
                      {job.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{job.steps.length}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => lockMut.mutate({ id: job.id, lock: !job.lock_status })}
                      className={`p-1.5 rounded-lg transition-colors ${
                        job.lock_status
                          ? 'bg-amber-100 text-amber-700 hover:bg-amber-200'
                          : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                      }`}
                      title={job.lock_status ? 'Unlock job' : 'Lock job'}
                    >
                      {job.lock_status ? <Lock size={14} /> : <Unlock size={14} />}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <Link to={`/sched-jobs/${job.id}/steps`}
                        className="p-1.5 rounded-lg bg-indigo-50 text-indigo-600 hover:bg-indigo-100" title="View Steps">
                        <Layers size={14} />
                      </Link>
                      <Link to={`/sched-jobs/${job.id}/print`} target="_blank"
                        className="p-1.5 rounded-lg bg-gray-50 text-gray-500 hover:bg-gray-100" title="Print">
                        <Printer size={14} />
                      </Link>
                      <button onClick={() => setEditJob(job)}
                        className="p-1.5 rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-100">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => setDeleteId(job.id)}
                        className="p-1.5 rounded-lg bg-red-50 text-red-500 hover:bg-red-100">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
                {expandedId === job.id && (
                  <tr key={`${job.id}-steps`}>
                    <td colSpan={10} className="p-0"><InlineSteps steps={job.steps} /></td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>

      {editJob !== null && (
        <JobModal
          initial={editJob === 'new' ? undefined : editJob}
          onClose={() => setEditJob(null)}
          onSave={d => {
            if (editJob === 'new') createMut.mutate(d)
            else updateMut.mutate({ id: (editJob as SchedJob).id, d })
          }}
        />
      )}

      {deleteId !== null && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
          <div className="bg-white rounded-xl shadow-xl p-6 w-80 text-center">
            <Trash2 className="text-red-500 mx-auto mb-3" size={28} />
            <h3 className="font-semibold text-gray-900 mb-1">Delete job?</h3>
            <p className="text-sm text-gray-500 mb-4">All steps will be permanently deleted.</p>
            <div className="flex gap-2 justify-center">
              <button onClick={() => setDeleteId(null)} className="px-4 py-2 text-sm rounded-lg border hover:bg-gray-50">Cancel</button>
              <button onClick={() => deleteMut.mutate(deleteId)} disabled={deleteMut.isPending}
                className="px-4 py-2 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700">
                {deleteMut.isPending ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
