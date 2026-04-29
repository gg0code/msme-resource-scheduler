// frontend/src/pages/settings/__tests__/TeamAndRoles.test.tsx
//
// FILE PURPOSE
// v6.3.5 component tests for the redesigned Team & Roles page:
//   1. row with email=null + name=null renders the "(unnamed)" empty state
//   2. row with whatsapp_status='invited' shows the Invited status pill
//
// CALLED BY
//   npx vitest run
//
// CALLS INTO
//   - TeamAndRoles (component under test)
//   - mocked teamApi.list returning a curated fixture
//   - mocked useAuth (proprietor)

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { TeamMember } from '../../../types/types_index'


// vi.mock is hoisted to the top of the file, so any value referenced by its
// factory must be created via vi.hoisted() (or inlined in the factory).
const fixtureRefs = vi.hoisted(() => {
  const FIXTURE: TeamMember[] = [
    {
      id: 1,
      email: 'owner@t.com',
      phone_e164: null,
      role: 'proprietor',
      is_active: true,
      is_top_tier: true,
      created_via: 'desktop_signup',
      whatsapp_status: 'none',
      name: 'Gaurav',
    },
    {
      // Synthesised email stripped to null + no name -> renders "(unnamed)".
      id: 2,
      email: null,
      phone_e164: '+919999900200',
      role: 'manager',
      is_active: true,
      is_top_tier: false,
      created_via: 'web_invite',
      whatsapp_status: 'active',
      name: null,
    },
    {
      // Awaiting HAAN reply -> "Invited" status pill.
      id: 3,
      email: null,
      phone_e164: '+919999900300',
      role: 'manager',
      is_active: true,
      is_top_tier: false,
      created_via: 'web_invite',
      whatsapp_status: 'invited',
      name: null,
    },
  ]
  return { FIXTURE }
})

vi.mock('../../../api/api_team', () => ({
  teamApi: {
    list:       vi.fn().mockResolvedValue(fixtureRefs.FIXTURE),
    invite:     vi.fn(),
    changeRole: vi.fn(),
    remove:     vi.fn(),
  },
}))

vi.mock('../../../auth/useAuth', async () => {
  const actual: typeof import('../../../auth/useAuth') = await vi.importActual(
    '../../../auth/useAuth',
  )
  return {
    ...actual,
    useAuth: () => ({
      user: { id: 1, email: 'owner@t.com', role: 'proprietor', tenant_id: 1, industry_type: 'printing' },
      accessToken: null, isLoading: false,
      login: vi.fn(), register: vi.fn(), logout: vi.fn(), hasRole: () => true,
    }),
  }
})

import TeamAndRoles from '../TeamAndRoles'


function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TeamAndRoles />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}


describe('TeamAndRoles', () => {

  it('renders (unnamed) tag for a row with no name and a synthetic-email-stripped email', async () => {
    renderPage()
    // Wait for fetched fixture.
    await waitFor(() => expect(screen.getByText(/Gaurav/)).toBeInTheDocument())
    // The id=2 row has email=null + name=null - should display "(unnamed)".
    const unnamedNodes = screen.getAllByText(/\(unnamed\)/i)
    expect(unnamedNodes.length).toBeGreaterThanOrEqual(1)
    // The synthesised email should NOT appear anywhere.
    expect(screen.queryByText(/@invite\.zetaops\.com/)).not.toBeInTheDocument()
  })

  it('renders the Invited status pill for whatsapp_status=invited rows', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText(/Gaurav/)).toBeInTheDocument())
    const invitedPills = screen.getAllByText(/^Invited$/i)
    expect(invitedPills.length).toBeGreaterThanOrEqual(1)
    // For a v6.3.5 invited row the email cell shows the awaiting-YES hint.
    expect(screen.getByText(/Awaiting/i)).toBeInTheDocument()
  })
})
