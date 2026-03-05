import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Wrench, Users, Settings, BriefcaseBusiness, Factory, CalendarOff, ShieldCheck, LogOut } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'

const navItems = [
  { to:'/dashboard',    label:'Dashboard',      icon:LayoutDashboard  },
  { to:'/jobs',         label:'Jobs',           icon:BriefcaseBusiness },
  { to:'/employees',    label:'Employees',      icon:Users             },
  { to:'/machines',     label:'Machines',       icon:Factory           },
  { to:'/availability', label:'Availability',   icon:CalendarOff       },
  { to:'/checker',      label:'Avail. Checker', icon:ShieldCheck       },
  { to:'/skills',       label:'Skills',         icon:Settings          },
]

const ROLE_BADGE: Record<string, { label: string; color: string }> = {
  proprietor: { label: 'Proprietor', color: 'bg-blue-600' },
  scheduler:  { label: 'Scheduler',  color: 'bg-green-600' },
  viewer:     { label: 'Viewer',     color: 'bg-gray-500' },
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  const badge = ROLE_BADGE[user?.role ?? '']

  return (
    <div className="flex h-screen bg-gray-50 font-sans">
      {/* ── Sidebar ── */}
      <aside className="w-56 bg-gray-900 text-white flex flex-col shrink-0">
        <div className="px-5 py-5 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <Wrench className="text-blue-400" size={20}/>
            <span className="font-bold text-sm leading-tight">
              MSME<br/>
              <span className="text-blue-400 font-semibold">Resource Scheduler</span>
            </span>
          </div>
        </div>

        <nav className="flex-1 py-4 px-2 space-y-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                ${isActive ? 'bg-blue-600 text-white font-medium' : 'text-gray-300 hover:bg-gray-700 hover:text-white'}`
              }>
              <Icon size={17}/>{label}
            </NavLink>
          ))}
        </nav>

        <div className="px-5 py-3 border-t border-gray-700 text-xs text-gray-500">
          v1.1.0
        </div>
      </aside>

      {/* ── Main area ── */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shrink-0">
          <h1 className="text-gray-700 font-semibold text-sm">MSME Resource Scheduler</h1>

          {/* User info + logout */}
          <div className="flex items-center gap-3">
            {user && (
              <>
                {/* Role badge */}
                {badge && (
                  <span className={`text-xs text-white font-medium px-2 py-0.5 rounded-full ${badge.color}`}>
                    {badge.label}
                  </span>
                )}

                {/* Email */}
                <span className="text-xs text-gray-500 hidden sm:block">
                  {user.email}
                </span>

                {/* Divider */}
                <div className="w-px h-4 bg-gray-200"/>

                {/* Logout button */}
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-600 transition-colors"
                  title="Sign out"
                >
                  <LogOut size={14}/>
                  <span className="hidden sm:block">Sign out</span>
                </button>
              </>
            )}
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6">
          <Outlet/>
        </main>
      </div>
    </div>
  )
}
