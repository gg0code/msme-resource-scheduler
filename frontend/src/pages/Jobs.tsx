// src/pages/Jobs.tsx  — full rewrite with:
//   · Colour badge (green/amber/red) with tooltip + expandable conflict panel
//   · Auto availability check after job creation
//   · Raw materials builder in wizard + edit
//   · Job timer: Start / Pause / Resume / End

import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import {
  Plus, Pencil, Trash2, Loader2, AlertCircle, CalendarDays, IndianRupee,
  X, Check, Search, ChevronRight, ChevronLeft, ChevronDown, ChevronUp,
  Users, ClipboardCheck, AlertTriangle, UserCheck, Factory,
  Play, Pause, Square, RotateCcw, Clock, Package,
} from 'lucide-react'
import { usePlanLimits, LimitedButton, PlanLimitBanner, RawMaterialLimitHint } from '../components/PlanLimitGuard'

// ── Types ──────────────────────────────────────────────
interface Skill    { id: number; name: string; is_premium: boolean }
interface Employee { id: number; full_name: string; department: string | null }
interface MachineSkillReq { skill_id: number; min_skill_level: string; employees_required: number }
interface Machine  { id: number; name: string; status: string; location_bay: string | null; skill_requirements: MachineSkillReq[] }
interface SkillReq { id?: number; skill_id: number; min_skill_level: string; employees_required: number }
interface RawMat   { name: string; quantity: number; unit: string; unit_cost: number }
interface AssignedEmployee { id: number; full_name: string; department: string | null }
interface AssignedMachine  { id: number; name: string; machine_type: string | null }
interface Job {
  id: number; name: string; customer: string | null
  start_date: string; end_date: string; estimated_hours_per_day: number
  tentative_profit: number | null; order_value: number | null; misc_cost: number | null
  priority: string; status: string
  notes: string | null; skill_requirements: (SkillReq & { id: number })[]
  raw_materials: RawMat[]
  assigned_employees: AssignedEmployee[]
  assigned_machines: AssignedMachine[]
  timer_status: 'idle' | 'running' | 'paused' | 'ended'
  actual_start_at: string | null; actual_end_at: string | null
  paused_seconds: number; timer_log: { event: string; timestamp: string }[]
  availability?: AvailResult | null
}
interface AvailResult {
  feasible: boolean; feasibility_score: number
  conflicts: { resource_name: string; reason: string; resource_type: string }[]
  available_employees: Record<string, number[]>
}
interface SkillReqInfo {
  id: number; skill_id: number; skill_name: string
  min_skill_level: string; employees_required: number
  available_employee_ids: number[]
}
interface MachineInfo {
  id: number; name: string; machine_type: string | null
  location_bay: string | null; hourly_rate: number | null
  available: boolean; busy_reason: string | null
  skill_requirements: { skill_id: number; skill_name: string; min_skill_level: string; employees_required: number }[]
}
interface EmpInfo {
  id: number; full_name: string; department: string | null
  employment_type: string; hourly_rate: number | null
  available: boolean; busy_reason: string | null
  skills: { skill_id: number; skill_name: string; skill_level: string }[]
}
interface CheckResult {
  job_id: number; feasible: boolean; feasibility_score: number
  conflicts: { resource_type: string; resource_name: string; reason: string }[]
  skill_requirements: SkillReqInfo[]
  machines: MachineInfo[]
  employees: EmpInfo[]
  currently_assigned_employee_ids: number[]
  currently_assigned_machine_ids: number[]
}

// ── Constants ──────────────────────────────────────────
const PRIORITIES = ['Low','Medium','High','Critical']
const STATUSES   = ['Draft','Pending Assignment','Scheduled','In Progress','Completed','Cancelled']
const LEVELS     = ['Generic','Intermediate','Premium']
const UNITS      = ['pcs','kg','m','l','set','lot']

const priorityColour: Record<string,string> = {
  Critical:'bg-red-100 text-red-700', High:'bg-orange-100 text-orange-700',
  Medium:'bg-yellow-100 text-yellow-700', Low:'bg-gray-100 text-gray-600',
}
const statusColour: Record<string,string> = {
  'Scheduled':'bg-green-100 text-green-700','Pending Assignment':'bg-blue-100 text-blue-700',
  'In Progress':'bg-purple-100 text-purple-700','Draft':'bg-gray-100 text-gray-600',
  'Completed':'bg-teal-100 text-teal-700','Cancelled':'bg-red-100 text-red-600',
}
const scoreColour = (s: number) =>
  s === 100 ? { bar:'bg-green-500', text:'text-green-700', bg:'bg-green-50', badge:'bg-green-500', label:'Feasible' }
  : s >= 60  ? { bar:'bg-orange-400', text:'text-orange-700', bg:'bg-orange-50', badge:'bg-orange-400', label:'Partial' }
  : { bar:'bg-red-500', text:'text-red-700', bg:'bg-red-50', badge:'bg-red-500', label:'Conflicts' }

const timerColour: Record<string,string> = {
  idle:'text-gray-400', running:'text-green-600', paused:'text-yellow-600', ended:'text-teal-600'
}

const emptyDetails = () => ({
  name:'', customer:'', notes:'', start_date:'', end_date:'',
  estimated_hours_per_day: 8, tentative_profit:'', order_value:'', misc_cost:'', priority:'Medium', status:'Draft',
})
const emptyMat = (): RawMat => ({ name:'', quantity:1, unit:'pcs', unit_cost:0 })

// ── Availability badge component ───────────────────────
function AvailBadge({ result, loading }: { result?: AvailResult | null; loading?: boolean }) {
  const [showTip, setShowTip] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) { setShowTip(false) }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  if (loading) return <span className="w-3 h-3 rounded-full bg-gray-300 animate-pulse inline-block"/>
  if (!result)  return null

  const c = scoreColour(result.feasibility_score)
  return (
    <div ref={ref} className="relative inline-block">
      {/* Badge dot */}
      <button
        onClick={() => setShowTip(t => !t)}
        className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold text-white ${c.badge} hover:opacity-80 transition-opacity`}
        title="Click for details">
        {result.feasibility_score}% {c.label}
      </button>

      {/* Tooltip */}
      {showTip && (
        <div className="absolute right-0 top-7 z-30 bg-white border border-gray-200 rounded-xl shadow-xl p-3 w-72">
          <div className={`${c.bg} rounded-lg px-3 py-2 mb-2`}>
            <div className="flex items-center justify-between">
              <span className={`text-xs font-bold ${c.text}`}>Availability: {c.label}</span>
              <span className={`text-sm font-black ${c.text}`}>{result.feasibility_score}%</span>
            </div>
            <div className="w-full bg-white/60 rounded-full h-1.5 mt-1">
              <div className={`${c.bar} h-1.5 rounded-full`} style={{ width:`${result.feasibility_score}%` }}/>
            </div>
          </div>
          {result.conflicts.length === 0
            ? <p className="text-xs text-green-600 flex items-center gap-1"><Check size={12}/>All requirements met</p>
            : <>
                <p className="text-xs font-semibold text-gray-600 mb-1">{result.conflicts.length} conflict(s):</p>
                {result.conflicts.slice(0,4).map((c,i) => (
                  <p key={i} className="text-xs text-red-600 mb-0.5">· <span className="font-medium">{c.resource_name}</span>: {c.reason}</p>
                ))}
                {result.conflicts.length > 4 && <p className="text-xs text-gray-400">+{result.conflicts.length-4} more</p>}
              </>
          }
        </div>
      )}
    </div>
  )
}

// ── Timer display ──────────────────────────────────────
function TimerDisplay({ job }: { job: Job }) {
  const [elapsed, setElapsed] = useState('')
  useEffect(() => {
    if (job.timer_status !== 'running' || !job.actual_start_at) { setElapsed(''); return }
    const tick = () => {
      const start = new Date(job.actual_start_at!).getTime()
      const now   = Date.now()
      const secs  = Math.floor((now - start) / 1000) - (job.paused_seconds || 0)
      const h = Math.floor(secs/3600), m = Math.floor((secs%3600)/60), s = secs%60
      setElapsed(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`)
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [job.timer_status, job.actual_start_at, job.paused_seconds])

  if (job.timer_status === 'idle') return null
  return (
    <div className={`flex items-center gap-1.5 text-xs font-mono font-semibold ${timerColour[job.timer_status]}`}>
      <Clock size={12}/>
      {job.timer_status === 'running' && elapsed ? elapsed
        : job.timer_status === 'paused' ? 'Paused'
        : job.timer_status === 'ended' && job.actual_start_at && job.actual_end_at
          ? (() => {
              const total = Math.floor((new Date(job.actual_end_at).getTime() - new Date(job.actual_start_at).getTime()) / 1000)
              const net   = total - (job.paused_seconds||0)
              const h = Math.floor(net/3600), m = Math.floor((net%3600)/60)
              return `Done — ${h}h ${m}m`
            })()
          : job.timer_status
      }
    </div>
  )
}

// ══════════════════════════════════════════════════════
export default function Jobs() {
  const qc = useQueryClient()

  // Filters
  const [search, setSearch]               = useState('')
  const [filterStatus, setFilterStatus]   = useState('All')
  const [filterPriority, setFilterPriority] = useState('All')
  const [filterFrom, setFilterFrom]       = useState('')
  const [filterTo, setFilterTo]           = useState('')

  // Availability cache: jobId → result
  const [availCache, setAvailCache]       = useState<Record<number, AvailResult | null | 'loading'>>({})
  // Expanded conflict panels
  const [expandedConflicts, setExpandedConflicts] = useState<Set<number>>(new Set())
  // Expanded table rows
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

  // Wizard
  const [wizardOpen, setWizardOpen]       = useState(false)
  const [wizardStep, setWizardStep]       = useState(1)
  const [details, setDetails]             = useState(emptyDetails())
  const [skillReqs, setSkillReqs]         = useState<SkillReq[]>([])
  const [rawMats, setRawMats]             = useState<RawMat[]>([])
  const [selectedEmps, setSelectedEmps]   = useState<number[]>([])
  const [selectedMachines, setSelectedMachines] = useState<number[]>([])
  const [wizardCheck, setWizardCheck]     = useState<AvailResult | null>(null)
  const [wizardChecking, setWizardChecking] = useState(false)

  // Edit
  const [editJob, setEditJob]             = useState<Job | null>(null)
  const [editForm, setEditForm]           = useState(emptyDetails())
  const [editSkillReqs, setEditSkillReqs] = useState<SkillReq[]>([])
  const [editRawMats, setEditRawMats]     = useState<RawMat[]>([])

  // Assign drawer
  const [assignJob, setAssignJob]           = useState<Job | null>(null)
  const [assignCheck, setAssignCheck]       = useState<CheckResult | null>(null)
  const [assignChecking, setAssignChecking] = useState(false)
  const [assignEmps, setAssignEmps]         = useState<number[]>([])
  const [assignMachines, setAssignMachines] = useState<number[]>([])
  const [assignError, setAssignError]       = useState('')
  const [assignTab, setAssignTab]           = useState<'machines'|'people'|'extras'>('machines')

  const [deleteId, setDeleteId]           = useState<number | null>(null)
  const [toast, setToast]                 = useState('')
  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(''), 3500) }

  // ── Queries ───────────────────────────────────────────
  const { data: jobs = [], isLoading, isError } = useQuery<Job[]>({
    queryKey:['jobs'], queryFn:() => apiClient.get('/jobs/').then(r => r.data),
  })
  const { data: skills = [] } = useQuery<Skill[]>({
    queryKey:['skills'], queryFn:() => apiClient.get('/skills/').then(r => r.data),
  })
  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey:['employees'], queryFn:() => apiClient.get('/employees/').then(r => r.data),
  })
  const { data: machines = [] } = useQuery<Machine[]>({
    queryKey:['machines'], queryFn:() => apiClient.get('/machines/').then(r => r.data),
  })
  const { planLimits } = usePlanLimits()

  const getSkillName = useCallback((id: number) => skills.find(s => s.id === id)?.name ?? `Skill#${id}`, [skills])
  const getEmpName   = useCallback((id: number) => {
    const e = employees.find(e => e.id === id)
    return e ? `${e.full_name}${e.department ? ` · ${e.department}` : ''}` : `Emp#${id}`
  }, [employees])

  // ── Auto-check availability for all non-completed jobs ─
  const runAvailCheck = useCallback(async (jobId: number) => {
    setAvailCache(c => ({ ...c, [jobId]: 'loading' }))
    try {
      const res = await apiClient.get(`/assignments/check/${jobId}`)
      setAvailCache(c => ({ ...c, [jobId]: res.data }))
    } catch {
      setAvailCache(c => ({ ...c, [jobId]: null }))
    }
  }, [])

  // Run checks for jobs that don't have a result yet
  useEffect(() => {
    jobs.forEach(job => {
      if (!['Completed','Cancelled'].includes(job.status) && availCache[job.id] === undefined) {
        runAvailCheck(job.id)
      }
    })
  }, [jobs, availCache, runAvailCheck])

  // ── Filters ────────────────────────────────────────────
  const filtered = useMemo(() => jobs.filter(j => {
    const q = search.toLowerCase()
    if (q && !j.name.toLowerCase().includes(q) && !(j.customer ?? '').toLowerCase().includes(q)) return false
    if (filterStatus   !== 'All' && j.status   !== filterStatus)   return false
    if (filterPriority !== 'All' && j.priority !== filterPriority) return false
    if (filterFrom && j.end_date   < filterFrom) return false
    if (filterTo   && j.start_date > filterTo)   return false
    return true
  }), [jobs, search, filterStatus, filterPriority, filterFrom, filterTo])

  // ── Mutations ──────────────────────────────────────────
  const createJob = useMutation({
    mutationFn: (p: object) => apiClient.post('/jobs/', p),
    onSuccess: async (res) => {
      const newJobId = res.data.id
      if ((selectedEmps.length > 0 || selectedMachines.length > 0) && newJobId) {
        try { await apiClient.post('/assignments/', { job_id:newJobId, employee_ids:selectedEmps, machine_ids:selectedMachines }) }
        catch (_) {}
      }
      qc.invalidateQueries({queryKey:['jobs']})
      qc.invalidateQueries({queryKey:['dashboard']})
      qc.invalidateQueries({queryKey:['plan-limits']})
      setTimeout(() => runAvailCheck(newJobId), 500)
      closeWizard()
      showToast('Job created! Running availability check...')
    },
  })

  const updateJob = useMutation({
    mutationFn: ({id,p}:{id:number;p:object}) => apiClient.patch(`/jobs/${id}`, p),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({queryKey:['jobs']})
      setEditJob(null)
      // Re-run availability check after edit
      runAvailCheck((vars as {id:number}).id)
      showToast('Job updated!')
    },
  })

  const deleteJobMut = useMutation({
    mutationFn: (id: number) => apiClient.delete(`/jobs/${id}`),
    onSuccess: () => { qc.invalidateQueries({queryKey:['jobs']}); qc.invalidateQueries({queryKey:['dashboard']}); qc.invalidateQueries({queryKey:['plan-limits']}); setDeleteId(null); showToast('Job deleted!') },
  })

  const timerMut = useMutation({
    mutationFn: ({id,action}:{id:number;action:string}) => apiClient.post(`/jobs/${id}/timer`, {action}),
    onSuccess: () => { qc.invalidateQueries({queryKey:['jobs']}); qc.invalidateQueries({queryKey:['dashboard']}) },
  })

  const assignMut = useMutation({
    mutationFn: (p: object) => apiClient.post('/assignments/', p),
    onSuccess: (res) => {
      qc.invalidateQueries({queryKey:['jobs']})
      qc.invalidateQueries({queryKey:['dashboard']})
      if (assignJob) runAvailCheck(assignJob.id)
      setAssignJob(null)
      showToast(`${res.data.assignments.length} resource(s) assigned!`)
    },
    onError: (e: unknown) => {
      const msg = (e as {response?:{data?:{detail?:string}}})?.response?.data?.detail
      setAssignError(msg ?? 'Assignment failed.')
    },
  })

  // ── Wizard helpers ────────────────────────────────────
  function openWizard() { setDetails(emptyDetails()); setSkillReqs([]); setRawMats([]); setSelectedEmps([]); setSelectedMachines([]); setWizardCheck(null); setWizardStep(1); setWizardOpen(true) }
  function closeWizard() { setWizardOpen(false); setWizardStep(1) }

  async function wizardCheckAvail() {
    if (skillReqs.length === 0) return
    setWizardChecking(true); setWizardCheck(null)
    try {
      const empData = await apiClient.get('/employees/').then(r => r.data) as (Employee & { skills:{skill_id:number;skill_level:string}[] })[]
      const RANK: Record<string,number> = { Generic:1, Intermediate:2, Premium:3 }
      const newMap: Record<string,number[]> = {}
      skillReqs.forEach((req,i) => {
        newMap[String(i)] = empData.filter(e =>
          e.skills?.some(s => s.skill_id===req.skill_id && RANK[s.skill_level]>=RANK[req.min_skill_level])
        ).map(e => e.id)
      })
      const needed = skillReqs.reduce((s,r)=>s+r.employees_required,0)
      const avail  = skillReqs.reduce((s,_,i)=>s+Math.min(newMap[String(i)]?.length??0,skillReqs[i].employees_required),0)
      const score  = needed>0 ? Math.round((avail/needed)*100) : 100
      setWizardCheck({ feasible:score>=100, feasibility_score:score, conflicts:[], available_employees:newMap })
    } catch(_) {}
    finally { setWizardChecking(false) }
  }

  function submitWizard() {
    createJob.mutate({
      name:details.name, customer:details.customer||null, notes:details.notes||null,
      start_date:details.start_date, end_date:details.end_date,
      estimated_hours_per_day:Number(details.estimated_hours_per_day),
      tentative_profit:details.tentative_profit!==''?Number(details.tentative_profit):null,
      order_value:details.order_value!==''?Number(details.order_value):null,
      misc_cost:details.misc_cost!==''?Number(details.misc_cost):null,
      priority:details.priority,
      status: selectedEmps.length>0||selectedMachines.length>0 ? 'Scheduled' : details.status,
      skill_requirements:skillReqs, raw_materials:rawMats,
    })
  }

  // ── Edit helpers ──────────────────────────────────────
  function openEdit(job: Job) {
    setEditJob(job)
    setEditForm({ name:job.name, customer:job.customer??'', notes:job.notes??'',
      start_date:job.start_date, end_date:job.end_date,
      estimated_hours_per_day:job.estimated_hours_per_day,
      tentative_profit:job.tentative_profit!=null?String(job.tentative_profit):'',
      order_value:job.order_value!=null?String(job.order_value):'',
      misc_cost:job.misc_cost!=null?String(job.misc_cost):'',
      priority:job.priority, status:job.status })
    setEditSkillReqs(job.skill_requirements.map(r=>({skill_id:r.skill_id,min_skill_level:r.min_skill_level,employees_required:r.employees_required})))
    setEditRawMats(job.raw_materials || [])
  }

  function submitEdit() {
    if (!editJob) return
    updateJob.mutate({ id:editJob.id, p:{
      ...editForm,
      estimated_hours_per_day:Number(editForm.estimated_hours_per_day),
      tentative_profit:editForm.tentative_profit!==''?Number(editForm.tentative_profit):null,
      order_value:editForm.order_value!==''?Number(editForm.order_value):null,
      misc_cost:editForm.misc_cost!==''?Number(editForm.misc_cost):null,
      skill_requirements:editSkillReqs, raw_materials:editRawMats,
    }})
  }

  // ── Assign drawer ─────────────────────────────────────
  async function openAssign(job: Job) {
    setAssignJob(job)
    setAssignEmps([])
    setAssignMachines([])
    setAssignError('')
    setAssignCheck(null)
    setAssignChecking(true)
    setAssignTab('machines')
    try {
      const res = await apiClient.get(`/assignments/check/${job.id}`)
      const data: CheckResult = res.data
      // Pre-fill currently assigned resources
      setAssignEmps(data.currently_assigned_employee_ids)
      setAssignMachines(data.currently_assigned_machine_ids)
      setAssignCheck(data)
    } catch(_) {
      setAssignCheck(null)
    } finally {
      setAssignChecking(false)
    }
  }

  // When machines change in assign drawer, auto-select skill-required employees
  function onAssignMachineToggle(machineId: number, machines: MachineInfo[], checked: boolean) {
    if (checked) {
      setAssignMachines(p => [...p, machineId])
    } else {
      setAssignMachines(p => p.filter(id => id !== machineId))
    }
  }

  // Raw material helpers
  const matTotal = (mats: RawMat[]) => mats.reduce((s,m)=>s+m.quantity*m.unit_cost,0)
  const rawMatLimit = planLimits?.limits?.raw_materials?.limit ?? null
  const rawMatLimitReached = (count: number) => rawMatLimit !== null && count >= rawMatLimit

  // Toggle conflict expand
  function toggleConflict(id: number) {
    setExpandedConflicts(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  // ─────────────────────────────────────────────────────
  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Jobs</h2>
          <p className="text-sm text-gray-500 mt-0.5">{filtered.length} of {jobs.length} jobs shown.</p>
        </div>
        <LimitedButton resource="jobs" planLimits={planLimits} onClick={openWizard}>
          <Plus size={16}/> New Job
        </LimitedButton>
      </div>

      <PlanLimitBanner resource="jobs" planLimits={planLimits} label="jobs" />

      {toast && <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-sm"><Check size={15}/>{toast}</div>}

      {/* Filters */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
        <div className="flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-52">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
            <input className="w-full pl-8 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Search by name or customer..." value={search} onChange={e=>setSearch(e.target.value)}/>
          </div>
          <select className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={filterStatus} onChange={e=>setFilterStatus(e.target.value)}>
            <option value="All">All Statuses</option>{STATUSES.map(s=><option key={s}>{s}</option>)}
          </select>
          <select className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={filterPriority} onChange={e=>setFilterPriority(e.target.value)}>
            <option value="All">All Priorities</option>{PRIORITIES.map(p=><option key={p}>{p}</option>)}
          </select>
        </div>
        <div className="flex flex-wrap gap-3 items-center">
          <span className="text-xs text-gray-500 font-medium">Date range:</span>
          <input type="date" className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm" value={filterFrom} onChange={e=>setFilterFrom(e.target.value)}/>
          <span className="text-gray-400">→</span>
          <input type="date" className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm" value={filterTo} onChange={e=>setFilterTo(e.target.value)}/>
          {(search||filterStatus!=='All'||filterPriority!=='All'||filterFrom||filterTo) && (
            <button onClick={()=>{setSearch('');setFilterStatus('All');setFilterPriority('All');setFilterFrom('');setFilterTo('')}}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-1.5">
              <X size={12}/> Clear
            </button>
          )}
        </div>
      </div>

      {isLoading && <div className="flex items-center gap-2 text-gray-500 justify-center py-10"><Loader2 className="animate-spin" size={18}/>Loading jobs...</div>}
      {isError   && <div className="flex items-center gap-2 text-red-500 justify-center py-10"><AlertCircle size={18}/>Failed to load jobs.</div>}

      {/* ── Jobs Table ── */}
      {!isLoading && !isError && (() => {
        // cost helper — computed client-side from what we know
        const jobCost = (job: Job) => {
          const rawTotal  = matTotal(job.raw_materials || [])
          const miscTotal = job.misc_cost ?? 0
          // machine run cost = hourly_rate * hours_per_day * duration_days (machines don't carry rate here yet, so 0 until extended)
          return rawTotal + miscTotal
        }
        const jobProfit = (job: Job) => {
          const ov = job.order_value
          if (ov == null) return null
          return ov - jobCost(job)
        }

        return (
          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500 font-semibold uppercase tracking-wide">
                    <th className="w-8 px-3 py-3"/>
                    <th className="text-left px-4 py-3">Job</th>
                    <th className="text-left px-4 py-3">Dates</th>
                    <th className="text-left px-4 py-3">Status</th>
                    <th className="text-left px-4 py-3">Resources</th>
                    <th className="text-right px-4 py-3">Order Value</th>
                    <th className="text-right px-4 py-3">Total Cost</th>
                    <th className="text-right px-4 py-3">Profit</th>
                    <th className="text-right px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filtered.map(job => {
                    const avail    = availCache[job.id]
                    const aLoading = avail === 'loading'
                    const result   = typeof avail === 'object' ? avail : null
                    const isExpanded = expandedRow === job.id
                    const rawTotal   = matTotal(job.raw_materials || [])
                    const totalCost  = jobCost(job)
                    const profit     = jobProfit(job)
                    const profitPos  = profit != null && profit >= 0

                    return (
                      <>
                        <tr key={job.id}
                          onClick={() => setExpandedRow(isExpanded ? null : job.id)}
                          className={`cursor-pointer transition-colors ${isExpanded ? 'bg-blue-50' : 'hover:bg-gray-50'}`}>

                          {/* Expand chevron */}
                          <td className="px-3 py-3 text-gray-400">
                            {isExpanded
                              ? <ChevronDown size={14} className="text-blue-500"/>
                              : <ChevronRight size={14}/>}
                          </td>

                          {/* Job name + customer + avail badge */}
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-semibold text-gray-800">{job.name}</span>
                              <AvailBadge result={result} loading={aLoading}/>
                            </div>
                            {job.customer && <p className="text-xs text-gray-400 mt-0.5">{job.customer}</p>}
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${priorityColour[job.priority]??''}`}>{job.priority}</span>
                            </div>
                          </td>

                          {/* Dates */}
                          <td className="px-4 py-3 whitespace-nowrap">
                            <div className="flex items-center gap-1 text-xs text-gray-600">
                              <CalendarDays size={11} className="text-gray-400"/>
                              {job.start_date}
                            </div>
                            <div className="text-xs text-gray-400 mt-0.5 pl-4">→ {job.end_date}</div>
                            <div className="text-xs text-gray-400 mt-0.5 pl-4">{job.estimated_hours_per_day}h/day</div>
                          </td>

                          {/* Status */}
                          <td className="px-4 py-3">
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColour[job.status]??''}`}>
                              {job.status}
                            </span>
                            <div className="mt-1.5"><TimerDisplay job={job}/></div>
                          </td>

                          {/* Resources summary */}
                          <td className="px-4 py-3">
                            {job.assigned_machines.length > 0 && (
                              <div className="flex flex-wrap items-center gap-1 mb-1">
                                <Factory size={11} className="text-green-600 shrink-0"/>
                                {job.assigned_machines.slice(0,2).map(m => (
                                  <span key={m.id} className="bg-green-50 border border-green-200 text-green-700 text-xs px-1.5 py-0.5 rounded-full">{m.name}</span>
                                ))}
                                {job.assigned_machines.length > 2 && <span className="text-xs text-gray-400">+{job.assigned_machines.length-2}</span>}
                              </div>
                            )}
                            {job.assigned_employees.length > 0
                              ? <div className="flex flex-wrap items-center gap-1">
                                  <Users size={11} className="text-blue-500 shrink-0"/>
                                  {job.assigned_employees.slice(0,2).map(e => (
                                    <span key={e.id} className="bg-blue-50 border border-blue-200 text-blue-700 text-xs px-1.5 py-0.5 rounded-full">{e.full_name}</span>
                                  ))}
                                  {job.assigned_employees.length > 2 && <span className="text-xs text-gray-400">+{job.assigned_employees.length-2}</span>}
                                </div>
                              : !['Completed','Cancelled'].includes(job.status) && (
                                  <div className="flex items-center gap-1 text-xs text-amber-600">
                                    <AlertTriangle size={11}/>Unassigned
                                  </div>
                                )
                            }
                          </td>

                          {/* Order value */}
                          <td className="px-4 py-3 text-right">
                            {job.order_value != null
                              ? <span className="text-sm font-semibold text-gray-800 flex items-center gap-0.5 justify-end">
                                  <IndianRupee size={12}/>{job.order_value.toLocaleString('en-IN')}
                                </span>
                              : <span className="text-xs text-gray-300 italic">—</span>
                            }
                          </td>

                          {/* Total cost */}
                          <td className="px-4 py-3 text-right">
                            {totalCost > 0
                              ? <span className="text-sm font-semibold text-red-600 flex items-center gap-0.5 justify-end">
                                  <IndianRupee size={12}/>{totalCost.toLocaleString('en-IN')}
                                </span>
                              : <span className="text-xs text-gray-300 italic">—</span>
                            }
                          </td>

                          {/* Profit */}
                          <td className="px-4 py-3 text-right">
                            {profit != null
                              ? <span className={`text-sm font-bold flex items-center gap-0.5 justify-end ${profitPos ? 'text-green-600' : 'text-red-500'}`}>
                                  {profitPos ? '+' : ''}<IndianRupee size={12}/>{Math.abs(profit).toLocaleString('en-IN')}
                                </span>
                              : <span className="text-xs text-gray-300 italic">—</span>
                            }
                          </td>

                          {/* Actions */}
                          <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                            <div className="flex items-center gap-1.5 justify-end flex-wrap">
                              {/* Timer buttons */}
                              {!['Completed','Cancelled'].includes(job.status) && (
                                <>
                                  {job.timer_status === 'idle' && (
                                    <button onClick={()=>timerMut.mutate({id:job.id,action:'start'})}
                                      className="flex items-center gap-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded-md px-2 py-1">
                                      <Play size={11}/> Start
                                    </button>
                                  )}
                                  {job.timer_status === 'running' && <>
                                    <button onClick={()=>timerMut.mutate({id:job.id,action:'pause'})}
                                      className="flex items-center gap-1 text-xs bg-yellow-500 hover:bg-yellow-600 text-white rounded-md px-2 py-1">
                                      <Pause size={11}/> Pause
                                    </button>
                                    <button onClick={()=>timerMut.mutate({id:job.id,action:'end'})}
                                      className="flex items-center gap-1 text-xs bg-gray-600 hover:bg-gray-700 text-white rounded-md px-2 py-1">
                                      <Square size={11}/> End
                                    </button>
                                  </>}
                                  {job.timer_status === 'paused' && <>
                                    <button onClick={()=>timerMut.mutate({id:job.id,action:'resume'})}
                                      className="flex items-center gap-1 text-xs bg-green-600 hover:bg-green-700 text-white rounded-md px-2 py-1">
                                      <RotateCcw size={11}/> Resume
                                    </button>
                                    <button onClick={()=>timerMut.mutate({id:job.id,action:'end'})}
                                      className="flex items-center gap-1 text-xs bg-gray-600 hover:bg-gray-700 text-white rounded-md px-2 py-1">
                                      <Square size={11}/> End
                                    </button>
                                  </>}
                                </>
                              )}
                              {!['Completed','Cancelled'].includes(job.status) && (
                                <button onClick={()=>openAssign(job)}
                                  className="text-xs flex items-center gap-1 text-green-700 hover:text-green-900 border border-green-200 bg-green-50 rounded-md px-2 py-1 font-medium">
                                  <ClipboardCheck size={11}/> Assign
                                </button>
                              )}
                              <button onClick={()=>openEdit(job)}
                                className="text-xs flex items-center gap-1 text-blue-600 hover:text-blue-800 border border-blue-200 rounded-md px-2 py-1">
                                <Pencil size={11}/> Edit
                              </button>
                              <button onClick={()=>setDeleteId(job.id)}
                                className="text-xs flex items-center gap-1 text-red-500 hover:text-red-700 border border-red-200 rounded-md px-2 py-1">
                                <Trash2 size={11}/> Delete
                              </button>
                            </div>
                          </td>
                        </tr>

                        {/* Expanded detail row */}
                        {isExpanded && (
                          <tr key={`${job.id}-detail`}>
                            <td colSpan={9} className="bg-blue-50 border-b border-blue-100 px-6 py-4">
                              <div className="grid grid-cols-3 gap-6">

                                {/* Cost breakdown */}
                                <div>
                                  <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                                    <IndianRupee size={12} className="text-red-500"/> Cost Breakdown
                                  </p>
                                  <div className="space-y-1.5 text-xs">
                                    <div className="flex justify-between">
                                      <span className="text-gray-500">Raw Materials</span>
                                      <span className="font-medium text-gray-800">₹{rawTotal.toLocaleString('en-IN')}</span>
                                    </div>
                                    <div className="flex justify-between">
                                      <span className="text-gray-500">Misc / Overhead</span>
                                      <span className="font-medium text-gray-800">₹{(job.misc_cost??0).toLocaleString('en-IN')}</span>
                                    </div>
                                    <div className="flex justify-between border-t border-blue-200 pt-1 mt-1">
                                      <span className="font-semibold text-gray-700">Total Cost</span>
                                      <span className="font-bold text-red-600">₹{totalCost.toLocaleString('en-IN')}</span>
                                    </div>
                                    {job.order_value != null && (
                                      <div className="flex justify-between border-t border-blue-200 pt-1">
                                        <span className="font-semibold text-gray-700">Order Value</span>
                                        <span className="font-bold text-gray-800">₹{job.order_value.toLocaleString('en-IN')}</span>
                                      </div>
                                    )}
                                    {profit != null && (
                                      <div className={`flex justify-between border-t-2 pt-1 ${profitPos?'border-green-300':'border-red-300'}`}>
                                        <span className="font-bold text-gray-700">Profit</span>
                                        <span className={`font-black ${profitPos?'text-green-600':'text-red-500'}`}>
                                          {profitPos?'+':''}₹{Math.abs(profit).toLocaleString('en-IN')}
                                        </span>
                                      </div>
                                    )}
                                  </div>
                                </div>

                                {/* Raw materials list */}
                                <div>
                                  <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                                    <Package size={12} className="text-orange-500"/> Raw Materials
                                  </p>
                                  {(job.raw_materials||[]).length === 0
                                    ? <p className="text-xs text-gray-400 italic">None specified</p>
                                    : <div className="space-y-1">
                                        {job.raw_materials.map((m,i) => (
                                          <div key={i} className="flex justify-between text-xs">
                                            <span className="text-gray-700">{m.name} <span className="text-gray-400">{m.quantity}{m.unit}</span></span>
                                            <span className="font-medium text-gray-800">₹{(m.quantity*m.unit_cost).toLocaleString('en-IN')}</span>
                                          </div>
                                        ))}
                                      </div>
                                  }
                                </div>

                                {/* Assigned resources */}
                                <div>
                                  <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                                    <Users size={12} className="text-blue-500"/> Assigned Resources
                                  </p>
                                  {job.assigned_machines.length > 0 && (
                                    <div className="mb-2">
                                      <p className="text-xs text-gray-400 mb-1 flex items-center gap-1"><Factory size={10}/>Machines</p>
                                      {job.assigned_machines.map(m => (
                                        <div key={m.id} className="text-xs text-gray-700 py-0.5">{m.name}</div>
                                      ))}
                                    </div>
                                  )}
                                  {job.assigned_employees.length > 0 && (
                                    <div>
                                      <p className="text-xs text-gray-400 mb-1 flex items-center gap-1"><Users size={10}/>People</p>
                                      {job.assigned_employees.map(e => (
                                        <div key={e.id} className="text-xs text-gray-700 py-0.5">{e.full_name} <span className="text-gray-400">{e.department??''}</span></div>
                                      ))}
                                    </div>
                                  )}
                                  {job.assigned_machines.length === 0 && job.assigned_employees.length === 0 && (
                                    <p className="text-xs text-amber-600 flex items-center gap-1"><AlertTriangle size={11}/>No resources assigned</p>
                                  )}
                                  {/* Conflicts */}
                                  {result && result.conflicts.length > 0 && (
                                    <div className="mt-2 border-t border-blue-200 pt-2">
                                      <p className="text-xs font-semibold text-orange-600 mb-1 flex items-center gap-1"><AlertTriangle size={11}/>Conflicts</p>
                                      {result.conflicts.map((c,i) => (
                                        <div key={i} className="text-xs text-red-600 py-0.5">{c.resource_name}: {c.reason}</div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </div>
                              {job.notes && (
                                <div className="mt-3 pt-3 border-t border-blue-200 text-xs text-gray-500">
                                  <span className="font-semibold text-gray-600">Notes: </span>{job.notes}
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </>
                    )
                  })}
                  {filtered.length === 0 && (
                    <tr><td colSpan={9} className="text-center text-gray-400 py-10 text-sm">No jobs match your filters.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Footer totals */}
            {filtered.length > 0 && (() => {
              const totalOV     = filtered.reduce((s,j) => s + (j.order_value??0), 0)
              const totalCosts  = filtered.reduce((s,j) => s + jobCost(j), 0)
              const totalProfit = totalOV - totalCosts
              return (
                <div className="border-t border-gray-100 bg-gray-50 px-4 py-2.5 flex flex-wrap items-center gap-6 text-xs text-gray-500">
                  <span><span className="font-semibold text-gray-700">{filtered.length}</span> jobs</span>
                  <span><span className="font-semibold text-gray-700">{filtered.filter(j=>j.status==='In Progress').length}</span> in progress</span>
                  <span><span className="font-semibold text-gray-700">{filtered.filter(j=>j.status==='Completed').length}</span> completed</span>
                  <span className="ml-auto flex items-center gap-1">
                    Total order value: <span className="font-bold text-gray-800 flex items-center gap-0.5 ml-1"><IndianRupee size={11}/>{totalOV.toLocaleString('en-IN')}</span>
                  </span>
                  <span className="flex items-center gap-1">
                    Total cost: <span className="font-bold text-red-600 flex items-center gap-0.5 ml-1"><IndianRupee size={11}/>{totalCosts.toLocaleString('en-IN')}</span>
                  </span>
                  <span className="flex items-center gap-1">
                    Est. profit: <span className={`font-bold flex items-center gap-0.5 ml-1 ${totalProfit>=0?'text-green-600':'text-red-500'}`}>
                      {totalProfit>=0?'+':''}<IndianRupee size={11}/>{Math.abs(totalProfit).toLocaleString('en-IN')}
                    </span>
                  </span>
                </div>
              )
            })()}
          </div>
        )
      })()}

      {/* ══ NEW JOB WIZARD ══════════════════════════════════ */}
      {wizardOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div>
                <h3 className="font-bold text-gray-800">New Job</h3>
                <div className="flex items-center gap-2 mt-1">
                  {['Job Details','Machines & People','Materials & Confirm'].map((label,i)=>(
                    <div key={i} className="flex items-center gap-1.5">
                      <span className={`w-5 h-5 rounded-full text-xs flex items-center justify-center font-bold ${wizardStep>i+1?'bg-green-500 text-white':wizardStep===i+1?'bg-blue-600 text-white':'bg-gray-200 text-gray-400'}`}>
                        {wizardStep>i+1?'✓':i+1}
                      </span>
                      <span className={`text-xs ${wizardStep===i+1?'text-blue-600 font-medium':'text-gray-400'}`}>{label}</span>
                      {i<2 && <ChevronRight size={12} className="text-gray-300"/>}
                    </div>
                  ))}
                </div>
              </div>
              <button onClick={closeWizard}><X size={18} className="text-gray-400 hover:text-gray-600"/></button>
            </div>

            {/* Step 1: Details */}
            {wizardStep===1 && (
              <div className="p-6 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Job Name *</label>
                    <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.name} onChange={e=>setDetails({...details,name:e.target.value})} placeholder="e.g. CNC Shaft Machining"/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Customer</label>
                    <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.customer} onChange={e=>setDetails({...details,customer:e.target.value})} placeholder="e.g. Tata Motors"/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Order Value (₹)</label>
                    <input type="number" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="Total contract / order value"
                      value={details.order_value} onChange={e=>setDetails({...details,order_value:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Misc / Overhead Cost (₹)</label>
                    <input type="number" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g. transport, consumables"
                      value={details.misc_cost} onChange={e=>setDetails({...details,misc_cost:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Start Date *</label>
                    <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.start_date} onChange={e=>setDetails({...details,start_date:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">End Date *</label>
                    <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.end_date} onChange={e=>setDetails({...details,end_date:e.target.value})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Hours / Day</label>
                    <input type="number" min="1" max="24" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.estimated_hours_per_day} onChange={e=>setDetails({...details,estimated_hours_per_day:Number(e.target.value)})}/>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Priority</label>
                    <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      value={details.priority} onChange={e=>setDetails({...details,priority:e.target.value})}>
                      {PRIORITIES.map(p=><option key={p}>{p}</option>)}
                    </select>
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Notes</label>
                    <textarea className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                      rows={2} value={details.notes} onChange={e=>setDetails({...details,notes:e.target.value})}/>
                  </div>
                </div>
                <div className="flex gap-2 pt-2">
                  <button onClick={()=>{ if(details.name&&details.start_date&&details.end_date) setWizardStep(2) }}
                    disabled={!details.name||!details.start_date||!details.end_date}
                    className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm py-2.5 rounded-xl font-medium">
                    Next — Skills & People <ChevronRight size={15}/>
                  </button>
                  <button onClick={closeWizard} className="px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-xl">Cancel</button>
                </div>
              </div>
            )}

            {/* Step 2: Machines → Skills → People */}
            {wizardStep===2 && (
              <div className="p-6 space-y-5">

                {/* 2a — Pick machines */}
                <div>
                  <h4 className="font-semibold text-gray-700 flex items-center gap-2 mb-1">
                    <Factory size={15} className="text-green-600"/> Step 1 — Select Machines
                  </h4>
                  <p className="text-xs text-gray-400 mb-3">Selecting a machine auto-adds its skill requirements below.</p>
                  {machines.filter(m=>m.status==='Operational').length === 0
                    ? <p className="text-xs text-gray-400 italic">No operational machines found.</p>
                    : <div className="grid grid-cols-2 gap-2">
                        {machines.filter(m=>m.status==='Operational').map(m=>{
                          const sel = selectedMachines.includes(m.id)
                          return (
                            <button key={m.id} type="button"
                              onClick={()=>{
                                if (sel) {
                                  // Deselect: remove machine and its auto-added skill reqs
                                  setSelectedMachines(p=>p.filter(x=>x!==m.id))
                                  setSkillReqs(prev => prev.filter(r => !(r as SkillReq & {fromMachine?:number}).fromMachine === m.id))
                                } else {
                                  // Select: add machine and merge its skill reqs
                                  setSelectedMachines(p=>[...p,m.id])
                                  const newReqs = (m.skill_requirements||[]).map(sr=>({
                                    ...sr, fromMachine: m.id
                                  }))
                                  setSkillReqs(prev=>{
                                    const merged = [...prev]
                                    newReqs.forEach(nr=>{
                                      const exists = merged.find(r=>r.skill_id===nr.skill_id && r.min_skill_level===nr.min_skill_level)
                                      if (exists) {
                                        exists.employees_required = Math.max(exists.employees_required, nr.employees_required)
                                      } else {
                                        merged.push(nr)
                                      }
                                    })
                                    return merged
                                  })
                                }
                                setWizardCheck(null)
                              }}
                              className={`flex flex-col items-start gap-1 p-3 rounded-xl border text-left transition-all ${
                                sel ? 'border-green-500 bg-green-50 ring-1 ring-green-300' : 'border-gray-200 hover:border-green-300 hover:bg-gray-50'
                              }`}>
                              <div className="flex items-center gap-2 w-full">
                                <Factory size={14} className={sel?'text-green-600':'text-gray-400'}/>
                                <span className="text-sm font-medium text-gray-800 truncate">{m.name}</span>
                                {sel && <Check size={13} className="text-green-600 ml-auto shrink-0"/>}
                              </div>
                              {m.location_bay && <span className="text-xs text-gray-400 pl-5">Bay: {m.location_bay}</span>}
                              {(m.skill_requirements||[]).length>0 && (
                                <div className="flex flex-wrap gap-1 pl-5">
                                  {m.skill_requirements.map((sr,i)=>(
                                    <span key={i} className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full">
                                      {getSkillName(sr.skill_id)}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </button>
                          )
                        })}
                      </div>
                  }
                </div>

                <hr className="border-gray-100"/>

                {/* 2b — Skill requirements (auto-populated + editable) */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h4 className="font-semibold text-gray-700 flex items-center gap-2">
                        <Users size={15} className="text-blue-500"/> Step 2 — Skill Requirements
                      </h4>
                      <p className="text-xs text-gray-400">
                        {selectedMachines.length>0
                          ? 'Pre-filled from selected machines. Add more if needed.'
                          : 'No machines selected — add skill requirements manually.'}
                      </p>
                    </div>
                    <button onClick={()=>setSkillReqs(r=>[...r,{skill_id:skills[0]?.id??0,min_skill_level:'Generic',employees_required:1}])}
                      className="flex items-center gap-1.5 text-xs text-blue-600 border border-blue-200 rounded-lg px-3 py-1.5">
                      <Plus size={12}/> Add Skill
                    </button>
                  </div>
                  {skillReqs.length===0
                    ? <div className="border-2 border-dashed border-gray-200 rounded-xl p-4 text-center text-xs text-gray-400">
                        Select a machine above or click "Add Skill" to define requirements.
                      </div>
                    : skillReqs.map((req,i)=>{
                        const fromMachine = (req as SkillReq & {fromMachine?:number}).fromMachine
                        const machineName = fromMachine ? machines.find(m=>m.id===fromMachine)?.name : null
                        return (
                          <div key={i} className={`flex gap-2 mb-2 items-center rounded-xl p-3 ${fromMachine?'bg-green-50 border border-green-200':'bg-gray-50'}`}>
                            {machineName && <span className="text-xs text-green-600 font-medium whitespace-nowrap shrink-0">⚙ {machineName}</span>}
                            <select className="flex-1 border border-gray-300 rounded-lg px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                              value={req.skill_id} onChange={e=>setSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,skill_id:Number(e.target.value)}:s))}>
                              {skills.map(s=><option key={s.id} value={s.id}>{s.name}{s.is_premium?' ⭐':''}</option>)}
                            </select>
                            <select className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                              value={req.min_skill_level} onChange={e=>setSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,min_skill_level:e.target.value}:s))}>
                              {LEVELS.map(l=><option key={l}>{l}</option>)}
                            </select>
                            <span className="text-xs text-gray-500">×</span>
                            <input type="number" min="1" className="w-14 border border-gray-300 rounded-lg px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                              value={req.employees_required} onChange={e=>setSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,employees_required:Number(e.target.value)}:s))}/>
                            <button onClick={()=>setSkillReqs(r=>r.filter((_,idx)=>idx!==i))} className="text-red-400 hover:text-red-600 shrink-0"><X size={14}/></button>
                          </div>
                        )
                      })
                  }
                </div>

                {/* 2c — Check + select people */}
                {skillReqs.length>0 && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-gray-700 flex items-center gap-2">
                        <UserCheck size={15} className="text-purple-500"/> Step 3 — Available People
                      </h4>
                      <button onClick={wizardCheckAvail}
                        className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 border border-blue-200 rounded-lg px-3 py-2">
                        {wizardChecking ? <><Loader2 className="animate-spin" size={12}/>Checking...</> : <><Search size={12}/>Check availability</>}
                      </button>
                    </div>

                    {!wizardCheck && !wizardChecking && (
                      <div className="border-2 border-dashed border-blue-100 rounded-xl p-4 text-center text-xs text-blue-400">
                        Click "Check availability" to see who's available for {details.start_date} → {details.end_date}
                      </div>
                    )}

                    {wizardCheck && !wizardChecking && (
                      <div className="border border-gray-200 rounded-xl overflow-hidden">
                        <div className={`${scoreColour(wizardCheck.feasibility_score).bg} px-4 py-2.5 flex items-center justify-between`}>
                          <span className={`text-sm font-semibold ${scoreColour(wizardCheck.feasibility_score).text}`}>
                            {wizardCheck.feasible ? '✓ All requirements can be met' : '⚠ Some requirements cannot be fully met'}
                          </span>
                          <span className={`text-lg font-black ${scoreColour(wizardCheck.feasibility_score).text}`}>{wizardCheck.feasibility_score}%</span>
                        </div>
                        <div className="p-4 space-y-4">
                          {skillReqs.map((req,i)=>{
                            const availIds:number[] = wizardCheck.available_employees[String(i)]??[]
                            const RANK: Record<string,number> = { Generic:1, Intermediate:2, Premium:3 }
                            const allQualified = employees.filter(e =>
                              (e as Employee & {skills?:{skill_id:number;skill_level:string}[]}).skills
                                ?.some((s:{skill_id:number;skill_level:string}) =>
                                  s.skill_id === req.skill_id && RANK[s.skill_level] >= RANK[req.min_skill_level]
                                )
                            )
                            const unavailIds = allQualified.filter(e => !availIds.includes(e.id)).map(e => e.id)
                            const sel = availIds.filter(id=>selectedEmps.includes(id)).length
                            const needed = req.employees_required
                            return (
                              <div key={i} className="border border-gray-100 rounded-xl overflow-hidden">
                                {/* Skill header */}
                                <div className="flex items-center justify-between bg-gray-50 px-3 py-2 border-b border-gray-100">
                                  <div className="flex items-center gap-2">
                                    <span className="text-xs font-semibold text-gray-700">{getSkillName(req.skill_id)}</span>
                                    <span className="px-2 py-0.5 bg-white rounded-full text-xs text-gray-500 border border-gray-200">{req.min_skill_level}</span>
                                  </div>
                                  <div className="flex items-center gap-3 text-xs font-semibold">
                                    <span className="text-gray-500">Need: <span className="text-gray-800">{needed}</span></span>
                                    <span className={sel>=needed?'text-green-600':'text-orange-600'}>Selected: {sel}</span>
                                  </div>
                                </div>
                                <div className="grid grid-cols-2 gap-0 divide-x divide-gray-100">
                                  {/* Available — selectable */}
                                  <div className="p-3">
                                    <p className="text-xs font-semibold text-green-700 mb-2 flex items-center gap-1">
                                      <Check size={11}/> Available ({availIds.length})
                                    </p>
                                    {availIds.length===0
                                      ? <p className="text-xs text-gray-400 italic">None free</p>
                                      : availIds.map(empId=>(
                                          <label key={empId} className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer text-xs transition-colors mb-1 ${selectedEmps.includes(empId)?'bg-blue-50 border border-blue-300':'hover:bg-gray-50 border border-transparent'}`}>
                                            <input type="checkbox" checked={selectedEmps.includes(empId)}
                                              onChange={()=>setSelectedEmps(p=>p.includes(empId)?p.filter(e=>e!==empId):[...p,empId])} className="rounded"/>
                                            <span className="w-2 h-2 rounded-full bg-green-400 shrink-0"/>
                                            <span className="text-gray-800">{employees.find(e=>e.id===empId)?.full_name??`#${empId}`}</span>
                                          </label>
                                        ))
                                    }
                                  </div>
                                  {/* Unavailable — info only */}
                                  <div className="p-3 bg-gray-50/50">
                                    <p className="text-xs font-semibold text-orange-600 mb-2 flex items-center gap-1">
                                      <X size={11}/> Busy / On Leave ({unavailIds.length})
                                    </p>
                                    {unavailIds.length===0
                                      ? <p className="text-xs text-gray-400 italic">All free</p>
                                      : unavailIds.map(empId=>(
                                          <div key={empId} className="flex items-center gap-2 px-2 py-1.5 text-xs mb-1">
                                            <span className="w-2 h-2 rounded-full bg-orange-300 shrink-0"/>
                                            <span className="text-gray-400 line-through">{employees.find(e=>e.id===empId)?.full_name??`#${empId}`}</span>
                                          </div>
                                        ))
                                    }
                                  </div>
                                </div>
                                {sel < needed && availIds.length > 0 && (
                                  <div className="bg-orange-50 border-t border-orange-100 px-3 py-1.5 text-xs text-orange-600">
                                    Select {needed - sel} more person{needed-sel!==1?'s':''} for this requirement
                                  </div>
                                )}
                                {availIds.length < needed && (
                                  <div className="bg-red-50 border-t border-red-100 px-3 py-1.5 text-xs text-red-600">
                                    Short by {needed - availIds.length} — not enough available staff
                                  </div>
                                )}
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                <div className="flex gap-2">
                  <button onClick={()=>setWizardStep(1)} className="flex items-center gap-1.5 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-xl"><ChevronLeft size={15}/>Back</button>
                  <button onClick={()=>setWizardStep(3)} className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm py-2.5 rounded-xl font-medium">
                    Next — Materials & Confirm <ChevronRight size={15}/>
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Raw Materials + Confirm */}
            {wizardStep===3 && (
              <div className="p-6 space-y-5">
                {/* Raw materials */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h4 className="font-semibold text-gray-700 flex items-center gap-1.5"><Package size={15} className="text-orange-500"/>Raw Materials</h4>
                      <p className="text-xs text-gray-400">Add materials needed for this job with quantities and costs.</p>
                    </div>
                    <button onClick={()=>setRawMats(m=>[...m,emptyMat()])}
                      disabled={rawMatLimitReached(rawMats.length)}
                      className={`flex items-center gap-1.5 text-xs border rounded-lg px-3 py-1.5 transition-colors ${
                        rawMatLimitReached(rawMats.length)
                          ? 'text-gray-400 border-gray-200 cursor-not-allowed'
                          : 'text-orange-600 border-orange-200 hover:bg-orange-50'
                      }`}>
                      <Plus size={12}/> Add Material
                    </button>
                  </div>
                  <RawMaterialLimitHint current={rawMats.length} planLimits={planLimits} />
                  {rawMats.length===0 && (
                    <div className="border-2 border-dashed border-gray-200 rounded-xl p-4 text-center text-sm text-gray-400">
                      No raw materials added yet.
                    </div>
                  )}
                  {rawMats.map((mat,i)=>(
                    <div key={i} className="grid grid-cols-12 gap-2 mb-2 items-center">
                      <input className="col-span-4 border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                        placeholder="Material name" value={mat.name} onChange={e=>setRawMats(m=>m.map((r,idx)=>idx===i?{...r,name:e.target.value}:r))}/>
                      <input type="number" min="0" step="0.1" className="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                        placeholder="Qty" value={mat.quantity} onChange={e=>setRawMats(m=>m.map((r,idx)=>idx===i?{...r,quantity:Number(e.target.value)}:r))}/>
                      <select className="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                        value={mat.unit} onChange={e=>setRawMats(m=>m.map((r,idx)=>idx===i?{...r,unit:e.target.value}:r))}>
                        {UNITS.map(u=><option key={u}>{u}</option>)}
                      </select>
                      <input type="number" min="0" className="col-span-3 border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                        placeholder="Unit cost ₹" value={mat.unit_cost} onChange={e=>setRawMats(m=>m.map((r,idx)=>idx===i?{...r,unit_cost:Number(e.target.value)}:r))}/>
                      <button onClick={()=>setRawMats(m=>m.filter((_,idx)=>idx!==i))} className="col-span-1 text-red-400 hover:text-red-600 flex justify-center"><X size={14}/></button>
                    </div>
                  ))}
                  {rawMats.length>0 && (
                    <div className="text-right text-sm font-semibold text-orange-700 mt-2">
                      Total Materials: ₹{matTotal(rawMats).toLocaleString('en-IN')}
                    </div>
                  )}
                </div>

                {/* Summary */}
                <div className="bg-gray-50 rounded-xl p-4 text-sm space-y-1.5">
                  <p className="font-semibold text-gray-700 mb-2">Confirm Details</p>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div><span className="text-gray-500">Job:</span> <span className="font-medium">{details.name}</span></div>
                    <div><span className="text-gray-500">Customer:</span> <span className="font-medium">{details.customer||'—'}</span></div>
                    <div><span className="text-gray-500">Dates:</span> <span className="font-medium">{details.start_date} → {details.end_date}</span></div>
                    <div><span className="text-gray-500">Priority:</span> <span className={`px-2 py-0.5 rounded-full font-medium ${priorityColour[details.priority]??''}`}>{details.priority}</span></div>
                  </div>
                  {selectedEmps.length>0 && <p className="text-xs text-green-700 mt-1">· {selectedEmps.length} employee(s) will be assigned</p>}
                  {selectedMachines.length>0 && <p className="text-xs text-green-700">· {selectedMachines.length} machine(s) will be assigned</p>}
                  {rawMats.length>0 && <p className="text-xs text-orange-700">· {rawMats.length} raw material(s) — ₹{matTotal(rawMats).toLocaleString('en-IN')}</p>}
                  {selectedEmps.length===0&&selectedMachines.length===0 && (
                    <p className="text-xs text-yellow-600 flex items-center gap-1 mt-1"><AlertTriangle size={11}/>No resources selected — can assign later.</p>
                  )}
                </div>

                <div className="flex gap-2">
                  <button onClick={()=>setWizardStep(2)} className="flex items-center gap-1.5 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-xl"><ChevronLeft size={15}/>Back</button>
                  <button onClick={submitWizard} disabled={createJob.isPending}
                    className="flex-1 flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-sm py-2.5 rounded-xl font-medium">
                    {createJob.isPending ? <><Loader2 className="animate-spin" size={15}/>Creating...</> : <><Check size={15}/>{selectedEmps.length>0||selectedMachines.length>0?'Create Job & Assign':'Create Job'}</>}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══ ASSIGN DRAWER ══════════════════════════════════ */}
      {assignJob && (
        <div className="fixed inset-0 bg-black/40 z-50 flex justify-end">
          <div className="bg-white w-full max-w-lg h-full shadow-2xl flex flex-col">

            {/* Header */}
            <div className="px-5 py-4 border-b border-gray-200 flex items-start justify-between shrink-0">
              <div>
                <p className="font-bold text-gray-800">Assign Resources</p>
                <p className="text-xs text-blue-600 font-medium mt-0.5">{assignJob.name}</p>
                <p className="text-xs text-gray-400">{assignJob.start_date} → {assignJob.end_date}</p>
              </div>
              <button onClick={()=>setAssignJob(null)}><X size={18} className="text-gray-400 hover:text-gray-600"/></button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-gray-200 shrink-0 bg-gray-50">
              {([
                ['machines', Factory,    'Machines'],
                ['people',   Users,      'Skilled People'],
                ['extras',   UserCheck,  'Extra People'],
              ] as const).map(([tab, Icon, label]) => (
                <button key={tab} onClick={()=>setAssignTab(tab as typeof assignTab)}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-semibold border-b-2 transition-colors ${
                    assignTab===tab ? 'border-blue-600 text-blue-600 bg-white' : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}>
                  <Icon size={13}/>{label}
                </button>
              ))}
            </div>

            {assignChecking && (
              <div className="flex-1 flex items-center justify-center">
                <div className="flex items-center gap-2 text-gray-400"><Loader2 className="animate-spin" size={18}/>Loading availability...</div>
              </div>
            )}

            {!assignChecking && !assignCheck && (
              <div className="flex-1 flex items-center justify-center">
                <p className="text-sm text-red-400">Failed to load availability data.</p>
              </div>
            )}

            {assignCheck && !assignChecking && (
              <div className="flex-1 overflow-y-auto">

                {/* Score banner */}
                <div className={`${scoreColour(assignCheck.feasibility_score).bg} px-5 py-2.5 flex items-center justify-between`}>
                  <span className={`text-xs font-semibold ${scoreColour(assignCheck.feasibility_score).text}`}>
                    {assignCheck.feasible ? '✓ All requirements can be met' : '⚠ Some requirements cannot be fully met'}
                  </span>
                  <span className={`text-base font-black ${scoreColour(assignCheck.feasibility_score).text}`}>{assignCheck.feasibility_score}%</span>
                </div>

                {/* ── TAB: MACHINES ── */}
                {assignTab === 'machines' && (
                  <div className="p-5 space-y-3">
                    <p className="text-xs text-gray-500">Select the machine(s) for this job. Skill requirements will be auto-derived from your selection.</p>
                    {assignCheck.machines.length === 0
                      ? <p className="text-sm text-gray-400 italic">No operational machines available.</p>
                      : assignCheck.machines.map(m => {
                          const sel = assignMachines.includes(m.id)
                          return (
                            <div key={m.id}
                              onClick={() => !m.available && !sel ? null : setAssignMachines(p => p.includes(m.id) ? p.filter(x=>x!==m.id) : [...p, m.id])}
                              className={`rounded-xl border p-3 cursor-pointer transition-all ${
                                sel ? 'border-green-500 bg-green-50 ring-1 ring-green-300'
                                : !m.available ? 'border-gray-100 bg-gray-50 opacity-60 cursor-not-allowed'
                                : 'border-gray-200 hover:border-green-300 hover:bg-gray-50'
                              }`}>
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <Factory size={14} className={sel ? 'text-green-600' : 'text-gray-400'}/>
                                  <span className="text-sm font-semibold text-gray-800">{m.name}</span>
                                  {sel && <Check size={13} className="text-green-600"/>}
                                </div>
                                {!m.available
                                  ? <span className="text-xs text-red-500 bg-red-50 px-2 py-0.5 rounded-full">{m.busy_reason}</span>
                                  : <span className="text-xs text-green-600 bg-green-100 px-2 py-0.5 rounded-full">Available</span>
                                }
                              </div>
                              <div className="flex items-center gap-3 mt-1 pl-5 text-xs text-gray-400">
                                {m.machine_type && <span>{m.machine_type}</span>}
                                {m.location_bay && <span>Bay: {m.location_bay}</span>}
                                {m.hourly_rate != null && <span>₹{m.hourly_rate}/hr</span>}
                              </div>
                              {m.skill_requirements.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-2 pl-5">
                                  <span className="text-xs text-gray-400">Needs:</span>
                                  {m.skill_requirements.map((sr,i) => (
                                    <span key={i} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">
                                      {sr.skill_name} · {sr.min_skill_level} × {sr.employees_required}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })
                    }
                    {assignMachines.length > 0 && (
                      <div className="pt-2 border-t border-gray-100">
                        <p className="text-xs text-gray-500 mb-1">Selected: <span className="font-semibold text-green-700">{assignMachines.length} machine(s)</span> — now go to <strong>Skilled People</strong> tab</p>
                      </div>
                    )}
                  </div>
                )}

                {/* ── TAB: SKILLED PEOPLE ── */}
                {assignTab === 'people' && (
                  <div className="p-5 space-y-4">
                    {/* Derive skill requirements from selected machines */}
                    {(() => {
                      const selectedMachineData = assignCheck.machines.filter(m => assignMachines.includes(m.id))
                      // Merge skill reqs from selected machines + job's own skill reqs
                      const jobSkillReqs = assignCheck.skill_requirements
                      const machineSkillMap: Record<string, {skill_id:number; skill_name:string; min_skill_level:string; employees_required:number; from_machine:string}[]> = {}
                      selectedMachineData.forEach(m => {
                        m.skill_requirements.forEach(sr => {
                          const key = `${sr.skill_id}-${sr.min_skill_level}`
                          if (!machineSkillMap[key]) machineSkillMap[key] = []
                          machineSkillMap[key].push({...sr, from_machine: m.name})
                        })
                      })

                      const allReqs = [
                        ...jobSkillReqs.map(r => ({
                          key: `job-${r.id}`,
                          skill_id: r.skill_id,
                          skill_name: r.skill_name,
                          min_skill_level: r.min_skill_level,
                          employees_required: r.employees_required,
                          available_ids: r.available_employee_ids,
                          source: 'Job requirement',
                        })),
                        ...Object.entries(machineSkillMap).map(([key, entries]) => {
                          const sr = entries[0]
                          const qualifiedEmps = assignCheck.employees.filter(e =>
                            e.available && e.skills.some(s =>
                              s.skill_id === sr.skill_id &&
                              ['Generic','Intermediate','Premium'].indexOf(s.skill_level) >=
                              ['Generic','Intermediate','Premium'].indexOf(sr.min_skill_level)
                            )
                          ).map(e => e.id)
                          return {
                            key: `machine-${key}`,
                            skill_id: sr.skill_id,
                            skill_name: sr.skill_name,
                            min_skill_level: sr.min_skill_level,
                            employees_required: entries.reduce((s,e) => s + e.employees_required, 0),
                            available_ids: qualifiedEmps,
                            source: entries.map(e=>e.from_machine).join(', '),
                          }
                        })
                      ]

                      if (allReqs.length === 0) return (
                        <div className="text-center py-8">
                          <p className="text-sm text-gray-400">No skill requirements defined.</p>
                          <p className="text-xs text-gray-400 mt-1">Select machines first, or add skill requirements to the job.</p>
                        </div>
                      )

                      return allReqs.map(req => {
                        const sel = req.available_ids.filter(id => assignEmps.includes(id)).length
                        return (
                          <div key={req.key} className="border border-gray-200 rounded-xl overflow-hidden">
                            <div className="bg-gray-50 px-3 py-2 flex items-center justify-between border-b border-gray-100">
                              <div>
                                <span className="text-xs font-semibold text-gray-800">{req.skill_name}</span>
                                <span className="ml-2 text-xs text-gray-400 bg-white border border-gray-200 px-1.5 py-0.5 rounded-full">{req.min_skill_level}</span>
                                <span className="ml-2 text-xs text-gray-400">from: {req.source}</span>
                              </div>
                              <span className={`text-xs font-bold ${sel >= req.employees_required ? 'text-green-600' : 'text-orange-600'}`}>
                                {sel} / {req.employees_required} selected
                              </span>
                            </div>
                            <div className="p-2 space-y-1">
                              {req.available_ids.length === 0
                                ? <p className="text-xs text-red-500 italic p-2">No qualified employees available for this date range.</p>
                                : req.available_ids.map(empId => {
                                    const emp = assignCheck.employees.find(e => e.id === empId)
                                    if (!emp) return null
                                    const empSkill = emp.skills.find(s => s.skill_id === req.skill_id)
                                    return (
                                      <label key={empId} className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer text-xs transition-colors ${
                                        assignEmps.includes(empId) ? 'border-blue-400 bg-blue-50' : 'border-transparent hover:bg-gray-50'
                                      }`}>
                                        <input type="checkbox" checked={assignEmps.includes(empId)}
                                          onChange={() => setAssignEmps(p => p.includes(empId) ? p.filter(e=>e!==empId) : [...p,empId])} className="rounded"/>
                                        <span className="w-2 h-2 rounded-full bg-green-400 shrink-0"/>
                                        <span className="font-medium text-gray-800">{emp.full_name}</span>
                                        {emp.department && <span className="text-gray-400">{emp.department}</span>}
                                        {empSkill && (
                                          <span className="ml-auto text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded-full">{empSkill.skill_level}</span>
                                        )}
                                        {emp.hourly_rate != null && <span className="text-gray-400">₹{emp.hourly_rate}/hr</span>}
                                      </label>
                                    )
                                  })
                              }
                            </div>
                            {sel < req.employees_required && req.available_ids.length > 0 && (
                              <div className="bg-orange-50 border-t border-orange-100 px-3 py-1.5 text-xs text-orange-600">
                                Need {req.employees_required - sel} more person{req.employees_required - sel !== 1 ? 's' : ''}
                              </div>
                            )}
                          </div>
                        )
                      })
                    })()}
                  </div>
                )}

                {/* ── TAB: EXTRA PEOPLE (helpers etc.) ── */}
                {assignTab === 'extras' && (
                  <div className="p-5 space-y-3">
                    <p className="text-xs text-gray-500">Add helpers or support staff who don't need specific skills for this job.</p>
                    {assignCheck.employees
                      .filter(e => e.available)
                      .map(emp => {
                        const alreadySkillSelected = assignEmps.includes(emp.id)
                        return (
                          <label key={emp.id} className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border cursor-pointer text-xs transition-colors ${
                            assignEmps.includes(emp.id) ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'
                          }`}>
                            <input type="checkbox" checked={assignEmps.includes(emp.id)}
                              onChange={() => setAssignEmps(p => p.includes(emp.id) ? p.filter(e=>e!==emp.id) : [...p,emp.id])} className="rounded"/>
                            <span className="font-medium text-gray-800">{emp.full_name}</span>
                            {emp.department && <span className="text-gray-400">{emp.department}</span>}
                            {alreadySkillSelected && <span className="ml-1 text-blue-500 text-xs">(already selected)</span>}
                            <div className="ml-auto flex gap-1 flex-wrap justify-end">
                              {emp.skills.slice(0,2).map(s => (
                                <span key={s.skill_id} className="bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full">{s.skill_name}</span>
                              ))}
                            </div>
                          </label>
                        )
                      })
                    }
                    {assignCheck.employees.filter(e => !e.available).length > 0 && (
                      <div className="mt-3 pt-3 border-t border-gray-100">
                        <p className="text-xs font-semibold text-gray-400 mb-2">Unavailable ({assignCheck.employees.filter(e=>!e.available).length})</p>
                        {assignCheck.employees.filter(e => !e.available).map(emp => (
                          <div key={emp.id} className="flex items-center gap-2 px-3 py-2 text-xs text-gray-300">
                            <span className="w-2 h-2 rounded-full bg-gray-200 shrink-0"/>
                            <span className="line-through">{emp.full_name}</span>
                            <span className="text-gray-300 ml-auto">{emp.busy_reason}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {assignError && (
                  <div className="mx-5 mb-3 flex items-center gap-2 text-red-600 bg-red-50 border border-red-200 rounded-xl px-3 py-2.5 text-xs">
                    <AlertCircle size={14}/>{assignError}
                  </div>
                )}
              </div>
            )}

            {/* Footer */}
            <div className="px-5 py-4 border-t border-gray-200 shrink-0">
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-3">
                <span className="flex items-center gap-1"><Factory size={11} className="text-green-600"/><strong className="text-green-700">{assignMachines.length}</strong> machines</span>
                <span>·</span>
                <span className="flex items-center gap-1"><Users size={11} className="text-blue-500"/><strong className="text-blue-700">{assignEmps.length}</strong> people</span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={()=>assignMut.mutate({job_id:assignJob.id,employee_ids:assignEmps,machine_ids:assignMachines})}
                  disabled={assignMut.isPending||(assignEmps.length===0&&assignMachines.length===0)}
                  className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm py-2.5 rounded-xl font-medium">
                  {assignMut.isPending
                    ? <><Loader2 className="animate-spin" size={15}/>Saving...</>
                    : <><ClipboardCheck size={15}/>Confirm Assignment</>
                  }
                </button>
                <button onClick={()=>setAssignJob(null)} className="px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-xl">Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit modal */}
      {editJob && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h3 className="font-bold text-gray-800">Edit Job</h3>
              <button onClick={()=>setEditJob(null)}><X size={18} className="text-gray-400 hover:text-gray-600"/></button>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-gray-600 mb-1">Job Name</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.name} onChange={e=>setEditForm({...editForm,name:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Customer</label>
                  <input className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.customer} onChange={e=>setEditForm({...editForm,customer:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Order Value (₹)</label>
                  <input type="number" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Total contract / order value"
                    value={editForm.order_value} onChange={e=>setEditForm({...editForm,order_value:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Misc / Overhead Cost (₹)</label>
                  <input type="number" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="e.g. transport, consumables"
                    value={editForm.misc_cost} onChange={e=>setEditForm({...editForm,misc_cost:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Start Date</label>
                  <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.start_date} onChange={e=>setEditForm({...editForm,start_date:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">End Date</label>
                  <input type="date" className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.end_date} onChange={e=>setEditForm({...editForm,end_date:e.target.value})}/>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Priority</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.priority} onChange={e=>setEditForm({...editForm,priority:e.target.value})}>
                    {PRIORITIES.map(p=><option key={p}>{p}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                  <select className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={editForm.status} onChange={e=>setEditForm({...editForm,status:e.target.value})}>
                    {STATUSES.map(s=><option key={s}>{s}</option>)}
                  </select>
                </div>
              </div>
              {/* Edit skill reqs */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-gray-600">Skill Requirements</label>
                  <button onClick={()=>setEditSkillReqs(r=>[...r,{skill_id:skills[0]?.id??0,min_skill_level:'Generic',employees_required:1}])}
                    className="text-xs text-blue-600 flex items-center gap-1"><Plus size={12}/>Add</button>
                </div>
                {editSkillReqs.map((req,i)=>(
                  <div key={i} className="flex gap-2 mb-2 items-center">
                    <select className="flex-1 border border-gray-300 rounded-lg px-2 py-1.5 text-xs"
                      value={req.skill_id} onChange={e=>setEditSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,skill_id:Number(e.target.value)}:s))}>
                      {skills.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                    <select className="border border-gray-300 rounded-lg px-2 py-1.5 text-xs"
                      value={req.min_skill_level} onChange={e=>setEditSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,min_skill_level:e.target.value}:s))}>
                      {LEVELS.map(l=><option key={l}>{l}</option>)}
                    </select>
                    <input type="number" min="1" className="w-16 border border-gray-300 rounded-lg px-2 py-1.5 text-xs"
                      value={req.employees_required} onChange={e=>setEditSkillReqs(r=>r.map((s,idx)=>idx===i?{...s,employees_required:Number(e.target.value)}:s))}/>
                    <button onClick={()=>setEditSkillReqs(r=>r.filter((_,idx)=>idx!==i))} className="text-red-400 hover:text-red-600"><X size={14}/></button>
                  </div>
                ))}
              </div>
              {/* Edit raw materials */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-gray-600 flex items-center gap-1"><Package size={12} className="text-orange-500"/>Raw Materials</label>
                  <div className="flex items-center gap-2">
                    <RawMaterialLimitHint current={editRawMats.length} planLimits={planLimits} />
                    <button
                      onClick={()=>setEditRawMats(m=>[...m,emptyMat()])}
                      disabled={rawMatLimitReached(editRawMats.length)}
                      className={`text-xs flex items-center gap-1 ${rawMatLimitReached(editRawMats.length) ? 'text-gray-300 cursor-not-allowed' : 'text-orange-600'}`}>
                      <Plus size={12}/>Add
                    </button>
                  </div>
                </div>
                {editRawMats.map((mat,i)=>(
                  <div key={i} className="grid grid-cols-12 gap-2 mb-2 items-center">
                    <input className="col-span-4 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" placeholder="Material" value={mat.name}
                      onChange={e=>setEditRawMats(m=>m.map((r,idx)=>idx===i?{...r,name:e.target.value}:r))}/>
                    <input type="number" className="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" placeholder="Qty" value={mat.quantity}
                      onChange={e=>setEditRawMats(m=>m.map((r,idx)=>idx===i?{...r,quantity:Number(e.target.value)}:r))}/>
                    <select className="col-span-2 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" value={mat.unit}
                      onChange={e=>setEditRawMats(m=>m.map((r,idx)=>idx===i?{...r,unit:e.target.value}:r))}>
                      {UNITS.map(u=><option key={u}>{u}</option>)}
                    </select>
                    <input type="number" className="col-span-3 border border-gray-300 rounded-lg px-2 py-1.5 text-xs" placeholder="Unit cost ₹" value={mat.unit_cost}
                      onChange={e=>setEditRawMats(m=>m.map((r,idx)=>idx===i?{...r,unit_cost:Number(e.target.value)}:r))}/>
                    <button onClick={()=>setEditRawMats(m=>m.filter((_,idx)=>idx!==i))} className="col-span-1 text-red-400 hover:text-red-600 flex justify-center"><X size={14}/></button>
                  </div>
                ))}
                {editRawMats.length>0 && <div className="text-right text-xs font-semibold text-orange-700">Total: ₹{matTotal(editRawMats).toLocaleString('en-IN')}</div>}
              </div>
            </div>
            <div className="flex gap-2 px-6 pb-6">
              <button onClick={submitEdit} disabled={!editForm.name||updateJob.isPending}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm py-2.5 rounded-lg font-medium">
                {updateJob.isPending?'Saving...':'Update Job'}
              </button>
              <button onClick={()=>setEditJob(null)} className="px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-lg">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirm */}
      {deleteId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 shadow-xl w-80 space-y-4">
            <h3 className="font-bold text-gray-800">Delete Job?</h3>
            <p className="text-sm text-gray-600">This permanently deletes the job and all its assignments.</p>
            <div className="flex gap-2">
              <button onClick={()=>deleteJobMut.mutate(deleteId)} className="flex-1 bg-red-600 hover:bg-red-700 text-white text-sm py-2 rounded-lg">{deleteJobMut.isPending?'Deleting...':'Yes, Delete'}</button>
              <button onClick={()=>setDeleteId(null)} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2 rounded-lg">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
