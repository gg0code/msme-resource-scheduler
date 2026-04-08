// src/pages/Checker.tsx
// ---------------------
// Availability Checker page. Select a job, run the 5-step availability check
// from the backend engine, and see a full feasibility report:
//   - Feasibility score (0-100%)
//   - Pass / Fail per skill requirement with available employee list
//   - Conflict details with blocked dates and reasons
// No data is changed - this is a read-only diagnostic tool.

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'
import { ASSIGNMENTS, EMPLOYEES, JOBS, SKILLS } from '../api/api_endpoints'
import {
  CheckCircle2, XCircle, AlertTriangle, Loader2, ChevronRight,
  Users, CalendarDays, Gauge, Search
} from 'lucide-react'

// --- Types ---
interface Job {
  id: number; name: string; customer: string | null
  start_date: string; end_date: string; status: string; priority: string
  skill_requirements: { id: number; skill_id: number; min_skill_level: string; employees_required: number }[]
}
interface Skill    { id: number; name: string }
interface Employee { id: number; full_name: string; department: string | null; skills?: {skill_id:number; skill_level:string}[] }

interface Conflict {
  resource_type: string; resource_id: number; resource_name: string
  dates: string[]; reason: string
}
interface CheckResult {
  job_id: number; feasible: boolean; feasibility_score: number
  conflicts: Conflict[]
  available_employees: Record<string, number[]>
}

// --- Helpers ---
const scoreColour = (score: number) => {
  if (score === 100) return { bar: 'bg-green-500',  text: 'text-green-700',  bg: 'bg-green-50',  label: 'Feasible' }
  if (score >= 60)  return { bar: 'bg-orange-400', text: 'text-orange-700', bg: 'bg-orange-50', label: 'Partial' }
  return             { bar: 'bg-red-500',   text: 'text-red-700',   bg: 'bg-red-50',   label: 'Not Feasible' }
}

const priorityColour: Record<string,string> = {
  Critical:'bg-red-100 text-red-700', High:'bg-orange-100 text-orange-700',
  Medium:'bg-yellow-100 text-yellow-700', Low:'bg-gray-100 text-gray-600',
}
const statusColour: Record<string,string> = {
  'Scheduled':'bg-green-100 text-green-700','Pending Assignment':'bg-blue-100 text-blue-700',
  'In Progress':'bg-purple-100 text-purple-700','Draft':'bg-gray-100 text-gray-600',
  'Completed':'bg-teal-100 text-teal-700','Cancelled':'bg-red-100 text-red-600',
}

export default function Checker() {
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [jobSearch, setJobSearch]         = useState('')
  const [result, setResult]               = useState<CheckResult | null>(null)
  const [checking, setChecking]           = useState(false)
  const [error, setError]                 = useState('')

  const { data: jobs = [] } = useQuery<Job[]>({
    queryKey:['jobs'], queryFn:() => apiClient.get(JOBS.list).then(r => r.data),
  })
  const { data: skills = [] } = useQuery<Skill[]>({
    queryKey:['skills'], queryFn:() => apiClient.get(SKILLS.list).then(r => r.data),
  })
  const { data: employees = [] } = useQuery<Employee[]>({
    queryKey:['employees'], queryFn:() => apiClient.get(EMPLOYEES.list).then(r => r.data),
  })

  const getSkillName = (id: number) => skills.find(s => s.id === id)?.name ?? `Skill#${id}`
  const getEmpName   = (id: number) => employees.find(e => e.id === id)?.full_name ?? `Emp#${id}`

  const selectedJob = jobs.find(j => j.id === selectedJobId)

  const filteredJobs = jobs.filter(j => {
    const q = jobSearch.toLowerCase()
    return !q || j.name.toLowerCase().includes(q) || (j.customer ?? '').toLowerCase().includes(q)
  })

  async function runCheck() {
    if (!selectedJobId) return
    setChecking(true)
    setResult(null)
    setError('')
    try {
      const res = await apiClient.get(ASSIGNMENTS.check(selectedJobId))
      setResult(res.data)
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Failed to run availability check.')
    } finally {
      setChecking(false)
    }
  }

  const colours = result ? scoreColour(result.feasibility_score) : null

  return (
    <div className="space-y-6">

      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-gray-800">Availability Checker</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Select a job and run a full feasibility check - no data is changed.
        </p>
      </div>

      {/* Job selector panel */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
        <h3 className="font-semibold text-gray-700 text-sm">Step 1 - Select a Job</h3>

        {/* Search */}
        <div className="relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
          <input className="w-full pl-8 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Search jobs by name or customer..."
            value={jobSearch} onChange={e => setJobSearch(e.target.value)}/>
        </div>

        {/* Job list */}
        <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
          {filteredJobs.map(job => (
            <button key={job.id} onClick={() => { setSelectedJobId(job.id); setResult(null); setError('') }}
              className={`w-full text-left px-4 py-3 rounded-xl border transition-all ${
                selectedJobId === job.id
                  ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200'
                  : 'border-gray-200 bg-white hover:bg-gray-50'
              }`}>
              <div className="flex items-center justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-gray-800 text-sm truncate">{job.name}</p>
                  {job.customer && <p className="text-xs text-gray-500 mt-0.5">{job.customer}</p>}
                  <div className="flex items-center gap-1.5 mt-1 text-xs text-gray-400">
                    <CalendarDays size={11}/>
                    <span>{job.start_date} → {job.end_date}</span>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${priorityColour[job.priority]??''}`}>{job.priority}</span>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColour[job.status]??''}`}>{job.status}</span>
                </div>
                {selectedJobId === job.id && <ChevronRight size={16} className="text-blue-500 shrink-0"/>}
              </div>
            </button>
          ))}
          {filteredJobs.length === 0 && <p className="text-center text-gray-400 py-4 text-sm">No jobs found.</p>}
        </div>

        {/* Run check button */}
        <button
          onClick={runCheck}
          disabled={!selectedJobId || checking}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white font-medium text-sm py-3 rounded-xl transition-colors">
          {checking
            ? <><Loader2 className="animate-spin" size={16}/>Running check...</>
            : <><Gauge size={16}/>Run Availability Check{selectedJob ? ` - ${selectedJob.name}` : ''}</>
          }
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm">
          <XCircle size={16}/>{error}
        </div>
      )}

      {/* Results */}
      {result && colours && (
        <div className="space-y-4">

          {/* Score card */}
          <div className={`${colours.bg} border-2 ${result.feasible ? 'border-green-300' : result.feasibility_score >= 60 ? 'border-orange-300' : 'border-red-300'} rounded-xl p-5`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                {result.feasible
                  ? <CheckCircle2 className="text-green-600" size={22}/>
                  : <AlertTriangle className="text-yellow-600" size={22}/>
                }
                <span className={`font-bold text-lg ${colours.text}`}>{colours.label}</span>
              </div>
              <span className={`text-3xl font-black ${colours.text}`}>{result.feasibility_score}%</span>
            </div>
            {/* Score bar */}
            <div className="w-full bg-white/60 rounded-full h-3">
              <div className={`${colours.bar} h-3 rounded-full transition-all duration-500`}
                style={{ width: `${result.feasibility_score}%` }}/>
            </div>
            <p className={`text-xs mt-2 ${colours.text} opacity-80`}>
              {result.feasible
                ? 'All skill requirements can be met - ready for assignment.'
                : `${result.conflicts.length} conflict${result.conflicts.length !== 1 ? 's' : ''} found - resolve before assigning.`
              }
            </p>
          </div>

          {/* Skill requirements breakdown */}
          {selectedJob && selectedJob.skill_requirements.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-xl p-5">
              <h3 className="font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <Users size={16} className="text-blue-500"/>
                Skill Requirements
              </h3>
              <div className="space-y-4">
                {selectedJob.skill_requirements.map(req => {
                  const availEmpIds: number[] = result.available_employees[String(req.id)] ?? []
                  // All employees who have this skill at this level (qualified)
                  const RANK: Record<string,number> = { Generic:1, Intermediate:2, Premium:3 }
                  const allQualified = employees.filter(e =>
                    (e as Employee & {skills?:{skill_id:number;skill_level:string}[]}).skills
                      ?.some((s: {skill_id:number;skill_level:string}) =>
                        s.skill_id === req.skill_id &&
                        RANK[s.skill_level] >= RANK[req.min_skill_level]
                      )
                  )
                  const unavailIds = allQualified.filter(e => !availEmpIds.includes(e.id)).map(e => e.id)
                  const met = availEmpIds.length >= req.employees_required
                  const needed = req.employees_required

                  return (
                    <div key={req.id} className="border border-gray-200 rounded-xl overflow-hidden">
                      {/* Header row */}
                      <div className={`flex items-center justify-between px-4 py-3 ${met ? 'bg-green-50' : 'bg-red-50'}`}>
                        <div className="flex items-center gap-2">
                          {met
                            ? <CheckCircle2 size={15} className="text-green-600 shrink-0"/>
                            : <XCircle size={15} className="text-red-500 shrink-0"/>
                          }
                          <span className="font-semibold text-sm text-gray-800">{getSkillName(req.skill_id)}</span>
                          <span className="px-2 py-0.5 bg-white rounded-full text-xs text-gray-500 border border-gray-200 font-medium">
                            Min: {req.min_skill_level}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 text-xs font-semibold">
                          <span className="text-gray-500">Need: <span className="text-gray-800">{needed}</span></span>
                          <span className={met ? 'text-green-700' : 'text-red-600'}>
                            Available: {availEmpIds.length}
                          </span>
                          {unavailIds.length > 0 && (
                            <span className="text-orange-500">Busy/Leave: {unavailIds.length}</span>
                          )}
                        </div>
                      </div>

                      <div className="p-4 grid grid-cols-2 gap-x-6 gap-y-1">
                        {/* Available column */}
                        <div>
                          <p className="text-xs font-semibold text-green-700 mb-2 flex items-center gap-1">
                            <CheckCircle2 size={12}/> Available ({availEmpIds.length})
                          </p>
                          {availEmpIds.length === 0
                            ? <p className="text-xs text-gray-400 italic">None free in this period</p>
                            : availEmpIds.map(empId => (
                                <div key={empId} className="flex items-center gap-2 py-1 border-b border-gray-50 last:border-0">
                                  <span className="w-2 h-2 rounded-full bg-green-400 shrink-0"/>
                                  <span className="text-sm text-gray-800">{getEmpName(empId)}</span>
                                </div>
                              ))
                          }
                        </div>

                        {/* Unavailable column */}
                        <div>
                          <p className="text-xs font-semibold text-orange-600 mb-2 flex items-center gap-1">
                            <XCircle size={12}/> Qualified but Unavailable ({unavailIds.length})
                          </p>
                          {unavailIds.length === 0
                            ? <p className="text-xs text-gray-400 italic">All qualified staff are free</p>
                            : unavailIds.map(empId => (
                                <div key={empId} className="flex items-center gap-2 py-1 border-b border-gray-50 last:border-0">
                                  <span className="w-2 h-2 rounded-full bg-orange-300 shrink-0"/>
                                  <span className="text-sm text-gray-400 line-through">{getEmpName(empId)}</span>
                                  <span className="text-xs text-orange-500 ml-auto">busy</span>
                                </div>
                              ))
                          }
                        </div>
                      </div>

                      {/* Bottom status bar */}
                      {!met && (
                        <div className="bg-red-50 border-t border-red-100 px-4 py-2 text-xs text-red-600 flex items-center gap-1.5">
                          <XCircle size={12}/>
                          Need {needed} but only {availEmpIds.length} available -
                          short by {needed - availEmpIds.length} person{needed - availEmpIds.length !== 1 ? 's' : ''}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Conflicts */}
          {result.conflicts.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-xl p-5">
              <h3 className="font-semibold text-gray-700 mb-3 flex items-center gap-2">
                <XCircle size={16} className="text-red-500"/>
                Conflicts ({result.conflicts.length})
              </h3>
              <div className="space-y-3">
                {result.conflicts.map((c, i) => (
                  <div key={i} className="border border-red-200 bg-red-50 rounded-xl p-4">
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div>
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium mr-2 ${c.resource_type === 'machine' ? 'bg-green-100 text-green-700' : 'bg-purple-100 text-purple-700'}`}>
                          {c.resource_type}
                        </span>
                        <span className="font-semibold text-sm text-gray-800">{c.resource_name}</span>
                      </div>
                    </div>
                    <p className="text-xs text-red-700 mb-2">{c.reason}</p>
                    {c.dates.length > 0 && c.dates.length <= 10 && (
                      <div className="flex flex-wrap gap-1">
                        {c.dates.map(d => (
                          <span key={d} className="bg-red-100 text-red-600 text-xs px-2 py-0.5 rounded-full">{d}</span>
                        ))}
                      </div>
                    )}
                    {c.dates.length > 10 && (
                      <p className="text-xs text-red-500">{c.dates.length} blocked dates ({c.dates[0]} → {c.dates[c.dates.length-1]})</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* All clear */}
          {result.feasible && result.conflicts.length === 0 && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-5 flex items-center gap-3">
              <CheckCircle2 size={20} className="text-green-600 shrink-0"/>
              <div>
                <p className="font-semibold text-green-800">Ready for Assignment</p>
                <p className="text-sm text-green-700 mt-0.5">All requirements can be met. Head to the Jobs page to assign resources.</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
