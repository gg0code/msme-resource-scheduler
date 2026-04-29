// frontend/src/components/__tests__/InviteMemberModal.test.tsx
//
// FILE PURPOSE
// v6.3.5 component tests for the consolidated invite modal:
//   1. switching channel toggles the phone vs email field
//   2. consent checkbox is required to enable submit on the whatsapp path
//   3. submit button label reflects the chosen channel
//
// CALLED BY
//   npx vitest run
//
// CALLS INTO
//   - InviteMemberModal (the component under test)
//   - mocked teamApi (we don't want to actually hit /api/team/invite)
//   - mocked useAuth (we don't need a real AuthProvider)

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Mock teamApi BEFORE importing the component so the mutation can be spied on.
const mockInvite = vi.fn().mockResolvedValue({
  member: {
    id: 99, email: 'alpha@example.com', phone_e164: null, role: 'manager',
    is_active: true, is_top_tier: false, created_via: 'web_invite',
    whatsapp_status: 'none', name: null,
  },
  temp_password: 'totally-fake-pw',
})
vi.mock('../../api/api_team', () => ({
  teamApi: {
    invite:     (...args: unknown[]) => mockInvite(...args),
    list:       vi.fn(),
    changeRole: vi.fn(),
    remove:     vi.fn(),
  },
}))

vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({
    user: { id: 1, email: 'me@t.com', role: 'proprietor', tenant_id: 1, industry_type: 'printing' },
    accessToken: null, isLoading: false,
    login: vi.fn(), register: vi.fn(), logout: vi.fn(), hasRole: () => true,
  }),
}))

import InviteMemberModal from '../InviteMemberModal'


function renderModal(
  props?: Partial<Parameters<typeof InviteMemberModal>[0]>,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const onClose   = props?.onClose   ?? vi.fn()
  const onInvited = props?.onInvited ?? vi.fn()
  const open      = props?.open ?? true
  return {
    qc, onClose, onInvited,
    ...render(
      <QueryClientProvider client={qc}>
        <InviteMemberModal open={open} onClose={onClose} onInvited={onInvited} />
      </QueryClientProvider>,
    ),
  }
}


describe('InviteMemberModal', () => {
  beforeEach(() => { mockInvite.mockClear() })

  it('switching channel toggles phone vs email field', () => {
    renderModal()
    // Default channel = whatsapp -> phone field visible.
    expect(screen.getByLabelText(/Phone number/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/Email address/i)).not.toBeInTheDocument()

    // Click "Desktop only" - the phone field should disappear, email appear.
    fireEvent.click(screen.getByText(/Desktop only/i))
    expect(screen.queryByLabelText(/Phone number/i)).not.toBeInTheDocument()
    expect(screen.getByLabelText(/Email address/i)).toBeInTheDocument()
  })

  it('consent checkbox is required for WhatsApp path', () => {
    renderModal()
    const submit = screen.getByRole('button', { name: /Send WhatsApp invite/i })

    // Fill phone - consent still unchecked.
    fireEvent.change(screen.getByLabelText(/Phone number/i), {
      target: { value: '+919999900100' },
    })
    expect(submit).toBeDisabled()

    // Tick consent - submit enables.
    const consent = screen.getByRole('checkbox')
    fireEvent.click(consent)
    expect(submit).not.toBeDisabled()
  })

  it('submit button label reflects the chosen channel', () => {
    renderModal()
    expect(screen.getByRole('button', { name: /Send WhatsApp invite/i })).toBeInTheDocument()
    fireEvent.click(screen.getByText(/Desktop only/i))
    expect(screen.getByRole('button', { name: /Send email invite/i })).toBeInTheDocument()
  })
})
