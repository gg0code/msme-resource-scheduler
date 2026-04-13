// frontend/src/pages/OnboardingSetup.tsx
// Version: 1.1
// Branch: v5-whatsapp
//
// FILE PURPOSE
// Day 1 onboarding — first screen after registration. Three entry paths:
//   Path A: No data — manual Day 1 table (worker name + skill + type, machine name + type)
//   Path B: Has Excel/CSV — upload file, review pre-populated table, confirm
//   Path C: Has SAP/Tally/HR software — ERP placeholder, redirects to Path A for now
//
// This screen must be completed before the morning WhatsApp briefing is useful.
// After saving, workers and machines exist in the DB and v5.15 manager check-in
// can map attendance replies to real people from Day 1.
//
// WHO CALLS THIS FILE
//   App.tsx - rendered at /onboarding route after registration
//
// WHAT THIS FILE CALLS
//   api/api_endpoints.ts  - EMPLOYEES.create, MACHINES.create, SKILLS.list, IMPORT.*
//   api/client.ts         - apiClient
//   @tanstack/react-query - useQuery, useQueryClient

import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight, CheckCircle2, Database, FileSpreadsheet,
  Plus, Trash2, Upload, Wrench, X,
} from 'lucide-react'
import apiClient from '../api/client'
import { EMPLOYEES, IMPORT, MACHINES, SKILLS } from '../api/api_endpoints'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type EntryPath = 'fresh' | 'csv' | 'erp' | null

interface Skill {
  id:   number
  name: string
}

interface WorkerRow {
  id:          string            // client-side key only
  full_name:   string
  skill_id:    number | null
  worker_type: 'permanent' | 'contractor'
}

interface MachineRow {
  id:           string           // client-side key only
  name:         string
  machine_type: string
}

// Shape of one row returned by the CSV import preview endpoint
interface CsvPreviewRow {
  full_name:    string
  skill_name:   string | null
  worker_type?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function uid(): string {
  return Math.random().toString(36).slice(2, 9)
}

function emptyWorker(): WorkerRow {
  return { id: uid(), full_name: '', skill_id: null, worker_type: 'permanent' }
}

function emptyMachine(): MachineRow {
  return { id: uid(), name: '', machine_type: '' }
}

// ---------------------------------------------------------------------------
// Sub-component: Path selection screen
// ---------------------------------------------------------------------------

interface PathSelectorProps {
  onSelect: (path: EntryPath) => void
}

function PathSelector({ onSelect }: PathSelectorProps) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-10 max-w-lg w-full space-y-6">

        <div>
          <h2 className="text-xl font-bold text-gray-800">Set up your factory</h2>
          <p className="text-sm text-gray-500 mt-1">
            How would you like to add your workers and machines?
          </p>
        </div>

        <div className="space-y-3">
          {/* Path A — fresh start */}
          <button
            onClick={() => onSelect('fresh')}
            className="w-full py-4 px-5 rounded-xl border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 text-left transition-all"
          >
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl bg-orange-50 flex items-center justify-center shrink-0">
                <Wrench size={18} className="text-orange-500" />
              </div>
              <div>
                <p className="font-semibold text-gray-800 text-sm">Start fresh</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  Type in your workers and machines manually. Takes about 5 minutes.
                </p>
              </div>
            </div>
          </button>

          {/* Path B — CSV/Excel */}
          <button
            onClick={() => onSelect('csv')}
            className="w-full py-4 px-5 rounded-xl border-2 border-gray-200 hover:border-green-400 hover:bg-green-50 text-left transition-all"
          >
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl bg-green-50 flex items-center justify-center shrink-0">
                <FileSpreadsheet size={18} className="text-green-600" />
              </div>
              <div>
                <p className="font-semibold text-gray-800 text-sm">Upload Excel or CSV</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  Have a worker list in a spreadsheet? Upload it and we will
                  pre-fill the table for you.
                </p>
              </div>
            </div>
          </button>

          {/* Path C — ERP */}
          <button
            onClick={() => onSelect('erp')}
            className="w-full py-4 px-5 rounded-xl border-2 border-gray-200 hover:border-purple-400 hover:bg-purple-50 text-left transition-all"
          >
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl bg-purple-50 flex items-center justify-center shrink-0">
                <Database size={18} className="text-purple-500" />
              </div>
              <div>
                <p className="font-semibold text-gray-800 text-sm">
                  I use SAP, Tally, or HR software
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                  Automatic sync from dedicated systems is coming soon.
                </p>
              </div>
            </div>
          </button>
        </div>

        <p className="text-xs text-gray-400 text-center">
          You can always edit workers and machines later from the main menu.
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-component: CSV upload screen (Path B)
// ---------------------------------------------------------------------------

interface CsvUploadProps {
  skills:    Skill[]
  onLoaded:  (workers: WorkerRow[]) => void
  onSkip:    () => void
}

function CsvUpload({ skills, onLoaded, onSkip }: CsvUploadProps) {
  const fileRef              = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError]    = useState('')

  async function handleFile(file: File): Promise<void> {
    setError('')
    setUploading(true)

    const formData = new FormData()
    formData.append('file', file)

    try {
      // Use existing import_csv backend — employees endpoint returns preview rows
      const res = await apiClient.post<CsvPreviewRow[]>(
        IMPORT.employees,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )

      // Map CSV preview rows to WorkerRow shape
      const mapped: WorkerRow[] = res.data.map(row => {
        // Match skill by name if provided
        const matchedSkill = row.skill_name
          ? skills.find(s => s.name.toLowerCase() === row.skill_name!.toLowerCase())
          : null

        return {
          id:          uid(),
          full_name:   row.full_name ?? '',
          skill_id:    matchedSkill?.id ?? null,
          worker_type: (row.worker_type === 'contractor' ? 'contractor' : 'permanent') as WorkerRow['worker_type'],
        }
      }).filter(r => r.full_name.trim())

      if (mapped.length === 0) {
        setError('No valid worker rows found. Make sure your file has a "name" or "full_name" column.')
        return
      }

      onLoaded(mapped)

    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(msg ?? 'Could not read the file. Please check the format and try again.')
    } finally {
      setUploading(false)
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>): void {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-10 max-w-md w-full space-y-6">

        <div>
          <h2 className="text-xl font-bold text-gray-800">Upload your worker list</h2>
          <p className="text-sm text-gray-500 mt-1">
            Upload a CSV or Excel file. We will read the worker names and skills
            and pre-fill the table for your review.
          </p>
        </div>

        {/* Expected format hint */}
        <div className="bg-gray-50 rounded-xl p-4 space-y-1">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Expected columns
          </p>
          <p className="text-xs text-gray-600">
            <span className="font-medium">full_name</span> or <span className="font-medium">name</span> — worker name (required)
          </p>
          <p className="text-xs text-gray-600">
            <span className="font-medium">skill</span> or <span className="font-medium">skill_name</span> — primary skill (optional)
          </p>
          <p className="text-xs text-gray-600">
            <span className="font-medium">worker_type</span> — permanent or contractor (optional, defaults to permanent)
          </p>
        </div>

        {/* Upload area */}
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="w-full py-8 border-2 border-dashed border-gray-300 hover:border-blue-400 rounded-xl flex flex-col items-center gap-3 transition-colors disabled:opacity-50"
        >
          <Upload size={24} className="text-gray-400" />
          <div className="text-center">
            <p className="text-sm font-medium text-gray-700">
              {uploading ? 'Reading file...' : 'Click to upload'}
            </p>
            <p className="text-xs text-gray-400 mt-0.5">CSV or Excel (.xlsx)</p>
          </div>
        </button>

        <input
          ref={fileRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={handleInputChange}
        />

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 flex items-start gap-2">
            <X size={15} className="text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        <button
          onClick={onSkip}
          className="w-full text-sm text-gray-400 hover:text-gray-600 transition-colors"
        >
          Skip — I will type in my workers manually
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-component: ERP placeholder (Path C)
// ---------------------------------------------------------------------------

interface ErpPlaceholderProps {
  onFallback: () => void
  onSkip:     () => void
}

function ErpPlaceholder({ onFallback, onSkip }: ErpPlaceholderProps) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-10 max-w-md w-full text-center space-y-5">
        <div className="flex justify-center">
          <div className="w-16 h-16 rounded-full bg-purple-50 flex items-center justify-center">
            <Database size={28} className="text-purple-500" />
          </div>
        </div>
        <h2 className="text-xl font-bold text-gray-800">ERP sync coming soon</h2>
        <p className="text-sm text-gray-500">
          Automatic sync from SAP, Tally, and dedicated HR systems is on our
          roadmap. For now, add your workers manually — we will migrate your
          data when the connector is ready.
        </p>
        <button
          onClick={onFallback}
          className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl flex items-center justify-center gap-2 transition-colors"
        >
          Add workers manually for now
          <ArrowRight size={16} />
        </button>
        <button
          onClick={onSkip}
          className="w-full py-3 px-4 bg-white hover:bg-gray-50 text-gray-500 font-medium rounded-xl border border-gray-200 transition-colors"
        >
          Skip setup, go to dashboard
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-component: Done screen
// ---------------------------------------------------------------------------

interface DoneScreenProps {
  onNavigate: () => void
}

function DoneScreen({ onNavigate }: DoneScreenProps) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-10 max-w-md w-full text-center space-y-5">
        <div className="flex justify-center">
          <div className="w-16 h-16 rounded-full bg-green-50 flex items-center justify-center">
            <CheckCircle2 size={32} className="text-green-600" />
          </div>
        </div>
        <h2 className="text-xl font-bold text-gray-800">Setup complete</h2>
        <p className="text-sm text-gray-500">
          Your workers and machines are saved. Your manager can now send
          attendance updates on WhatsApp and the morning briefing will
          name real people from Day 1.
        </p>
        <button
          onClick={onNavigate}
          className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-xl flex items-center justify-center gap-2 transition-colors"
        >
          Go to Dashboard
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function OnboardingSetup() {
  const navigate    = useNavigate()
  const queryClient = useQueryClient()

  const [path,     setPath]     = useState<EntryPath>(null)
  const [workers,  setWorkers]  = useState<WorkerRow[]>([emptyWorker()])
  const [machines, setMachines] = useState<MachineRow[]>([emptyMachine()])
  const [saving,   setSaving]   = useState(false)
  const [errors,   setErrors]   = useState<string[]>([])
  const [done,     setDone]     = useState(false)

  // Skills list — needed for dropdown in table and CSV mapping
  const { data: skills = [] } = useQuery<Skill[]>({
    queryKey: ['skills'],
    queryFn:  () => apiClient.get(SKILLS.list).then(r => r.data),
  })

  // -------------------------------------------------------------------------
  // Worker row helpers
  // -------------------------------------------------------------------------

  function updateWorker(id: string, patch: Partial<WorkerRow>): void {
    setWorkers(rows => rows.map(r => r.id === id ? { ...r, ...patch } : r))
  }

  function updateMachine(id: string, patch: Partial<MachineRow>): void {
    setMachines(rows => rows.map(r => r.id === id ? { ...r, ...patch } : r))
  }

  function addWorker():  void { setWorkers(rows => [...rows, emptyWorker()]) }
  function addMachine(): void { setMachines(rows => [...rows, emptyMachine()]) }

  function removeWorker(id: string):  void { setWorkers(rows => rows.filter(r => r.id !== id)) }
  function removeMachine(id: string): void { setMachines(rows => rows.filter(r => r.id !== id)) }

  // CSV loaded — replace worker rows with imported data, keep machines as-is
  function handleCsvLoaded(imported: WorkerRow[]): void {
    setWorkers(imported.length > 0 ? imported : [emptyWorker()])
    setPath('fresh') // proceed to table review with pre-populated rows
  }

  // -------------------------------------------------------------------------
  // Validation
  // -------------------------------------------------------------------------

  function validate(): string[] {
    const errs: string[] = []
    const filledWorkers  = workers.filter(w => w.full_name.trim())

    if (filledWorkers.length === 0) {
      errs.push('Add at least one worker before continuing.')
    }
    machines.filter(m => m.name.trim()).forEach((m, i) => {
      if (!m.name.trim()) errs.push(`Machine row ${i + 1}: name is required.`)
    })
    return errs
  }

  // -------------------------------------------------------------------------
  // Save
  // -------------------------------------------------------------------------

  async function handleSave(): Promise<void> {
    const validationErrors = validate()
    if (validationErrors.length > 0) {
      setErrors(validationErrors)
      return
    }
    setErrors([])
    setSaving(true)

    try {
      const workerPromises = workers
        .filter(w => w.full_name.trim())
        .map(w =>
          apiClient.post(EMPLOYEES.create, {
            full_name:   w.full_name.trim(),
            source:      'manual',
            worker_type: w.worker_type,
            skills:      w.skill_id
              ? [{ skill_id: w.skill_id, skill_level: 'Generic' }]
              : [],
          })
        )

      const machinePromises = machines
        .filter(m => m.name.trim())
        .map(m =>
          apiClient.post(MACHINES.create, {
            name:         m.name.trim(),
            machine_type: m.machine_type.trim() || null,
            source:       'manual',
          })
        )

      await Promise.all([...workerPromises, ...machinePromises])

      await queryClient.invalidateQueries({ queryKey: ['employees'] })
      await queryClient.invalidateQueries({ queryKey: ['machines'] })

      setDone(true)

    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setErrors([msg ?? 'Something went wrong. Please try again.'])
    } finally {
      setSaving(false)
    }
  }

  // -------------------------------------------------------------------------
  // Routing between screens
  // -------------------------------------------------------------------------

  if (done) {
    return <DoneScreen onNavigate={() => navigate('/dashboard')} />
  }

  if (path === null) {
    return <PathSelector onSelect={setPath} />
  }

  if (path === 'erp') {
    return (
      <ErpPlaceholder
        onFallback={() => setPath('fresh')}
        onSkip={() => navigate('/dashboard')}
      />
    )
  }

  if (path === 'csv') {
    return (
      <CsvUpload
        skills={skills}
        onLoaded={handleCsvLoaded}
        onSkip={() => setPath('fresh')}
      />
    )
  }

  // -------------------------------------------------------------------------
  // Path A and post-CSV-import: Day 1 table
  // -------------------------------------------------------------------------

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-10">
      <div className="max-w-3xl mx-auto space-y-8">

        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-800">
            Your workers and machines
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Review and confirm. You can add more at any time from the main menu.
          </p>
        </div>

        {/* Workers table */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-gray-800">Workers</h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Name, primary skill, permanent or contractor
              </p>
            </div>
            <button
              onClick={addWorker}
              className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 font-medium"
            >
              <Plus size={15} />
              Add row
            </button>
          </div>

          <div className="divide-y divide-gray-50">
            <div className="grid grid-cols-12 gap-3 px-6 py-2 bg-gray-50 text-xs font-medium text-gray-400 uppercase tracking-wide">
              <div className="col-span-4">Name</div>
              <div className="col-span-4">Primary skill</div>
              <div className="col-span-3">Type</div>
              <div className="col-span-1" />
            </div>

            {workers.map(worker => (
              <div key={worker.id} className="grid grid-cols-12 gap-3 px-6 py-3 items-center">
                <div className="col-span-4">
                  <input
                    type="text"
                    placeholder="e.g. Raju Kumar"
                    value={worker.full_name}
                    onChange={e => updateWorker(worker.id, { full_name: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
                  />
                </div>

                <div className="col-span-4">
                  <select
                    value={worker.skill_id ?? ''}
                    onChange={e => updateWorker(worker.id, {
                      skill_id: e.target.value ? Number(e.target.value) : null,
                    })}
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
                  >
                    <option value="">No skill assigned</option>
                    {skills.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>

                <div className="col-span-3">
                  <select
                    value={worker.worker_type}
                    onChange={e => updateWorker(worker.id, {
                      worker_type: e.target.value as 'permanent' | 'contractor',
                    })}
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
                  >
                    <option value="permanent">Permanent</option>
                    <option value="contractor">Contractor</option>
                  </select>
                </div>

                <div className="col-span-1 flex justify-center">
                  {workers.length > 1 && (
                    <button
                      onClick={() => removeWorker(worker.id)}
                      className="text-gray-300 hover:text-red-400 transition-colors"
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Machines table */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-gray-800">Machines</h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Optional but useful for machine status alerts
              </p>
            </div>
            <button
              onClick={addMachine}
              className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 font-medium"
            >
              <Plus size={15} />
              Add row
            </button>
          </div>

          <div className="divide-y divide-gray-50">
            <div className="grid grid-cols-12 gap-3 px-6 py-2 bg-gray-50 text-xs font-medium text-gray-400 uppercase tracking-wide">
              <div className="col-span-6">Machine name</div>
              <div className="col-span-5">Type</div>
              <div className="col-span-1" />
            </div>

            {machines.map(machine => (
              <div key={machine.id} className="grid grid-cols-12 gap-3 px-6 py-3 items-center">
                <div className="col-span-6">
                  <input
                    type="text"
                    placeholder="e.g. Cutting Machine 1"
                    value={machine.name}
                    onChange={e => updateMachine(machine.id, { name: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
                  />
                </div>

                <div className="col-span-5">
                  <input
                    type="text"
                    placeholder="e.g. Cutting, Stitching, Printing"
                    value={machine.machine_type}
                    onChange={e => updateMachine(machine.id, { machine_type: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
                  />
                </div>

                <div className="col-span-1 flex justify-center">
                  {machines.length > 1 && (
                    <button
                      onClick={() => removeMachine(machine.id)}
                      className="text-gray-300 hover:text-red-400 transition-colors"
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Errors */}
        {errors.length > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 space-y-1">
            {errors.map((e, i) => (
              <p key={i} className="text-sm text-red-600">{e}</p>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => navigate('/dashboard')}
            className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
          >
            Skip for now
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 py-3 px-7 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold rounded-xl transition-colors"
          >
            {saving ? 'Saving...' : 'Save and continue'}
            {!saving && <ArrowRight size={16} />}
          </button>
        </div>

      </div>
    </div>
  )
}
