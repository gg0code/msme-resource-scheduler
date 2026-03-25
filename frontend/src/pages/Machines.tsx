// src/pages/Machines.tsx — table layout (matching Employees page)
// Expandable rows show assigned jobs with Remove button.

import { useState, useMemo } from 'react'
import type { MouseEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import { useLabels } from '../context/IndustryContext'
import { CoachMark } from '../components/onboarding'
import CsvImport from '../components/common/CsvImport'
import { useFeatureFlags } from '../context/FeatureFlags'

import {
  Plus, Pencil, Trash2, Loader2, AlertCircle, Factory,
  Search, X, Check, ChevronRight, ChevronDown,
  CalendarDays, Briefcase, IndianRupee,
} from 'lucide-react'
import { usePlanLimits, LimitedButton, PlanLimitBanner } from '../components/PlanLimitGuard'
import UnavailabilityPanel from '../components/common/UnavailabilityPanel'

interface Skill { id: number; name: string }
interface MachineSkillReq { id: number; skill_id: number; min_skill_level: string; employees_required: number }
interface Machine {
  id: number; name: string; machine_type: string | null; base_availability_pct: number
  location_bay: string | null; status: string; hourly_rate: number | null
  skill_requirements: MachineSkillReq[]
}
interface Assignment {
  assignment_id: number; job_id: number; job_name: string; customer: string | null
  start_date: string; end_date: string; status: string; priority: string
}

const STATUSES = ['Operational', 'Under Maintenance', 'Decommissioned']
const LEVELS   = ['Generic', 'Intermediate', 'Premium']

const statusColour: Record<string, string> = {
  'Operational':        'bg-green-100 text-green-700',
  'Under Maintenance':  'bg-yellow-100 text-yellow-700',
  'Decommissioned':     'bg-red-100 text-red-600',
}
const jobStatusColour: Record<string, string> = {
  'Scheduled':           'bg-green-100 text-green-700',
  'Pending Assignment':  'bg-blue-100 text-blue-700',
  'In Progress':         'bg-purple-100 text-purple-700',
  'Draft':               'bg-gray-100 text-gray-600',
  'Completed':           'bg-teal-100 text-teal-700',
  'Cancelled':           'bg-red-100 text-red-600',
}
const priorityColour: Record<string, string> = {
  Critical: 'bg-red-100 text-red-700',
  High:     'bg-orange-100 text-orange-700',
  Medium:   'bg-yellow-100 text-yellow-700',
  Low:      'bg-gray-100 text-gray-600',
}
const availBar  = (p: number) => p >= 100 ? 'bg-green-400' : p >= 50 ? 'bg-yellow-400' : 'bg-red-400'
const availText = (p: number) => p >= 100 ? 'text-green-600' : p >= 50 ? 'text-yellow-600' : 'text-red-500'

// ── Assignment sub-rows ───────────────────────────────
function AssignmentRows({ machineId }: { machineId: number }) {
  const qc = useQueryClient()
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const { data: assignments = [], isLoading, isError } = useQuery<Assignment[]>({
    queryKey: ['machine-assignments', machineId],
    queryFn:  () => apiClient.get(`/api/assignments/machine/${machineId}`).then(r => r.data),
  })

  const removeAssignment = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/assignments/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['machine-assignments', machineId] })
      qc.invalidateQueries({ queryKey: ['jobs'] })
      setDeletingId(null)
    },
  })

  if (isLoading) return (
    <tr><td colSpan={8} className="bg-green-50 px-8 py-4">
      <div className="flex items-center gap-2 text-gray-400 text-xs">
        <Loader2 size={13} className="animate-spin"/>Loading assignments...
      </div>
    </td></tr>
  )
  if (isError) return (
    <tr><td colSpan={8} className="bg-green-50 px-8 py-3 text-xs text-red-400">
      Failed to load assignments.
    </td></tr>
  )

  return (
    <tr>
      <td colSpan={8} className="bg-green-50 border-b border-green-100 px-6 py-3">
        <div className="flex items-center gap-2 mb-2">
          <Briefcase size={13} className="text-green-600"/>
          <span className="text-xs font-semibold text-green-700">
            {assignments.length === 0
              ? 'No jobs assigned'
              : `${assignments.length} job assignment${assignments.length !== 1 ? 's' : ''}`}
          </span>
        </div>

        {assignments.length === 0
          ? <p className="text-xs text-gray-400 italic pl-5">This machine has no job assignments yet.</p>
          : <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-400 font-semibold uppercase tracking-wide text-left border-b border-green-100">
                  <th className="pb-1.5 pr-4">Job Name</th>
                  <th className="pb-1.5 pr-4">Customer</th>
                  <th className="pb-1.5 pr-4">Start Date</th>
                  <th className="pb-1.5 pr-4">End Date</th>
                  <th className="pb-1.5 pr-4">Status</th>
                  <th className="pb-1.5 pr-4">Priority</th>
                  <th className="pb-1.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-green-100">
                {assignments.map(a => (
                  <tr key={a.assignment_id} className="hover:bg-green-100/40 transition-colors">
                    <td className="py-2 pr-4 font-medium text-gray-800">{a.job_name}</td>
                    <td className="py-2 pr-4 text-gray-500">{a.customer ?? '—'}</td>
                    <td className="py-2 pr-4 text-gray-600">
                      <span className="flex items-center gap-1">
                        <CalendarDays size={11} className="text-gray-400"/>{a.start_date}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-gray-600">{a.end_date}</td>
                    <td className="py-2 pr-4">
                      <span className={`px-2 py-0.5 rounded-full font-medium ${jobStatusColour[a.status] ?? 'bg-gray-100 text-gray-600'}`}>
                        {a.status}
                      </span>
                    </td>
                    <td className="py-2 pr-4">
                      <span className={`px-2 py-0.5 rounded-full font-medium ${priorityColour[a.priority] ?? ''}`}>
                        {a.priority}
                      </span>
                    </td>
                    <td className="py-2 text-right">
                      {deletingId === a.assignment_id ? (
                        <span className="inline-flex items-center gap-2 text-xs">
                          <span className="text-red-600">Remove?</span>
                          <button onClick={() => removeAssignment.mutate(a.assignment_id)}
                            className="px-2 py-0.5 bg-red-600 text-white rounded hover:bg-red-700 font-medium">
                            {removeAssignment.isPending ? '...' : 'Yes'}
                          </button>
                          <button onClick={() => setDeletingId(null)}
                            className="px-2 py-0.5 bg-gray-200 text-gray-600 rounded hover:bg-gray-300">
                            No
                          </button>
                        </span>
                      ) : (
                        <button onClick={() => setDeletingId(a.assignment_id)}
                          className="flex items-center gap-1 text-xs text-red-400 hover:text-red-600 border border-red-200 rounded px-2 py-0.5 ml-auto">
                          <X size={10}/> Remove
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
        }
      </td>
    </tr>
  )
}

const emptyForm = () => ({
  name: '', machine_type: '', location_bay: '', base_availability_pct: 100,
  status: 'Operational', hourly_rate: '',
  skill_requirements: [] as { skill_id: number; min_skill_level: string; employees_required: number }[],
})

// ══════════════════════════════════════════════════════
export default function Machines() {
  const qc = useQueryClient()
   const flags = useFeatureFlags()
  const [search, setSearch]             = useState('')
  const [filterType, setFilterType]     = useState('All')
  const [filterBay, setFilterBay]       = useState('All')
  const [filterStatus, setFilterStatus] = useState('All')
  const [filterSkill, setFilterSkill]   = useState('All')
  const [expandedId, setExpandedId]     = useState<number | null>(null)
  const [showForm, setShowForm]         = useState(false)
  const [editingMachine, setEditingMachine] = useState<Machine | null>(null)
  const [form, setForm]                 = useState(emptyForm())
  const [deleteId, setDeleteId]         = useState<number | null>(null)
  const [toast, setToast]               = useState('')

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(''), 3000) }

  const { data: machines = [], isLoading, isError } = useQuery<Machine[]>({
    queryKey: ['machines'],
    queryFn:  () => apiClient.get('/api/machines/').then(r => r.data),
  })
  const { data: skills = [] } = useQuery<Skill[]>({
    queryKey: ['skills'],
    queryFn:  () => apiClient.get('/api/skills/').then(r => r.data),
  })
  const { planLimits } = usePlanLimits()
  const labels = useLabels()

  const types = useMemo(() => ['All', ...Array.from(new Set(machines.map(m => m.machine_type).filter(Boolean) as string[])).sort()], [machines])
  const bays  = useMemo(() => ['All', ...Array.from(new Set(machines.map(m => m.location_bay).filter(Boolean) as string[])).sort()], [machines])

  const filtered = useMemo(() => machines.filter(m => {
    if (search && !m.name.toLowerCase().includes(search.toLowerCase()) &&
        !(m.machine_type ?? '').toLowerCase().includes(search.toLowerCase())) return false
    if (filterType   !== 'All' && m.machine_type !== filterType)   return false
    if (filterBay    !== 'All' && m.location_bay !== filterBay)    return false
    if (filterStatus !== 'All' && m.status       !== filterStatus) return false
    if (filterSkill  !== 'All' && !m.skill_requirements.some(r => String(r.skill_id) === filterSkill)) return false
    return true
  }), [machines, search, filterType, filterBay, filterStatus, filterSkill])

  const createMachine = useMutation({
    mutationFn: (p: object) => apiClient.post('/api/machines/', p),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['machines'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }); qc.invalidateQueries({ queryKey: ['plan-limits'] }); closeForm(); showToast('Machine added!') },
  })
  const updateMachine = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: object }) => apiClient.patch(`/api/machines/${id}`, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['machines'] }); closeForm(); showToast('Machine updated!') },
  })
  const deleteMachine = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/machines/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['machines'] }); qc.invalidateQueries({ queryKey: ['dashboard'] }); qc.invalidateQueries({ queryKey: ['plan-limits'] }); setDeleteId(null); showToast('Machine deleted!') },
  })

  function openCreate() { setEditingMachine(null); setForm(emptyForm()); setShowForm(true) }
  function openEdit(m: Machine, e: MouseEvent) {
    e.stopPropagation()
    setEditingMachine(m)
    setForm({
      name: m.name, machine_type: m.machine_type ?? '', location_bay: m.location_bay ?? '',
      base_availability_pct: m.base_availability_pct, status: m.status,
      hourly_rate: m.hourly_rate != null ? String(m.hourly_rate) : '',
      skill_requirements: m.skill_requirements.map(r => ({
        skill_id: r.skill_id, min_skill_level: r.min_skill_level, employees_required: r.employees_required,
      })),
    })
    setShowForm(true)
  }
  function closeForm() { setShowForm(false); setEditingMachine(null); setForm(emptyForm()) }

  function addSkillReq() {
    setForm(f => ({ ...f, skill_requirements: [...f.skill_requirements, { skill_id: skills[0]?.id ?? 0, min_skill_level: 'Generic', employees_required: 1 }] }))
  }
  function removeSkillReq(i: number) { setForm(f => ({ ...f, skill_requirements: f.skill_requirements.filter((_, idx) => idx !== i) })) }
  function updateSkillReq(i: number, field: string, value: string | number) {
    setForm(f => ({ ...f, skill_requirements: f.skill_requirements.map((r, idx) => idx === i ? { ...r, [field]: value } : r) }))
  }

  function submitForm() {
    const payload = {
      ...form,
      base_availability_pct: Number(form.base_availability_pct),
      hourly_rate: (form as { hourly_rate: string }).hourly_rate !== '' ? Number((form as { hourly_rate: string }).hourly_rate) : null,
    }
    if (editingMachine) updateMachine.mutate({ id: editingMachine.id, payload })
    else createMachine.mutate(payload)
  }

  const isSaving = createMachine.isPending || updateMachine.isPending
  const getSkillName = (id: number) => skills.find(s => s.id === id)?.name ?? `Skill#${id}`
  const hasFilters = search || filterType !== 'All' || filterBay !== 'All' || filterStatus !== 'All' || filterSkill !== 'All'

  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-800">{labels.machinesPageTitle}</h2>
          <p className="text-sm text-gray-500 mt-0.5">{filtered.length} of {machines.length} machines · click a row to see assigned jobs</p>
        </div>
        <div className="flex items-center gap-2">
          {flags.csv_import && <CsvImport resource="machines" onSuccess={() => qc.invalidateQueries({ queryKey: ['machines'] })}/>}
          <CoachMark id="machines-add" title="Register your machines" description="Add equipment with hourly cost and bay location. The scheduler assigns them to jobs automatically." position="bottom" step={1} totalSteps={2}>
            <LimitedButton resource="machines" planLimits={planLimits} onClick={openCreate}>
              <Plus size={16}/> Add {labels.machine}
            </LimitedButton>
          </CoachMark>
        </div>
      </div>

      <PlanLimitBanner resource="machines" planLimits={planLimits} label="machines" />

      {toast && <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-sm"><Check size={15}/>{toast}</div>}

      {/* Filters */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
          <input className="w-full pl-8 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Search by name or type..." value={search} onChange={e => setSearch(e.target.value)}/>
        </div>
        <select className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={filterType} onChange={e => setFilterType(e.target.value)}>
          <option value="All">All Types</option>
          {types.filter(t => t !== 'All').map(t => <option key={t}>{t}</option>)}
        </select>
        <select className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={filterBay} onChange={e => setFilterBay(e.target.value)}>
          <option value="All">All Bays</option>
          {bays.filter(b => b !== 'All').map(b => <option key={b}>{b}</option>)}
        </select>
        <select className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
          <option value="All">All Statuses</option>
          {STATUSES.map(s => <option key={s}>{s}</option>)}
        </select>
        <select className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={filterSkill} onChange={e => setFilterSkill(e.target.value)}>
          <option value="All">All Skills Required</option>
          {skills.map(s => <option key={s.id} value={String(s.id)}>{s.name}</option>)}
        </select>
        {hasFilters && (
          <button onClick={() => { setSearch(''); setFilterType('All'); setFilterBay('All'); setFilterStatus('All'); setFilterSkill('All') }}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-2">
            <X size={12}/> Clear
          </button>
        )}
      </div>

      {isLoading && <div className="flex items-center gap-2 text-gray-500 justify-center py-10"><Loader2 className="animate-spin" size={18}/>Loading machines...</div>}
      {isError   && <div className="flex items-center gap-2 text-red-500 justify-center py-10"><AlertCircle size={18}/>Failed to load machines.</div>}

      {/* Table */}
      {!isLoading && !isError && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500 font-semibold uppercase tracking-wide">
                  <th className="w-8 px-3 py-3"/>
                  <th className="px-4 py-3 text-left">Machine</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Availability</th>
                  <th className="px-4 py-3 text-left">Bay</th>
                  <th className="px-4 py-3 text-left">Skills Required</th>
                  <th className="px-4 py-3 text-right">Cost / hr</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map(machine => {
                  const isExpanded = expandedId === machine.id
                  return (
                    <>
                      <tr key={machine.id}
                        onClick={() => setExpandedId(isExpanded ? null : machine.id)}
                        className={`cursor-pointer transition-colors ${isExpanded ? 'bg-green-50' : 'hover:bg-gray-50'}`}>

                        {/* Expand chevron */}
                        <td className="px-3 py-3 text-gray-400">
                          {isExpanded
                            ? <ChevronDown size={15} className="text-green-600"/>
                            : <ChevronRight size={15}/>}
                        </td>

                        {/* Name */}
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="bg-green-100 p-1.5 rounded-full shrink-0">
                              <Factory size={13} className="text-green-600"/>
                            </div>
                            <div>
                              <p className="font-semibold text-gray-800">{machine.name}</p>
                              <p className="text-xs text-gray-400 mt-0.5">{machine.machine_type ?? 'Unknown type'}</p>
                            </div>
                          </div>
                        </td>

                        {/* Status */}
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColour[machine.status] ?? ''}`}>
                            {machine.status}
                          </span>
                        </td>

                        {/* Availability */}
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-16 bg-gray-100 rounded-full h-1.5 shrink-0">
                              <div className={`h-1.5 rounded-full ${availBar(machine.base_availability_pct)}`}
                                style={{ width: `${machine.base_availability_pct}%` }}/>
                            </div>
                            <span className={`text-xs font-semibold whitespace-nowrap ${availText(machine.base_availability_pct)}`}>
                              {machine.base_availability_pct}%
                            </span>
                          </div>
                        </td>

                        {/* Bay */}
                        <td className="px-4 py-3 text-gray-700">
                          {machine.location_bay ?? <span className="text-gray-300 italic text-xs">—</span>}
                        </td>

                        {/* Skills */}
                        <td className="px-4 py-3 max-w-xs">
                          {machine.skill_requirements.length === 0
                            ? <span className="text-gray-300 text-xs italic">None</span>
                            : <div className="flex flex-wrap gap-1">
                                {machine.skill_requirements.map(req => (
                                  <span key={req.id} className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full text-xs font-medium">
                                    {getSkillName(req.skill_id)}
                                    <span className="opacity-60 ml-1">· {req.min_skill_level.slice(0,3)} · {req.employees_required}op</span>
                                  </span>
                                ))}
                              </div>
                          }
                        </td>

                        {/* Cost */}
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          {machine.hourly_rate != null
                            ? <div className="flex items-center gap-0.5 justify-end text-sm font-semibold text-gray-800">
                                <IndianRupee size={12}/>{machine.hourly_rate}/hr
                              </div>
                            : <span className="text-gray-300 text-xs italic">—</span>
                          }
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2 justify-end">
                            <button onClick={e => openEdit(machine, e)}
                              className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 border border-blue-200 rounded-md px-2 py-1">
                              <Pencil size={11}/> Edit
                            </button>
                            <button onClick={e => { e.stopPropagation(); setDeleteId(machine.id) }}
                              className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700 border border-red-200 rounded-md px-2 py-1">
                              <Trash2 size={11}/> Delete
                            </button>
                          </div>
                        </td>
                      </tr>

                      {/* Expanded assignment rows */}
                      {isExpanded && <AssignmentRows machineId={machine.id}/>}
                      {isExpanded && (
                        <tr>
                          <td colSpan={8} className="p-0">
                            <UnavailabilityPanel resourceType="machine" resourceId={machine.id} accentColor="green"/>
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
                {filtered.length === 0 && (
                  <tr><td colSpan={8} className="text-center text-gray-400 py-10 text-sm">No machines match your filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Footer */}
          {filtered.length > 0 && (
            <div className="border-t border-gray-100 bg-gray-50 px-4 py-2.5 flex flex-wrap items-center gap-5 text-xs text-gray-500">
              <span><span className="font-semibold text-gray-700">{filtered.filter(m => m.status === 'Operational').length}</span> Operational</span>
              <span><span className="font-semibold text-gray-700">{filtered.filter(m => m.status === 'Under Maintenance').length}</span> Under Maintenance</span>
              <span><span className="font-semibold text-gray-700">{filtered.filter(m => m.base_availability_pct === 100).length}</span> Fully Available</span>
              <span><span className="font-semibold text-gray-700">{filtered.filter(m => m.base_availability_pct < 100).length}</span> Partial / Unavailable</span>
            </div>
          )}
        </div>
      )}

      {/* Delete confirm */}
      {deleteId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 shadow-xl w-80 space-y-4">
            <h3 className="font-bold text-gray-800">Delete Machine?</h3>
            <p className="text-sm text-gray-600">This will permanently remove the machine and all its skill requirements.</p>
            <div className="flex gap-2">
              <button onClick={() => deleteMachine.mutate(deleteId)} className="flex-1 bg-red-600 hover:bg-red-700 text-white text-sm py-2 rounded-lg">
                {deleteMachine.isPending ? 'Deleting...' : 'Yes, Delete'}
              </button>
              <button onClick={() => setDeleteId(null)} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2 rounded-lg">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Add / Edit modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h3 className="font-bold text-gray-800">{editingMachine ? `Edit ${labels.machine}` : `New ${labels.machine}`}</h3>
              <button onClick={closeForm}><X size={18} className="text-gray-400 hover:text-gray-600"/></button>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Machine Name *</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. CNC Lathe #2"/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Machine Type</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.machine_type} onChange={e => setForm({ ...form, machine_type: e.target.value })} placeholder="e.g. CNC Lathe"/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Location Bay</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.location_bay} onChange={e => setForm({ ...form, location_bay: e.target.value })} placeholder="e.g. Bay A"/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Running Cost (₹/hr)</label>
                  <input type="number" min="0" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={(form as { hourly_rate: string }).hourly_rate}
                    onChange={e => setForm({ ...form, hourly_rate: e.target.value } as typeof form)}
                    placeholder="Electricity + consumables"/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Base Availability %</label>
                  <input type="number" min="0" max="100" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.base_availability_pct} onChange={e => setForm({ ...form, base_availability_pct: Number(e.target.value) })}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}>
                    {STATUSES.map(s => <option key={s}>{s}</option>)}
                  </select>
                </div>
              </div>

              {/* Skill requirements */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-gray-600">Skill Requirements</label>
                  <button onClick={addSkillReq} className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"><Plus size={12}/>Add Skill</button>
                </div>
                {form.skill_requirements.length === 0 && (
                  <p className="text-xs text-gray-400 italic">No skill requirements — machine can be operated by anyone.</p>
                )}
                {form.skill_requirements.map((req, i) => (
                  <div key={i} className="flex gap-2 mb-2 items-center">
                    <select className="flex-1 border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={req.skill_id} onChange={e => updateSkillReq(i, 'skill_id', Number(e.target.value))}>
                      {skills.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                    <select className="border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={req.min_skill_level} onChange={e => updateSkillReq(i, 'min_skill_level', e.target.value)}>
                      {LEVELS.map(l => <option key={l}>{l}</option>)}
                    </select>
                    <input type="number" min="1" className="w-16 border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={req.employees_required} onChange={e => updateSkillReq(i, 'employees_required', Number(e.target.value))}/>
                    <button onClick={() => removeSkillReq(i)} className="text-red-400 hover:text-red-600"><X size={14}/></button>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-2 px-6 pb-6">
              <button onClick={submitForm} disabled={!form.name || isSaving}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm py-2.5 rounded-lg font-medium transition-colors">
                {isSaving ? 'Saving...' : editingMachine ? `Update ${labels.machine}` : `Add ${labels.machine}`}
              </button>
              <button onClick={closeForm} className="px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-lg transition-colors">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
