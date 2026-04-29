// frontend/src/pages/settings/TeamAndRoles.tsx
//
// PURPOSE
// v6.3.3 Team & Roles page. Lists all users in the tenant, with controls
// to invite new members, change a member's role inline, and remove
// (soft-delete) a member. The backend enforces every permission rule;
// the UI only mirrors the gates so the user gets feedback before the
// API rejects them.
//
// CALLED BY
// - frontend/src/App.tsx routes /settings/team here, mounted inside the
//   Settings.tsx shell.
//
// CALLS INTO
// - teamApi (../../api/api_team) for list / invite / changeRole / remove.
// - useAuth() for the actor's role (drives "can promote into top-tier" UI gate).
// - React Query for caching + automatic refetch after mutations.

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle, Loader2, Plus, Trash2, X } from 'lucide-react'

import { teamApi } from '../../api/api_team'
import { useAuth, isTopTier } from '../../auth/useAuth'
import type { TeamMember } from '../../types/types_index'


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


export default function TeamAndRoles() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [showInvite, setShowInvite] = useState(false)
  const [inviteForm, setInviteForm] = useState({ email_or_phone: '', role: 'manager' })
  const [credential, setCredential] = useState<{ email: string; password: string } | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  const actorIsTopGrantor = !!user
    && (TOP_TIER_GRANT_ROLES as readonly string[]).includes(user.role)

  const { data: members = [], isLoading, isError } = useQuery<TeamMember[]>({
    queryKey: ['team-members'],
    queryFn: teamApi.list,
  })

  function clearMessages() {
    setErrorMsg('')
    setSuccessMsg('')
  }

  function flashSuccess(msg: string) {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(''), 3500)
  }

  const inviteMut = useMutation({
    mutationFn: () => teamApi.invite(inviteForm),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['team-members'] })
      if (data.temp_password) {
        setCredential({ email: data.member.email, password: data.temp_password })
      }
      flashSuccess(`Invited ${data.member.email}.`)
      setInviteForm({ email_or_phone: '', role: 'manager' })
      setShowInvite(false)
    },
    onError: (err) => {
      setErrorMsg(getErrorDetail(err, 'Failed to invite member.'))
    },
  })

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

  // Per-row UI gating: a non-top-grantor cannot present TOP_TIER_TARGET roles
  // in the inline dropdown. Backend enforces this anyway; UI mirroring keeps
  // the user from picking an option that will 403.
  function rolesAvailableTo(actorIsGrantor: boolean): readonly string[] {
    if (actorIsGrantor) return ALL_ROLES
    return ALL_ROLES.filter(r => !(TOP_TIER_TARGET_ROLES as readonly string[]).includes(r))
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Team & Roles</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Invite, promote, and manage members of your factory team.
          </p>
        </div>
        <button
          onClick={() => { clearMessages(); setShowInvite(true) }}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg transition-colors"
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

      {/* One-time login credential reveal after a successful invite */}
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
      {showInvite && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-700">Invite a new member</h3>
            <button onClick={() => setShowInvite(false)} className="text-gray-400 hover:text-gray-600">
              <X size={18} />
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">Email or phone (E.164)</span>
              <input
                type="text"
                value={inviteForm.email_or_phone}
                onChange={(e) => setInviteForm({ ...inviteForm, email_or_phone: e.target.value })}
                placeholder="user@example.com or +919876543210"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </label>
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">Role</span>
              <select
                value={inviteForm.role}
                onChange={(e) => setInviteForm({ ...inviteForm, role: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {rolesAvailableTo(actorIsTopGrantor).map(r => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setShowInvite(false)}
              className="text-sm text-gray-600 hover:text-gray-800 px-3 py-2"
            >
              Cancel
            </button>
            <button
              onClick={() => { clearMessages(); inviteMut.mutate() }}
              disabled={!inviteForm.email_or_phone || inviteMut.isPending}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm px-4 py-2 rounded-lg transition-colors"
            >
              {inviteMut.isPending && <Loader2 size={14} className="animate-spin" />}
              Send invite
            </button>
          </div>
        </div>
      )}

      {/* Member list */}
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
                <th className="px-4 py-2 font-medium">Email</th>
                <th className="px-4 py-2 font-medium">Phone</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {members.map(m => {
                const isSelf = user?.id === m.id
                return (
                  <tr key={m.id} className="border-t border-gray-100">
                    <td className="px-4 py-2 text-gray-800">{m.email}{isSelf && <span className="text-xs text-gray-400 ml-1">(you)</span>}</td>
                    <td className="px-4 py-2 text-gray-600">{m.phone_e164 ?? '-'}</td>
                    <td className="px-4 py-2">
                      <select
                        value={m.role}
                        onChange={(e) => { clearMessages(); roleChangeMut.mutate({ id: m.id, role: e.target.value }) }}
                        disabled={!m.is_active || roleChangeMut.isPending}
                        className={`text-xs text-white px-2 py-1 rounded-full disabled:opacity-50 ${ROLE_BADGE[m.role] ?? 'bg-gray-500'}`}
                      >
                        {rolesAvailableTo(actorIsTopGrantor).map(r => (
                          <option key={r} value={r} className="bg-white text-gray-800">{r}</option>
                        ))}
                        {/* If the current role is one the actor cannot grant, still show it
                            so the dropdown reflects truth. */}
                        {!rolesAvailableTo(actorIsTopGrantor).includes(m.role) && (
                          <option value={m.role} className="bg-white text-gray-800">{m.role}</option>
                        )}
                      </select>
                      {isTopTier(m.role as never) && (
                        <span className="ml-2 text-[10px] uppercase text-amber-700">Top-tier</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {m.is_active ? (
                        <span className="text-green-700">Active</span>
                      ) : (
                        <span className="text-gray-400">Inactive</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {actorIsTopGrantor && m.is_active && !isSelf && (
                        <button
                          onClick={() => {
                            clearMessages()
                            if (window.confirm(`Remove ${m.email} from the team?`)) {
                              removeMut.mutate(m.id)
                            }
                          }}
                          disabled={removeMut.isPending}
                          className="text-red-600 hover:text-red-800 disabled:opacity-50 text-sm inline-flex items-center gap-1"
                        >
                          <Trash2 size={14} /> Remove
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
