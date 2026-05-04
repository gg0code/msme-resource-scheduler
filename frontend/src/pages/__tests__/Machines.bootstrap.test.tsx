// frontend/src/pages/__tests__/Machines.bootstrap.test.tsx
//
// FILE PURPOSE
// v6.3.10 component tests for the trimmed Machine form (6.19-AC2, AC3, AC4, AC5):
//   - only two required fields render by default (name, machine_type)
//   - Save gates on name + machine_type
//   - "Add more details" expand reveals optional fields
//   - industry-specific machine_type list
//
// CALLED BY: npx vitest run

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

const { state, mockGet, mockPost, mockPatch, mockDelete } = vi.hoisted(() => {
  return {
    state: {
      industry: 'printing' as 'printing'|'fabrication'|'manufacturing'|'chemical'|'field_service',
      machines: [] as unknown[],
      skills:   [] as { id: number; name: string }[],
    },
    mockGet:    vi.fn(),
    mockPost:   vi.fn(),
    mockPatch:  vi.fn(),
    mockDelete: vi.fn(),
  }
})

vi.mock('../../api/client', () => ({
  default: {
    get:    (...a: unknown[]) => mockGet(...a),
    post:   (...a: unknown[]) => mockPost(...a),
    patch:  (...a: unknown[]) => mockPatch(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
}))

vi.mock('../../api/api_endpoints', () => ({
  EMPLOYEES:   { list: '/api/employees/', update: (id: number) => `/api/employees/${id}` },
  MACHINES:    { list: '/api/machines/',  update: (id: number) => `/api/machines/${id}` },
  SKILLS:      { list: '/api/skills/' },
  ASSIGNMENTS: {
    byEmployee: (id: number) => `/api/assignments/by-employee/${id}`,
    byMachine:  (id: number) => `/api/assignments/by-machine/${id}`,
    delete:     (id: number) => `/api/assignments/${id}`,
  },
}))

vi.mock('../../context/useIndustry', () => {
  const PICKERS = {
    printing:      { skills: ['Flexo Printing','Die Cutting','Lamination','Quality Control','Helper'],
                     machineTypes: ['Flexo Printer','Die Cutter','Laminator','Offset Press','Folder/Gluer'] },
    fabrication:   { skills: ['Fabrication','Welding','Grinding','Fitting','Helper'],
                     machineTypes: ['Plasma Cutter','MIG Welder','Press Brake','Bandsaw','Bench Grinder'] },
    manufacturing: { skills: ['CNC Operation','Welding','Assembly','Quality Check','Helper'],
                     machineTypes: ['CNC Lathe','Welding Station','Assembly Line','Milling Machine','Drilling Machine'] },
    chemical:      { skills: ['Process Operation','Quality Control','Filling Operation','Safety Officer','Helper'],
                     machineTypes: ['Reactor','Mixer','Filling Line','Centrifuge','Distillation Column'] },
    field_service: { skills: ['HVAC','Electrical','Plumbing','Civil Works','Helper'],
                     machineTypes: ['Service Van','Hydraulic Lift','Diagnostic Kit','Pressure Washer','Pipe Threader'] },
  }
  const LABELS = {
    job:'Job', jobs:'Jobs', employee:'Operator', employees:'Operators',
    machine:'Machine', machines:'Machines', material:'Material', materials:'Materials',
    skill:'Skill', skills:'Skills', step:'Step', steps:'Steps',
    jobsPageTitle:'Jobs', jobsPageSubtitle:'', employeesPageTitle:'Operators',
    machinesPageTitle:'Machines',
    jobNamePlaceholder:'', jobTypePlaceholder:'', newJobButton:'New Job',
    kpiJobs:'', kpiOrderBook:'', kpiProfit:'',
  }
  return {
    useLabels:   () => LABELS,
    usePickers:  () => PICKERS[state.industry],
    useIndustry: () => ({ industryType: state.industry, labels: LABELS, config: { pickers: PICKERS[state.industry], labels: LABELS } }),
  }
})

vi.mock('../../components/onboarding', () => ({
  CoachMark: ({ children }: { children: ReactNode }) => <>{children}</>,
}))
vi.mock('../../components/common/CsvImport', () => ({ default: () => null }))
vi.mock('../../components/common/UnavailabilityPanel', () => ({ default: () => null }))
vi.mock('../../context/useFeatureFlags', () => ({
  useFeatureFlags: () => ({ csv_import: false }),
}))
vi.mock('../../components/usePlanLimits', () => ({
  usePlanLimits: () => ({ planLimits: { machines: { current: 0, limit: 100, remaining: 100 } } }),
}))
vi.mock('../../components/PlanLimitGuard', () => ({
  LimitedButton: ({ children, onClick }: { children: ReactNode; onClick: () => void }) =>
    <button onClick={onClick}>{children}</button>,
  PlanLimitBanner: () => null,
}))

import Machines from '../Machines'

function renderMachines(industry: typeof state.industry = 'printing') {
  state.industry = industry
  mockGet.mockReset(); mockPost.mockClear(); mockPatch.mockClear(); mockDelete.mockClear()
  mockGet.mockImplementation((url: string) => {
    if (url.startsWith('/api/machines')) return Promise.resolve({ data: state.machines })
    if (url.startsWith('/api/skills'))   return Promise.resolve({ data: state.skills })
    return Promise.resolve({ data: [] })
  })
  mockPost.mockResolvedValue({ data: {} })
  mockPatch.mockResolvedValue({ data: {} })

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Machines />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function openCreate() {
  const btn = await screen.findByText(/^\s*Add (Machine|Work Center|Reactor|Vehicle)/i)
  fireEvent.click(btn)
  await screen.findByTestId('machine-name')
}


describe('Machines form (v6.3.10 bootstrap UI trim)', () => {
  beforeEach(() => {
    state.machines = []
    state.skills = []
  })

  it('renders only two required fields by default (name, machine_type)', async () => {
    renderMachines('printing')
    await openCreate()
    expect(screen.getByTestId('machine-name')).toBeInTheDocument()
    expect(screen.getByTestId('machine-type-picker')).toBeInTheDocument()
    expect(screen.queryByTestId('machine-optional-section')).not.toBeInTheDocument()
  })

  it('Save is disabled until name + machine_type are filled', async () => {
    renderMachines('printing')
    await openCreate()
    const save = screen.getByTestId('machine-save')
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByTestId('machine-name'), { target: { value: 'Press 2' } })
    expect(save).toBeDisabled()
    fireEvent.click(screen.getByText('Flexo Printer'))
    expect(save).not.toBeDisabled()
  })

  it('Save with minimum fields posts the trimmed payload (optional fields null)', async () => {
    renderMachines('printing')
    await openCreate()
    fireEvent.change(screen.getByTestId('machine-name'), { target: { value: 'Press 2' } })
    fireEvent.click(screen.getByText('Die Cutter'))
    fireEvent.click(screen.getByTestId('machine-save'))
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1))
    const [, body] = mockPost.mock.calls[0]
    expect(body).toMatchObject({
      name: 'Press 2',
      machine_type: 'Die Cutter',
      location_bay: null,    // 6.19-AC5
      hourly_rate: null,
    })
  })

  it('expand reveals optional fields, collapse preserves values', async () => {
    renderMachines('printing')
    await openCreate()
    expect(screen.queryByTestId('machine-optional-section')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('machine-show-more'))
    const bay = await screen.findByPlaceholderText(/Bay A/i)
    fireEvent.change(bay, { target: { value: 'Bay X' } })
    fireEvent.click(screen.getByTestId('machine-show-more'))
    expect(screen.queryByTestId('machine-optional-section')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('machine-show-more'))
    const bay2 = await screen.findByPlaceholderText(/Bay A/i)
    expect((bay2 as HTMLInputElement).value).toBe('Bay X')
  })

  it('industry-specific machine_type list - fabrication', async () => {
    renderMachines('fabrication')
    await openCreate()
    expect(screen.getByText('Plasma Cutter')).toBeInTheDocument()
    expect(screen.getByText('MIG Welder')).toBeInTheDocument()
    expect(screen.queryByText('Flexo Printer')).not.toBeInTheDocument()
  })

  it('industry-specific machine_type list - field_service', async () => {
    renderMachines('field_service')
    await openCreate()
    expect(screen.getByText('Service Van')).toBeInTheDocument()
    expect(screen.getByText('Hydraulic Lift')).toBeInTheDocument()
    expect(screen.queryByText('Plasma Cutter')).not.toBeInTheDocument()
  })
})
