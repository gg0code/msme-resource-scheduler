// src/components/Layout.tsx — V3.7
// Removed: Availability, Avail. Checker, Scheduling Jobs nav items
// Added: AICopilot floating panel
// V3.7: gantt and ai_copilot nav items + button are gated by feature flags

import { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Wrench, Users, Settings,
  BriefcaseBusiness, Factory,
  LogOut, BarChart2, Bot,MessageCircle, 
} from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import SchedulerToolbar from '../scheduler/SchedulerToolbar'
import GettingStarted from './onboarding/GettingStarted'
import TourButton from './onboarding/TourButton'
import AICopilot from './AICopilot'
import { useFeatureFlags } from '../context/FeatureFlags'

const ROLE_BADGE: Record<string, { label: string; color: string }> = {
  proprietor: { label: 'Proprietor', color: 'bg-blue-600' },
  scheduler:  { label: 'Scheduler',  color: 'bg-green-600' },
  viewer:     { label: 'Viewer',     color: 'bg-gray-500' },
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [aiOpen, setAiOpen] = useState(false)
  const flags = useFeatureFlags()

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  const badge = ROLE_BADGE[user?.role ?? '']

  // ── Nav items — always visible ──────────────────────────────────────────
  const coreNavItems = [
    { to: '/dashboard', label: 'Dashboard',  icon: LayoutDashboard   },
    { to: '/jobs',      label: 'Jobs',        icon: BriefcaseBusiness },
    { to: '/employees', label: 'Employees',   icon: Users             },
    { to: '/machines',  label: 'Machines',    icon: Factory           },
    { to: '/skills',    label: 'Skills',      icon: Settings          },
    { to: '/whatsapp',  label: 'WhatsApp',    icon: MessageCircle     },

  ]

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
          {/* Core nav — always visible */}
          {coreNavItems.map(({ to, label, icon: Icon }) => (
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

          {/* Gantt — V3.7 gated */}
          {flags.gantt && (
            <NavLink
              to="/gantt"
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                 ${isActive
                   ? 'bg-blue-600 text-white'
                   : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                 }`
              }
            >
              <BarChart2 size={16} />
              Timeline
            </NavLink>
          )}
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
          <TourButton />
          <SchedulerToolbar />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      {/* Getting Started checklist */}
      <GettingStarted />

      {/* AI Copilot floating button — V3.7 gated */}
      {flags.ai_copilot && (
        <>
          <button
            onClick={() => setAiOpen(o => !o)}
            className={`fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-3 rounded-full shadow-lg text-white text-sm font-medium transition-all
              ${aiOpen ? 'bg-gray-700 hover:bg-gray-800' : 'bg-blue-600 hover:bg-blue-700'}`}
          >
            <Bot size={18} />
            {aiOpen ? 'Close AI' : 'AI Copilot'}
          </button>

          <AICopilot isOpen={aiOpen} onClose={() => setAiOpen(false)} />
        </>
      )}
    </div>
  )
}
