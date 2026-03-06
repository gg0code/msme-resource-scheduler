// src/pages/RegisterPage.tsx — V2.1
// Shows free plan limits including 5 raw materials per job

import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import apiClient from '../api/client'
import { Factory, CheckCircle2, XCircle } from 'lucide-react'

const FREE_LIMITS = [
  { label: '5 Jobs',                    ok: true },
  { label: '10 Employees',              ok: true },
  { label: '5 Machines',                ok: true },
  { label: '20 Skills',                 ok: true },
  { label: '5 Raw material lines / job',ok: true },
  { label: 'Auto-assignment engine',    ok: false },
  { label: 'PDF & Excel reports',       ok: false },
  { label: 'Email notifications',       ok: false },
]

export default function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    company_name: '',
    slug: '',
    email: '',
    password: '',
    confirmPassword: '',
  })
  const [error, setError]   = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      const res = await apiClient.post('/auth/register', {
        company_name: form.company_name,
        slug: form.slug.toLowerCase().replace(/\s+/g, '-'),
        email: form.email,
        password: form.password,
      })
      localStorage.setItem('access_token', res.data.access_token)
      navigate('/')
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">

        {/* Logo */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-blue-600 rounded-2xl shadow-lg mb-3">
            <Factory size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">MSME Scheduler</h1>
          <p className="text-sm text-gray-500 mt-1">Create your company workspace</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">

          {/* Free plan info */}
          <div className="md:col-span-2 bg-white rounded-2xl border border-gray-200 p-5 shadow-sm h-fit">
            <div className="flex items-center gap-2 mb-3">
              <span className="px-2 py-0.5 text-xs font-bold bg-blue-100 text-blue-700 rounded-full">FREE PLAN</span>
            </div>
            <p className="text-xs text-gray-500 mb-4">Start for free. No credit card needed.</p>
            <ul className="space-y-2">
              {FREE_LIMITS.map((item, i) => (
                <li key={i} className="flex items-center gap-2 text-xs">
                  {item.ok
                    ? <CheckCircle2 size={13} className="text-green-500 flex-shrink-0" />
                    : <XCircle size={13} className="text-gray-300 flex-shrink-0" />
                  }
                  <span className={item.ok ? 'text-gray-700' : 'text-gray-400'}>{item.label}</span>
                </li>
              ))}
            </ul>
            <div className="mt-4 pt-4 border-t border-gray-100">
              <p className="text-xs text-gray-400">Upgrade anytime to unlock unlimited resources and advanced features.</p>
            </div>
          </div>

          {/* Registration form */}
          <div className="md:col-span-3 bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
            <h2 className="text-lg font-semibold text-gray-800 mb-1">Create your workspace</h2>
            <p className="text-sm text-gray-400 mb-6">Your team will join under this workspace</p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Company Name</label>
                <input
                  type="text"
                  value={form.company_name}
                  onChange={set('company_name')}
                  required
                  placeholder="Sharma Fabrication Works"
                  className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Workspace ID
                  <span className="ml-1 text-gray-400 font-normal">(used in your URL)</span>
                </label>
                <input
                  type="text"
                  value={form.slug}
                  onChange={set('slug')}
                  required
                  placeholder="sharma-fab"
                  pattern="[a-z0-9\-]+"
                  title="Lowercase letters, numbers, hyphens only"
                  className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-gray-400 mt-1">Lowercase, no spaces — e.g. sharma-fab</p>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Admin Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={set('email')}
                  required
                  placeholder="owner@company.com"
                  className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Password</label>
                  <input
                    type="password"
                    value={form.password}
                    onChange={set('password')}
                    required
                    minLength={8}
                    placeholder="Min. 8 characters"
                    className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Confirm</label>
                  <input
                    type="password"
                    value={form.confirmPassword}
                    onChange={set('confirmPassword')}
                    required
                    placeholder="Repeat password"
                    className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-semibold rounded-lg transition-colors flex items-center justify-center gap-2 mt-2"
              >
                {loading ? (
                  <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />Creating workspace…</>
                ) : 'Create Free Workspace'}
              </button>
            </form>

            <p className="text-xs text-center text-gray-400 mt-5">
              Already have a workspace?{' '}
              <Link to="/login" className="text-blue-600 hover:underline font-medium">
                Sign in
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
