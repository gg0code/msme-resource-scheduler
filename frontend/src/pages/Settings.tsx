// frontend/src/pages/Settings.tsx
//
// PURPOSE
// Parent shell for the Settings area introduced in v6.3.3. Renders a
// vertical sub-nav and an <Outlet /> for the active section. Currently
// only "Team & Roles" exists; later iterations slot Briefings, Plan,
// Profile etc. into the same shell.
//
// CALLED BY
// - frontend/src/App.tsx routes the protected /settings/* tree here.
// - The default /settings landing redirects to /settings/team.
//
// CALLS INTO
// - react-router-dom NavLink + Outlet for the sub-nav + slot pattern.
// - useAuth().user for the role badge in the header (no role-gating here;
//   nav-item-level gating in Layout.tsx hides /settings entirely from
//   roles that can't enter, so by the time we render here the user is
//   authorised to see at least one section).

import { NavLink, Outlet } from 'react-router-dom'
import { MessageCircle, Users, Settings as SettingsIcon } from 'lucide-react'

const sections = [
  { to: 'team', label: 'Team & Roles', icon: Users, disabled: false, badge: undefined as string | undefined },
] as const

// v6.3.5 (Q3 decision): "WhatsApp Briefings" appears as a disabled stub
// since the briefings config UI ships in v6.3.6. Entry Mode / Business
// Details / Billing are NOT shown in v6.3.5 - they will appear once their
// pages exist (avoids the "click here, get nothing" anti-pattern).
const stubs = [
  { label: 'WhatsApp Briefings', icon: MessageCircle, badge: 'v6.3.6' },
] as const

export default function Settings() {
  return (
    <div className="flex h-full">
      {/* Sub-nav */}
      <aside className="w-56 shrink-0 border-r border-gray-200 bg-white">
        <div className="px-5 py-4 border-b border-gray-200">
          <div className="flex items-center gap-2 text-gray-700">
            <SettingsIcon size={18} />
            <h2 className="font-semibold">Settings</h2>
          </div>
        </div>
        <nav className="p-2 space-y-1">
          {sections.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-50'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}

          {/* Disabled stubs - hint at the v6.3.6+ roadmap without shipping
              broken links. Cursor goes to not-allowed; clicks are no-ops. */}
          {stubs.map(({ label, icon: Icon, badge }) => (
            <div
              key={label}
              aria-disabled="true"
              title={`Coming in ${badge}`}
              className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-sm text-gray-400 cursor-not-allowed select-none"
            >
              <span className="flex items-center gap-2">
                <Icon size={16} />
                {label}
              </span>
              <span className="text-[9px] font-bold uppercase tracking-wide text-gray-400 bg-gray-100 border border-gray-200 px-1.5 py-0.5 rounded">
                {badge}
              </span>
            </div>
          ))}
        </nav>
      </aside>

      {/* Active section */}
      <main className="flex-1 overflow-y-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
