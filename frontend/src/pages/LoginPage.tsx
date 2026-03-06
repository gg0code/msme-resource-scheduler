// src/pages/LoginPage.tsx — V2.1
// Shows role context selector (Scheduler / Proprietor / Admin) as a visual indicator.
// The actual role is tied to the user account — the selector simply guides which
// credential the user intends to log in with. The JWT role returned by the server
// is always authoritative; a banner displays the actual logged-in role after auth.

import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import apiClient from '../api/client'
import { Factory } from 'lucide-react'

const ROLE_OPTIONS = [
  { value: 'proprietor', label: 'Owner / Proprietor', desc: 'Full access — jobs, team, reports', icon: '🏭' },
  { value: 'scheduler',  label: 'Scheduler',           desc: 'Create & manage jobs and assignments', icon: '📋' },
  { value: 'viewer',     label: 'Viewer / Admin',       desc: 'Read-only view of all data', icon: '👁️' },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const [selectedRole, setSelectedRole] = useState<string>('proprietor')
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState<string | null>(null)
  const [loading, setLoading]   = useState(false)
  const [actualRole, setActualRole] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await apiClient.post('/auth/login', { email, password })
      const token = res.data.access_token
      localStorage.setItem('access_token', token)
      // Decode role from JWT payload
      try {
        const payload = JSON.parse(atob(token.split('.')[1]))
        setActualRole(payload.role ?? null)
        if (payload.role && payload.role !== selectedRole) {
          // Brief mismatch warning then redirect
          setTimeout(() => navigate('/'), 1200)
        } else {
          navigate('/')
        }
      } catch {
        navigate('/')
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Login failed. Check email / password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">

        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-blue-600 rounded-2xl shadow-lg mb-3">
            <Factory size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">MSME Scheduler</h1>
          <p className="text-sm text-gray-500 mt-1">Production resource management</p>
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

          {/* Actual role mismatch notice */}
          {actualRole && actualRole !== selectedRole && (
            <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
              ⚠️ Your account has <strong>{actualRole}</strong> role. Redirecting…
            </div>
          )}

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
