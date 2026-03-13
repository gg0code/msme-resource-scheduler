// src/pages/JobPrintPage.tsx — Prompt 1 Part B §10
// A4 print-ready job card with QR codes
// npm install qrcode @types/qrcode

import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import QRCode from 'qrcode'
import { schedJobsApi, stepsApi, resourcesApi } from '../api/scheduling'
import type { SchedJob, SchedStep, SchedResource } from '../api/scheduling'

// ── Config ────────────────────────────────────────────────────────────────────

const COMPANY_NAME = 'MSME Resource Scheduler'
const BASE_URL = window.location.origin   // e.g. http://13.202.211.172:8081

// ── QR helper ─────────────────────────────────────────────────────────────────

function useQr(text: string, size: number = 120) {
  const [dataUrl, setDataUrl] = useState<string>('')
  useEffect(() => {
    QRCode.toDataURL(text, {
      width: size, margin: 1,
      color: { dark: '#000000', light: '#FFFFFF' },
    }).then(setDataUrl).catch(console.error)
  }, [text, size])
  return dataUrl
}

// ── Resource name helper ──────────────────────────────────────────────────────

function resNames(ids: number[], resources: SchedResource[]) {
  return ids.map(id => resources.find(r => r.id === id)?.name ?? `#${id}`).join(', ') || '—'
}

// ── Big QR (start job) ────────────────────────────────────────────────────────

function BigQR({ jobId }: { jobId: number }) {
  const url = `${BASE_URL}/scan/${jobId}/0/start`
  const src = useQr(url, 180)
  return (
    <div style={{ textAlign: 'center', margin: '24px 0 16px', pageBreakInside: 'avoid' }}>
      {src && <img src={src} alt="Start QR" style={{ width: 180, height: 180, display: 'inline-block' }} />}
      <div style={{ fontWeight: 700, fontSize: 15, marginTop: 8, letterSpacing: 1 }}>
        SCAN TO START JOB + STEP 1
      </div>
      <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{url}</div>
    </div>
  )
}

// ── Step QR row ───────────────────────────────────────────────────────────────

function StepRow({
  step, isLast, resources,
}: { step: SchedStep; isLast: boolean; resources: SchedResource[] }) {
  const url = `${BASE_URL}/scan/${step.job_id}/${step.sequence_order}/done`
  const src = useQr(url, 72)

  const isSetup = step.step_type === 'setup'
  const rowStyle: React.CSSProperties = {
    background: isSetup ? '#fffbeb' : '#ffffff',
    borderBottom: '1px solid #e5e7eb',
    display: 'flex',
    alignItems: 'center',
    padding: '6px 0',
    pageBreakInside: 'avoid',
  }

  return (
    <div style={rowStyle}>
      {/* QR */}
      <div style={{ width: 88, textAlign: 'center', flexShrink: 0 }}>
        {src && <img src={src} alt={`Step ${step.sequence_order} QR`} style={{ width: 72, height: 72 }} />}
        <div style={{ fontSize: 9, fontWeight: 700, color: '#374151', marginTop: 2 }}>
          {isLast ? 'DONE = JOB COMPLETE' : `S${step.sequence_order} DONE`}
        </div>
      </div>

      {/* Seq */}
      <div style={{ width: 36, fontWeight: 700, fontSize: 14, textAlign: 'center', color: '#1f2937' }}>
        {step.sequence_order}
      </div>

      {/* Type badge */}
      <div style={{ width: 64 }}>
        <span style={{
          display: 'inline-block',
          padding: '1px 6px',
          borderRadius: 4,
          fontSize: 10,
          fontWeight: 600,
          background: isSetup ? '#fef3c7' : '#dbeafe',
          color:      isSetup ? '#92400e' : '#1d4ed8',
          border:     isSetup ? '1px solid #f59e0b' : '1px solid #93c5fd',
        }}>
          {step.step_type}
        </span>
      </div>

      {/* Resources */}
      <div style={{ flex: 1, fontSize: 11, color: '#374151' }}>
        {step.step_type === 'regular' && step.required_machine_ids.length > 0 && (
          <div><strong>M:</strong> {resNames(step.required_machine_ids, resources)}</div>
        )}
        {step.required_helper_ids.length > 0 && (
          <div><strong>H:</strong> {resNames(step.required_helper_ids, resources)}</div>
        )}
        {step.is_setup_active && (
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            marginTop: 3, padding: '1px 6px', borderRadius: 4,
            background: '#fef3c7', color: '#92400e', fontSize: 10,
            border: '1px solid #f59e0b',
          }}>
            ⛓ Reserves {resources.find(r => r.id === step.reserve_machine_id)?.name ?? `#${step.reserve_machine_id}`}
          </div>
        )}
      </div>

      {/* Duration */}
      <div style={{ width: 64, fontSize: 11, color: '#6b7280', textAlign: 'right', paddingRight: 8 }}>
        {step.duration_minutes} min
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function JobPrintPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const id = Number(jobId)

  const [job,       setJob]       = useState<SchedJob | null>(null)
  const [steps,     setSteps]     = useState<SchedStep[]>([])
  const [resources, setResources] = useState<SchedResource[]>([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState<string | null>(null)
  const printedAt = new Date().toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })

  useEffect(() => {
    Promise.all([
      schedJobsApi.get(id),
      stepsApi.list(id),
      resourcesApi.list(),
    ])
      .then(([j, s, r]) => {
        setJob(j.data)
        setSteps(s.data)
        setResources(r.data)
        setLoading(false)
      })
      .catch(e => {
        setError(String(e))
        setLoading(false)
      })
  }, [id])

  if (loading) return (
    <div style={{ padding: 48, textAlign: 'center', color: '#6b7280' }}>
      Loading job card…
    </div>
  )
  if (error || !job) return (
    <div style={{ padding: 48, color: '#dc2626' }}>
      Failed to load job: {error}
    </div>
  )

  const PRIORITY_COLOR: Record<string, string> = {
    critical: '#dc2626', urgent: '#d97706', low: '#6b7280',
  }

  const cardStyle: React.CSSProperties = {
    fontFamily: 'Arial, sans-serif',
    maxWidth: 740,
    margin: '0 auto',
    padding: '0 0 24px',
    background: '#fff',
  }

  return (
    <>
      {/* Print button — hidden in @media print */}
      <div className="print:hidden flex justify-end p-4 bg-gray-100 border-b">
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800"
        >
          🖨 Print
        </button>
      </div>

      <div style={cardStyle}>
        {/* ── HEADER ─────────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
          padding: '16px 20px 12px',
          borderBottom: '3px solid #1e3a5f',
        }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: '#1e3a5f' }}>{COMPANY_NAME}</div>
          <div style={{ textAlign: 'right', fontSize: 11, color: '#6b7280' }}>
            <div style={{ fontWeight: 700, color: '#374151' }}>JOB #{job.id}</div>
            <div>{printedAt}</div>
          </div>
        </div>

        <div style={{ padding: '12px 20px 0' }}>
          <div style={{ fontWeight: 800, fontSize: 22, color: '#111827', marginBottom: 6 }}>
            {job.name}
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 4 }}>
            <span style={{
              padding: '2px 10px', borderRadius: 99, fontSize: 11,
              fontWeight: 700, color: '#fff',
              background: PRIORITY_COLOR[job.priority] ?? '#6b7280',
            }}>
              {job.priority.toUpperCase()}
            </span>
            <span style={{ fontSize: 12, color: '#374151' }}>
              📅 Deadline: {new Date(job.deadline).toLocaleDateString('en-IN', {
                day: '2-digit', month: 'short', year: 'numeric',
              })}
            </span>
            {job.expected_profit && (
              <span style={{ fontSize: 12, color: '#374151' }}>
                ₹ {job.expected_profit.toLocaleString('en-IN')} profit
              </span>
            )}
            <span style={{ fontSize: 12, color: '#374151', textTransform: 'capitalize' }}>
              🌅 {job.shift} shift
            </span>
          </div>
        </div>

        {/* ── DIVIDER ────────────────────────────────────────────────────── */}
        <div style={{ borderTop: '1px solid #e5e7eb', margin: '8px 20px' }} />

        {/* ── BIG QR ─────────────────────────────────────────────────────── */}
        <div style={{ padding: '0 20px' }}>
          <BigQR jobId={id} />
        </div>

        <div style={{ borderTop: '1px solid #e5e7eb', margin: '0 20px 12px' }} />

        {/* ── STEPS TABLE ────────────────────────────────────────────────── */}
        <div style={{ padding: '0 20px' }}>
          {/* Column headers */}
          <div style={{
            display: 'flex', padding: '4px 0 4px',
            borderBottom: '2px solid #1e3a5f',
            fontSize: 10, fontWeight: 700, color: '#6b7280',
            textTransform: 'uppercase', letterSpacing: 0.8,
          }}>
            <div style={{ width: 88 }}>QR</div>
            <div style={{ width: 36 }}>Seq</div>
            <div style={{ width: 64 }}>Type</div>
            <div style={{ flex: 1 }}>Resources</div>
            <div style={{ width: 64, textAlign: 'right', paddingRight: 8 }}>Duration</div>
          </div>

          {steps.map((step, idx) => (
            <StepRow
              key={step.id}
              step={step}
              isLast={idx === steps.length - 1}
              resources={resources}
            />
          ))}
        </div>

        {/* ── FOOTER ─────────────────────────────────────────────────────── */}
        <div style={{
          borderTop: '2px solid #e5e7eb',
          margin: '20px 20px 0',
          paddingTop: 10,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: 10,
          color: '#9ca3af',
        }}>
          <div>Printed: {printedAt} · {COMPANY_NAME}</div>
          <div style={{ fontWeight: 600 }}>Scan each QR when step is done</div>
        </div>
      </div>

      {/* ── Print styles ────────────────────────────────────────────────── */}
      <style>{`
        @media print {
          @page { size: A4 portrait; margin: 10mm; }
          body > *:not(div:has(.print-card)) { display: none !important; }
          nav, aside, header, .sidebar, [data-sidebar] { display: none !important; }
          button { display: none !important; }
          .print\\:hidden { display: none !important; }
        }
      `}</style>
    </>
  )
}
