// src/pages/Dashboard.tsx
// -----------------------
// Main dashboard showing live clock, current date, week number, summary cards,
// jobs-by-status breakdown, and upcoming jobs this week.
// Clock updates every second via setInterval. Dashboard data refreshes every 30s.

import { useQuery } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import apiClient from '../api/client'
import { BriefcaseBusiness, Factory, Users, AlertCircle, Loader2, Clock, CalendarDays } from 'lucide-react'

interface DashboardData {
  total_active_jobs: number
  available_machines: number
  available_employees: number
  jobs_by_status: Record<string, number>
  upcoming_jobs_this_week: {
    id: number; name: string; start_date: string; end_date: string
    priority: string; status: string; tentative_profit: number | null
  }[]
}

function getWeekNumber(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNum = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  return Math.ceil((((date.valueOf() - yearStart.valueOf()) / 86400000) + 1) / 7)
}

const DAYS   = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']

const priorityColour: Record<string, string> = {
  Critical:'bg-red-100 text-red-700', High:'bg-orange-100 text-orange-700',
  Medium:'bg-yellow-100 text-yellow-700', Low:'bg-gray-100 text-gray-600',
}
const statusColour: Record<string, string> = {
  'Scheduled':'bg-green-100 text-green-700', 'Pending Assignment':'bg-blue-100 text-blue-700',
  'In Progress':'bg-purple-100 text-purple-700', 'Draft':'bg-gray-100 text-gray-600',
  'Completed':'bg-teal-100 text-teal-700', 'Cancelled':'bg-red-100 text-red-600',
}

export default function Dashboard() {
  const [now, setNow] = useState(new Date())
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t) }, [])

  const { data, isLoading, isError } = useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: () => apiClient.get('/dashboard/').then(r => r.data),
    refetchInterval: 30_000,
  })

  const timeStr = now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const dateStr = `${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`
  const weekNo  = getWeekNumber(now)

  if (isLoading) return <div className="flex items-center gap-2 text-gray-500 mt-10 justify-center"><Loader2 className="animate-spin" size={20}/>Loading dashboard...</div>
  if (isError)   return <div className="flex items-center gap-2 text-red-500 mt-10 justify-center"><AlertCircle size={20}/>Failed to load dashboard.</div>

  const cards = [
    { label:'Active Jobs',         value:data!.total_active_jobs,   icon:BriefcaseBusiness, colour:'text-blue-600',   bg:'bg-blue-50'   },
    { label:'Available Machines',  value:data!.available_machines,  icon:Factory,           colour:'text-green-600',  bg:'bg-green-50'  },
    { label:'Available Employees', value:data!.available_employees, icon:Users,             colour:'text-purple-600', bg:'bg-purple-50' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Dashboard</h2>
          <p className="text-sm text-gray-500 mt-0.5">Live overview of jobs, machines and employees.</p>
        </div>
        {/* Live date / time / week panel */}
        <div className="bg-white border border-gray-200 rounded-xl px-5 py-3 flex items-center gap-5 text-sm shadow-sm">
          <div className="flex items-center gap-2 text-gray-700">
            <Clock size={15} className="text-blue-500"/>
            <span className="font-mono font-bold text-lg tracking-widest">{timeStr}</span>
          </div>
          <div className="w-px h-8 bg-gray-200"/>
          <div className="flex items-center gap-2 text-gray-700">
            <CalendarDays size={15} className="text-blue-500"/>
            <div>
              <p className="font-semibold text-gray-800">{dateStr}</p>
              <p className="text-xs text-gray-400">Week {weekNo} &bull; {now.getFullYear()}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {cards.map(({ label, value, icon:Icon, colour, bg }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 p-5 flex items-center gap-4">
            <div className={`${bg} p-3 rounded-lg`}><Icon className={colour} size={22}/></div>
            <div>
              <p className="text-2xl font-bold text-gray-800">{value}</p>
              <p className="text-sm text-gray-500">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Jobs by status */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-700 mb-3">Jobs by Status</h3>
        <div className="flex flex-wrap gap-2">
          {Object.entries(data!.jobs_by_status).map(([status, count]) => (
            <span key={status} className={`px-3 py-1 rounded-full text-xs font-medium ${statusColour[status] ?? 'bg-gray-100 text-gray-600'}`}>
              {status}: {count}
            </span>
          ))}
        </div>
      </div>

      {/* Upcoming jobs */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-700 mb-3">Upcoming Jobs This Week</h3>
        {data!.upcoming_jobs_this_week.length === 0
          ? <p className="text-sm text-gray-400">No jobs starting in the next 7 days.</p>
          : <table className="w-full text-sm">
              <thead><tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="pb-2 font-medium">Job Name</th>
                <th className="pb-2 font-medium">Dates</th>
                <th className="pb-2 font-medium">Priority</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium text-right">Profit (₹)</th>
              </tr></thead>
              <tbody>
                {data!.upcoming_jobs_this_week.map(job => (
                  <tr key={job.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2 font-medium text-gray-800">{job.name}</td>
                    <td className="py-2 text-gray-500 text-xs">{job.start_date} → {job.end_date}</td>
                    <td className="py-2"><span className={`px-2 py-0.5 rounded-full text-xs font-medium ${priorityColour[job.priority]??''}`}>{job.priority}</span></td>
                    <td className="py-2"><span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColour[job.status]??''}`}>{job.status}</span></td>
                    <td className="py-2 text-right text-gray-700">{job.tentative_profit != null ? `₹${job.tentative_profit.toLocaleString('en-IN')}` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
        }
      </div>
    </div>
  )
}
