// src/components/EndJobModal.tsx - V2.0
// Modal shown when user clicks End button on a running/paused job.
// Allows editing final employee/machine list, shows live cost preview.

import { useEffect, useMemo, useState } from 'react'
import { X, Users, Wrench, TrendingUp, TrendingDown, Loader2, CheckCircle2 } from 'lucide-react'
import timerApi from '../api/api_timer'
import type { CostBreakdown, JobSummaryResponse } from '../api/api_timer'

interface Props {
  jobId: number
  jobName: string
  onConfirm: (employeeIds: number[], machineIds: number[]) => Promise<void>
  onClose: () => void
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '-'
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

  // Load summary on mount
  useEffect(() => {
    timerApi.summary(jobId)
      .then(s => {
        setSummary(s)
        setSelectedEmpIds(s.current_employee_ids)
        setSelectedMacIds(s.current_machine_ids)
      })
      .catch(() => setError('Failed to load job summary'))
      .finally(() => setLoading(false))
  }, [jobId])

  // Derived preview: rates + hours already live in `summary`, so we recompute
  // synchronously rather than re-hitting /summary on every checkbox toggle.
  const preview = useMemo<CostBreakdown | null>(() => {
    if (!summary) return null
    const empRate = selectedEmpIds.reduce((sum, id) => {
      const emp = summary.available_employees.find(e => e.id === id)
      return sum + (emp?.hourly_rate ?? 0)
    }, 0)
    const macRate = selectedMacIds.reduce((sum, id) => {
      const mac = summary.available_machines.find(m => m.id === id)
      return sum + (mac?.hourly_rate ?? 0)
    }, 0)
    const hours = summary.actual_hours
    const empCost = empRate * hours
    const macCost = macRate * hours
    const matCost = summary.cost_preview.material_cost
    const misc = summary.cost_preview.misc_cost
    const total = empCost + macCost + matCost + misc
    const profit = summary.cost_preview.order_value - total

    return {
      hours,
      employee_cost: empCost,
      machine_cost: macCost,
      material_cost: matCost,
      misc_cost: misc,
      total_cost: total,
      order_value: summary.cost_preview.order_value,
      profit,
    }
  }, [summary, selectedEmpIds, selectedMacIds])

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
                </div>
                <div className="divide-y divide-gray-100">
                  <CostRow label="Employee Cost" value={preview.employee_cost} />
                  <CostRow label="Machine Cost" value={preview.machine_cost} />
                  <CostRow label="Raw Material Cost" value={preview.material_cost} />
                  <CostRow label="Misc Cost" value={preview.misc_cost} />
                  <CostRow label="Total Actual Cost" value={preview.total_cost} highlight />
                  <CostRow label="Order Value" value={preview.order_value} />
                </div>
                <div className={`mt-2 pt-2 border-t border-gray-200 flex justify-between items-center`}>
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
