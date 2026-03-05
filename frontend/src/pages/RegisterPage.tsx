// src/pages/RegisterPage.tsx
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const FREE_PLAN_FEATURES = [
  { icon: '👷', label: 'Up to 10 employees' },
  { icon: '🏭', label: 'Up to 5 machines' },
  { icon: '📋', label: 'Up to 5 active jobs' },
  { icon: '🔧', label: 'Up to 20 skills' },
  { icon: '📊', label: 'Dashboard & reports' },
  { icon: '📥', label: 'CSV import / export' },
]

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [form, setForm] = useState({
    company_name: '',
    slug: '',
    email: '',
    password: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { name, value } = e.target
    setForm(prev => {
      const next = { ...prev, [name]: value }
      if (name === 'company_name') {
        next.slug = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
      }
      return next
    })
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(form)
      navigate('/dashboard', { replace: true })
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex" style={{ fontFamily: "'DM Sans', sans-serif", background: '#f8f9fb' }}>

      {/* ── Left panel — product pitch ─────────────────────────────────── */}
      <div
        className="hidden lg:flex flex-col justify-between w-5/12 p-12 text-white"
        style={{ background: 'linear-gradient(160deg, #1e3a5f 0%, #0f2440 60%, #091829 100%)' }}
      >
        {/* Logo */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-2xl">⚙️</span>
            <span className="font-bold text-lg tracking-tight">MSME Scheduler</span>
          </div>
          <p className="text-blue-300 text-xs">Resource & Job Management</p>
        </div>

        {/* Headline */}
        <div>
          <h2 className="text-3xl font-bold leading-snug mb-4">
            Run your shop floor<br />
            <span style={{ color: '#60a5fa' }}>without the chaos.</span>
          </h2>
          <p className="text-blue-200 text-sm leading-relaxed mb-10">
            Schedule jobs, assign workers and machines, track availability —
            all in one place built for small manufacturers.
          </p>

          {/* Free plan feature list */}
          <div className="mb-6">
            <p className="text-xs font-semibold uppercase tracking-widest text-blue-400 mb-4">
              Free plan includes
            </p>
            <div className="grid grid-cols-1 gap-3">
              {FREE_PLAN_FEATURES.map(f => (
                <div key={f.label} className="flex items-center gap-3">
                  <span className="text-base">{f.icon}</span>
                  <span className="text-sm text-blue-100">{f.label}</span>
                </div>
              ))}
            </div>
          </div>

          <div
            className="rounded-xl p-4 text-sm"
            style={{ background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)' }}
          >
            <p className="text-blue-200 leading-relaxed">
              <span className="text-white font-semibold">No credit card required.</span>{' '}
              Start free, upgrade when your team grows.
            </p>
          </div>
        </div>

        {/* Footer */}
        <p className="text-blue-400 text-xs">
          © {new Date().getFullYear()} MSME Scheduler. Built for Indian manufacturers.
        </p>
      </div>

      {/* ── Right panel — registration form ────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">

          {/* Mobile logo */}
          <div className="lg:hidden text-center mb-8">
            <span className="text-3xl">⚙️</span>
            <h1 className="text-xl font-bold text-gray-900 mt-1">MSME Scheduler</h1>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-bold text-gray-900">Create your account</h2>
            <p className="text-gray-500 text-sm mt-1">
              Set up your company workspace — free, no card needed.
            </p>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-5 flex items-start gap-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">
              <span className="mt-0.5">⚠️</span>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">

            {/* Company name */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Company name
              </label>
              <input
                type="text"
                name="company_name"
                required
                value={form.company_name}
                onChange={handleChange}
                placeholder="e.g. Acme Manufacturing Pvt Ltd"
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
              />
            </div>

            {/* Slug — auto generated, shown as read-only feel */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Workspace ID
                <span className="text-gray-400 font-normal ml-1 text-xs">— auto-generated from company name</span>
              </label>
              <div className="relative">
                <input
                  type="text"
                  name="slug"
                  required
                  value={form.slug}
                  onChange={handleChange}
                  pattern="[a-z0-9-]+"
                  placeholder="acme-manufacturing"
                  className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm font-mono text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                  style={{ background: '#f8f9fb' }}
                />
              </div>
              <p className="text-xs text-gray-400 mt-1">
                Lowercase letters, numbers and hyphens only. Must be unique.
              </p>
            </div>

            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Your email
              </label>
              <input
                type="email"
                name="email"
                required
                value={form.email}
                onChange={handleChange}
                placeholder="owner@yourcompany.com"
                className="w-full border border-gray-300 rounded-xl px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
              />
              <p className="text-xs text-gray-400 mt-1">
                This will be your login and the Proprietor account (full access).
              </p>
            </div>

            {/* Password */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  name="password"
                  required
                  minLength={8}
                  value={form.password}
                  onChange={handleChange}
                  placeholder="Min. 8 characters"
                  className="w-full border border-gray-300 rounded-xl px-4 py-2.5 pr-10 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(p => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs"
                  tabIndex={-1}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full text-white font-semibold py-3 px-4 rounded-xl text-sm transition-all"
              style={{
                background: loading ? '#93c5fd' : 'linear-gradient(135deg, #2563eb, #1d4ed8)',
                cursor: loading ? 'not-allowed' : 'pointer',
              }}
            >
              {loading ? 'Creating your workspace…' : 'Start for free →'}
            </button>

          </form>

          {/* Divider */}
          <div className="flex items-center gap-3 my-6">
            <div className="flex-1 h-px bg-gray-200" />
            <span className="text-xs text-gray-400">already have an account?</span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>

          <Link
            to="/login"
            className="block w-full text-center border border-gray-300 text-gray-700 font-medium py-2.5 px-4 rounded-xl text-sm hover:bg-gray-50 transition"
          >
            Sign in instead
          </Link>

          {/* Trust note */}
          <p className="text-center text-xs text-gray-400 mt-6 leading-relaxed">
            By registering you agree to our Terms of Service.<br />
            Your data is isolated — no other company can see it.
          </p>

        </div>
      </div>
    </div>
  )
}
