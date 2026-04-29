// frontend/src/components/InviteMemberModal.tsx
//
// PURPOSE
// v6.3.5 consolidated invite modal. Replaces both the standalone
// /whatsapp page (LinkWhatsApp.tsx, deleted) and the inline invite form
// that lived in TeamAndRoles.tsx. One modal owns: channel choice
// (WhatsApp / Desktop), the conditional phone-or-email field, optional
// name, role selection, and the consent checkbox required for the
// WhatsApp path.
//
// CALLED BY
// - frontend/src/pages/settings/TeamAndRoles.tsx - opens the modal when
//   the "Invite member" header button is clicked.
//
// CALLS INTO
// - teamApi.invite (../api/api_team)
// - useAuth (../auth/useAuth) - actor's role gates which target roles
//   can be presented in the role grid.
// - lucide-react icons.
//
// DESIGN NOTES
// - Channel + role + (consent when WA) are required to enable Submit.
// - When channel='desktop' the consent checkbox row is hidden entirely so
//   the user is not asked to confirm consent for a path that does not
//   send WhatsApp messages.
// - The submit button label switches by channel ("Send WhatsApp invite"
//   vs "Send email invite") so the user always knows what is about to
//   happen - matches the mockup view 2 spec.
// - Validation mirrors the backend's _resolve_channel: WA -> E.164 phone,
//   desktop -> email shape. We also let the backend re-validate; surfacing
//   the message ourselves catches errors before the round-trip.

import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, X } from 'lucide-react'

import { teamApi } from '../api/api_team'
import { useAuth } from '../auth/useAuth'
import type { InviteChannel, InviteRequest } from '../types/types_index'


// -- Role grid -----------------------------------------------------------------
// Mockup view 2 lays roles out in 3 cols x 2 rows: top-tier (3), mid-tier (1),
// operational (2). Tier label drives the accent colour. Disabled roles are
// excluded for non-top-grantor actors so the user never sees an option that
// will 403 on submit.
type Tier = 'top' | 'mid' | 'low'

const ROLE_GRID: ReadonlyArray<{
  key: string; label: string; tier: Tier; tierLabel: string
}> = [
  { key: 'owner',           label: 'Owner',           tier: 'top', tierLabel: 'Top-tier' },
  { key: 'factory_manager', label: 'Factory Manager', tier: 'top', tierLabel: 'Top-tier' },
  { key: 'co_owner',        label: 'Co-Owner',        tier: 'top', tierLabel: 'Top-tier' },
  { key: 'manager',         label: 'Manager',         tier: 'mid', tierLabel: 'Mid-tier' },
  { key: 'scheduler',       label: 'Scheduler',       tier: 'mid', tierLabel: 'Mid-tier' },
  { key: 'viewer',          label: 'Viewer',          tier: 'low', tierLabel: 'Read-only' },
]

const TOP_TIER_GRANT_ROLES = ['owner', 'proprietor'] as const
const TOP_TIER_TARGET_ROLES = ['owner', 'proprietor', 'factory_manager', 'co_owner'] as const

const E164_RE = /^\+[1-9]\d{1,14}$/
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/


function tierBorder(tier: Tier, selected: boolean): string {
  if (selected) {
    return tier === 'top'
      ? 'border-amber-500 bg-amber-50'
      : tier === 'mid'
      ? 'border-blue-500 bg-blue-50'
      : 'border-gray-400 bg-gray-50'
  }
  return 'border-gray-200 hover:bg-gray-50'
}

function tierLabelClass(tier: Tier): string {
  return tier === 'top'
    ? 'text-amber-600'
    : tier === 'mid'
    ? 'text-blue-600'
    : 'text-gray-500'
}


function getErrorDetail(err: unknown, fallback: string): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ?? fallback
  )
}


export interface InviteMemberModalProps {
  open:      boolean
  onClose:   () => void
  onInvited?: (member: { email: string | null; password: string | null }) => void
}


export default function InviteMemberModal({
  open, onClose, onInvited,
}: InviteMemberModalProps) {
  const { user } = useAuth()
  const qc = useQueryClient()

  // -- Local form state ------------------------------------------------------
  // State is reset in resetAndClose() on every close (cancel / success / X /
  // backdrop click) so the next open always starts fresh. We deliberately do
  // NOT reset on `open` becoming true via useEffect because that triggers
  // react-hooks/set-state-in-effect and the close-time reset achieves the
  // same outcome without the cascade.
  const [channel, setChannel] = useState<InviteChannel>('whatsapp')
  const [phone, setPhone]     = useState('')
  const [email, setEmail]     = useState('')
  const [name,  setName]      = useState('')
  const [role,  setRole]      = useState<string>('factory_manager')
  const [consent, setConsent] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  function resetForm() {
    setChannel('whatsapp')
    setPhone(''); setEmail(''); setName('')
    setRole('factory_manager')
    setConsent(false)
    setErrorMsg('')
  }

  function resetAndClose() {
    resetForm()
    onClose()
  }

  const actorIsTopGrantor = !!user
    && (TOP_TIER_GRANT_ROLES as readonly string[]).includes(user.role)

  // Hide top-tier role cards from non-top-grantor actors so they cannot
  // pick one (backend would 403 anyway).
  const visibleRoles = useMemo(() => {
    if (actorIsTopGrantor) return ROLE_GRID
    return ROLE_GRID.filter(
      r => !(TOP_TIER_TARGET_ROLES as readonly string[]).includes(r.key),
    )
  }, [actorIsTopGrantor])

  // -- Validation -----------------------------------------------------------
  const phoneValid = E164_RE.test(phone.trim())
  const emailValid = EMAIL_RE.test(email.trim())
  const isWA = channel === 'whatsapp'
  const isFormValid =
    !!role
    && (isWA ? (phoneValid && consent) : emailValid)

  // -- Mutation -------------------------------------------------------------
  const inviteMut = useMutation({
    mutationFn: () => {
      const payload: InviteRequest = isWA
        ? {
            email_or_phone: phone.trim(),
            role,
            channel:        'whatsapp',
            consent_given:  true,
            name:           name.trim() || null,
          }
        : {
            email_or_phone: email.trim(),
            role,
            channel:        'desktop',
            consent_given:  false,
            name:           name.trim() || null,
          }
      return teamApi.invite(payload)
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['team-members'] })
      onInvited?.({
        email:    data.member.email ?? null,
        password: data.temp_password ?? null,
      })
      resetAndClose()
    },
    onError: (err) => {
      setErrorMsg(getErrorDetail(err, 'Failed to send invite.'))
    },
  })

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={resetAndClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="invite-modal-title"
    >
      <div
        className="w-full max-w-xl bg-white rounded-2xl shadow-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-gray-200">
          <div>
            <h2 id="invite-modal-title" className="text-lg font-bold text-gray-800">
              Invite a teammate
            </h2>
            <p className="text-xs text-gray-500 mt-1">
              They&apos;ll get a welcome message based on the channel you pick.
            </p>
          </div>
          <button
            onClick={resetAndClose}
            aria-label="Close"
            className="text-gray-400 hover:text-gray-700 rounded-md p-1 hover:bg-gray-100"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-5 max-h-[70vh] overflow-y-auto">
          {/* Channel radio */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-2">
              How will they connect? <span className="text-red-600">*</span>
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                type="button"
                role="radio"
                aria-checked={channel === 'whatsapp'}
                onClick={() => setChannel('whatsapp')}
                className={`text-left rounded-lg border p-3 transition-colors ${
                  channel === 'whatsapp'
                    ? 'border-amber-500 bg-amber-50'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <div className="text-sm font-semibold text-gray-800">
                  WhatsApp
                  <span className="ml-2 text-[10px] font-bold uppercase bg-green-600 text-white px-1.5 py-0.5 rounded">
                    Recommended
                  </span>
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Phone-based identity. Most common for floor staff.
                </div>
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={channel === 'desktop'}
                onClick={() => setChannel('desktop')}
                className={`text-left rounded-lg border p-3 transition-colors ${
                  channel === 'desktop'
                    ? 'border-amber-500 bg-amber-50'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <div className="text-sm font-semibold text-gray-800">
                  Desktop only
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Email + password login. For office or finance roles.
                </div>
              </button>
            </div>
          </div>

          {/* Phone OR email */}
          {isWA ? (
            <div>
              <label htmlFor="invite-phone" className="block text-xs font-semibold text-gray-700 mb-2">
                Phone number <span className="text-red-600">*</span>
              </label>
              <input
                id="invite-phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91 99999 12345"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <div className="text-[11px] text-gray-500 mt-1">
                International format with country code, no spaces.
              </div>
            </div>
          ) : (
            <div>
              <label htmlFor="invite-email" className="block text-xs font-semibold text-gray-700 mb-2">
                Email address <span className="text-red-600">*</span>
              </label>
              <input
                id="invite-email"
                type="text"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="suresh@example.com"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <div className="text-[11px] text-gray-500 mt-1">
                A magic-link sign-up will be sent here.
              </div>
            </div>
          )}

          {/* Name */}
          <div>
            <label htmlFor="invite-name" className="block text-xs font-semibold text-gray-700 mb-2">
              Name <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              id="invite-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Suresh Patel"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <div className="text-[11px] text-gray-500 mt-1">
              Used so the AI Copilot can address them by name.
            </div>
          </div>

          {/* Role grid */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-2">
              Role <span className="text-red-600">*</span>
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {visibleRoles.map((r) => (
                <button
                  key={r.key}
                  type="button"
                  role="radio"
                  aria-checked={role === r.key}
                  onClick={() => setRole(r.key)}
                  className={`text-left rounded-lg border p-2.5 transition-colors ${
                    tierBorder(r.tier, role === r.key)
                  }`}
                >
                  <div className="text-sm font-semibold text-gray-800">{r.label}</div>
                  <div className={`text-[10px] uppercase tracking-wide font-semibold mt-0.5 ${tierLabelClass(r.tier)}`}>
                    {r.tierLabel}
                  </div>
                </button>
              ))}
            </div>
            <div className="text-[11px] text-gray-500 mt-2">
              Top-tier members can invite, promote, and demote others. Operational
              roles can run the floor but not change the team.
            </div>
          </div>

          {/* Consent (whatsapp only) */}
          {isWA && (
            <label className="flex items-start gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2.5 text-xs text-gray-700">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                className="mt-0.5"
              />
              <span>
                I confirm this person consents to receiving WhatsApp messages from
                ZetaOps Copilot for factory operations.
              </span>
            </label>
          )}

          {errorMsg && (
            <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {errorMsg}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-6 py-3 border-t border-gray-200 bg-gray-50">
          <button
            onClick={resetAndClose}
            type="button"
            className="text-sm text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-100 border border-gray-300"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => { setErrorMsg(''); inviteMut.mutate() }}
            disabled={!isFormValid || inviteMut.isPending}
            className="flex items-center gap-2 bg-amber-600 hover:bg-amber-700 disabled:bg-amber-300 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
          >
            {inviteMut.isPending && <Loader2 size={14} className="animate-spin" />}
            {isWA ? 'Send WhatsApp invite' : 'Send email invite'}
          </button>
        </div>
      </div>
    </div>
  )
}
