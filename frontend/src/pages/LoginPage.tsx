/**
 * frontend/src/pages/LoginPage.tsx — v3.7.3
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * The sign-in page for ZetaOps Copilot. Users enter email and password. The page
 * also shows a role selector (Owner / Scheduler / Viewer) as a UI hint — the actual
 * role is determined by the backend from the user's DB record, not by this selector.
 * Fixed in v3.7.3 to use AuthContext.login() instead of direct apiClient calls,
 * ensuring tokenStore is populated and ProtectedRoute works correctly after sign-in.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Renders a role selector (visual only — does not affect authentication).
 * 2. Renders email + password fields.
 * 3. On submit: calls useAuth().login(email, password).
 * 4. On success: navigates to / (which redirects to /dashboard).
 * 5. On failure: shows error from the backend detail field.
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — registered as the /login route (public)
 *
 * INTERN NOTES
 * - The role selector is purely cosmetic — it shows role descriptions but does NOT
 *   send the role to the backend. The backend determines role from the users table.
 * - login() is from AuthContext — it calls /auth/login, gets the token, calls
 *   /auth/me, sets tokenStore, and schedules refresh. Never bypass it with direct
 *   apiClient calls.
 * - Design Principle 3: no tokens stored in state here — AuthContext owns that.
 */
import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const ROLE_OPTIONS = [
  { value: 'proprietor', label: 'Owner / Proprietor', desc: 'Full access — jobs, team, reports', icon: '🏭' },
  { value: 'scheduler',  label: 'Scheduler',           desc: 'Create & manage jobs and assignments', icon: '📋' },
  { value: 'viewer',     label: 'Viewer / Admin',       desc: 'Read-only view of all data', icon: '👁️' },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [selectedRole, setSelectedRole] = useState<string>('proprietor')
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState<string | null>(null)
  const [loading, setLoading]   = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(email, password)
      navigate('/')
    } catch (err: unknown) {
      const e = err as {response?:{data?:{detail?:string}};message?:string}
      setError(e?.response?.data?.detail ?? e?.message ?? 'Login failed. Check email / password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">

        {/* Logo */}
        <div className="text-center mb-8">
          <div className="flex justify-center mb-3">
            <img src="/logo.png" alt="ZeroZeta" className="h-8" />
          </div>
          <h1 className="text-xl font-bold text-gray-900">ZetaOps Copilot</h1>
          <p className="text-sm text-gray-500 mt-1">AI-powered production scheduling</p>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
          <h2 className="text-lg font-semibold text-gray-800 mb-1">Welcome back</h2>
          <p className="text-sm text-gray-400 mb-6">Sign in to your workspace</p>

          {/* Role selector */}
          <div className="mb-6">
            <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 block">
              Logging in as
            </label>
            <div className="grid grid-cols-3 gap-2">
              {ROLE_OPTIONS.map(r => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => setSelectedRole(r.value)}
                  className={`flex flex-col items-center gap-1 px-2 py-3 rounded-xl border-2 text-center transition-all text-xs ${
                    selectedRole === r.value
                      ? 'border-blue-500 bg-blue-50 text-blue-700'
                      : 'border-gray-200 bg-white text-gray-500 hover:border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  <span className="text-lg">{r.icon}</span>
                  <span className="font-semibold leading-tight">{r.label.split(' ')[0]}</span>
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-2 text-center">
              {ROLE_OPTIONS.find(r => r.value === selectedRole)?.desc}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                placeholder="you@company.com"
                className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {loading ? (
                <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />Signing in…</>
              ) : `Sign in as ${ROLE_OPTIONS.find(r => r.value === selectedRole)?.label.split(' ')[0]}`}
            </button>
          </form>

          <p className="text-xs text-center text-gray-400 mt-5">
            New workspace?{' '}
            <Link to="/register" className="text-blue-600 hover:underline font-medium">
              Register your company
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}