// frontend/src/pages/LinkWhatsApp.tsx - v5.5
// FILE:    LinkWhatsApp.tsx
// PATH:    frontend/src/pages/LinkWhatsApp.tsx
// PURPOSE: Allows a logged-in proprietor to link their WhatsApp number to their
//          ZetaOps tenant account. Calls POST /api/v1/whatsapp/link-phone and
//          shows current linked numbers for the tenant.
// BRANCH:  v5-whatsapp
// CREATED: 2026-03-29

import { useEffect, useState, type FormEvent } from 'react'
import { MessageCircle, Phone, Trash2, Plus, CheckCircle, AlertCircle, Loader2, ShieldCheck } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { tokenStore } from '../api/client'
import { WHATSAPP } from '../api/api_endpoints'

// -- Constants -----------------------------------------------------------------
const API_BASE        = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const LINK_URL = `${API_BASE}${WHATSAPP.linkPhone}`
const LINKED_LIST_URL = `${API_BASE}${WHATSAPP.linkedPhones}`

// Roles a phone number can have in the factory
const PHONE_ROLE_OPTIONS = [
  { value: 'owner',     label: 'Owner',     desc: 'Full access - schedule, alerts, actions' },
  { value: 'manager',   label: 'Manager',   desc: 'View schedule, mark attendance'          },
  { value: 'operator',  label: 'Operator',  desc: 'View own assignments only'               },
]

// -- Types ---------------------------------------------------------------------
interface LinkedPhone {
  id:           number
  phone_number: string
  display_name: string
  phone_role:   string
  is_active:    boolean
  consent_given: boolean
}

// -- Helper - build auth header from token store -------------------------------
function authHeaders(): Record<string, string> {
  const token = tokenStore.get()
  return token
    ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
    : { 'Content-Type': 'application/json' }
}

// -- Main Component ------------------------------------------------------------
export default function LinkWhatsApp() {
  const { user } = useAuth()

  // Form state
  const [phone,       setPhone]       = useState('+91')
  const [displayName, setDisplayName] = useState('')
  const [phoneRole,   setPhoneRole]   = useState('owner')
  const [consent,     setConsent]     = useState(false)

  // UI state
  const [submitting,  setSubmitting]  = useState(false)
  const [loadingList, setLoadingList] = useState(true)
  const [linkedPhones, setLinkedPhones] = useState<LinkedPhone[]>([])
  const [successMsg,  setSuccessMsg]  = useState<string | null>(null)
  const [errorMsg,    setErrorMsg]    = useState<string | null>(null)

  // -- Load existing linked phones on mount ------------------------------------
  useEffect(() => {
    fetchLinkedPhones()
  }, [])

  /**
   * fetchLinkedPhones - GET /api/v1/whatsapp/linked-phones
   * Loads all phone numbers linked to this tenant.
   * Side effect: sets linkedPhones state.
   */
  async function fetchLinkedPhones() {
    setLoadingList(true)
    try {
      const res = await fetch(LINKED_LIST_URL, { headers: authHeaders() })
      if (!res.ok) throw new Error(`Server returned ${res.status}`)
      const data = await res.json()
      // Backend returns { phones: LinkedPhone[] }
      setLinkedPhones(data.phones ?? [])
    } catch (err: unknown) {
      const _errMsg = err instanceof Error ? err.message : 'Unknown error'
      // Non-fatal - show empty list, user can still link
      console.error('[LinkWhatsApp] fetchLinkedPhones failed:', err.message)
      setLinkedPhones([])
    } finally {
      setLoadingList(false)
    }
  }

  /**
   * handleLink - POST /api/v1/whatsapp/link-phone
   * Submits form to link a new phone number.
   * Args: form submit event
   * Side effects: refreshes linked phones list, clears form on success.
   */
  async function handleLink(e: FormEvent) {
    e.preventDefault()
    setErrorMsg(null)
    setSuccessMsg(null)

    // Basic phone validation - must start with + and have 10-15 digits
    const cleaned = phone.replace(/\s/g, '')
    if (!/^\+\d{10,15}$/.test(cleaned)) {
      setErrorMsg('Phone number must be in international format, e.g. +919876543210')
      return
    }
    if (!consent) {
      setErrorMsg('Please confirm consent before linking.')
      return
    }

    setSubmitting(true)
    try {
      const res = await fetch(LINK_URL, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          phone_number:  cleaned,
          display_name:  displayName.trim() || (user?.email ?? 'Owner'),
          phone_role:    phoneRole,
          consent_given: true,
        }),
      })

      if (!res.ok) {
        // Parse backend error detail if available
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail ?? `Failed to link phone (${res.status})`)
      }

      setSuccessMsg(`${cleaned} linked successfully! You can now use WhatsApp to talk to ZetaOps Copilot.`)
      // Reset form
      setPhone('+91')
      setDisplayName('')
      setPhoneRole('owner')
      setConsent(false)
      // Refresh list
      await fetchLinkedPhones()
    } catch (err: unknown) {
      const _errMsg = err instanceof Error ? err.message : 'Unknown error'
      setErrorMsg(_errMsg ?? 'Something went wrong. Check backend logs.')
    } finally {
      setSubmitting(false)
    }
  }

  /**
   * handleDeactivate - PATCH /api/v1/whatsapp/linked-phones/:id/deactivate
   * Deactivates a linked phone without deleting it.
   * Args: phone record id
   * Side effects: refreshes linked phones list.
   */
  async function handleDeactivate(id: number) {
    if (!confirm('Deactivate this number? It will no longer receive alerts or be able to chat.')) return
    try {
      const res = await fetch(`${API_BASE}${WHATSAPP.deactivatePhone(id)}`, {
        method: 'PATCH',
        headers: authHeaders(),
      })
      if (!res.ok) throw new Error(`Server returned ${res.status}`)
      await fetchLinkedPhones()
    } catch (err: unknown) {
      const _errMsg = err instanceof Error ? err.message : 'Unknown error'
      setErrorMsg(`Deactivate failed: ${_errMsg}. Check backend logs at routers/whatsapp.py.`)
    }
  }

  // -- Render -----------------------------------------------------------------
  return (
    <div className="min-h-full bg-gray-50 p-6">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* -- Page header --------------------------------------------------- */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-green-500 flex items-center justify-center shrink-0">
            <MessageCircle size={20} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">WhatsApp Copilot</h1>
            <p className="text-sm text-gray-500">
              Link a phone number to get schedule alerts and control ZetaOps via WhatsApp
            </p>
          </div>
        </div>

        {/* -- How it works callout ------------------------------------------- */}
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 flex gap-3">
          <ShieldCheck size={18} className="text-green-600 shrink-0 mt-0.5" />
          <div className="text-sm text-green-800 space-y-1">
            <p className="font-semibold">How it works</p>
            <p>Once linked, send any message to your ZetaOps WhatsApp number to chat with the AI Copilot - ask for today's schedule, mark someone absent, or check machine status. All in Hindi, English, or Hinglish.</p>
          </div>
        </div>

        {/* -- Link new phone form -------------------------------------------- */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <Plus size={16} className="text-blue-500" />
            Link a new number
          </h2>

          <form onSubmit={handleLink} className="space-y-4">

            {/* Phone number */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                WhatsApp Number <span className="text-red-400">*</span>
              </label>
              <div className="flex items-center gap-2">
                <Phone size={16} className="text-gray-400 shrink-0" />
                <input
                  type="tel"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  placeholder="+919876543210"
                  required
                  className="flex-1 px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent font-mono"
                />
              </div>
              <p className="text-xs text-gray-400 mt-1">International format with country code, no spaces</p>
            </div>

            {/* Display name */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Your name <span className="text-gray-400">(optional)</span>
              </label>
              <input
                type="text"
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                placeholder={user?.email ?? 'e.g. Rajan Mehta'}
                className="w-full px-3 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
              />
              <p className="text-xs text-gray-400 mt-1">Used by AI to address you by name in WhatsApp</p>
            </div>

            {/* Role selector */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-2">
                Role for this number <span className="text-red-400">*</span>
              </label>
              <div className="grid grid-cols-3 gap-2">
                {PHONE_ROLE_OPTIONS.map(r => (
                  <button
                    key={r.value}
                    type="button"
                    onClick={() => setPhoneRole(r.value)}
                    className={`flex flex-col gap-1 px-3 py-2.5 rounded-xl border-2 text-left transition-all ${
                      phoneRole === r.value
                        ? 'border-green-500 bg-green-50 text-green-800'
                        : 'border-gray-200 bg-white text-gray-500 hover:border-gray-300'
                    }`}
                  >
                    <span className="text-xs font-bold">{r.label}</span>
                    <span className="text-xs leading-tight opacity-75">{r.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Consent checkbox */}
            <label className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={consent}
                onChange={e => setConsent(e.target.checked)}
                className="mt-0.5 w-4 h-4 accent-green-500 cursor-pointer"
              />
              <span className="text-xs text-gray-600 group-hover:text-gray-800 transition-colors">
                I confirm this number belongs to me or someone at my factory, and they consent to receiving WhatsApp messages from ZetaOps Copilot.
              </span>
            </label>

            {/* Success / error messages */}
            {successMsg && (
              <div className="flex items-start gap-2 p-3 bg-green-50 border border-green-200 rounded-lg text-xs text-green-700">
                <CheckCircle size={14} className="shrink-0 mt-0.5" />
                {successMsg}
              </div>
            )}
            {errorMsg && (
              <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">
                <AlertCircle size={14} className="shrink-0 mt-0.5" />
                {errorMsg}
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={submitting || !consent}
              className="w-full py-2.5 px-4 bg-green-600 hover:bg-green-700 disabled:bg-green-300 text-white text-sm font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {submitting
                ? <><Loader2 size={16} className="animate-spin" /> Linking…</>
                : <><MessageCircle size={16} /> Link WhatsApp Number</>
              }
            </button>
          </form>
        </div>

        {/* -- Linked phones list --------------------------------------------- */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-base font-semibold text-gray-800 mb-4 flex items-center gap-2">
            <Phone size={16} className="text-gray-500" />
            Linked numbers
            {linkedPhones.length > 0 && (
              <span className="ml-auto text-xs font-normal text-gray-400">{linkedPhones.length} number{linkedPhones.length !== 1 ? 's' : ''}</span>
            )}
          </h2>

          {loadingList ? (
            <div className="flex items-center justify-center py-8 text-gray-400 gap-2">
              <Loader2 size={16} className="animate-spin" />
              <span className="text-sm">Loading…</span>
            </div>
          ) : linkedPhones.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <MessageCircle size={32} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">No numbers linked yet.</p>
              <p className="text-xs mt-1">Link your first WhatsApp number above.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {linkedPhones.map(p => (
                <div
                  key={p.id}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${
                    p.is_active
                      ? 'border-gray-200 bg-gray-50'
                      : 'border-gray-100 bg-white opacity-50'
                  }`}
                >
                  {/* Status dot */}
                  <div className={`w-2 h-2 rounded-full shrink-0 ${p.is_active ? 'bg-green-500' : 'bg-gray-300'}`} />

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono font-medium text-gray-800">{p.phone_number}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded-md bg-gray-200 text-gray-600 capitalize">{p.phone_role}</span>
                      {!p.is_active && <span className="text-xs text-gray-400">inactive</span>}
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5 truncate">{p.display_name}</div>
                  </div>

                  {/* Deactivate button - only if active */}
                  {p.is_active && (
                    <button
                      onClick={() => handleDeactivate(p.id)}
                      title="Deactivate this number"
                      className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors shrink-0"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* -- Test hint for dev ---------------------------------------------- */}
        {import.meta.env.DEV && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-xs text-yellow-800">
            <p className="font-semibold mb-1">🛠 Dev mode - simulator tip</p>
            <p>Test the linked number via: <code className="bg-yellow-100 px-1 rounded">POST /api/v1/whatsapp/simulate</code> with <code className="bg-yellow-100 px-1 rounded">{`{"phone": "+91...", "message": "aaj ka schedule", "type": "text"}`}</code></p>
          </div>
        )}

      </div>
    </div>
  )
}
