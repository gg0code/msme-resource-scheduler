// frontend/src/pages/__tests__/Employees.bootstrap.test.tsx
//
// FILE PURPOSE
// v6.3.10 component tests for the trimmed Employee form (6.19-AC1, AC3, AC4, AC5):
//   - only three required fields render by default
//   - Save gates on full_name + primary_skill + worker_type
//   - "Add more details" expand reveals optional fields, collapse preserves values
//   - industry-specific skill picker (printing / fabrication / field_service)
//   - worker_type buttons mutually exclusive
//   - edit-flow auto-expands optional section when prior optional data exists
//
// CALLED BY: npx vitest run

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

// ---- vi.hoisted state so mock factories can read mutable test config -------
const { state, mockGet, mockPost, mockPatch, mockDelete } = vi.hoisted(() => {
  return {
    state: {
      industry: 'printing' as 'printing'|'fabrication'|'manufacturing'|'chemical'|'field_service',
      employees: [] as unknown[],
      skills:    [] as { id: number; name: string }[],
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

// useIndustry / useLabels / usePickers — switchable via state.industry.
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
  // Minimal labels stub - fields the form & page header read.
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
  usePlanLimits: () => ({ planLimits: { employees: { current: 0, limit: 100, remaining: 100 } } }),
}))

vi.mock('../../components/PlanLimitGuard', () => ({
  LimitedButton: ({ children, onClick }: { children: ReactNode; onClick: () => void }) =>
    <button onClick={onClick}>{children}</button>,
  PlanLimitBanner: () => null,
}))

import Employees from '../Employees'

function renderEmployees(industry: typeof state.industry = 'printing') {
  state.industry = industry
  mockGet.mockReset(); mockPost.mockClear(); mockPatch.mockClear(); mockDelete.mockClear()
  mockGet.mockImplementation((url: string) => {
    if (url.startsWith('/api/employees')) return Promise.resolve({ data: state.employees })
    if (url.startsWith('/api/skills'))    return Promise.resolve({ data: state.skills })
    return Promise.resolve({ data: [] })
  })
  mockPost.mockResolvedValue({ data: {} })
  mockPatch.mockResolvedValue({ data: {} })

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Employees />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function openCreate() {
  // Header has a single "Add Operator" / "Add Fabricator" / etc. button.
  const btn = await screen.findByText(/^\s*Add (Operator|Fabricator|Technician|Worker|Employee)/i)
  fireEvent.click(btn)
  await screen.findByTestId('emp-full-name')
}


describe('Employees form (v6.3.10 bootstrap UI trim)', () => {
  beforeEach(() => {
    state.employees = []
    state.skills = []
  })

  it('renders only three required fields by default (full_name, primary_skill, worker_type)', async () => {
    renderEmployees('printing')
    await openCreate()
    expect(screen.getByTestId('emp-full-name')).toBeInTheDocument()
    expect(screen.getByTestId('emp-skill-picker')).toBeInTheDocument()
    expect(screen.getByTestId('emp-worker-type-permanent')).toBeInTheDocument()
    expect(screen.getByTestId('emp-worker-type-contractor')).toBeInTheDocument()
    // 6.19-AC3: optional section collapsed by default.
    expect(screen.queryByTestId('emp-optional-section')).not.toBeInTheDocument()
  })

  it('Save is disabled until all three required fields are filled', async () => {
    renderEmployees('printing')
    await openCreate()
    const save = screen.getByTestId('emp-save')
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByTestId('emp-full-name'), { target: { value: 'Ramesh Sharma' } })
    expect(save).toBeDisabled()
    fireEvent.click(screen.getByText('Flexo Printing'))
    expect(save).toBeDisabled()
    fireEvent.click(screen.getByTestId('emp-worker-type-permanent'))
    expect(save).not.toBeDisabled()
  })

  it('Save with minimum fields posts the trimmed payload (worker_type lowercase, optional fields null)', async () => {
    renderEmployees('printing')
    await openCreate()
    fireEvent.change(screen.getByTestId('emp-full-name'), { target: { value: 'Ramesh Sharma' } })
    fireEvent.click(screen.getByText('Die Cutting'))
    fireEvent.click(screen.getByTestId('emp-worker-type-contractor'))
    fireEvent.click(screen.getByTestId('emp-save'))
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1))
    const [, body] = mockPost.mock.calls[0]
    expect(body).toMatchObject({
      full_name: 'Ramesh Sharma',
      worker_type: 'contractor',  // 6.19-AC1, lowercase per VALID_WORKER_TYPE_VALUES
      department: null,            // 6.19-AC5
      contact_number: null,
      join_date: null,
      hourly_rate: null,
      overtime_rate: null,
    })
  })

  it('expand reveals optional fields, collapse preserves values, re-expand restores them', async () => {
    renderEmployees('printing')
    await openCreate()
    expect(screen.queryByTestId('emp-optional-section')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('emp-show-more'))
    const hourly = await screen.findByPlaceholderText(/e\.g\. 150/)
    fireEvent.change(hourly, { target: { value: '250' } })
    // Collapse.
    fireEvent.click(screen.getByTestId('emp-show-more'))
    expect(screen.queryByTestId('emp-optional-section')).not.toBeInTheDocument()
    // Re-expand: value preserved.
    fireEvent.click(screen.getByTestId('emp-show-more'))
    const hourly2 = await screen.findByPlaceholderText(/e\.g\. 150/)
    expect((hourly2 as HTMLInputElement).value).toBe('250')
  })

  it('industry-specific skill list - printing', async () => {
    renderEmployees('printing')
    await openCreate()
    expect(screen.getByText('Flexo Printing')).toBeInTheDocument()
    expect(screen.getByText('Die Cutting')).toBeInTheDocument()
    // Negative: a fabrication-only skill is NOT shown.
    expect(screen.queryByText('Plasma Cutter')).not.toBeInTheDocument()
  })

  it('industry-specific skill list - fabrication', async () => {
    renderEmployees('fabrication')
    await openCreate()
    expect(screen.getByText('Fabrication')).toBeInTheDocument()
    expect(screen.getByText('Welding')).toBeInTheDocument()
    expect(screen.getByText('Grinding')).toBeInTheDocument()
  })

  it('industry-specific skill list - field_service', async () => {
    renderEmployees('field_service')
    await openCreate()
    expect(screen.getByText('HVAC')).toBeInTheDocument()
    expect(screen.getByText('Plumbing')).toBeInTheDocument()
    expect(screen.getByText('Civil Works')).toBeInTheDocument()
  })

  it('worker_type buttons are mutually exclusive', async () => {
    renderEmployees('printing')
    await openCreate()
    const perm = screen.getByTestId('emp-worker-type-permanent')
    const cont = screen.getByTestId('emp-worker-type-contractor')
    fireEvent.click(perm)
    expect(perm).toHaveAttribute('aria-pressed', 'true')
    expect(cont).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(cont)
    expect(perm).toHaveAttribute('aria-pressed', 'false')
    expect(cont).toHaveAttribute('aria-pressed', 'true')
  })

  it('Other / Type custom flips into a free-text input and back', async () => {
    renderEmployees('printing')
    await openCreate()
    expect(screen.queryByTestId('emp-primary-skill-text')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('+ Other'))
    expect(screen.getByTestId('emp-primary-skill-text')).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('emp-primary-skill-text'), { target: { value: 'Custom Trade' } })
    fireEvent.click(screen.getByText(/Back to list/))
    expect(screen.queryByTestId('emp-primary-skill-text')).not.toBeInTheDocument()
    expect(screen.getByTestId('emp-skill-picker')).toBeInTheDocument()
  })

  it('edit-existing-with-optional-data auto-expands the optional section', async () => {
    state.skills = [{ id: 7, name: 'Flexo Printing' }]
    state.employees = [{
      id: 1, full_name: 'Suresh', department: 'Production', employment_type: 'Full-time',
      base_availability_pct: 100, status: 'Active',
      contact_number: null, join_date: null,
      hourly_rate: 175, overtime_rate: null,    // <- optional populated
      worker_type: 'permanent',
      skills: [{ id: 1, skill_id: 7, skill_level: 'Premium' }],
    }]
    renderEmployees('printing')
    // Wait for list, click the row's Edit button.
    const editBtn = await screen.findByText(/^\s*Edit\s*$/i)
    fireEvent.click(editBtn)
    // Modal opens with optional section already expanded (because hourly_rate is set).
    await screen.findByTestId('emp-full-name')
    expect(screen.getByTestId('emp-optional-section')).toBeInTheDocument()
    // Hourly rate prefilled.
    const hourly = screen.getByPlaceholderText(/e\.g\. 150/) as HTMLInputElement
    expect(hourly.value).toBe('175')
  })

  it('edit-existing-without-optional-data leaves the section collapsed', async () => {
    state.skills = [{ id: 7, name: 'Helper' }]
    state.employees = [{
      id: 2, full_name: 'Anil', department: null, employment_type: 'Full-time',
      base_availability_pct: 100, status: 'Active',
      contact_number: null, join_date: null,
      hourly_rate: null, overtime_rate: null,   // <- nothing optional
      worker_type: 'permanent',
      skills: [{ id: 2, skill_id: 7, skill_level: 'Generic' }],
    }]
    renderEmployees('printing')
    const editBtn = await screen.findByText(/^\s*Edit\s*$/i)
    fireEvent.click(editBtn)
    await screen.findByTestId('emp-full-name')
    expect(screen.queryByTestId('emp-optional-section')).not.toBeInTheDocument()
  })
})
