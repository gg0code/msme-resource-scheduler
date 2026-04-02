/**
 * frontend/src/components/EndJobModal.tsx — v2.0
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * The modal dialog shown when a user clicks the End button on a running or paused job.
 * It serves as the final step of the job timer flow — letting the user review and edit
 * which employees and machines were actually used, see a live cost preview, and confirm
 * job completion. Introduced in v2.0 as part of the time-tracking feature. Sits in the
 * shared components layer; called from Jobs.tsx. Contains real-time client-side cost
 * recalculation logic based on hourly rates from the backend summary.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. On mount, calls timerApi.summary(jobId) to load actual hours, current assignments,
 *    available employees/machines, and the initial cost preview from the backend.
 * 2. Pre-selects employee and machine IDs from the backend's current_employee_ids and
 *    current_machine_ids arrays.
 * 3. Renders an "Actual Hours Worked" banner showing the real time tracked.
 * 4. Renders two scrollable toggle-button grids: one for employees, one for machines.
 *    Each button shows the person/machine name and their hourly rate.
 * 5. When the user toggles a selection, a useEffect fires that recalculates the cost
 *    preview client-side using the hourly rates from the summary response.
 * 6. Renders a Final Cost Summary breakdown: employee cost, machine cost, materials,
 *    misc, total, order value, and actual profit with a green/red trending icon.
 * 7. On Confirm & Complete, calls onConfirm(selectedEmpIds, selectedMacIds) which
 *    triggers timerApi.end() in the parent (Jobs.tsx).
 * 8. Handles loading, error, and confirming states with spinners and disabled buttons.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : EndJobModal (default export)
 * Type         : React component
 * Purpose      : Full-screen modal for completing a job. Loads job summary, shows
 *                editable resource selection, live cost preview, and confirm button.
 * Parameters   : jobId: number — the job being completed
 *                jobName: string — displayed in the modal header
 *                onConfirm: (empIds, macIds) => Promise<void> — called on confirm click
 *                onClose: () => void — called on cancel or backdrop click
 * Returns      : JSX.Element — fixed-position modal with backdrop
 * Calls        : timerApi.summary(), timerApi (via onConfirm in parent)
 * DB/API       : GET /api/timer/{jobId}/summary (on mount and on selection change)
 * Side effects : none — parent handles the actual end() call via onConfirm
 *
 * Name         : CostRow
 * Type         : React component (internal)
 * Purpose      : Renders a single label/value row in the cost breakdown table.
 *                highlight prop makes the row bold (used for Total Cost row).
 * Parameters   : label: string, value: number, highlight?: boolean
 * Returns      : JSX.Element
 * Calls        : fmt() helper
 * DB/API       : none
 * Side effects : none
 *
 * Name         : fmt
 * Type         : internal function
 * Purpose      : Formats a number as Indian Rupee currency string (₹1,23,456).
 *                Returns '—' for null/undefined values.
 * Parameters   : n: number | null | undefined
 * Returns      : string
 * Calls        : Intl/toLocaleString with en-IN locale
 * DB/API       : none
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Jobs.tsx — renders this modal when user clicks End on a job
 *
 * IMPORTS EXPLAINED
 * - useEffect, useState from 'react': State for summary data, selected IDs, preview, loading.
 * - X, Users, Wrench, TrendingUp, TrendingDown, Loader2, CheckCircle2 from 'lucide-react':
 *   Icons for close button, section headers, profit direction, and loading/confirm states.
 * - timerApi from '../api/api_timer': Provides summary() and end() API calls.
 * - JobSummaryResponse from '../api/api_timer': TypeScript type for the summary response.
 *
 * INTERN NOTES
 * - The cost preview is recalculated CLIENT-SIDE when resource selection changes. It
 *   reads hourly rates from the summary response and multiplies by actual_hours. This
 *   avoids an extra API call on every toggle but means the preview logic must stay in
 *   sync with the backend cost_service.py formula.
 * - Design Principle 1: The backend computes actual_hours and provides hourly rates.
 *   The frontend only multiplies them — it does not own the cost formula.
 * - onConfirm is async and the parent (Jobs.tsx) handles calling timerApi.end().
 *   This component never calls end() directly — it delegates via the callback.
 * - The useEffect for preview recalculation re-fetches summary on every selection
 *   change. This is a known minor inefficiency — the rates are already in state from
 *   the first fetch but are re-fetched to stay safe. Acceptable for current scale.
 * - If the modal shows a blank error state: check that /api/timer/{jobId}/summary
 *   is returning 200. The job must be in 'running' or 'paused' state for summary to work.
 * - The catch block in handleConfirm reads error.response.data.detail — FastAPI's
 *   standard error shape. If the backend changes error format this will break silently.
 */

import { useEffect, useState } from 'react'
import { X, Users, Wrench, TrendingUp, TrendingDown, Loader2, CheckCircle2 } from 'lucide-react'
import timerApi from '../api/api_timer'
import type { JobSummaryResponse } from '../api/api_timer'

interface CostBreakdown {
  hours: number
  employee_cost: number
  machine_cost: number
  material_cost: number
  misc_cost: number
  total_cost: number
  order_value: number
  profit: number
}

interface Props {
  jobId: number
  jobName: string
  onConfirm: (employeeIds: number[], machineIds: number[]) => Promise<void>
  onClose: () => void
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function CostRow({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`flex justify-between text-sm py-1 ${highlight ? 'font-semibold text-gray-900' : 'text-gray-600'}`}>
      <span>{label}</span>
      <span>{fmt(value)}</span>
    </div>
  )
}

export default function EndJobModal({ jobId, jobName, onConfirm, onClose }: Props) {
  const [summary, setSummary] = useState<JobSummaryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedEmpIds, setSelectedEmpIds] = useState<number[]>([])
  const [selectedMacIds, setSelectedMacIds] = useState<number[]>([])
  const [preview, setPreview] = useState<CostBreakdown | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  // Load summary on mount
  useEffect(() => {
    timerApi.summary(jobId)
      .then(s => {
        setSummary(s)
        setSelectedEmpIds(s.current_employee_ids)
        setSelectedMacIds(s.current_machine_ids)
        setPreview(s.cost_preview)
      })
      .catch(() => setError('Failed to load job summary'))
      .finally(() => setLoading(false))
  }, [jobId])

  // Recompute preview when selections change
  useEffect(() => {
    if (!summary) return
    setPreviewLoading(true)
    timerApi.summary(jobId)
      .then(s => {
        const empRate = selectedEmpIds.reduce((sum, id) => {
          const emp = s.available_employees.find(e => e.id === id)
          return sum + (emp?.hourly_rate ?? 0)
        }, 0)
        const macRate = selectedMacIds.reduce((sum, id) => {
          const mac = s.available_machines.find(m => m.id === id)
          return sum + (mac?.hourly_rate ?? 0)
        }, 0)
        const hours = s.actual_hours
        const empCost = empRate * hours
        const macCost = macRate * hours
        const matCost = s.cost_preview.material_cost
        const misc = s.cost_preview.misc_cost
        const total = empCost + macCost + matCost + misc
        const profit = s.cost_preview.order_value - total

        setPreview({
          hours,
          employee_cost: empCost,
          machine_cost: macCost,
          material_cost: matCost,
          misc_cost: misc,
          total_cost: total,
          order_value: s.cost_preview.order_value,
          profit,
        })
      })
      .catch(() => {})
      .finally(() => setPreviewLoading(false))
  }, [selectedEmpIds, selectedMacIds])

  const toggleEmp = (id: number) => {
    setSelectedEmpIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const toggleMac = (id: number) => {
    setSelectedMacIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      await onConfirm(selectedEmpIds, selectedMacIds)
    } catch (e: unknown) {
      const msg = (e as {response?:{data?:{detail?:string}}})?.response?.data?.detail
      setError(msg ?? 'Failed to complete job')
      setConfirming(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Complete Job</h2>
            <p className="text-xs text-gray-400 mt-0.5">{jobName}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <X size={18} />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16 gap-2 text-gray-400">
            <Loader2 size={18} className="animate-spin" />
            <span className="text-sm">Loading summary…</span>
          </div>
        ) : error ? (
          <div className="px-6 py-8 text-center text-red-500 text-sm">{error}</div>
        ) : summary ? (
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
            {/* Actual hours */}
            <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 flex items-center justify-between">
              <span className="text-sm font-medium text-blue-700">Actual Hours Worked</span>
              <span className="text-lg font-bold text-blue-800">{summary.actual_hours.toFixed(2)} hrs</span>
            </div>

            {/* Employees */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Users size={14} className="text-gray-500" />
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Employees Used
                </span>
                <span className="text-xs text-gray-400">({selectedEmpIds.length} selected)</span>
              </div>
              <div className="grid grid-cols-2 gap-1.5 max-h-40 overflow-y-auto pr-1">
                {summary.available_employees.map(emp => (
                  <button
                    key={emp.id}
                    onClick={() => toggleEmp(emp.id)}
                    className={`flex items-center justify-between px-3 py-2 rounded-lg text-left text-xs border transition-colors ${
                      selectedEmpIds.includes(emp.id)
                        ? 'bg-blue-50 border-blue-300 text-blue-800'
                        : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    <span className="font-medium truncate">{emp.full_name}</span>
                    <span className="text-gray-400 ml-1 flex-shrink-0">₹{emp.hourly_rate}/hr</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Machines */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Wrench size={14} className="text-gray-500" />
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Machines Used
                </span>
                <span className="text-xs text-gray-400">({selectedMacIds.length} selected)</span>
              </div>
              <div className="grid grid-cols-2 gap-1.5 max-h-32 overflow-y-auto pr-1">
                {summary.available_machines.map(mac => (
                  <button
                    key={mac.id}
                    onClick={() => toggleMac(mac.id)}
                    className={`flex items-center justify-between px-3 py-2 rounded-lg text-left text-xs border transition-colors ${
                      selectedMacIds.includes(mac.id)
                        ? 'bg-purple-50 border-purple-300 text-purple-800'
                        : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    <span className="font-medium truncate">{mac.name}</span>
                    <span className="text-gray-400 ml-1 flex-shrink-0">₹{mac.hourly_rate}/hr</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Cost preview */}
            {preview && (
              <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Final Cost Summary
                  </span>
                  {previewLoading && <Loader2 size={12} className="animate-spin text-gray-400" />}
                </div>
                <div className="divide-y divide-gray-100">
                  <CostRow label="Employee Cost" value={preview.employee_cost} />
                  <CostRow label="Machine Cost" value={preview.machine_cost} />
                  <CostRow label="Raw Material Cost" value={preview.material_cost} />
                  <CostRow label="Misc Cost" value={preview.misc_cost} />
                  <CostRow label="Total Actual Cost" value={preview.total_cost} highlight />
                  <CostRow label="Order Value" value={preview.order_value} />
                </div>
                <div className="mt-2 pt-2 border-t border-gray-200 flex justify-between items-center">
                  <span className="text-sm font-bold text-gray-800">Actual Profit</span>
                  <div className="flex items-center gap-1.5">
                    {preview.profit >= 0
                      ? <TrendingUp size={15} className="text-green-600" />
                      : <TrendingDown size={15} className="text-red-500" />
                    }
                    <span className={`text-base font-bold ${preview.profit >= 0 ? 'text-green-600' : 'text-red-500'}`}>
                      {fmt(preview.profit)}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : null}

        {/* Footer */}
        {!loading && !error && (
          <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-end gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              disabled={confirming}
              className="flex items-center gap-2 px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-60 transition-colors"
            >
              {confirming
                ? <><Loader2 size={14} className="animate-spin" /> Completing…</>
                : <><CheckCircle2 size={14} /> Confirm & Complete</>
              }
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
