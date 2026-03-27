// src/pages/Availability.tsx
// --------------------------
// Availability Overrides page. Covers both individual leave/maintenance and
// bulk factory holidays. Shows a filterable list of all overrides with
// add, edit and delete. Uses GET/POST/PATCH/DELETE /api/availability/.

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import { Plus, Pencil, Trash2, Loader2, AlertCircle, X, Check, Search, Users, Factory, CalendarOff } from 'lucide-react'
import { useLabels } from '../context/IndustryContext'

interface Employee { id: number; full_name: string; department: string | null }
interface Machine  { id: number; name: string }
interface Override {
  id: number; employee_id: number | null; machine_id: number | null
  date_from: string; date_to: string; availability_pct: number; reason: string | null
}

const emptyForm = () => ({
  resource_type: 'employee' as 'employee' | 'machine' | 'bulk',
  employee_id: '' as string | number,
  machine_id:  '' as string | number,
  bulk_employee_ids: [] as number[],
  date_from: '', date_to: '',
  availability_pct: 0,
  reason: '',
})

export default function Availability() {
  const labels = useLabels()
  const qc = useQueryClient()
  const [search, setSearch]             = useState('')
  const [filterType, setFilterType]     = useState('All')   // All / Employee / Machine
  const [showForm, setShowForm]         = useState(false)
  const [editingOvr, setEditingOvr]     = useState<Override | null>(null)
  const [form, setForm]                 = useState(emptyForm())
  const [deleteId, setDeleteId]         = useState<number | null>(null)
  const [toast, setToast]               = useState('')

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(''), 3000) }

  const { data: overrides = [], isLoading, isError } = useQuery<Override[]>({
    queryKey:['availability'], queryFn:() => apiClient.get('/api/availability/').then(r => r.data),
  })
  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey:['employees'], queryFn:() => apiClient.get('/api/employees/').then(r => r.data),
  })
  const { data: machines = [] } = useQuery<Machine[]>({
    queryKey:['machines'], queryFn:() => apiClient.get('/api/machines/').then(r => r.data),
  })

  const getEmpName = (id: number) => employees.find(e => e.id === id)?.full_name ?? `Employee #${id}`
  const getMachName = (id: number) => machines.find(m => m.id === id)?.name ?? `Machine #${id}`

  // Filtered list
  const filtered = useMemo(() => overrides.filter(o => {
    if (filterType === 'Employee' && !o.employee_id) return false
    if (filterType === 'Machine'  && !o.machine_id)  return false
    if (search) {
      const q = search.toLowerCase()
      const name = o.employee_id ? getEmpName(o.employee_id) : o.machine_id ? getMachName(o.machine_id) : ''
      const reason = o.reason ?? ''
      if (!name.toLowerCase().includes(q) && !reason.toLowerCase().includes(q)) return false
    }
    return true
  }), [overrides, filterType, search, employees, machines])

  // --- Mutations ---
  const createOverride = useMutation({
    mutationFn: (p: object) => apiClient.post('/api/availability/', p),
    onSuccess: () => { qc.invalidateQueries({queryKey:['availability']}); closeForm(); showToast('Override saved!') },
  })
  const updateOverride = useMutation({
    mutationFn: ({id,payload}:{id:number;payload:object}) => apiClient.patch(`/availability/${id}`, payload),
    onSuccess: () => { qc.invalidateQueries({queryKey:['availability']}); closeForm(); showToast('Override updated!') },
  })
  const deleteOverride = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/availability/${id}`),
    onSuccess: () => { qc.invalidateQueries({queryKey:['availability']}); setDeleteId(null); showToast('Override deleted!') },
  })

  function openCreate() { setEditingOvr(null); setForm(emptyForm()); setShowForm(true) }
  function openEdit(o: Override) {
    setEditingOvr(o)
    setForm({
      resource_type: o.employee_id ? 'employee' : 'machine',
      employee_id: o.employee_id ?? '',
      machine_id:  o.machine_id  ?? '',
      bulk_employee_ids: [],
      date_from: o.date_from, date_to: o.date_to,
      availability_pct: o.availability_pct,
      reason: o.reason ?? '',
    })
    setShowForm(true)
  }
  function closeForm() { setShowForm(false); setEditingOvr(null); setForm(emptyForm()) }

  function toggleBulkEmp(id: number) {
    setForm(f => ({
      ...f,
      bulk_employee_ids: f.bulk_employee_ids.includes(id)
        ? f.bulk_employee_ids.filter(e => e !== id)
        : [...f.bulk_employee_ids, id],
    }))
  }

  async function submitForm() {
    if (form.resource_type === 'bulk') {
      // Create one override per selected employee
      for (const emp_id of form.bulk_employee_ids) {
        await createOverride.mutateAsync({
          employee_id: emp_id, machine_id: null,
          date_from: form.date_from, date_to: form.date_to,
          availability_pct: Number(form.availability_pct), reason: form.reason || null,
        })
      }
      closeForm()
      showToast(`${form.bulk_employee_ids.length} overrides created!`)
      return
    }
    const payload = {
      employee_id: form.resource_type === 'employee' ? Number(form.employee_id) || null : null,
      machine_id:  form.resource_type === 'machine'  ? Number(form.machine_id)  || null : null,
      date_from: form.date_from, date_to: form.date_to,
      availability_pct: Number(form.availability_pct),
      reason: form.reason || null,
    }
    if (editingOvr) updateOverride.mutate({id: editingOvr.id, payload})
    else createOverride.mutate(payload)
  }

  const isSaving = createOverride.isPending || updateOverride.isPending

  const pctColour = (pct: number) => {
    if (pct === 0)   return 'bg-red-100 text-red-700'
    if (pct <= 50)   return 'bg-orange-100 text-orange-700'
    return 'bg-yellow-100 text-yellow-700'
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Availability Overrides</h2>
          <p className="text-sm text-gray-500 mt-0.5">Manage leave, holidays and machine maintenance windows.</p>
        </div>
        <button onClick={openCreate} className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg transition-colors">
          <Plus size={16}/> Add Override
        </button>
      </div>

      {toast && <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-sm"><Check size={15}/>{toast}</div>}

      {/* Quick stat cards */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label:'Total Overrides',      value: overrides.length,                                     icon:CalendarOff, colour:'text-blue-600',  bg:'bg-blue-50'   },
          { label:'Employee Leave/Blocks', value: overrides.filter(o=>o.employee_id).length,            icon:Users,       colour:'text-purple-600',bg:'bg-purple-50' },
          { label:'Machine Maintenance',  value: overrides.filter(o=>o.machine_id).length,             icon:Factory,     colour:'text-green-600', bg:'bg-green-50'  },
        ].map(({label,value,icon:Icon,colour,bg})=>(
          <div key={label} className="bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3">
            <div className={`${bg} p-2.5 rounded-lg`}><Icon className={colour} size={18}/></div>
            <div><p className="text-xl font-bold text-gray-800">{value}</p><p className="text-xs text-gray-500">{label}</p></div>
          </div>
        ))}
      </div>

      {/* Search + filter */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
          <input className="w-full pl-8 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Search by name or reason..." value={search} onChange={e=>setSearch(e.target.value)}/>
        </div>
        <select className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={filterType} onChange={e=>setFilterType(e.target.value)}>
          <option value="All">All Types</option>
          <option value="Employee">{labels.employees} Only</option>
          <option value="Machine">{labels.machines} Only</option>
        </select>
      </div>

      {isLoading && <div className="flex items-center gap-2 text-gray-500 justify-center py-10"><Loader2 className="animate-spin" size={18}/>Loading overrides...</div>}
      {isError   && <div className="flex items-center gap-2 text-red-500 justify-center py-10"><AlertCircle size={18}/>Failed to load overrides.</div>}

      {/* Overrides table */}
      {!isLoading && !isError && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr className="text-left text-gray-500">
                <th className="px-4 py-3 font-medium">Resource</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Date From</th>
                <th className="px-4 py-3 font-medium">Date To</th>
                <th className="px-4 py-3 font-medium">Availability</th>
                <th className="px-4 py-3 font-medium">Reason</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(o => (
                <tr key={o.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800">
                    {o.employee_id ? getEmpName(o.employee_id) : o.machine_id ? getMachName(o.machine_id) : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${o.employee_id ? 'bg-purple-100 text-purple-700' : 'bg-green-100 text-green-700'}`}>
                      {o.employee_id ? 'Employee' : 'Machine'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{o.date_from}</td>
                  <td className="px-4 py-3 text-gray-600">{o.date_to}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${pctColour(o.availability_pct)}`}>
                      {o.availability_pct}%
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500 max-w-xs truncate">{o.reason ?? '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button onClick={()=>openEdit(o)} className="text-xs flex items-center gap-1 text-blue-600 hover:text-blue-800 border border-blue-200 rounded-md px-2 py-1"><Pencil size={11}/>Edit</button>
                      <button onClick={()=>setDeleteId(o.id)} className="text-xs flex items-center gap-1 text-red-500 hover:text-red-700 border border-red-200 rounded-md px-2 py-1"><Trash2 size={11}/>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && <p className="text-center text-gray-400 py-8 text-sm">No overrides found.</p>}
        </div>
      )}

      {/* Delete confirm */}
      {deleteId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 shadow-xl w-80 space-y-4">
            <h3 className="font-bold text-gray-800">Delete Override?</h3>
            <p className="text-sm text-gray-600">This availability override will be permanently removed.</p>
            <div className="flex gap-2">
              <button onClick={()=>deleteOverride.mutate(deleteId)} className="flex-1 bg-red-600 hover:bg-red-700 text-white text-sm py-2 rounded-lg">{deleteOverride.isPending?'Deleting...':'Yes, Delete'}</button>
              <button onClick={()=>setDeleteId(null)} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2 rounded-lg">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Add / Edit modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h3 className="font-bold text-gray-800">{editingOvr ? 'Edit Override' : 'New Override'}</h3>
              <button onClick={closeForm}><X size={18} className="text-gray-400 hover:text-gray-600"/></button>
            </div>
            <div className="p-6 space-y-4">

              {/* Type selector — only show on create */}
              {!editingOvr && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-2">Override Type</label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { key:'employee', label:`Individual ${labels.employee}`, icon:Users },
                      { key:'machine',  label:labels.machine,        icon:Factory },
                      { key:'bulk',     label:'Bulk / Holiday',      icon:CalendarOff },
                    ].map(({key,label,icon:Icon})=>(
                      <button key={key} type="button" onClick={()=>setForm({...form,resource_type:key as 'employee'|'machine'|'bulk'})}
                        className={`flex flex-col items-center gap-1.5 p-3 rounded-xl border text-xs font-medium transition-colors ${form.resource_type===key?'bg-blue-600 text-white border-blue-600':'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'}`}>
                        <Icon size={16}/>{label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Individual employee */}
              {form.resource_type === 'employee' && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Employee *</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.employee_id} onChange={e=>setForm({...form,employee_id:e.target.value})}>
                    <option value="">— Select {labels.employee.toLowerCase()} —</option>
                    {employees.map(e=><option key={e.id} value={e.id}>{e.full_name} {e.department?`(${e.department})`:''}</option>)}
                  </select>
                </div>
              )}

              {/* Machine */}
              {form.resource_type === 'machine' && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Machine *</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.machine_id} onChange={e=>setForm({...form,machine_id:e.target.value})}>
                    <option value="">— Select {labels.machine.toLowerCase()} —</option>
                    {machines.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                </div>
              )}

              {/* Bulk employee selector */}
              {form.resource_type === 'bulk' && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-2">
                    Select Employees ({form.bulk_employee_ids.length} selected)
                  </label>
                  <div className="border border-gray-300 rounded-lg max-h-40 overflow-y-auto p-2 space-y-1">
                    {employees.map(e=>(
                      <label key={e.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-gray-50 cursor-pointer text-sm">
                        <input type="checkbox" checked={form.bulk_employee_ids.includes(e.id)} onChange={()=>toggleBulkEmp(e.id)} className="rounded"/>
                        <span className="text-gray-800">{e.full_name}</span>
                        {e.department && <span className="text-gray-400 text-xs">· {e.department}</span>}
                      </label>
                    ))}
                  </div>
                  <div className="flex gap-2 mt-2">
                    <button type="button" onClick={()=>setForm(f=>({...f,bulk_employee_ids:employees.map(e=>e.id)}))}
                      className="text-xs text-blue-600 hover:text-blue-800">Select all</button>
                    <span className="text-gray-300">|</span>
                    <button type="button" onClick={()=>setForm(f=>({...f,bulk_employee_ids:[]}))}
                      className="text-xs text-gray-500 hover:text-gray-700">Clear all</button>
                  </div>
                </div>
              )}

              {/* Date range */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">From Date *</label>
                  <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.date_from} onChange={e=>setForm({...form,date_from:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">To Date *</label>
                  <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={form.date_to} onChange={e=>setForm({...form,date_to:e.target.value})}/>
                </div>
              </div>

              {/* Availability % */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Availability % <span className="text-gray-400">(0 = fully unavailable, 50 = half day)</span>
                </label>
                <div className="flex items-center gap-3">
                  <input type="range" min="0" max="100" step="10" className="flex-1"
                    value={form.availability_pct} onChange={e=>setForm({...form,availability_pct:Number(e.target.value)})}/>
                  <span className={`px-3 py-1 rounded-full text-sm font-bold min-w-14 text-center ${pctColour(form.availability_pct)}`}>
                    {form.availability_pct}%
                  </span>
                </div>
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>0% — Full leave</span><span>50% — Half day</span><span>100% — Full availability</span>
                </div>
              </div>

              {/* Reason */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Reason</label>
                <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={form.reason} onChange={e=>setForm({...form,reason:e.target.value})}
                  placeholder="e.g. Sick leave, Factory holiday, Scheduled maintenance"/>
              </div>
            </div>
            <div className="flex gap-2 px-6 pb-6">
              <button onClick={submitForm}
                disabled={isSaving || !form.date_from || !form.date_to ||
                  (form.resource_type==='employee' && !form.employee_id) ||
                  (form.resource_type==='machine'  && !form.machine_id)  ||
                  (form.resource_type==='bulk'     && form.bulk_employee_ids.length===0)}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm py-2.5 rounded-lg font-medium transition-colors">
                {isSaving ? 'Saving...' : editingOvr ? 'Update Override' : form.resource_type==='bulk' ? `Create ${form.bulk_employee_ids.length} Overrides` : 'Save Override'}
              </button>
              <button onClick={closeForm} className="px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-lg">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
