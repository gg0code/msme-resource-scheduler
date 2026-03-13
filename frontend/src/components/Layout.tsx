// src/components/Layout.tsx — V3.2
// Added: AICopilot side panel + "Ask AI Copilot" toggle button in header

import { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Wrench, Users, Settings,
  BriefcaseBusiness, Factory, CalendarOff,
  ShieldCheck, LogOut, BarChart2, ClipboardList,
  Sparkles,
} from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import SchedulerToolbar from '../scheduler/SchedulerToolbar'
import AICopilot from './AICopilot'

const navItems = [
  { to: '/dashboard',    label: 'Dashboard',         icon: LayoutDashboard  },
  { to: '/jobs',         label: 'Jobs',               icon: BriefcaseBusiness },
  { to: '/sched-jobs',   label: 'Scheduling Jobs',    icon: ClipboardList    },
  { to: '/gantt',        label: 'Gantt Chart',        icon: BarChart2        },
  { to: '/employees',    label: 'Employees',          icon: Users            },
  { to: '/machines',     label: 'Machines',           icon: Factory          },
  { to: '/availability', label: 'Availability',       icon: CalendarOff      },
  { to: '/checker',      label: 'Avail. Checker',     icon: ShieldCheck      },
  { to: '/skills',       label: 'Skills',             icon: Settings         },
]

const ROLE_BADGE: Record<string, { label: string; color: string }> = {
  proprietor: { label: 'Proprietor', color: 'bg-blue-600' },
  scheduler:  { label: 'Scheduler',  color: 'bg-green-600' },
  viewer:     { label: 'Viewer',     color: 'bg-gray-500' },
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [aiOpen, setAiOpen] = useState(false)

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  const badge = ROLE_BADGE[user?.role ?? '']

  return (
    <div className="flex h-screen bg-gray-50 font-sans">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 text-white flex flex-col shrink-0">
        <div className="px-5 py-5 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <Wrench className="text-blue-400" size={20} />
            <span className="font-bold text-sm leading-tight">
              MSME<br />
              <span className="text-blue-400 font-semibold">Resource Scheduler</span>
            </span>
          </div>
        </div>

        <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                 ${isActive
                   ? 'bg-blue-600 text-white'
                   : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                 }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-4 py-4 border-t border-gray-700">
          <div className="text-xs text-gray-400 truncate mb-1">{user?.email}</div>
          {badge && (
            <span className={`text-xs px-2 py-0.5 rounded-full text-white ${badge.color}`}>
              {badge.label}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="mt-3 flex items-center gap-2 text-xs text-gray-400 hover:text-white transition-colors"
          >
            <LogOut size={14} /> Log out
          </button>
        </div>
      </aside>

      {/* Right side */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Top header bar */}
        <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-end px-6 gap-4 shrink-0">
          <SchedulerToolbar />

          {/* AI Copilot toggle button */}
          <button
            onClick={() => setAiOpen(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-violet-600 text-white text-xs font-semibold hover:opacity-90 transition-opacity shadow-sm"
          >
            <Sparkles size={13} />
            Ask AI Copilot
          </button>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      {/* AI Copilot side panel */}
      <AICopilot isOpen={aiOpen} onClose={() => setAiOpen(false)} />
    </div>
  )
}
