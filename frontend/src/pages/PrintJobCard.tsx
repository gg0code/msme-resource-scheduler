/**
 * PrintJobCard.tsx — V3.4
 * - Completed/Cancelled jobs: print card without QR (shows completion summary)
 * - Active jobs with steps: print card with QR codes per step
 * Route: /jobs/:jobId/print  (auth required, no sidebar)
 */

import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import apiClient from '../api/client'

const SCAN_BASE = import.meta.env.VITE_SCAN_BASE_URL || window.location.origin

// ── Types ─────────────────────────────────────────────────────────────────────

interface JobDetail {
  id: number
  name: string
  customer?: string
  status: string
  priority: string
  start_date?: string
  end_date?: string
  actual_hours?: number
  estimated_hours_per_day?: number
  assigned_employees?: { name: string }[]
  assigned_machines?: { name: string }[]
  notes?: string
}

interface StepToken {
  step_id: number
  sequence_no: number
  step_name: string
  step_type: string
  duration_minutes: number
  status: string
  start_token: string
  complete_token: string
  expires_at: string
}

interface JobTokens {
  job_id: number
  job_name: string
  expires_at: string
  steps: StepToken[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const STEP_TYPE_ICON: Record<string, string> = {
  setup: '⚙️', production: '🔨', inspection: '🔍',
  packaging: '📦', finishing: '✨',
}

const PRIORITY_COLOR: Record<string, string> = {
  Critical: '#dc2626', High: '#ea580c', Medium: '#2563eb', Low: '#16a34a',
}

function fmtDate(iso?: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

function fmtDuration(mins: number) {
  if (mins < 60) return `${mins}min`
  const h = Math.floor(mins / 60), m = mins % 60
  return m ? `${h}h ${m}min` : `${h}h`
}

// ── InfoRow helper ────────────────────────────────────────────────────────────

function InfoRow({ label, value, valueStyle, span }: {
  label: string; value: string;
  valueStyle?: React.CSSProperties; span?: boolean
}) {
  return (
    <div style={{
      ...(span ? { gridColumn: '1 / -1' } : {}),
      padding: '0.75rem 1rem',
      background: '#f8fafc', borderRadius: '0.5rem', border: '1px solid #e2e8f0'
    }}>
      <div style={{ fontSize: '0.7rem', fontWeight: 700, color: '#64748b',
        letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: '0.2rem' }}>
        {label}
      </div>
      <div style={{ fontSize: '0.9rem', color: '#1e293b', ...valueStyle }}>{value}</div>
    </div>
  )
}

// ── Completed card (no QR) ────────────────────────────────────────────────────

function CompletedCard({ job, printedAt }: { job: JobDetail; printedAt: Date }) {
  const employees = job.assigned_employees?.map(e => e.name).join(', ') || '—'
  const machines  = job.assigned_machines?.map(m => m.name).join(', ') || '—'

  return (
    <div style={s.page}>
      {/* Header — dark green for completed */}
      <div style={{ ...s.jobHeader, background: '#064e3b' }}>
        <div style={s.jobHeaderLeft}>
          <div style={s.jobId}>JOB CARD #{job.id} · COMPLETED</div>
          <div style={s.jobName}>{job.name}</div>
          {job.customer && (
            <div style={{ ...s.jobMeta, marginBottom: '0.5rem' }}>Customer: {job.customer}</div>
          )}
          <div style={s.jobMeta}>
            Printed: {printedAt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
            {' · '}
            {printedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>
        <div style={{ ...s.jobHeaderRight, background: 'rgba(255,255,255,0.15)' }}>
          <div style={{ fontSize: '2.5rem', lineHeight: 1 }}>✅</div>
          <div style={{ fontSize: '0.7rem', color: '#6ee7b7', fontWeight: 700,
            letterSpacing: '0.08em', marginTop: '0.4rem' }}>DONE</div>
        </div>
      </div>

      {/* Completion summary grid */}
      <div style={s.sectionTitle}>JOB SUMMARY</div>
      <div style={s.completionGrid}>
        <InfoRow label="Priority" value={job.priority}
          valueStyle={{ color: PRIORITY_COLOR[job.priority] || '#374151', fontWeight: 700 }} />
        <InfoRow label="Status"   value={job.status}
          valueStyle={{ color: '#065f46', fontWeight: 700 }} />
        <InfoRow label="Start Date"    value={fmtDate(job.start_date)} />
        <InfoRow label="End Date"      value={fmtDate(job.end_date)} />
        <InfoRow label="Actual Hours"  value={job.actual_hours != null ? `${job.actual_hours}h` : '—'} />
        <InfoRow label="Est. hrs/day"  value={job.estimated_hours_per_day != null ? `${job.estimated_hours_per_day}h/day` : '—'} />
        <InfoRow label="Employees" value={employees} span />
        <InfoRow label="Machines"  value={machines}  span />
        {job.notes && <InfoRow label="Notes" value={job.notes} span />}
      </div>

      {/* No QR notice */}
      <div style={s.noQrNotice}>
        <span style={{ fontSize: '1.75rem', lineHeight: 1 }}>🔒</span>
        <div>
          <div style={{ fontWeight: 700, color: '#374151', marginBottom: '0.2rem', fontSize: '0.9rem' }}>
            No QR Code Required
          </div>
          <div style={{ fontSize: '0.8rem', color: '#6b7280' }}>
            This job is completed. QR codes are only generated for active jobs.
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={s.cardFooter}>
        <span>MSME Resource Scheduler</span>
        <span>Completed Job Record</span>
        <span>Job #{job.id}</span>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PrintJobCard() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate  = useNavigate()
  const [job, setJob]         = useState<JobDetail | null>(null)
  const [data, setData]       = useState<JobTokens | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [printedAt]           = useState(new Date())

  const load = async () => {
    setLoading(true); setError('')
    try {
      // Always fetch job details first
      const jobRes = await apiClient.get(`/api/jobs/${jobId}`)
      const jobDetail: JobDetail = jobRes.data
      setJob(jobDetail)

      // Only fetch QR tokens for active (non-completed) jobs
      const isDone = ['Completed', 'Cancelled'].includes(jobDetail.status)
      if (!isDone) {
        const tokenRes = await apiClient.post(`/api/jobs/${jobId}/scan-tokens`)
        setData(tokenRes.data)
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Could not load job data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [jobId])

  if (loading) return (
    <div style={s.loadPage}>
      <div style={s.loadCard}>
        <div style={s.spinner} />
        <p style={{ color: '#64748b', margin: 0 }}>Loading job card...</p>
      </div>
    </div>
  )

  if (error) return (
    <div style={s.loadPage}>
      <div style={s.loadCard}>
        <p style={{ color: '#dc2626', marginBottom: '1rem' }}>⚠️ {error}</p>
        <button style={s.btnSecondary} onClick={() => navigate(-1)}>← Go Back</button>
      </div>
    </div>
  )

  if (!job) return null

  const isCompleted = ['Completed', 'Cancelled'].includes(job.status)
  const expiryDisplay = data ? fmtDate(data.expires_at) : ''

  return (
    <>
      {/* ── Screen-only toolbar ── */}
      <div style={s.toolbar} className="no-print">
        <button style={s.btnSecondary} onClick={() => navigate(-1)}>← Back</button>
        <span style={s.toolbarTitle}>
          Job Card — {job.name}
          {isCompleted && (
            <span style={{ marginLeft: '0.75rem', fontSize: '0.72rem',
              background: '#d1fae5', color: '#065f46',
              padding: '0.2rem 0.6rem', borderRadius: '1rem', fontWeight: 700 }}>
              ✅ Completed
            </span>
          )}
        </span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {!isCompleted && (
            <button style={s.btnSecondary} onClick={load}>🔄 Regenerate QR</button>
          )}
          <button style={s.btnPrimary} onClick={() => window.print()}>🖨 Print</button>
        </div>
      </div>

      {/* ── Completed / Cancelled card (no QR) ── */}
      {isCompleted && <CompletedCard job={job} printedAt={printedAt} />}

      {/* ── Active job card with QR codes ── */}
      {!isCompleted && data && (
        <div style={s.page}>
          {/* Job header */}
          <div style={s.jobHeader}>
            <div style={s.jobHeaderLeft}>
              <div style={s.jobId}>JOB CARD #{data.job_id}</div>
              <div style={s.jobName}>{data.job_name}</div>
              {job.customer && (
                <div style={{ ...s.jobMeta, marginBottom: '0.25rem' }}>Customer: {job.customer}</div>
              )}
              <div style={s.jobMeta}>
                Printed: {printedAt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                {' · '}
                {printedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
              </div>
              <div style={s.expiry}>QR valid until: <strong>{expiryDisplay}</strong></div>
            </div>
            <div style={s.jobHeaderRight}>
              <div style={s.stepsCount}>{data.steps.length}</div>
              <div style={s.stepsLabel}>{data.steps.length === 1 ? 'Step' : 'Steps'}</div>
            </div>
          </div>

          {/* Steps */}
          <div style={s.stepsSection}>
            <div style={s.sectionTitle}>PRODUCTION STEPS</div>

            {data.steps.length === 0 && (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b',
                background: '#f8fafc', borderRadius: '0.75rem', border: '1px dashed #e2e8f0' }}>
                <p style={{ margin: 0, fontWeight: 600 }}>No steps defined — use job-level timer on the Jobs page</p>
              </div>
            )}

            {data.steps.map((step) => (
              <div key={step.step_id} style={{ ...s.stepRow, pageBreakInside: 'avoid' }}>
                <div style={s.stepInfo}>
                  <div style={s.stepSeq}>STEP {step.sequence_no}</div>
                  <div style={s.stepName}>
                    {STEP_TYPE_ICON[step.step_type] || '🔧'} {step.step_name}
                  </div>
                  <div style={s.stepMeta}>
                    {step.step_type.toUpperCase()} · {fmtDuration(step.duration_minutes)}
                  </div>
                  {step.status !== 'pending' && (
                    <div style={{ marginTop: '0.4rem', fontSize: '0.7rem', fontWeight: 700,
                      textTransform: 'uppercase', letterSpacing: '0.05em',
                      color: step.status === 'completed'  ? '#16a34a'
                           : step.status === 'in_progress' ? '#2563eb' : '#64748b' }}>
                      {step.status === 'completed'  ? '✅ Completed'
                     : step.status === 'in_progress' ? '▶ In Progress'
                     : step.status}
                    </div>
                  )}
                </div>

                {/* START QR */}
                <div style={s.qrBlock}>
                  <div style={s.qrLabel}>▶ START</div>
                  <div style={s.qrWrapper}>
                    <QRCodeSVG
                      value={`${SCAN_BASE}/scan?token=${step.start_token}`}
                      size={110} level="M"
                    />
                  </div>
                  <div style={s.qrHint}>Scan to start</div>
                </div>

                {/* COMPLETE QR */}
                <div style={s.qrBlock}>
                  <div style={{ ...s.qrLabel, color: '#16a34a' }}>✅ DONE</div>
                  <div style={s.qrWrapper}>
                    <QRCodeSVG
                      value={`${SCAN_BASE}/scan?token=${step.complete_token}`}
                      size={110} level="M"
                    />
                  </div>
                  <div style={s.qrHint}>Scan to complete</div>
                </div>
              </div>
            ))}
          </div>

          {/* Footer */}
          <div style={s.cardFooter}>
            <span>MSME Resource Scheduler</span>
            <span>QR codes expire: {expiryDisplay}</span>
            <span>Job #{data.job_id} · {data.steps.length} steps</span>
          </div>
        </div>
      )}

      {/* Print CSS */}
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { margin: 0; background: white; }
          @page { margin: 1.5cm; size: A4 portrait; }
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  loadPage:      { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8fafc' },
  loadCard:      { background: '#fff', borderRadius: '1rem', padding: '2rem', textAlign: 'center', boxShadow: '0 2px 12px rgba(0,0,0,0.08)' },
  spinner:       { width: '40px', height: '40px', border: '4px solid #e2e8f0', borderTop: '4px solid #3b82f6', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 1rem' },
  toolbar:       { position: 'sticky', top: 0, zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.75rem 1.5rem', background: '#fff', borderBottom: '1px solid #e2e8f0', boxShadow: '0 1px 4px rgba(0,0,0,0.06)' },
  toolbarTitle:  { fontWeight: 600, color: '#1e293b', fontSize: '0.95rem' },
  btnPrimary:    { padding: '0.5rem 1.25rem', background: '#2563eb', color: '#fff', border: 'none', borderRadius: '0.5rem', fontWeight: 600, cursor: 'pointer', fontSize: '0.875rem' },
  btnSecondary:  { padding: '0.5rem 1.25rem', background: '#f1f5f9', color: '#374151', border: '1px solid #e2e8f0', borderRadius: '0.5rem', fontWeight: 500, cursor: 'pointer', fontSize: '0.875rem' },
  page:          { maxWidth: '800px', margin: '2rem auto', padding: '0 1.5rem 3rem', fontFamily: 'system-ui, sans-serif' },
  jobHeader:     { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', background: '#0f172a', color: '#fff', borderRadius: '0.75rem', padding: '1.5rem 2rem', marginBottom: '1.5rem' },
  jobHeaderLeft: { flex: 1 },
  jobId:         { fontSize: '0.75rem', letterSpacing: '0.1em', color: '#94a3b8', marginBottom: '0.25rem' },
  jobName:       { fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' },
  jobMeta:       { fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' },
  expiry:        { fontSize: '0.8rem', color: '#fbbf24' },
  jobHeaderRight: { textAlign: 'center', background: 'rgba(255,255,255,0.1)', borderRadius: '0.5rem', padding: '0.75rem 1.25rem' },
  stepsCount:    { fontSize: '2rem', fontWeight: 800 },
  stepsLabel:    { fontSize: '0.75rem', color: '#94a3b8', letterSpacing: '0.05em' },
  stepsSection:  { marginBottom: '1.5rem' },
  sectionTitle:  { fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.1em', color: '#64748b', marginBottom: '1rem', paddingBottom: '0.5rem', borderBottom: '2px solid #e2e8f0' },
  stepRow:       { display: 'flex', alignItems: 'center', gap: '1.5rem', padding: '1rem 1.25rem', marginBottom: '0.75rem', border: '1px solid #e2e8f0', borderRadius: '0.75rem', background: '#fff' },
  stepInfo:      { flex: 1, minWidth: 0 },
  stepSeq:       { fontSize: '0.7rem', fontWeight: 700, color: '#64748b', letterSpacing: '0.08em', marginBottom: '0.25rem' },
  stepName:      { fontSize: '1rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' },
  stepMeta:      { fontSize: '0.75rem', color: '#64748b' },
  qrBlock:       { textAlign: 'center', flexShrink: 0 },
  qrLabel:       { fontSize: '0.7rem', fontWeight: 700, color: '#2563eb', letterSpacing: '0.05em', marginBottom: '0.4rem' },
  qrWrapper:     { padding: '0.5rem', background: '#fff', border: '1px solid #e2e8f0', borderRadius: '0.5rem', display: 'inline-block' },
  qrHint:        { fontSize: '0.65rem', color: '#94a3b8', marginTop: '0.3rem' },
  cardFooter:    { display: 'flex', justifyContent: 'space-between', padding: '0.75rem 0', borderTop: '1px solid #e2e8f0', fontSize: '0.7rem', color: '#94a3b8' },
  completionGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.5rem' },
  noQrNotice:    { display: 'flex', alignItems: 'center', gap: '1rem', padding: '1.25rem 1.5rem', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '0.75rem', marginBottom: '1.5rem' },
}
