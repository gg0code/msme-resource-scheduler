/**
 * frontend/src/pages/RegisterPage.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * New tenant registration page. Collects company name, slug, industry type, email,
 * and password. Calls AuthContext.register() which creates a Tenant + User, seeds
 * demo data, and logs the user in. The industry selector on this page determines
 * the tenant's industry_type — which drives all labels, colours, and AI terminology
 * for the entire account lifetime. Registered as a public route in App.tsx.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Renders industry selector (5 options with icons and taglines).
 * 2. Renders company name, slug, email, password fields.
 * 3. Auto-generates slug from company name (lowercase, hyphens).
 * 4. On submit: calls useAuth().register(payload) which calls POST /auth/register.
 * 5. On success: navigates to /dashboard — demo data is already seeded by backend.
 * 6. On failure: shows error from backend detail field.
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — registered as /register route (public)
 *
 * INTERN NOTES
 * - The industry_type selected here is stored on the Tenant model and drives the
 *   entire app experience via IndustryContext. It cannot be changed after registration
 *   without a backend admin operation.
 * - Slug validation: lowercase letters, numbers, hyphens only. Auto-generated from
 *   company name but user can edit. Must be globally unique (enforced by backend).
 * - Design Principle 3: register() is in AuthContext — it sets tokenStore after
 *   successful registration so the user is immediately logged in.
 */
import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import apiClient from '../api/client'
import { CheckCircle2, XCircle, ChevronRight, ChevronLeft } from 'lucide-react'

// ── Industry options ──────────────────────────────────────────────────────────

const INDUSTRIES = [
  {
    id:          'printing',
    label:       'Printing & Packaging',
    product:     'PrintFlow Scheduler',
    icon:        '🖨️',
    description: 'Corrugated boxes, labels, cartons, flexo printing',
    color:       'blue',
  },
  {
    id:          'manufacturing',
    label:       'Manufacturing',
    product:     'ShopFloor Resource Planner',
    icon:        '⚙️',
    description: 'CNC machining, assembly, production orders',
    color:       'slate',
  },
  {
    id:          'fabrication',
    label:       'Metal Fabrication',
    product:     'Fabrication Capacity Planner',
    icon:        '🔧',
    description: 'Steel fabrication, welding, sheet metal work',
    color:       'orange',
  },
  {
    id:          'chemical',
    label:       'Chemical / Process Industry',
    product:     'Process Batch Scheduler',
    icon:        '🧪',
    description: 'Batch processing, reactor scheduling, formulations',
    color:       'green',
  },
  {
    id:          'field_service',
    label:       'Field Service / Maintenance',
    product:     'Field Service Planner',
    icon:        '🚗',
    description: 'On-site service jobs, maintenance scheduling',
    color:       'purple',
  },
]

// Industry-specific terminology for free plan limits panel
const INDUSTRY_TERMS: Record<string, {
  jobs: string; employees: string; machines: string; materials: string
}> = {
  printing:      { jobs: 'Jobs',              employees: 'Operators',   machines: 'Machines',     materials: 'Raw material lines / job' },
  manufacturing: { jobs: 'Production Orders', employees: 'Operators',   machines: 'Work Centers', materials: 'BOM lines / order'        },
  fabrication:   { jobs: 'Work Orders',       employees: 'Fabricators', machines: 'Work Centers', materials: 'Material lines / order'   },
  chemical:      { jobs: 'Batch Orders',      employees: 'Operators',   machines: 'Reactors',     materials: 'Batch input lines'        },
  field_service: { jobs: 'Service Jobs',      employees: 'Technicians', machines: 'Vehicles/Tools',materials: 'Parts lines / job'       },
}

function getFreeLimits(industryId: string) {
  const t = INDUSTRY_TERMS[industryId] ?? INDUSTRY_TERMS.printing
  return [
    { label: `5 ${t.jobs}`,          ok: true  },
    { label: `10 ${t.employees}`,    ok: true  },
    { label: `5 ${t.machines}`,      ok: true  },
    { label: '20 Skills',            ok: true  },
    { label: `5 ${t.materials}`,     ok: true  },
    { label: 'Auto-assignment engine', ok: false },
    { label: 'PDF & Excel reports',    ok: false },
    { label: 'Email notifications',    ok: false },
  ]
}

const BORDER_COLOR: Record<string, string> = {
  blue:   'border-blue-500 bg-blue-50',
  slate:  'border-slate-500 bg-slate-50',
  orange: 'border-orange-500 bg-orange-50',
  green:  'border-green-500 bg-green-50',
  purple: 'border-purple-500 bg-purple-50',
}

const BADGE_COLOR: Record<string, string> = {
  blue:   'bg-blue-100 text-blue-700',
  slate:  'bg-slate-100 text-slate-700',
  orange: 'bg-orange-100 text-orange-700',
  green:  'bg-green-100 text-green-700',
  purple: 'bg-purple-100 text-purple-700',
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function RegisterPage() {
  const navigate = useNavigate()

  // Step 1: industry picker | Step 2: workspace form
  const [step, setStep] = useState<1 | 2>(1)

  const [selectedIndustry, setSelectedIndustry] = useState<string>('printing')
  const [form, setForm] = useState({
    company_name:    '',
    slug:            '',
    email:           '',
    password:        '',
    confirmPassword: '',
  })
  const [error, setError]     = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const selectedConfig = INDUSTRIES.find(i => i.id === selectedIndustry) ?? INDUSTRIES[0]

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
        company_name:  form.company_name,
        slug:          form.slug.toLowerCase().replace(/\s+/g, '-'),
        email:         form.email,
        password:      form.password,
        industry_type: selectedIndustry,
      })
      localStorage.setItem('access_token', res.data.access_token)
      navigate('/')
    } catch (err: unknown) {
      const detail = (err as {response?:{data?:{detail?:unknown}}})?.response?.data?.detail
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
          <div className="flex justify-center mb-3">
            <img src="/logo.png" alt="ZeroZeta" className="h-8" />
          </div>
          <h1 className="text-xl font-bold text-gray-900">ZetaOps Copilot</h1>
          <p className="text-sm text-gray-500 mt-1">
            {step === 1 ? 'Choose your industry to get started' : `Setting up ${selectedConfig.product}`}
          </p>
        </div>

        {/* Step indicator */}
        <div className="flex items-center justify-center gap-3 mb-6">
          {[1, 2].map(s => (
            <div key={s} className="flex items-center gap-2">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold
                ${step === s ? 'bg-blue-600 text-white' : step > s ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'}`}>
                {step > s ? '✓' : s}
              </div>
              <span className={`text-xs font-medium ${step === s ? 'text-blue-600' : 'text-gray-400'}`}>
                {s === 1 ? 'Choose Industry' : 'Create Workspace'}
              </span>
              {s < 2 && <ChevronRight size={14} className="text-gray-300" />}
            </div>
          ))}
        </div>

        {/* ── Step 1: Industry picker ── */}
        {step === 1 && (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-base font-semibold text-gray-800 mb-1">What best describes your business?</h2>
            <p className="text-xs text-gray-400 mb-5">Your app will be configured with the right terminology and demo data.</p>

            <div className="space-y-2.5">
              {INDUSTRIES.map(ind => (
                <button
                  key={ind.id}
                  type="button"
                  onClick={() => setSelectedIndustry(ind.id)}
                  className={`w-full flex items-center gap-4 px-4 py-3.5 rounded-xl border-2 text-left transition-all
                    ${selectedIndustry === ind.id
                      ? BORDER_COLOR[ind.color]
                      : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
                    }`}
                >
                  <span className="text-2xl shrink-0">{ind.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-gray-800">{ind.label}</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${BADGE_COLOR[ind.color]}`}>
                        {ind.product}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">{ind.description}</p>
                  </div>
                  <div className={`w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center
                    ${selectedIndustry === ind.id ? 'border-blue-500 bg-blue-500' : 'border-gray-300'}`}>
                    {selectedIndustry === ind.id && (
                      <div className="w-1.5 h-1.5 rounded-full bg-white" />
                    )}
                  </div>
                </button>
              ))}
            </div>

            <button
              onClick={() => setStep(2)}
              className="w-full mt-5 py-2.5 px-4 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              Continue <ChevronRight size={16} />
            </button>

            <p className="text-xs text-center text-gray-400 mt-4">
              Already have a workspace?{' '}
              <Link to="/login" className="text-blue-600 hover:underline font-medium">Sign in</Link>
            </p>
          </div>
        )}

        {/* ── Step 2: Workspace form ── */}
        {step === 2 && (
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">

            {/* Free plan info */}
            <div className="md:col-span-2 bg-white rounded-2xl border border-gray-200 p-5 shadow-sm h-fit">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xl">{selectedConfig.icon}</span>
                <span className="text-xs font-bold text-gray-700">{selectedConfig.product}</span>
              </div>
              <div className="flex items-center gap-2 mb-3">
                <span className="px-2 py-0.5 text-xs font-bold bg-blue-100 text-blue-700 rounded-full">FREE PLAN</span>
              </div>
              <p className="text-xs text-gray-500 mb-4">Start for free. No credit card needed.</p>
              <ul className="space-y-2">
                {getFreeLimits(selectedIndustry).map((item, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs">
                    {item.ok
                      ? <CheckCircle2 size={13} className="text-green-500 flex-shrink-0" />
                      : <XCircle size={13} className="text-gray-300 flex-shrink-0" />
                    }
                    <span className={item.ok ? 'text-gray-700' : 'text-gray-400'}>{item.label}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Registration form */}
            <div className="md:col-span-3 bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <button
                onClick={() => setStep(1)}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 mb-4"
              >
                <ChevronLeft size={13} /> Change industry
              </button>

              <h2 className="text-lg font-semibold text-gray-800 mb-1">Create your workspace</h2>
              <p className="text-sm text-gray-400 mb-6">Your team will join under this workspace</p>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Company Name</label>
                  <input type="text" value={form.company_name} onChange={set('company_name')} required
                    placeholder="Sharma Fabrication Works"
                    className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" />
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Workspace ID <span className="ml-1 text-gray-400 font-normal">(used in your URL)</span>
                  </label>
                  <input type="text" value={form.slug} onChange={set('slug')} required
                    placeholder="sharma-fab" pattern="[a-z0-9\-]+"
                    title="Lowercase letters, numbers, hyphens only"
                    className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  <p className="text-xs text-gray-400 mt-1">Lowercase, no spaces — e.g. sharma-fab</p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Admin Email</label>
                  <input type="email" value={form.email} onChange={set('email')} required
                    placeholder="owner@company.com"
                    className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Password</label>
                    <input type="password" value={form.password} onChange={set('password')} required
                      minLength={8} placeholder="Min. 8 characters"
                      className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Confirm</label>
                    <input type="password" value={form.confirmPassword} onChange={set('confirmPassword')} required
                      placeholder="Repeat password"
                      className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                </div>

                {error && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">{error}</div>
                )}

                <button type="submit" disabled={loading}
                  className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-semibold rounded-lg transition-colors flex items-center justify-center gap-2 mt-2">
                  {loading
                    ? <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />Creating workspace…</>
                    : 'Create Free Workspace'
                  }
                </button>
              </form>

              <p className="text-xs text-center text-gray-400 mt-5">
                Already have a workspace?{' '}
                <Link to="/login" className="text-blue-600 hover:underline font-medium">Sign in</Link>
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}