/**
 * frontend/src/components/Layout.tsx — v4.0.9
 * Branch: v4-dev | v5-whatsapp (both — WhatsApp nav item is feature-flagged)
 *
 * FILE PURPOSE
 * The main application shell for all authenticated pages. Layout renders the
 * sidebar navigation, the top header bar, and the <Outlet> where page content
 * renders. It is the component that every protected page lives inside. Introduced
 * in v4.0.9 with full ZetaOps Copilot branding, industry-aware nav labels, CSS
 * theme variables, and feature-flagged navigation items (Gantt, WhatsApp). Sits
 * at the top of the authenticated route tree — registered in App.tsx as the
 * element for the protected route group that wraps all pages.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Reads user and logout from useAuth() — displays user email, role badge, log out button.
 * 2. Reads feature flags from useFeatureFlags() — conditionally shows Gantt and WhatsApp nav items.
 * 3. Reads industry config and labels from useIndustry() / useLabels() — nav item labels
 *    change per industry (e.g. "Jobs" → "Orders" for field service).
 * 4. Defines ROLE_BADGE map for colour-coded role pills in the sidebar footer.
 * 5. Defines coreNavItems array using industry-aware labels and fixed icons.
 * 6. Renders a fixed sidebar (w-56) with brand logo, nav links, and user info.
 * 7. Sidebar colours come from CSS variables (--brand-sidebar-bg, --brand-active-bg etc.)
 *    set by IndustryContext for per-industry theming.
 * 8. Renders feature-flagged Gantt nav item (flags.gantt).
 * 9. Renders feature-flagged WhatsApp nav item (flags.whatsapp) — v5 only but
 *    guarded by flag so it is safely present in v4-dev without appearing.
 * 10. Renders right-side column: fixed header bar (TourButton + SchedulerToolbar)
 *     and scrollable main content area (<Outlet />).
 * 11. Renders GettingStarted checklist overlay (onboarding).
 * 12. Renders AI Copilot floating button + AICopilot panel (flags.ai_copilot).
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : Layout (default export)
 * Type         : React component
 * Purpose      : Application shell. Provides sidebar, header, and main content area.
 *                All authenticated pages render inside its <Outlet>.
 * Parameters   : none (receives no props — gets page content via React Router Outlet)
 * Returns      : JSX.Element — full-screen flex layout
 * Calls        : useAuth, useFeatureFlags, useIndustry, useLabels, logout,
 *                NavLink, Outlet from react-router-dom
 * DB/API       : none directly — child components handle their own data
 * Side effects : handleLogout() calls logout() which clears auth state and
 *                navigates to /login
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — registered as the element for the main protected route group
 *   <Route element={<FeatureFlagProvider><IndustryProvider><SchedulerProvider>
 *   <OnboardingProvider><Layout /></OnboardingProvider>...</Route>
 *
 * IMPORTS EXPLAINED
 * - useState from 'react': Controls aiOpen state for the AI Copilot panel toggle.
 * - Outlet, NavLink, useNavigate from 'react-router-dom': Renders child pages,
 *   creates sidebar links, navigates to /login after logout.
 * - LayoutDashboard, Users, Settings, BriefcaseBusiness, Factory, LogOut, BarChart2,
 *   Bot, MessageCircle from 'lucide-react': Sidebar nav icons and action icons.
 * - useAuth from '../auth/AuthContext': User info and logout function.
 * - useIndustry, useLabels from '../context/IndustryContext': Industry-specific
 *   nav labels and CSS theme variable values.
 * - SchedulerToolbar from '../scheduler/SchedulerToolbar': Run scheduler button
 *   in the header bar.
 * - GettingStarted from './onboarding/GettingStarted': Onboarding checklist overlay.
 * - TourButton from './onboarding/TourButton': Button to start the onboarding tour.
 * - AICopilot from './AICopilot': The sliding AI chat panel.
 * - useFeatureFlags from '../context/FeatureFlags': Feature flag values for nav
 *   item visibility and AI Copilot button.
 *
 * INTERN NOTES
 * - CSS theme variables (--brand-sidebar-bg etc.) are set by IndustryContext on
 *   the :root element. Changing industry in settings changes the sidebar colour
 *   without any Layout code changes — Layout just reads the variables.
 * - The WhatsApp nav item (flags.whatsapp) is present in this file on both branches.
 *   On v4-dev, flags.whatsapp is always false so the item never renders. On v5-whatsapp,
 *   it can be enabled. Never remove the flag check.
 * - The AI Copilot button uses inline style (not Tailwind) for brand colour when not
 *   open. This is because --brand-primary is a CSS variable that Tailwind cannot resolve
 *   at build time — it must be applied via style prop.
 * - Design Principle 8: Gantt, WhatsApp, and AI Copilot nav items are all gated by
 *   feature flags — never render them unconditionally.
 * - If the sidebar shows wrong labels (e.g. "Jobs" instead of "Orders"): check that
 *   IndustryProvider is mounted above Layout in App.tsx and that the tenant's
 *   industry_type is set correctly in the database.
 * - If the AI Copilot button does not appear: check flags.ai_copilot in the browser
 *   — fetch /api/features/ in devtools to see the flag values.
 */

import { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Users, Settings,
  BriefcaseBusiness, Factory,
  LogOut, BarChart2, Bot, MessageCircle,
} from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { useIndustry, useLabels } from '../context/IndustryContext'
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

  // ── Nav items — labels from IndustryContext ────────────────────────────────
  const coreNavItems = [
    { to: '/dashboard',   label: 'Dashboard',       icon: LayoutDashboard  },
    { to: '/jobs',        label: labels.jobs,        icon: BriefcaseBusiness },
    { to: '/employees',   label: labels.employees,   icon: Users             },
    { to: '/machines',    label: labels.machines,    icon: Factory           },
    { to: '/skills',      label: labels.skills,      icon: Settings          },
  ]

  return (
    <div className="flex h-screen bg-gray-50 font-sans">

      {/* Sidebar — colours from CSS theme variables */}
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

          {/* Core nav — always visible */}
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

          {/* Gantt — feature flagged */}
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

          {/* WhatsApp Copilot — v5.0, feature flagged */}
          {flags.whatsapp && (
            <NavLink
              to="/whatsapp"
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                 ${isActive ? 'text-white' : 'text-gray-300 hover:text-white hover:bg-white/10'}`
              }
              style={({ isActive }) =>
                isActive ? { backgroundColor: 'var(--brand-active-bg)' } : undefined
              }
            >
              <MessageCircle size={16} />
              WhatsApp
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

      {/* AI Copilot floating button — feature flagged */}
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
