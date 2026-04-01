// src/pages/Employees.tsx — table with expandable assignment rows

import { useState, useMemo } from 'react'
import type { MouseEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import { useLabels } from '../context/IndustryContext'
import { CoachMark } from '../components/onboarding'
import CsvImport from '../components/common/CsvImport'
import { useFeatureFlags } from '../context/FeatureFlags'

import {
  Plus,
  Pencil,
  Trash2,
  Loader2,
  AlertCircle,
  Search,
  X,
  Check,
  ChevronUp,
  ChevronDown,
  IndianRupee,
  ChevronRight,
} from 'lucide-react'
import { usePlanLimits, LimitedButton, PlanLimitBanner } from '../components/PlanLimitGuard'
import UnavailabilityPanel from '../components/common/UnavailabilityPanel'

interface Skill         { id: number; name: string }
interface EmployeeSkill { id: number; skill_id: number; skill_level: string }
interface Employee {
  id: number; full_name: string; department: string | null; employment_type: string
  base_availability_pct: number; status: string; contact_number: string | null
  join_date: string | null; hourly_rate: number | null; overtime_rate: number | null
  skills: EmployeeSkill[]
}
interface Assignment {
  assignment_id: number; job_id: number; job_name: string; customer: string | null
  start_date: string; end_date: string; status: string; priority: string
}

const STATUSES  = ['Active','Inactive','On Leave']
const EMP_TYPES = ['Full-time','Part-time','Contract']
const LEVELS    = ['Generic','Intermediate','Premium']
const DEPTS     = ['Production','Quality','Maintenance','Stores','Admin']

const statusColour: Record<string,string> = {
  'Active':'bg-green-100 text-green-700',
  'Inactive':'bg-gray-100 text-gray-500',
  'On Leave':'bg-yellow-100 text-yellow-700',
}
const jobStatusColour: Record<string,string> = {
  'Scheduled':'bg-green-100 text-green-700','Pending Assignment':'bg-blue-100 text-blue-700',
  'In Progress':'bg-purple-100 text-purple-700','Draft':'bg-gray-100 text-gray-600',
  'Completed':'bg-teal-100 text-teal-700','Cancelled':'bg-red-100 text-red-600',
}
const priorityColour: Record<string,string> = {
  Critical:'bg-red-100 text-red-700', High:'bg-orange-100 text-orange-700',
  Medium:'bg-yellow-100 text-yellow-700', Low:'bg-gray-100 text-gray-600',
}
const levelColour: Record<string,string> = {
  'Premium':'bg-purple-100 text-purple-700',
  'Intermediate':'bg-blue-100 text-blue-700',
  'Generic':'bg-gray-100 text-gray-600',
}
const availBar  = (p: number) => p >= 100 ? 'bg-green-400' : p >= 50 ? 'bg-yellow-400' : 'bg-red-400'
const availText = (p: number) => p >= 100 ? 'text-green-600' : p >= 50 ? 'text-yellow-600' : 'text-red-500'

const emptyForm = () => ({
  full_name:'', department:'Production', employment_type:'Full-time',
  base_availability_pct: 100, status:'Active', contact_number:'', join_date:'',
  hourly_rate:'', overtime_rate:'',
  skills: [] as { skill_id:number; skill_level:string }[],
})

type SortKey = 'full_name' | 'base_availability_pct' | 'department' | 'hourly_rate' | 'status'

// ── Expandable assignment sub-row ──────────────────────
function AssignmentRows({ employeeId }: { employeeId: number }) {
  const labels = useLabels()
  const qc = useQueryClient()
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const { data: assignments = [], isLoading, isError } = useQuery<Assignment[]>({
    queryKey: ['emp-assignments', employeeId],
    queryFn: () => apiClient.get(`/api/assignments/employee/${employeeId}`).then(r => r.data),
  })

  const removeAssignment = useMutation({
    mutationFn: (assignmentId: number) => apiClient.delete(`/api/assignments/${assignmentId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['emp-assignments', employeeId] })
      qc.invalidateQueries({ queryKey: ['jobs'] })
      setDeletingId(null)
    },
  })

  if (isLoading) return (
    <tr><td colSpan={7} className="bg-blue-50 px-8 py-4">
      <div className="flex items-center gap-2 text-gray-400 text-xs"><Loader2 size={13} className="animate-spin"/>Loading assignments...</div>
    </td></tr>
  )
  if (isError) return (
    <tr><td colSpan={7} className="bg-blue-50 px-8 py-3 text-xs text-red-400">Failed to load assignments.</td></tr>
  )

  return (
    <tr>
      <td colSpan={7} className="bg-blue-50 border-b border-blue-100 px-6 py-3">
        <div className="flex items-center gap-2 mb-2">
          <Briefcase size={13} className="text-blue-500"/>
          <span className="text-xs font-semibold text-blue-700">
            {assignments.length === 0 ? 'No jobs assigned' : `${assignments.length} job assignment${assignments.length !== 1 ? 's' : ''}`}
          </span>
        </div>

        {assignments.length === 0
          ? <p className="text-xs text-gray-400 italic pl-5">{`This ${labels.employee.toLowerCase()} has no ${labels.jobs.toLowerCase()} assignments yet.`}</p>
          : <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-400 font-semibold uppercase tracking-wide text-left border-b border-blue-100">
                  <th className="pb-1.5 pl-1 pr-4">Job Name</th>
                  <th className="pb-1.5 pr-4">Customer</th>
                  <th className="pb-1.5 pr-4">Start Date</th>
                  <th className="pb-1.5 pr-4">End Date</th>
                  <th className="pb-1.5 pr-4">Status</th>
                  <th className="pb-1.5 pr-4">Priority</th>
                  <th className="pb-1.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-blue-100">
                {assignments.map(a => (
                  <tr key={a.assignment_id} className="hover:bg-blue-100/40 transition-colors">
                    <td className="py-2 pl-1 pr-4 font-medium text-gray-800">{a.job_name}</td>
                    <td className="py-2 pr-4 text-gray-500">{a.customer ?? '—'}</td>
                    <td className="py-2 pr-4 text-gray-600">
                      <span className="flex items-center gap-1"><CalendarDays size={11} className="text-gray-400"/>{a.start_date}</span>
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

// ══════════════════════════════════════════════════════
export default function Employees() {
  const qc = useQueryClient()
  const flags = useFeatureFlags() 
  const [search, setSearch]             = useState('')
  const [filterDept, setFilterDept]     = useState('All')
  const [filterStatus, setFilterStatus] = useState('All')
  const [filterAvail, setFilterAvail]   = useState('All')
  const [sortKey, setSortKey]           = useState<SortKey>('full_name')
  const [sortAsc, setSortAsc]           = useState(true)
  const [expandedId, setExpandedId]     = useState<number | null>(null)
  const [showForm, setShowForm]         = useState(false)
  const [editingEmp, setEditingEmp]     = useState<Employee | null>(null)
  const [form, setForm]                 = useState(emptyForm())
  const [deleteId, setDeleteId]         = useState<number | null>(null)
  const [toast, setToast]               = useState('')

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(''), 3000) }

  const { data: employees = [], isLoading, isError } = useQuery<Employee[]>({
    queryKey:['employees'], queryFn:() => apiClient.get('/api/employees/').then(r => r.data),
  })
  const { data: skills = [] } = useQuery<Skill[]>({
    queryKey:['skills'], queryFn:() => apiClient.get('/api/skills/').then(r => r.data),
  })
  const { planLimits } = usePlanLimits()
  const labels = useLabels()

  const departments = useMemo(() => {
    const d = new Set(employees.map(e => e.department).filter(Boolean) as string[])
    return ['All', ...Array.from(d).sort()]
  }, [employees])

  const filtered = useMemo(() => {
    const list = employees.filter(e => {
      if (search) {
        const q = search.toLowerCase()
        const skillNames = e.skills.map(s => (skills.find(sk => sk.id === s.skill_id)?.name ?? '') + ' ' + s.skill_level).join(' ').toLowerCase()
        const searchable = [
          e.full_name, e.department ?? '', e.status, e.employment_type,
          String(e.base_availability_pct) + '%', skillNames,
          e.hourly_rate != null ? String(e.hourly_rate) : '',
        ].join(' ').toLowerCase()
        if (!searchable.includes(q)) return false
      }
      if (filterDept   !== 'All' && e.department !== filterDept)   return false
      if (filterStatus !== 'All' && e.status     !== filterStatus) return false
      if (filterAvail === '100%'  && e.base_availability_pct < 100)  return false
      if (filterAvail === '<100%' && e.base_availability_pct >= 100) return false
      if (filterAvail === '≤50%'  && e.base_availability_pct > 50)   return false
      return true
    })
    return [...list].sort((a, b) => {
      const av = a[sortKey] ?? '', bv = b[sortKey] ?? ''
      return sortAsc ? (av < bv ? -1 : av > bv ? 1 : 0) : (av > bv ? -1 : av < bv ? 1 : 0)
    })
  }, [employees, skills, search, filterDept, filterStatus, filterAvail, sortKey, sortAsc])

  const createEmp = useMutation({
    mutationFn: (p: object) => apiClient.post('/api/employees/', p),
    onSuccess: () => { qc.invalidateQueries({queryKey:['employees']}); qc.invalidateQueries({queryKey:['dashboard']}); qc.invalidateQueries({queryKey:['plan-limits']}); closeForm(); showToast(`${labels.employee} added!`) },
  })
  const updateEmp = useMutation({
    mutationFn: ({id,payload}:{id:number;payload:object}) => apiClient.patch(`/api/employees/${id}`, payload),
    onSuccess: () => { qc.invalidateQueries({queryKey:['employees']}); closeForm(); showToast(`${labels.employee} updated!`) },
  })
  const deleteEmp = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/api/employees/${id}`),
    onSuccess: () => { qc.invalidateQueries({queryKey:['employees']}); qc.invalidateQueries({queryKey:['dashboard']}); qc.invalidateQueries({queryKey:['plan-limits']}); setDeleteId(null); showToast(`${labels.employee} deleted!`) },
  })

  function openCreate() { setEditingEmp(null); setForm(emptyForm()); setShowForm(true) }
  function openEdit(emp: Employee, e: MouseEvent) {
    e.stopPropagation()
    setEditingEmp(emp)
    setForm({
      full_name: emp.full_name, department: emp.department ?? 'Production',
      employment_type: emp.employment_type, base_availability_pct: emp.base_availability_pct,
      status: emp.status, contact_number: emp.contact_number ?? '', join_date: emp.join_date ?? '',
      hourly_rate:   emp.hourly_rate   != null ? String(emp.hourly_rate)   : '',
      overtime_rate: emp.overtime_rate != null ? String(emp.overtime_rate) : '',
      skills: emp.skills.map(s => ({ skill_id: s.skill_id, skill_level: s.skill_level })),
    })
    setShowForm(true)
  }
  function closeForm() { setShowForm(false); setEditingEmp(null); setForm(emptyForm()) }

  function submitForm() {
    const payload = {
      ...form,
      base_availability_pct: Number(form.base_availability_pct),
      hourly_rate:   form.hourly_rate   !== '' ? Number(form.hourly_rate)   : null,
      overtime_rate: form.overtime_rate !== '' ? Number(form.overtime_rate) : null,
    }
    if (editingEmp) updateEmp.mutate({ id: editingEmp.id, payload })
    else createEmp.mutate(payload)
  }

  const isSaving = createEmp.isPending || updateEmp.isPending
  const getSkillName = (id: number) => skills.find(s => s.id === id)?.name ?? `#${id}`

  function toggleSort(col: SortKey) {
    if (sortKey === col) setSortAsc(a => !a)
    else { setSortKey(col); setSortAsc(true) }
  }
  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ChevronUp size={11} className="text-gray-300"/>
    return sortAsc ? <ChevronUp size={11} className="text-blue-500"/> : <ChevronDown size={11} className="text-blue-500"/>
  }

  const hasFilters = search || filterDept !== 'All' || filterStatus !== 'All' || filterAvail !== 'All'
  const withRate   = filtered.filter(e => e.hourly_rate != null)
  const avgRate    = withRate.length > 0 ? Math.round(withRate.reduce((s,e) => s+(e.hourly_rate??0),0) / withRate.length) : null

  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-800">{labels.employeesPageTitle}</h2>
          <p className="text-sm text-gray-500 mt-0.5">{filtered.length} of {employees.length} {labels.employees.toLowerCase()} · click a row to see assigned jobs</p>
        </div>
        <div className="flex items-center gap-2">
          {flags.csv_import && <CsvImport resource="employees" onSuccess={() => qc.invalidateQueries({queryKey:['employees']})}/>}
          <CoachMark id="employees-add" title="Add your team" description="Add each worker with their role, hourly rate, and skills. Skills are matched to job requirements." position="bottom" step={1} totalSteps={3}>
            <LimitedButton resource="employees" planLimits={planLimits} onClick={openCreate}>
              <Plus size={16}/> Add {labels.employee}
            </LimitedButton>
          </CoachMark>
        </div>
      </div>

      <PlanLimitBanner resource="employees" planLimits={planLimits} label="employees" />

      {toast && <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-sm"><Check size={15}/>{toast}</div>}

      {/* Filters */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
          <input className="w-full pl-8 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Search name, dept, skill, status..." value={search} onChange={e => setSearch(e.target.value)}/>
        </div>
        <select className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={filterDept} onChange={e => setFilterDept(e.target.value)}>
          {departments.map(d => <option key={d}>{d}</option>)}
        </select>
        <select className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
          <option value="All">All Statuses</option>
          {STATUSES.map(s => <option key={s}>{s}</option>)}
        </select>
        <select className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={filterAvail} onChange={e => setFilterAvail(e.target.value)}>
          <option value="All">All Availability</option>
          <option value="100%">100% Available</option>
          <option value="<100%">Partial (&lt;100%)</option>
          <option value="≤50%">Low (≤50%)</option>
        </select>
        {hasFilters && (
          <button onClick={() => { setSearch(''); setFilterDept('All'); setFilterStatus('All'); setFilterAvail('All') }}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-2">
            <X size={12}/> Clear
          </button>
        )}
      </div>

      {isLoading && <div className="flex items-center gap-2 text-gray-500 justify-center py-10"><Loader2 className="animate-spin" size={18}/>Loading...</div>}
      {isError   && <div className="flex items-center gap-2 text-red-500 justify-center py-10"><AlertCircle size={18}/>Failed to load {labels.employees.toLowerCase()}.</div>}

      {/* Table */}
      {!isLoading && !isError && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500 font-semibold uppercase tracking-wide">
                  <th className="w-8 px-3 py-3"/>
                  {([
                    ['full_name', labels.employee],
                    ['status',                'Status'      ],
                    ['base_availability_pct', 'Availability'],
                    ['department',            'Department'  ],
                    [null,                    'Skills'      ],
                    ['hourly_rate',           'Cost / hr'   ],
                    [null,                    'Actions'     ],
                  ] as [SortKey|null, string][]).map(([col, label], i) => (
                    <th key={i} className={`px-4 py-3 ${i === 6 ? 'text-right' : 'text-left'}`}>
                      {col
                        ? <button onClick={() => toggleSort(col)} className="flex items-center gap-1 hover:text-gray-800">
                            {label} <SortIcon col={col}/>
                          </button>
                        : label
                      }
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map(emp => {
                  const isExpanded = expandedId === emp.id
                  return (
                    <>
                      <tr
                        key={emp.id}
                        onClick={() => setExpandedId(isExpanded ? null : emp.id)}
                        className={`cursor-pointer transition-colors ${isExpanded ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                      >
                        {/* Expand chevron */}
                        <td className="px-3 py-3 text-gray-400">
                          {isExpanded
                            ? <ChevronDown size={15} className="text-blue-500"/>
                            : <ChevronRight size={15}/>
                          }
                        </td>

                        {/* Name */}
                        <td className="px-4 py-3">
                          <p className="font-semibold text-gray-800">{emp.full_name}</p>
                          <p className="text-xs text-gray-400 mt-0.5">{emp.employment_type}</p>
                        </td>

                        {/* Status */}
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColour[emp.status] ?? ''}`}>
                            {emp.status}
                          </span>
                        </td>

                        {/* Availability */}
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-16 bg-gray-100 rounded-full h-1.5 shrink-0">
                              <div className={`h-1.5 rounded-full ${availBar(emp.base_availability_pct)}`}
                                style={{ width:`${emp.base_availability_pct}%` }}/>
                            </div>
                            <span className={`text-xs font-semibold whitespace-nowrap ${availText(emp.base_availability_pct)}`}>
                              {emp.base_availability_pct}%
                            </span>
                          </div>
                        </td>

                        {/* Department */}
                        <td className="px-4 py-3 text-gray-700">
                          {emp.department ?? <span className="text-gray-300 italic text-xs">—</span>}
                        </td>

                        {/* Skills */}
                        <td className="px-4 py-3 max-w-xs">
                          {emp.skills.length === 0
                            ? <span className="text-gray-300 text-xs italic">No skills</span>
                            : <div className="flex flex-wrap gap-1">
                                {emp.skills.map(s => (
                                  <span key={s.id} className={`px-2 py-0.5 rounded-full text-xs font-medium ${levelColour[s.skill_level] ?? ''}`}>
                                    {getSkillName(s.skill_id)}
                                    <span className="opacity-60 ml-1">· {s.skill_level.slice(0,3)}</span>
                                  </span>
                                ))}
                              </div>
                          }
                        </td>

                        {/* Cost */}
                        <td className="px-4 py-3 whitespace-nowrap">
                          {emp.hourly_rate != null
                            ? <div>
                                <div className="flex items-center gap-0.5 text-sm font-semibold text-gray-800">
                                  <IndianRupee size={12}/>{emp.hourly_rate}/hr
                                </div>
                                {emp.overtime_rate != null && (
                                  <div className="flex items-center gap-0.5 text-xs text-orange-500 mt-0.5">
                                    <IndianRupee size={10}/>{emp.overtime_rate} OT
                                  </div>
                                )}
                              </div>
                            : <span className="text-gray-300 text-xs italic">—</span>
                          }
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2 justify-end">
                            <button onClick={e => openEdit(emp, e)}
                              className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 border border-blue-200 rounded-md px-2 py-1">
                              <Pencil size={11}/> Edit
                            </button>
                            <button onClick={e => { e.stopPropagation(); setDeleteId(emp.id) }}
                              className="flex items-center gap-1 text-xs text-red-500 hover:text-red-700 border border-red-200 rounded-md px-2 py-1">
                              <Trash2 size={11}/> Delete
                            </button>
                          </div>
                        </td>
                      </tr>

                      {/* Expanded assignment sub-rows */}
                      {isExpanded && <AssignmentRows employeeId={emp.id}/>}
                      {isExpanded && (
                        <tr>
                          <td colSpan={7} className="p-0">
                            <UnavailabilityPanel resourceType="employee" resourceId={emp.id} accentColor="blue"/>
                          </td>
                        </tr>
                      )}
                    </>
                  )
                })}
                {filtered.length === 0 && (
                  <tr><td colSpan={8} className="text-center text-gray-400 py-10 text-sm">No {labels.employees.toLowerCase()} match your filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Footer */}
          {filtered.length > 0 && (
            <div className="border-t border-gray-100 bg-gray-50 px-4 py-2.5 flex flex-wrap items-center gap-5 text-xs text-gray-500">
              <span><span className="font-semibold text-gray-700">{filtered.filter(e=>e.status==='Active').length}</span> Active</span>
              <span><span className="font-semibold text-gray-700">{filtered.filter(e=>e.status==='On Leave').length}</span> On Leave</span>
              <span><span className="font-semibold text-gray-700">{filtered.filter(e=>e.base_availability_pct===100).length}</span> Fully Available</span>
              <span><span className="font-semibold text-gray-700">{filtered.filter(e=>e.base_availability_pct<100).length}</span> Partial / Unavailable</span>
              {avgRate != null && (
                <span className="ml-auto flex items-center gap-0.5">
                  Avg cost: <span className="font-semibold text-gray-700 ml-1 flex items-center gap-0.5"><IndianRupee size={10}/>{avgRate}/hr</span>
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Delete confirm */}
      {deleteId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 shadow-xl w-80 space-y-4">
            <h3 className="font-bold text-gray-800">Delete {labels.employee}?</h3>
            <p className="text-sm text-gray-600">This permanently removes the {labels.employee.toLowerCase()} and all their assignments.</p>
            <div className="flex gap-2">
              <button onClick={() => deleteEmp.mutate(deleteId)} className="flex-1 bg-red-600 hover:bg-red-700 text-white text-sm py-2 rounded-lg">
                {deleteEmp.isPending ? 'Deleting...' : 'Yes, Delete'}
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
              <h3 className="font-bold text-gray-800">{editingEmp ? `Edit ${labels.employee}` : `New ${labels.employee}`}</h3>
              <button onClick={closeForm}><X size={18} className="text-gray-400 hover:text-gray-600"/></button>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Full Name *</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.full_name} onChange={e => setForm({...form, full_name:e.target.value})} placeholder="e.g. Ramesh Sharma"/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Department</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.department} onChange={e => setForm({...form, department:e.target.value})}>
                    {DEPTS.map(d => <option key={d}>{d}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Employment Type</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.employment_type} onChange={e => setForm({...form, employment_type:e.target.value})}>
                    {EMP_TYPES.map(t => <option key={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Base Availability %</label>
                  <input type="number" min="0" max="100" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.base_availability_pct} onChange={e => setForm({...form, base_availability_pct:Number(e.target.value)})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.status} onChange={e => setForm({...form, status:e.target.value})}>
                    {STATUSES.map(s => <option key={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Contact Number</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.contact_number} onChange={e => setForm({...form, contact_number:e.target.value})} placeholder="+91 98xxx xxxxx"/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Hourly Rate (₹)</label>
                  <input type="number" min="0" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.hourly_rate} onChange={e => setForm({...form, hourly_rate:e.target.value})} placeholder="e.g. 150"/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Overtime Rate (₹/hr)</label>
                  <input type="number" min="0" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.overtime_rate} onChange={e => setForm({...form, overtime_rate:e.target.value})} placeholder="e.g. 225"/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Join Date</label>
                  <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.join_date} onChange={e => setForm({...form, join_date:e.target.value})}/>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-gray-600">Skills</label>
                  <button onClick={() => setForm(f => ({...f, skills:[...f.skills,{skill_id:skills[0]?.id??0,skill_level:'Generic'}]}))}
                    className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"><Plus size={12}/>Add Skill</button>
                </div>
                {form.skills.map((s, i) => (
                  <div key={i} className="flex gap-2 mb-2 items-center">
                    <select className="flex-1 border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={s.skill_id} onChange={e => setForm(f => ({...f, skills:f.skills.map((sk,idx)=>idx===i?{...sk,skill_id:Number(e.target.value)}:sk)}))}>
                      {skills.map(sk => <option key={sk.id} value={sk.id}>{sk.name}</option>)}
                    </select>
                    <select className="border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={s.skill_level} onChange={e => setForm(f => ({...f, skills:f.skills.map((sk,idx)=>idx===i?{...sk,skill_level:e.target.value}:sk)}))}>
                      {LEVELS.map(l => <option key={l}>{l}</option>)}
                    </select>
                    <button onClick={() => setForm(f => ({...f, skills:f.skills.filter((_,idx)=>idx!==i)}))}
                      className="text-red-400 hover:text-red-600"><X size={14}/></button>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-2 px-6 pb-6">
              <button onClick={submitForm} disabled={!form.full_name || isSaving}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm py-2.5 rounded-lg font-medium">
                {isSaving ? 'Saving...' : editingEmp ? `Update ${labels.employee}` : `Add ${labels.employee}`}
              </button>
              <button onClick={closeForm} className="px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-lg">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
