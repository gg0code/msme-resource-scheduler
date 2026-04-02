/**
 * frontend/src/components/common/UnavailabilityPanel.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * A reusable panel for managing unavailability periods (leave for employees,
 * downtime for machines). Shown inside expanded rows on the Employees and Machines
 * pages. Lets users view existing periods, add new ones with a date + reason form,
 * and delete existing ones with a confirmation step. Uses TanStack Query for
 * fetching and mutation — no prop-drilling of data needed. The accent colour adapts
 * to blue (employee) or green (machine) based on the accentColor prop.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Derives the correct API path from resourceType and resourceId:
 *    /api/unavailability/employees/{id}/leaves or /machines/{id}/downtimes.
 * 2. Fetches existing periods with useQuery, renders them as date range rows.
 * 3. Shows an Add Period button that expands an inline form.
 * 4. Form: start date, end date, reason dropdown (employee or machine reasons),
 *    optional custom reason text input when "Other" is selected.
 * 5. Validates dates client-side (both required, end >= start).
 * 6. Submits via useMutation POST to the API path, invalidates query on success.
 * 7. Delete: clicking trash icon sets deletingId — shows inline Yes/No confirmation.
 *    Confirming fires DELETE mutation, clears deletingId on success.
 * 8. Formats dates as "14 Mar 2026" and computes day count between dates.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : UnavailabilityPanel (default export)
 * Type         : React component
 * Purpose      : Manages leave/downtime periods for one employee or machine.
 *                Fetches, creates, and deletes periods. Adapts colour scheme
 *                based on accentColor prop.
 * Parameters   : resourceType: 'employee' | 'machine'
 *                resourceId: number — the employee or machine primary key
 *                accentColor?: 'blue' | 'green' — defaults to 'blue'
 * Returns      : JSX.Element — panel with list, add form, and delete confirmation
 * Calls        : apiClient.get (list), apiClient.post (add), apiClient.delete (remove)
 * DB/API       : GET /api/unavailability/{type}/{id}/leaves|downtimes
 *                POST /api/unavailability/{type}/{id}/leaves|downtimes
 *                DELETE /api/unavailability/{type}/{id}/leaves|downtimes/{periodId}
 * Side effects : invalidates TanStack Query cache on add/delete
 *
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Employees.tsx — rendered in expanded employee row
 * - frontend/src/pages/Machines.tsx — rendered in expanded machine row
 *
 * IMPORTS EXPLAINED
 * - useState from 'react': form field state, showForm, deletingId, formError.
 * - useQuery, useMutation, useQueryClient from '@tanstack/react-query': data fetching,
 *   add/delete mutations, cache invalidation after changes.
 * - apiClient from '../../api/client': authenticated Axios instance.
 * - Plus, Trash2, Loader2, CalendarOff, X, Check, AlertCircle from 'lucide-react':
 *   icons for add button, delete, loading, calendar header, cancel, save, error.
 *
 * INTERN NOTES
 * - The query key uses the resourceId: ['emp-leaves', resourceId] or
 *   ['mach-downtimes', resourceId]. If two panels for the same resource are open
 *   simultaneously, they share the same cache entry — fine for read, but mutations
 *   invalidate correctly via the same key.
 * - The delete confirmation is inline (Yes/No buttons appear in place of the trash icon)
 *   rather than a modal. This is intentional — avoids a z-index fight with the
 *   expanded row and keeps the interaction fast.
 * - accentColor drives the entire colour scheme via the accent object. To add a third
 *   colour, add it to the accent mapping and the Props type.
 * - Design Principle 2: resourceId in the URL is already tenant-scoped by the backend
 *   (it verifies the resource belongs to the current tenant). Never pass tenant_id here.
 * - If periods are not loading: check that the backend /api/unavailability/ router is
 *   registered in main.py and that the JWT is valid.
 * - If add mutation fails with 422: the most common cause is end_date < start_date.
 *   The client validates this but the backend also enforces it.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../../api/client'
import { Plus, Trash2, Loader2, CalendarOff, X, Check, AlertCircle } from 'lucide-react'

interface Period {
  id: number
  start_date: string
  end_date: string
  reason: string | null
}

interface Props {
  resourceType: 'employee' | 'machine'
  resourceId: number
  accentColor?: 'blue' | 'green'
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
    ? `/api/unavailability/employees/${resourceId}/leaves`
    : `/api/unavailability/machines/${resourceId}/downtimes`
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
    mutationFn: (id: number) => apiClient.delete(`${apiPath}/${id}`),
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
                    {formatDate(p.start_date)} — {formatDate(p.end_date)}
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
