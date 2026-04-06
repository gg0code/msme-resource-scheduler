// src/components/common/UnavailabilityPanel.tsx
// Reusable panel shown in expanded employee/machine rows.
// Shows existing unavailability periods and a form to add new ones.

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../../api/client'
import { Plus, Trash2, Loader2, CalendarOff, X, Check, AlertCircle } from 'lucide-react'
import { UNAVAILABILITY } from '../../api/api_endpoints'

interface Period {
  id: number
  start_date: string
  end_date: string
  reason: string | null
}

interface Props {
  resourceType: 'employee' | 'machine'
  resourceId: number
  accentColor?: 'blue' | 'green'   // blue for employee, green for machine
}

const EMPLOYEE_REASONS = [
  'Annual Leave', 'Sick Leave', 'Casual Leave', 'Public Holiday',
  'Training', 'Personal', 'Other',
]
const MACHINE_REASONS = [
  'Scheduled Maintenance', 'Breakdown', 'Not Available', 'Repair',
  'Inspection', 'Calibration', 'Other',
]

export default function UnavailabilityPanel({ resourceType, resourceId, accentColor = 'blue' }: Props) {
  const qc = useQueryClient()
  const isEmp = resourceType === 'employee'
  const accent = accentColor === 'blue'
    ? { bg: 'bg-blue-50', border: 'border-blue-100', badge: 'bg-blue-100 text-blue-700', icon: 'text-blue-500', btn: 'bg-blue-600 hover:bg-blue-700' }
    : { bg: 'bg-green-50', border: 'border-green-100', badge: 'bg-green-100 text-green-700', icon: 'text-green-600', btn: 'bg-green-600 hover:bg-green-700' }

  const apiPath = isEmp
    ? UNAVAILABILITY.employeeLeaves(resourceId)
    : UNAVAILABILITY.machineDowntimes(resourceId)
  const queryKey = isEmp
    ? ['emp-leaves', resourceId]
    : ['mach-downtimes', resourceId]

  const [showForm, setShowForm] = useState(false)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate]     = useState('')
  const [reason, setReason]       = useState('')
  const [customReason, setCustomReason] = useState('')
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [formError, setFormError] = useState('')

  const { data: periods = [], isLoading } = useQuery<Period[]>({
    queryKey,
    queryFn: () => apiClient.get(apiPath).then(r => r.data),
  })

  const addPeriod = useMutation({
    mutationFn: (body: Record<string, unknown>) => apiClient.post(apiPath, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey })
      setShowForm(false)
      setStartDate(''); setEndDate(''); setReason(''); setCustomReason(''); setFormError('')
    },
    onError: (err: unknown) => {
      const msg = (err as {response?:{data?:{detail?:string}}})?.response?.data?.detail
      setFormError(msg ?? 'Failed to save')
    },
  })

  const deletePeriod = useMutation({
    mutationFn: (id: number) => apiClient.delete(isEmp ? UNAVAILABILITY.employeeLeave(resourceId, id) : UNAVAILABILITY.machineDowntime(resourceId, id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey })
      setDeletingId(null)
    },
  })

  function handleSubmit() {
    setFormError('')
    if (!startDate || !endDate) { setFormError('Start and end date are required'); return }
    if (endDate < startDate)    { setFormError('End date must be after start date'); return }
    const finalReason = reason === 'Other' ? customReason : reason
    addPeriod.mutate({ start_date: startDate, end_date: endDate, reason: finalReason || null } as Record<string, unknown>)
  }

  function formatDate(d: string) {
    return new Date(d + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
  }

  function dayCount(s: string, e: string) {
    const diff = (new Date(e).getTime() - new Date(s).getTime()) / 86400000
    return Math.round(diff) + 1
  }

  const reasons = isEmp ? EMPLOYEE_REASONS : MACHINE_REASONS

  return (
    <div className={`${accent.bg} border-t ${accent.border} px-6 py-4`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <CalendarOff size={13} className={accent.icon}/>
          <span className="text-xs font-semibold text-gray-700">
            {isEmp ? 'Leave / Unavailability' : 'Downtime / Unavailability'}
          </span>
          {periods.length > 0 && (
            <span className={`px-1.5 py-0.5 rounded-full text-xs font-medium ${accent.badge}`}>
              {periods.length}
            </span>
          )}
        </div>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className={`flex items-center gap-1 text-xs text-white ${accent.btn} rounded-md px-2.5 py-1 font-medium transition-colors`}>
            <Plus size={11}/> Add Period
          </button>
        )}
      </div>

      {/* Add form */}
      {showForm && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 mb-3 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Start Date *</label>
              <input type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={startDate} onChange={e => setStartDate(e.target.value)}/>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">End Date *</label>
              <input type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={endDate} onChange={e => setEndDate(e.target.value)} min={startDate}/>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Reason</label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={reason} onChange={e => setReason(e.target.value)}>
              <option value="">Select reason...</option>
              {reasons.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          {reason === 'Other' && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Specify reason</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Enter reason..."
                value={customReason} onChange={e => setCustomReason(e.target.value)}/>
            </div>
          )}
          {formError && (
            <div className="flex items-center gap-1.5 text-xs text-red-600">
              <AlertCircle size={12}/>{formError}
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={handleSubmit} disabled={addPeriod.isPending}
              className={`flex items-center gap-1 text-xs text-white ${accent.btn} rounded-md px-3 py-1.5 font-medium disabled:opacity-50`}>
              {addPeriod.isPending ? <><Loader2 size={11} className="animate-spin"/>Saving...</> : <><Check size={11}/>Save</>}
            </button>
            <button onClick={() => { setShowForm(false); setFormError('') }}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-md px-3 py-1.5">
              <X size={11}/> Cancel
            </button>
          </div>
        </div>
      )}

      {/* Periods list */}
      {isLoading ? (
        <div className="flex items-center gap-2 text-gray-400 text-xs py-2">
          <Loader2 size={12} className="animate-spin"/>Loading...
        </div>
      ) : periods.length === 0 ? (
        <p className="text-xs text-gray-400 italic">
          No {isEmp ? 'leave' : 'downtime'} periods recorded. Add one above.
        </p>
      ) : (
        <div className="space-y-1.5">
          {periods.map(p => (
            <div key={p.id}
              className="flex items-center justify-between bg-white border border-gray-100 rounded-lg px-3 py-2">
              <div className="flex items-center gap-3">
                <div>
                  <span className="text-xs font-medium text-gray-800">
                    {formatDate(p.start_date)} - {formatDate(p.end_date)}
                  </span>
                  <span className="ml-2 text-xs text-gray-400">
                    ({dayCount(p.start_date, p.end_date)} day{dayCount(p.start_date, p.end_date) !== 1 ? 's' : ''})
                  </span>
                </div>
                {p.reason && (
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${accent.badge}`}>
                    {p.reason}
                  </span>
                )}
              </div>
              <div>
                {deletingId === p.id ? (
                  <span className="inline-flex items-center gap-1.5 text-xs">
                    <button onClick={() => deletePeriod.mutate(p.id)}
                      className="px-2 py-0.5 bg-red-600 text-white rounded hover:bg-red-700 font-medium text-xs">
                      {deletePeriod.isPending ? '...' : 'Yes'}
                    </button>
                    <button onClick={() => setDeletingId(null)}
                      className="px-2 py-0.5 bg-gray-200 text-gray-600 rounded hover:bg-gray-300 text-xs">
                      No
                    </button>
                  </span>
                ) : (
                  <button onClick={() => setDeletingId(p.id)}
                    className="text-red-400 hover:text-red-600 p-1 rounded">
                    <Trash2 size={12}/>
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
