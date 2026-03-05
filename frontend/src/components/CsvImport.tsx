// components/common/CsvImport.tsx
// --------------------------------
// Reusable CSV import button + result modal.
// Props:
//   resource   — "employees" | "machines" | "skills"
//   onSuccess  — called after successful import so parent can refetch
//
// Shows: Download Template button + Upload CSV button
// After upload: result modal with rows_imported, rows_failed, error list

import { useRef, useState } from 'react'
import { Upload, Download, CheckCircle2, XCircle, AlertTriangle, X, Loader2, FileText } from 'lucide-react'
import apiClient from '../../api/client'
import type { ImportResult } from '../../types'

interface Props {
  resource: 'employees' | 'machines' | 'skills'
  onSuccess: () => void
}

const LABELS: Record<string, string> = {
  employees: 'Employees',
  machines:  'Machines',
  skills:    'Skills',
}

export default function CsvImport({ resource, onSuccess }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [result, setResult]       = useState<ImportResult | null>(null)
  const [error, setError]         = useState('')

  function downloadTemplate() {
    // Trigger browser download via anchor
    const a = document.createElement('a')
    a.href = `http://localhost:8000/api/import/template/${resource}`
    a.download = `${resource}_template.csv`
    a.click()
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.endsWith('.csv')) { setError('Please select a .csv file'); return }

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
        <button
          onClick={downloadTemplate}
          title={`Download ${LABELS[resource]} CSV template`}
          className="flex items-center gap-1.5 text-xs text-gray-600 hover:text-gray-800 border border-gray-300 rounded-lg px-3 py-2 bg-white hover:bg-gray-50 transition-colors">
          <Download size={13}/> Template
        </button>
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 border border-blue-300 rounded-lg px-3 py-2 bg-blue-50 hover:bg-blue-100 disabled:opacity-50 transition-colors">
          {uploading ? <><Loader2 size={13} className="animate-spin"/>Importing...</> : <><Upload size={13}/>Import CSV</>}
        </button>
        <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleFileChange}/>
      </div>

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
