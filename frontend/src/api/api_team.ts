// frontend/src/api/api_team.ts
//
// PURPOSE
// API helpers for the v6.3.3 /api/team endpoints. Used by Settings ->
// Team & Roles page (src/pages/settings/TeamAndRoles.tsx).
//
// CALLED BY
// - frontend/src/pages/settings/TeamAndRoles.tsx
//
// CALLS INTO
// - apiClient (./client) for HTTP transport (JWT auto-refresh handled there).
// - TEAM constants from ./api_endpoints (single source of truth for paths).

import apiClient from './client'
import { TEAM } from './api_endpoints'
import type {
  InviteRequest, InviteResponse, RoleChangeRequest, TeamMember,
} from '../types/types_index'

export const teamApi = {
  list: () =>
    apiClient.get<TeamMember[]>(TEAM.list).then(r => r.data),

  invite: (payload: InviteRequest) =>
    apiClient.post<InviteResponse>(TEAM.invite, payload).then(r => r.data),

  changeRole: (id: number, payload: RoleChangeRequest) =>
    apiClient.patch<TeamMember>(TEAM.changeRole(id), payload).then(r => r.data),

  remove: (id: number) =>
    apiClient.delete(TEAM.remove(id)),
}
