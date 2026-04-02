/**
 * frontend/src/components/common/CsvImport.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * A reusable import widget that lets users bulk-upload employees, machines, or skills
 * from CSV or XLSX files. Also provides a template download button so users can get a
 * pre-formatted file with the correct column headers. Used on the Employees, Machines,
 * and Skills pages. Introduced alongside the CSV import feature and updated to support
 * XLSX and unavailability columns. Sits in components/common/ — shared across multiple
 * resource pages.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Accepts a resource prop ('employees' | 'machines' | 'skills') and onSuccess callback.
 * 2. Renders a Template dropdown button with CSV and XLSX options (XLSX not available
 *    for skills — only employees and machines have XLSX templates).
 * 3. Renders an Import CSV/Excel button that opens a hidden file input.
 * 4. On file select: validates extension (.csv or .xlsx), uploads as FormData to
 *    /import/{resource}, shows a result modal with imported/failed counts and row errors.
 * 5. On success (rows_imported > 0): calls onSuccess() so the parent page refetches data.
 * 6. Template download: fetches from /api/import/template/{resource} or
 *    /api/import/template-xlsx/{resource} as a blob, triggers browser file download.
 * 7. Clicking outside the template dropdown closes it via a full-screen invisible div.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : CsvImport (default export)
 * Type         : React component
 * Purpose      : Import widget with template download + file upload + result modal.
 *                Handles the full import flow for employees, machines, and skills.
 * Parameters   : resource: 'employees' | 'machines' | 'skills'
 *                onSuccess: () => void — called when at least one row was imported
 * Returns      : JSX.Element — two buttons + optional result modal
 * Calls        : apiClient.get (template download), apiClient.post (file upload)
 * DB/API       : GET /api/import/template/{resource}
 *                GET /api/import/template-xlsx/{resource}
 *                POST /import/{resource} (note: no /api/ prefix — check backend routing)
 * Side effects : triggers browser file download, calls onSuccess() on import
 *
 * Name         : downloadTemplate
 * Type         : async function (internal)
 * Purpose      : Downloads CSV or XLSX template as a browser file download.
 *                Uses URL.createObjectURL + anchor click pattern.
 * Parameters   : format: 'csv' | 'xlsx'
 * Returns      : void (triggers download as side effect)
 * Calls        : apiClient.get with responseType: 'blob'
 * DB/API       : GET /api/import/template/{resource} or template-xlsx/{resource}
 * Side effects : browser file download
 *
 * Name         : handleFileChange
 * Type         : async function (internal)
 * Purpose      : Handles file input change. Validates extension, uploads as FormData,
 *                sets result state for the modal. Calls onSuccess if rows were imported.
 * Parameters   : e: React.ChangeEvent<HTMLInputElement>
 * Returns      : void
 * Calls        : apiClient.post
 * DB/API       : POST /import/{resource}
 * Side effects : sets uploading, result, error state; calls onSuccess; clears file input
 *
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Employees.tsx
 * - frontend/src/pages/Machines.tsx
 * - frontend/src/pages/Skills.tsx
 *
 * IMPORTS EXPLAINED
 * - useRef, useState from 'react': fileRef for hidden input, state for upload/result/error.
 * - Upload, Download, CheckCircle2, XCircle, AlertTriangle, X, Loader2, FileText,
 *   ChevronDown from 'lucide-react': Icons for buttons, result modal, and template dropdown.
 * - apiClient from '../../api/client': Authenticated Axios instance for all API calls.
 * - useLabels from '../../context/IndustryContext': Industry-aware resource names for
 *   the modal title (e.g. "Import Workers" instead of "Import Employees").
 * - ImportResult from '../../types/types_index': TypeScript type for the import response
 *   { rows_imported, rows_failed, errors[] }.
 *
 * INTERN NOTES
 * - The POST upload URL is /import/{resource} WITHOUT the /api/ prefix. This differs
 *   from all other API calls. Check backend main.py to confirm how the import router
 *   is registered — if it changes, update the URL here.
 * - XLSX template is only available for employees and machines. Skills only supports CSV.
 *   The XLSX option is conditionally hidden when resource === 'skills'.
 * - The template dropdown close-on-outside-click uses a full-screen z-10 div behind the
 *   dropdown. This is simpler than a useEffect with document.addEventListener but means
 *   the div blocks clicks on the page while the dropdown is open. Keep showTemplates
 *   false by default to avoid this.
 * - Design Principle 2: Tenant scoping happens server-side — the JWT identifies the tenant.
 *   This component never sends tenant_id.
 * - If import succeeds but onSuccess() is not refetching: check that the parent page
 *   is using the correct TanStack Query key and that invalidateQueries is called in
 *   the parent's onSuccess handler, or that the parent is using refetch().
 */

import { useRef, useState } from 'react'
import { Upload, Download, CheckCircle2, XCircle, AlertTriangle, X, Loader2, FileText, ChevronDown } from 'lucide-react'
import apiClient from '../../api/client'
import { useLabels } from '../../context/IndustryContext'
import type { ImportResult } from '../../types/types_index'

interface Props {
  resource: 'employees' | 'machines' | 'skills'
  onSuccess: () => void
}

export default function CsvImport({ resource, onSuccess }: Props) {
  const labels = useLabels()

  const LABELS: Record<string, string> = {
    employees: labels.employees,
    machines:  labels.machines,
    skills:    labels.skills,
  }
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading]   = useState(false)
  const [result, setResult]         = useState<ImportResult | null>(null)
  const [error, setError]           = useState('')
  const [showTemplates, setShowTemplates] = useState(false)

  async function downloadTemplate(format: 'csv' | 'xlsx') {
    try {
      const isXlsx = format === 'xlsx' && resource !== 'skills'
      const url = isXlsx
        ? `/api/import/template-xlsx/${resource}`
        : `/api/import/template/${resource}`
      const res = await apiClient.get(url, { responseType: 'blob' })
      const blob = new Blob([res.data])
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = isXlsx ? `${resource}_template.xlsx` : `${resource}_template.csv`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch {
      setError('Failed to download template. Please try again.')
    }
    setShowTemplates(false)
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.endsWith('.csv') && !file.name.endsWith('.xlsx')) {
      setError('Please select a .csv or .xlsx file')
      return
    }

    setUploading(true); setResult(null); setError('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await apiClient.post<ImportResult>(`/import/${resource}`, fd)
      setResult(res.data)
      if (res.data.rows_imported > 0) onSuccess()
    } catch (err: unknown) {
      const msg = (err as {response?:{data?:{detail?:string}}})?.response?.data?.detail
      setError(msg ?? 'Upload failed — check file format')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <>
      <div className="flex items-center gap-2">
        {/* Template dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowTemplates(v => !v)}
            className="flex items-center gap-1.5 text-xs text-gray-600 hover:text-gray-800 border border-gray-300 rounded-lg px-3 py-2 bg-white hover:bg-gray-50 transition-colors">
            <Download size={13}/> Template <ChevronDown size={11}/>
          </button>
          {showTemplates && (
            <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-20 min-w-36 overflow-hidden">
              <button onClick={() => downloadTemplate('csv')}
                className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2">
                <FileText size={12} className="text-gray-400"/> CSV Template
              </button>
              {resource !== 'skills' && (
                <button onClick={() => downloadTemplate('xlsx')}
                  className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-green-50 flex items-center gap-2 border-t border-gray-100">
                  <FileText size={12} className="text-green-500"/> Excel Template
                </button>
              )}
            </div>
          )}
        </div>

        {/* Upload button */}
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 border border-blue-300 rounded-lg px-3 py-2 bg-blue-50 hover:bg-blue-100 disabled:opacity-50 transition-colors">
          {uploading
            ? <><Loader2 size={13} className="animate-spin"/>Importing...</>
            : <><Upload size={13}/>Import CSV / Excel</>
          }
        </button>
        <input ref={fileRef} type="file" accept=".csv,.xlsx" className="hidden" onChange={handleFileChange}/>
      </div>

      {/* Click outside to close template dropdown */}
      {showTemplates && (
        <div className="fixed inset-0 z-10" onClick={() => setShowTemplates(false)}/>
      )}

      {/* Result modal */}
      {(result || error) && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-blue-500"/>
                <h3 className="font-bold text-gray-800">Import {LABELS[resource]} — Result</h3>
              </div>
              <button onClick={() => { setResult(null); setError('') }}>
                <X size={18} className="text-gray-400 hover:text-gray-600"/>
              </button>
            </div>

            <div className="p-5 space-y-4">
              {error && (
                <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700">
                  <XCircle size={15} className="shrink-0 mt-0.5"/>{error}
                </div>
              )}

              {result && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-green-50 border border-green-200 rounded-xl p-3 text-center">
                      <p className="text-2xl font-black text-green-700">{result.rows_imported}</p>
                      <p className="text-xs text-green-600 font-medium flex items-center justify-center gap-1 mt-1">
                        <CheckCircle2 size={12}/> Imported
                      </p>
                    </div>
                    <div className={`border rounded-xl p-3 text-center ${result.rows_failed > 0 ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200'}`}>
                      <p className={`text-2xl font-black ${result.rows_failed > 0 ? 'text-red-600' : 'text-gray-400'}`}>{result.rows_failed}</p>
                      <p className={`text-xs font-medium flex items-center justify-center gap-1 mt-1 ${result.rows_failed > 0 ? 'text-red-500' : 'text-gray-400'}`}>
                        <XCircle size={12}/> Failed
                      </p>
                    </div>
                  </div>

                  {result.errors.length > 0 && (
                    <div className="bg-orange-50 border border-orange-200 rounded-xl p-3">
                      <p className="text-xs font-semibold text-orange-700 mb-2 flex items-center gap-1">
                        <AlertTriangle size={12}/> Row errors ({result.errors.length})
                      </p>
                      <div className="space-y-1 max-h-40 overflow-y-auto">
                        {result.errors.map((e, i) => (
                          <p key={i} className="text-xs text-orange-700 font-mono">· {e}</p>
                        ))}
                      </div>
                    </div>
                  )}

                  {result.rows_imported > 0 && result.rows_failed === 0 && (
                    <div className="flex items-center gap-2 text-green-700 bg-green-50 rounded-xl p-3 text-sm">
                      <CheckCircle2 size={15}/> All rows imported successfully!
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="px-5 pb-5">
              <button onClick={() => { setResult(null); setError('') }}
                className="w-full bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm py-2.5 rounded-xl font-medium">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
