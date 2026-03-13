// src/pages/SchedStepsPage.tsx — Prompt 1 Part B §9
// Full step CRUD, status patch, amber setup rows, reserve machine tag

import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Pencil, Trash2, Loader2, AlertCircle,
  ChevronLeft, Printer, RefreshCw,
} from 'lucide-react'
import {
  schedJobsApi, stepsApi, resourcesApi,
  SchedJob, SchedStep, SchedResource,
  StepType, StepStatus, StepCreate, StepUpdate,
} from '../api/scheduling'
import { useSchedulerContext } from '../scheduler/SchedulerContext'

// ─── Colour maps ──────────────────────────────────────────────────────────────

const STEP_STATUS_BADGE: Record<StepStatus, string> = {
  pending:     'bg-gray-100 text-gray-500',
  ready:       'bg-blue-100 text-blue-700',
  in_progress: 'bg-amber-100 text-amber-700',
  complete:    'bg-green-100 text-green-700',
}

const PRIORITY_BADGE: Record<string, string> = {
  critical: 'bg-red-100 text-red-700',
  urgent:   'bg-amber-100 text-amber-700',
  low:      'bg-gray-100 text-gray-600',
}

// ─── Resource name resolver ───────────────────────────────────────────────────

function ResourceNames({
  ids, resources,
}: { ids: number[]; resources: SchedResource[] }) {
  const names = ids
    .map(id => resources.find(r => r.id === id)?.name ?? `#${id}`)
    .join(', ')
  return <span className="text-gray-700">{names || '—'}</span>
}

// ─── Step form ────────────────────────────────────────────────────────────────

interface StepFormData {
  step_type:             StepType
  duration_minutes:      string
  required_machine_ids:  number[]
  required_helper_ids:   number[]
  reserve_machine_id:    number | null
}

const EMPTY_STEP: StepFormData = {
  step_type: 'regular', duration_minutes: '',
  required_machine_ids: [], required_helper_ids: [], reserve_machine_id: null,
}

function StepModal({
  initial, resources, onClose, onSave,
}: {
  initial?: SchedStep
  resources: SchedResource[]
  onClose: () => void
  onSave: (data: StepCreate | StepUpdate) => void
}) {
  const [form, setForm] = useState<StepFormData>(
    initial
      ? {
          step_type: initial.step_type,
          duration_minutes: String(initial.duration_minutes),
          required_machine_ids: initial.required_machine_ids,
          required_helper_ids: initial.required_helper_ids,
          reserve_machine_id: initial.reserve_machine_id,
        }
      : EMPTY_STEP
  )

  const machines = resources.filter(r => r.type === 'machine')
  const helpers  = resources.filter(r => r.type === 'helper')

  const toggleId = (key: 'required_machine_ids' | 'required_helper_ids', id: number) => {
    setForm(f => ({
      ...f,
      [key]: f[key].includes(id) ? f[key].filter(x => x !== id) : [...f[key], id],
    }))
  }

  const validationError = (): string | null => {
    if (!form.duration_minutes || Number(form.duration_minutes) < 1)
      return 'Duration must be at least 1 minute.'
    if (form.step_type === 'setup' && form.required_machine_ids.length > 0)
      return 'Setup steps cannot have required machines.'
    if (form.step_type === 'regular' && form.reserve_machine_id !== null)
      return 'reserve_machine_id is only valid for setup steps.'
    return null
  }

  const err = validationError()

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-semibold mb-4">
          {initial ? `Edit Step ${initial.sequence_order}` : 'Add Step'}
        </h2>

        <div className="space-y-4">
          {/* Step type */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Step Type</label>
            <div className="flex gap-2">
              {(['regular', 'setup'] as StepType[]).map(t => (
                <button
                  key={t}
                  onClick={() => setForm(f => ({
                    ...f, step_type: t,
                    ...(t === 'regular' ? { reserve_machine_id: null } : { required_machine_ids: [] }),
                  }))}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    form.step_type === t
                      ? t === 'setup'
                        ? 'bg-amber-100 border-amber-400 text-amber-800'
                        : 'bg-blue-100 border-blue-400 text-blue-800'
                      : 'border-gray-200 text-gray-500 hover:bg-gray-50'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Duration */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Duration (minutes) *</label>
            <input
              type="number" min={1}
              className="w-full border rounded-lg px-3 py-2 text-sm"
              value={form.duration_minutes}
              onChange={e => setForm(f => ({ ...f, duration_minutes: e.target.value }))}
            />
          </div>

          {/* Machines — hidden for setup */}
          {form.step_type === 'regular' && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Required Machines</label>
              <div className="flex flex-wrap gap-2">
                {machines.map(m => (
                  <button
                    key={m.id}
                    onClick={() => toggleId('required_machine_ids', m.id)}
                    className={`px-2.5 py-1 rounded-lg text-xs border transition-colors ${
                      form.required_machine_ids.includes(m.id)
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'border-gray-300 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    {m.name}
                  </button>
                ))}
                {machines.length === 0 && <span className="text-xs text-gray-400">No machines available</span>}
              </div>
            </div>
          )}

          {/* Helpers */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Required Helpers</label>
            <div className="flex flex-wrap gap-2">
              {helpers.map(h => (
                <button
                  key={h.id}
                  onClick={() => toggleId('required_helper_ids', h.id)}
                  className={`px-2.5 py-1 rounded-lg text-xs border transition-colors ${
                    form.required_helper_ids.includes(h.id)
                      ? 'bg-green-600 text-white border-green-600'
                      : 'border-gray-300 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {h.name}
                </button>
              ))}
              {helpers.length === 0 && <span className="text-xs text-gray-400">No helpers available</span>}
            </div>
          </div>

          {/* Reserve machine — setup only */}
          {form.step_type === 'setup' && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Reserve Machine (optional)</label>
              <select
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={form.reserve_machine_id ?? ''}
                onChange={e => setForm(f => ({
                  ...f, reserve_machine_id: e.target.value ? Number(e.target.value) : null,
                }))}
              >
                <option value="">None</option>
                {machines.map(m => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
              <p className="text-xs text-gray-400 mt-1">
                Blocks this machine for the full step duration without running it.
              </p>
            </div>
          )}
        </div>

        {err && (
          <div className="mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {err}
          </div>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border hover:bg-gray-50">
            Cancel
          </button>
          <button
            disabled={!!err}
            onClick={() => {
              if (err) return
              onSave({
                step_type: form.step_type,
                duration_minutes: Number(form.duration_minutes),
                required_machine_ids: form.required_machine_ids,
                required_helper_ids: form.required_helper_ids,
                reserve_machine_id: form.reserve_machine_id,
              })
            }}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {initial ? 'Save' : 'Add Step'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function SchedStepsPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const id = Number(jobId)
  const qc = useQueryClient()

  const [editStep, setEditStep]   = useState<SchedStep | null | 'new'>(null)
  const [deleteId, setDeleteId]   = useState<number | null>(null)
  const [statusModal, setStatusModal] = useState<SchedStep | null>(null)

  const { data: job, isLoading: jobLoading } = useQuery({
    queryKey: ['sched-job', id],
    queryFn: () => schedJobsApi.get(id).then(r => r.data),
  })
  const { data: steps = [], isLoading: stepsLoading } = useQuery({
    queryKey: ['sched-steps', id],
    queryFn: () => stepsApi.list(id).then(r => r.data),
  })
  const { data: resources = [] } = useQuery({
    queryKey: ['sched-resources'],
    queryFn: () => resourcesApi.list().then(r => r.data),
  })

  const { markDirty } = useSchedulerContext()

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['sched-steps', id] })
    qc.invalidateQueries({ queryKey: ['sched-job', id] })
    qc.invalidateQueries({ queryKey: ['sched-jobs'] })
  }

  const createMut = useMutation({
    mutationFn: (d: StepCreate) => stepsApi.create(id, d),
    onSuccess: () => { invalidate(); setEditStep(null); markDirty() },
  })
  const updateMut = useMutation({
    mutationFn: ({ sid, d }: { sid: number; d: StepUpdate }) => stepsApi.update(id, sid, d),
    onSuccess: () => { invalidate(); setEditStep(null); markDirty() },
  })
  const deleteMut = useMutation({
    mutationFn: (sid: number) => stepsApi.delete(id, sid),
    onSuccess: () => { invalidate(); setDeleteId(null); markDirty() },
  })
  const statusMut = useMutation({
    mutationFn: ({ sid, status }: { sid: number; status: StepStatus }) =>
      stepsApi.patchStatus(id, sid, status),
    onSuccess: () => { invalidate(); setStatusModal(null); markDirty() },
  })

  if (jobLoading || stepsLoading)
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        <Loader2 className="animate-spin mr-2" size={20} /> Loading…
      </div>
    )
  if (!job)
    return (
      <div className="p-6 text-red-600 flex items-center gap-2">
        <AlertCircle size={18} /> Job not found.
      </div>
    )

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Back + header */}
      <div className="flex items-center gap-3 mb-4">
        <Link to="/sched-jobs" className="text-gray-400 hover:text-gray-700">
          <ChevronLeft size={20} />
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">{job.name}</h1>
            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${PRIORITY_BADGE[job.priority]}`}>
              {job.priority}
            </span>
          </div>
          <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
            <span>Deadline: {new Date(job.deadline).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</span>
            {job.expected_profit && (
              <span>Profit: ₹{job.expected_profit.toLocaleString('en-IN')}</span>
            )}
            <span className="capitalize">Shift: {job.shift}</span>
          </div>
        </div>
        <Link
          to={`/sched-jobs/${id}/print`}
          target="_blank"
          className="flex items-center gap-2 px-3 py-2 border rounded-lg text-sm text-gray-600 hover:bg-gray-50"
        >
          <Printer size={15} /> Print Job Card
        </Link>
      </div>

      {/* Steps table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden mb-4">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">Steps ({steps.length})</h2>
          <button
            onClick={() => setEditStep('new')}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
          >
            <Plus size={14} /> Add Step
          </button>
        </div>

        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600 w-12">Seq</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Type</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Duration</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Machines</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Helpers</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Reserve</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Status</th>
              <th className="text-left px-4 py-2.5 font-medium text-gray-600">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {steps.length === 0 && (
              <tr>
                <td colSpan={8} className="text-center py-8 text-gray-400">
                  No steps yet. Click "Add Step" to create the first one.
                </td>
              </tr>
            )}
            {steps.map(step => (
              <tr
                key={step.id}
                className={`transition-colors ${
                  step.step_type === 'setup'
                    ? 'bg-amber-50 hover:bg-amber-100/60'
                    : 'hover:bg-gray-50'
                }`}
              >
                <td className="px-4 py-3 font-mono font-medium text-gray-700">
                  {step.sequence_order}
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    step.step_type === 'setup'
                      ? 'bg-amber-100 text-amber-800 border border-amber-200'
                      : 'bg-blue-100 text-blue-700'
                  }`}>
                    {step.step_type}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-600">{step.duration_minutes} min</td>
                <td className="px-4 py-3">
                  <ResourceNames ids={step.required_machine_ids} resources={resources} />
                </td>
                <td className="px-4 py-3">
                  <ResourceNames ids={step.required_helper_ids} resources={resources} />
                </td>
                <td className="px-4 py-3">
                  {step.is_setup_active ? (
                    <span className="inline-flex items-center gap-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                      ⛓ {resources.find(r => r.id === step.reserve_machine_id)?.name ?? `#${step.reserve_machine_id}`} reserved
                    </span>
                  ) : (
                    <span className="text-gray-300">—</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => setStatusModal(step)}
                    className={`px-2 py-0.5 rounded-full text-xs font-medium cursor-pointer hover:opacity-80 ${STEP_STATUS_BADGE[step.status]}`}
                    title="Click to update status"
                  >
                    {step.status.replace('_', ' ')}
                  </button>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setEditStep(step)}
                      className="p-1.5 rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-100"
                      title="Edit step"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => setDeleteId(step.id)}
                      className="p-1.5 rounded-lg bg-red-50 text-red-500 hover:bg-red-100"
                      title="Delete step"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Step form modal */}
      {editStep !== null && (
        <StepModal
          initial={editStep === 'new' ? undefined : editStep}
          resources={resources}
          onClose={() => setEditStep(null)}
          onSave={d => {
            if (editStep === 'new') createMut.mutate(d as StepCreate)
            else updateMut.mutate({ sid: (editStep as SchedStep).id, d })
          }}
        />
      )}

      {/* Status update modal */}
      {statusModal && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
          <div className="bg-white rounded-xl shadow-xl p-6 w-80">
            <div className="flex items-center gap-2 mb-4">
              <RefreshCw size={18} className="text-blue-600" />
              <h3 className="font-semibold">Update Step {statusModal.sequence_order} Status</h3>
            </div>
            <div className="space-y-2">
              {(['pending', 'ready', 'in_progress', 'complete'] as StepStatus[]).map(s => (
                <button
                  key={s}
                  onClick={() => statusMut.mutate({ sid: statusModal.id, status: s })}
                  disabled={statusMut.isPending}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm border transition-colors
                    ${statusModal.status === s
                      ? 'border-blue-400 bg-blue-50 text-blue-700 font-medium'
                      : 'border-gray-200 hover:bg-gray-50'
                    }`}
                >
                  <span className={`inline-block w-2 h-2 rounded-full mr-2 ${
                    s === 'pending' ? 'bg-gray-400' :
                    s === 'ready' ? 'bg-blue-500' :
                    s === 'in_progress' ? 'bg-amber-500' : 'bg-green-500'
                  }`} />
                  {s.replace('_', ' ')}
                  {s === statusModal.status && ' (current)'}
                </button>
              ))}
            </div>
            {statusMut.error && (
              <div className="mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1">
                {(statusMut.error as Error).message}
              </div>
            )}
            <button
              onClick={() => setStatusModal(null)}
              className="mt-4 w-full px-4 py-2 text-sm rounded-lg border hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Delete confirm */}
      {deleteId !== null && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center">
          <div className="bg-white rounded-xl shadow-xl p-6 w-80 text-center">
            <Trash2 className="text-red-500 mx-auto mb-3" size={28} />
            <h3 className="font-semibold mb-1">Delete step?</h3>
            <p className="text-sm text-gray-500 mb-4">
              Remaining steps will be automatically re-sequenced.
            </p>
            <div className="flex gap-2 justify-center">
              <button
                onClick={() => setDeleteId(null)}
                className="px-4 py-2 text-sm rounded-lg border hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMut.mutate(deleteId)}
                disabled={deleteMut.isPending}
                className="px-4 py-2 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700"
              >
                {deleteMut.isPending ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
