// frontend/src/pages/settings/TeamAndRoles.tsx
//
// PURPOSE
// v6.3.5 redesign of the Team & Roles page. Adds a Phone column and a
// WhatsApp Status column as first-class peers of email + role; renders
// "(unnamed)" / "(invited)" empty states; opens the consolidated
// InviteMemberModal instead of the inline form (deleted from this file).
// Synthesised invite-*@invite.zetaops.com placeholders are no longer
// surfaced - the backend returns email=null for those rows in v6.3.5.
//
// CALLED BY
// - frontend/src/App.tsx routes /settings/team here, mounted inside the
//   Settings.tsx shell.
//
// CALLS INTO
// - teamApi (../../api/api_team) for list / changeRole / remove. Invite
//   now flows through InviteMemberModal which calls teamApi.invite itself.
// - useAuth() for the actor's role (drives "can promote into top-tier" UI gate).
// - InviteMemberModal (../../components/InviteMemberModal) - opened by
//   the header button.
// - React Query for caching + automatic refetch after mutations.

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle, Loader2, Plus, RefreshCw, Trash2, X } from 'lucide-react'

import InviteMemberModal from '../../components/InviteMemberModal'
import { teamApi } from '../../api/api_team'
import { useAuth, isTopTier } from '../../auth/useAuth'
import type { TeamMember, WhatsAppStatus } from '../../types/types_index'


const ALL_ROLES = [
  'owner', 'proprietor', 'factory_manager', 'co_owner',
  'scheduler', 'manager', 'viewer',
] as const
const TOP_TIER_GRANT_ROLES = ['owner', 'proprietor'] as const
const TOP_TIER_TARGET_ROLES = ['owner', 'proprietor', 'factory_manager', 'co_owner'] as const

const ROLE_BADGE: Record<string, string> = {
  owner:           'bg-amber-600',
  proprietor:      'bg-amber-600',
  factory_manager: 'bg-blue-600',
  co_owner:        'bg-purple-600',
  scheduler:       'bg-green-600',
  manager:         'bg-green-600',
  viewer:          'bg-gray-500',
}


function getErrorDetail(err: unknown, fallback: string): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    ?? fallback
  )
}


// -- Status pill --------------------------------------------------------------
// Mirrors mockup view 1: Active=green, Invited=amber, Disconnected=red,
// None=subtle grey. Single source for the colour map; do not redefine.
function StatusPill({ status }: { status: WhatsAppStatus }) {
  const cfg: Record<WhatsAppStatus, { dot: string; text: string; label: string }> = {
    active:       { dot: 'bg-green-600', text: 'text-green-700', label: 'Active' },
    invited:      { dot: 'bg-amber-500', text: 'text-amber-700', label: 'Invited' },
    disconnected: { dot: 'bg-red-600',   text: 'text-red-700',   label: 'Disconnected' },
    none:         { dot: 'bg-gray-400',  text: 'text-gray-500',  label: 'Not connected' },
  }
  const c = cfg[status]
  return (
    <span className={`inline-flex items-center gap-2 text-xs font-medium ${c.text}`}>
      <span className={`w-2 h-2 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  )
}


// -- Person cell --------------------------------------------------------------
// Renders avatar + name + email/hint. "(unnamed)" italic when name is null;
// "(invited)" italic when whatsapp_status='invited' AND name is null.
function PersonCell({ member, isSelf }: { member: TeamMember; isSelf: boolean }) {
  const initial = (member.name?.[0] ?? member.email?.[0] ?? '?').toUpperCase()
  const isInvited = member.whatsapp_status === 'invited' && !member.name
  const displayName = member.name ?? null
  const colour = isInvited
    ? 'from-amber-300 to-amber-500 opacity-70'
    : member.is_top_tier
    ? 'from-amber-500 to-amber-700'
    : 'from-blue-500 to-blue-700'

  return (
    <div className="flex items-center gap-3">
      <div
        className={`w-8 h-8 rounded-full bg-gradient-to-br grid place-items-center text-white text-xs font-semibold shrink-0 ${colour}`}
      >
        {initial}
      </div>
      <div className="min-w-0">
        <div className="text-sm font-semibold text-gray-800 truncate">
          {displayName ? (
            <>{displayName}{isSelf && <span className="ml-1 text-xs text-gray-400 font-normal">(you)</span>}</>
          ) : isInvited ? (
            <span className="italic text-gray-400">(invited)</span>
          ) : (
            <span className="italic text-gray-400">(unnamed)</span>
          )}
        </div>
        <div className="text-[11px] text-gray-500 truncate">
          {member.email
            ? member.email
            : isInvited
            ? <span className="text-amber-700">Awaiting &quot;YES&quot; reply on WhatsApp</span>
            : <span className="italic">Add a name to make WhatsApp messages personal</span>
          }
        </div>
      </div>
    </div>
  )
}


export default function TeamAndRoles() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [showInvite, setShowInvite] = useState(false)
  const [credential, setCredential] = useState<{ email: string; password: string } | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  const actorIsTopGrantor = !!user
    && (TOP_TIER_GRANT_ROLES as readonly string[]).includes(user.role)

  const { data: allMembers = [], isLoading, isError } = useQuery<TeamMember[]>({
    queryKey: ['team-members'],
    queryFn: teamApi.list,
  })
  // v6.3.5 fix: delete is a soft-delete on the backend (sets is_active=False)
  // so the events table's FK to users.id stays valid for audit purposes. The
  // v6.3.3 page used to show those rows with an "Inactive" status column;
  // the v6.3.5 redesign dropped that column, so we hide deactivated users
  // from the table entirely. Backend still returns them via /api/team for
  // anyone who wants the full audit list.
  const members = allMembers.filter(m => m.is_active)

  function clearMessages() {
    setErrorMsg('')
    setSuccessMsg('')
  }

  function flashSuccess(msg: string) {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(''), 3500)
  }

  const roleChangeMut = useMutation({
    mutationFn: (vars: { id: number; role: string }) =>
      teamApi.changeRole(vars.id, { role: vars.role }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team-members'] })
      flashSuccess('Role updated.')
    },
    onError: (err) => {
      setErrorMsg(getErrorDetail(err, 'Failed to change role.'))
    },
  })

  const removeMut = useMutation({
    mutationFn: (id: number) => teamApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team-members'] })
      flashSuccess('Member removed.')
    },
    onError: (err) => {
      setErrorMsg(getErrorDetail(err, 'Failed to remove member.'))
    },
  })

  function rolesAvailableTo(actorIsGrantor: boolean): readonly string[] {
    if (actorIsGrantor) return ALL_ROLES
    return ALL_ROLES.filter(r => !(TOP_TIER_TARGET_ROLES as readonly string[]).includes(r))
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Team &amp; Roles</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Invite, promote, and manage members of your factory team. WhatsApp
            connections and roles in one place.
          </p>
        </div>
        <button
          onClick={() => { clearMessages(); setShowInvite(true) }}
          className="flex items-center gap-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
        >
          <Plus size={16} /> Invite member
        </button>
      </div>

      {/* Status messages */}
      {successMsg && (
        <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-sm">
          <CheckCircle size={16} /> {successMsg}
        </div>
      )}
      {errorMsg && (
        <div className="flex items-center gap-2 text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-sm">
          <AlertCircle size={16} /> {errorMsg}
        </div>
      )}

      {/* One-time login credential reveal after a desktop-channel invite */}
      {credential && (
        <div className="flex items-start gap-2 text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5" />
          <div className="flex-1">
            <div className="font-semibold mb-1">One-time login credentials</div>
            <div>
              Share these with the new member out-of-band. They log in at the
              normal /login page using this email + password. They can change
              both after first login. <strong>This is shown only once.</strong>
            </div>
            <div className="mt-2 grid grid-cols-1 sm:grid-cols-[6rem_1fr] gap-x-3 gap-y-1 items-center">
              <span className="text-xs uppercase text-amber-700">Email</span>
              <code className="px-3 py-2 bg-white border border-amber-200 rounded font-mono text-amber-900 break-all">
                {credential.email}
              </code>
              <span className="text-xs uppercase text-amber-700">Password</span>
              <code className="px-3 py-2 bg-white border border-amber-200 rounded font-mono text-amber-900 break-all">
                {credential.password}
              </code>
            </div>
          </div>
          <button onClick={() => setCredential(null)} className="text-amber-700 hover:text-amber-900">
            <X size={16} />
          </button>
        </div>
      )}

      {/* Invite modal */}
      <InviteMemberModal
        open={showInvite}
        onClose={() => setShowInvite(false)}
        onInvited={(m) => {
          if (m.email && m.password) {
            // Desktop-channel invite: surface the temp password reveal box.
            setCredential({ email: m.email, password: m.password })
            flashSuccess(`Invited ${m.email}.`)
          } else if (m.email) {
            flashSuccess(`Invited ${m.email}.`)
          } else {
            // WhatsApp-channel invite: no email (synthesised, stripped).
            flashSuccess('WhatsApp invite sent. Awaiting YES reply.')
          }
        }}
      />

      {/* Member table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        {isLoading && (
          <div className="flex items-center gap-2 p-6 text-sm text-gray-500">
            <Loader2 size={16} className="animate-spin" /> Loading members...
          </div>
        )}
        {isError && (
          <div className="flex items-center gap-2 p-6 text-sm text-red-600">
            <AlertCircle size={16} /> Failed to load team members.
          </div>
        )}
        {!isLoading && !isError && members.length === 0 && (
          <div className="p-6 text-sm text-gray-500">No team members found.</div>
        )}
        {!isLoading && !isError && members.length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-600">
              <tr>
                <th className="px-4 py-3 font-semibold uppercase text-[10px] tracking-wide">Person</th>
                <th className="px-4 py-3 font-semibold uppercase text-[10px] tracking-wide">Phone</th>
                <th className="px-4 py-3 font-semibold uppercase text-[10px] tracking-wide">WhatsApp</th>
                <th className="px-4 py-3 font-semibold uppercase text-[10px] tracking-wide">Role</th>
                <th className="px-4 py-3 font-semibold uppercase text-[10px] tracking-wide text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {members.map(m => {
                const isSelf = user?.id === m.id
                return (
                  <tr key={m.id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <PersonCell member={m} isSelf={isSelf} />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700 whitespace-nowrap">
                      {m.phone_e164 ?? <span className="font-sans text-gray-400">- not linked</span>}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <StatusPill status={m.whatsapp_status} />
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={m.role}
                        onChange={(e) => { clearMessages(); roleChangeMut.mutate({ id: m.id, role: e.target.value }) }}
                        disabled={!m.is_active || roleChangeMut.isPending}
                        className={`text-xs text-white px-2 py-1 rounded-full disabled:opacity-50 ${ROLE_BADGE[m.role] ?? 'bg-gray-500'}`}
                      >
                        {rolesAvailableTo(actorIsTopGrantor).map(r => (
                          <option key={r} value={r} className="bg-white text-gray-800">{r}</option>
                        ))}
                        {!rolesAvailableTo(actorIsTopGrantor).includes(m.role) && (
                          <option value={m.role} className="bg-white text-gray-800">{m.role}</option>
                        )}
                      </select>
                      {isTopTier(m.role as never) && (
                        <span className="ml-2 text-[10px] uppercase font-semibold tracking-wide text-amber-700">Top-tier</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {actorIsTopGrantor && m.is_active && !isSelf && (
                        <div className="inline-flex items-center gap-1">
                          {m.whatsapp_status === 'invited' && (
                            <button
                              title="Resend WhatsApp invite"
                              onClick={() => alert('Resend invite (v6.3.6 — placeholder)')}
                              className="text-gray-400 hover:text-gray-700 p-1.5 rounded hover:bg-gray-100"
                            >
                              <RefreshCw size={14} />
                            </button>
                          )}
                          <button
                            onClick={() => {
                              clearMessages()
                              if (window.confirm(`Remove this member from the team?`)) {
                                removeMut.mutate(m.id)
                              }
                            }}
                            disabled={removeMut.isPending}
                            className="text-red-600 hover:text-red-800 disabled:opacity-50 p-1.5 rounded hover:bg-red-50 inline-flex items-center"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Info strip - mockup view 1 footer */}
      <div className="flex items-start gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2.5 text-xs text-gray-600">
        <AlertCircle size={14} className="mt-0.5 shrink-0" />
        <span>
          <strong>Top-tier roles</strong> (proprietor, factory_manager, co_owner)
          can invite, promote, and demote others. <strong>Manager</strong> and
          <strong> operator</strong> have operational rights only. Last-owner
          protection prevents removing the only proprietor.
        </span>
      </div>
    </div>
  )
}
