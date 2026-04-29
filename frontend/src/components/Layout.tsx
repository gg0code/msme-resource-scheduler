// src/components/Layout.tsx - v4.0.9
// Industry-aware nav labels, ZetaOps Copilot branding, CSS theme variables
// WhatsApp nav gated behind feature flag

import { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Users, Settings,
  BriefcaseBusiness, Factory,
  LogOut, BarChart2, Bot,
} from 'lucide-react'
import { useAuth, isTopTier } from '../auth/useAuth'
import { useIndustry, useLabels } from '../context/useIndustry'
import SchedulerToolbar from '../scheduler/SchedulerToolbar'
import GettingStarted from './onboarding/GettingStarted'
import TourButton from './onboarding/TourButton'
import AICopilot from './AICopilot'
import { useFeatureFlags } from '../context/useFeatureFlags'

// v6.3.3: extended to cover the full SRS Section 6.28.6 role taxonomy.
// Top-tier roles share a warm/amber/purple palette so they read as a
// group; mid-tier (scheduler/manager) share green; viewer stays grey.
const ROLE_BADGE: Record<string, { label: string; color: string }> = {
  owner:           { label: 'Owner',           color: 'bg-amber-600'  },
  proprietor:      { label: 'Proprietor',      color: 'bg-amber-600'  },
  factory_manager: { label: 'Factory Manager', color: 'bg-blue-600'   },
  co_owner:        { label: 'Co-owner',        color: 'bg-purple-600' },
  scheduler:       { label: 'Scheduler',       color: 'bg-green-600'  },
  manager:         { label: 'Manager',         color: 'bg-green-600'  },
  viewer:          { label: 'Viewer',          color: 'bg-gray-500'   },
}

export default function Layout() {
  const { user, logout }  = useAuth()
  const navigate          = useNavigate()
  const [aiOpen, setAiOpen] = useState(false)
  const flags             = useFeatureFlags()
  const { config }        = useIndustry()
  const labels            = useLabels()

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  const badge = ROLE_BADGE[user?.role ?? '']

  // -- Nav items - labels from IndustryContext --------------------------------
  const coreNavItems = [
    { to: '/dashboard',   label: 'Dashboard',       icon: LayoutDashboard  },
    { to: '/jobs',        label: labels.jobs,        icon: BriefcaseBusiness },
    { to: '/employees',   label: labels.employees,   icon: Users             },
    { to: '/machines',    label: labels.machines,    icon: Factory           },
    { to: '/skills',      label: labels.skills,      icon: Settings          },
  ]

  return (
    <div className="flex h-screen bg-gray-50 font-sans">

      {/* Sidebar - colours from CSS theme variables */}
      <aside
        className="w-56 flex flex-col shrink-0 text-white"
        style={{ backgroundColor: 'var(--brand-sidebar-bg)' }}
      >
        {/* Branding */}
        <div
          className="px-5 py-4"
          style={{ borderBottom: '1px solid var(--brand-sidebar-border)' }}
        >
          <img src="/logo.png" alt="ZeroZeta" className="h-5 brightness-0 invert" />
          <div className="mt-2">
            <div className="text-white text-xs font-bold leading-tight">ZetaOps Copilot</div>
            <div
              className="text-[10px] mt-0.5"
              style={{ color: 'var(--brand-accent)' }}
            >
              {config.branding.productName}
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">

          {/* Core nav - always visible */}
          {coreNavItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                 ${isActive ? 'text-white' : 'text-gray-300 hover:text-white hover:bg-white/10'}`
              }
              style={({ isActive }) =>
                isActive ? { backgroundColor: 'var(--brand-active-bg)' } : undefined
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}

          {/* Gantt - feature flagged */}
          {flags.gantt && (
            <NavLink
              to="/gantt"
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                 ${isActive ? 'text-white' : 'text-gray-300 hover:text-white hover:bg-white/10'}`
              }
              style={({ isActive }) =>
                isActive ? { backgroundColor: 'var(--brand-active-bg)' } : undefined
              }
            >
              <BarChart2 size={16} />
              Timeline
            </NavLink>
          )}

          {/* v6.3.5: WhatsApp nav item removed. Phone-link is now part of
              the Team & Roles invite flow under Settings. The flags.whatsapp
              feature gate still controls WhatsApp surfaces elsewhere
              (briefings dispatcher, AI Copilot WhatsApp integrations) and
              is therefore intentionally NOT touched here. */}

          {/* Settings (Team & Roles) - v6.3.3, top-tier only */}
          {isTopTier(user?.role ?? null) && (
            <NavLink
              to="/settings/team"
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                 ${isActive ? 'text-white' : 'text-gray-300 hover:text-white hover:bg-white/10'}`
              }
              style={({ isActive }) =>
                isActive ? { backgroundColor: 'var(--brand-active-bg)' } : undefined
              }
            >
              <Settings size={16} />
              Settings
            </NavLink>
          )}
        </nav>

        {/* User info */}
        <div
          className="px-4 py-4"
          style={{ borderTop: '1px solid var(--brand-sidebar-border)' }}
        >
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

      {/* AI Copilot floating button - feature flagged */}
      {flags.ai_copilot && (
        <>
          <button
            onClick={() => setAiOpen(o => !o)}
            className={`fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-3 rounded-full shadow-lg text-white text-sm font-medium transition-all
              ${aiOpen ? 'bg-gray-700 hover:bg-gray-800' : ''}`}
            style={!aiOpen ? { backgroundColor: 'var(--brand-primary)' } : undefined}
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
