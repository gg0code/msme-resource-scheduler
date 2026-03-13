/**
 * PrintJobCard.tsx — Block 2 V3.3
 * Job card print page with QR codes per step.
 * Route: /jobs/:jobId/print  (auth required, no sidebar)
 *
 * Requires: npm install qrcode.react
 */

import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import QRCode from 'qrcode.react'
import { useAuth } from '../auth/AuthContext'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// The base URL that gets embedded in QR codes
// On shop floor WiFi, phones need your machine's local IP, not localhost
const SCAN_BASE = import.meta.env.VITE_SCAN_BASE_URL || window.location.origin

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

const STEP_TYPE_ICON: Record<string, string> = {
  setup:      '⚙️',
  production: '🔨',
  inspection: '🔍',
  packaging:  '📦',
  finishing:  '✨',
}

function fmtDate(iso: string) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

function fmtDuration(mins: number) {
  if (mins < 60) return `${mins}min`
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return m ? `${h}h ${m}min` : `${h}h`
}

export default function PrintJobCard() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const { token: authToken } = useAuth()
  const [data, setData] = useState<JobTokens | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [printedAt] = useState(new Date())

  const fetchTokens = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API}/api/jobs/${jobId}/scan-tokens`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
      })
      if (!res.ok) {
        const err = await res.json()
        setError(err.detail || 'Failed to generate tokens')
        return
      }
      setData(await res.json())
    } catch {
      setError('Could not connect to server')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchTokens() }, [jobId])

  if (loading) return (
    <div style={s.loadPage}>
      <div style={s.loadCard}>
        <div style={s.spinner} />
        <p>Generating QR codes...</p>
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

  if (!data) return null

  const expiryDisplay = fmtDate(data.expires_at)

  return (
    <>
      {/* ── Screen-only toolbar ── */}
      <div style={s.toolbar} className="no-print">
        <button style={s.btnSecondary} onClick={() => navigate(-1)}>← Back</button>
        <span style={s.toolbarTitle}>Job Card — {data.job_name}</span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button style={s.btnSecondary} onClick={fetchTokens}>🔄 Regenerate QR</button>
          <button style={s.btnPrimary} onClick={() => window.print()}>🖨 Print</button>
        </div>
      </div>

      {/* ── Print card ── */}
      <div style={s.page}>

        {/* Job header */}
        <div style={s.jobHeader}>
          <div style={s.jobHeaderLeft}>
            <div style={s.jobId}>JOB CARD #{data.job_id}</div>
            <div style={s.jobName}>{data.job_name}</div>
            <div style={s.jobMeta}>
              Printed: {printedAt.toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' })}
              {' · '}
              {printedAt.toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' })}
            </div>
            <div style={s.expiry}>QR valid until: <strong>{expiryDisplay}</strong></div>
          </div>
          <div style={s.jobHeaderRight}>
            <div style={s.stepsCount}>{data.steps.length}</div>
            <div style={s.stepsLabel}>Steps</div>
          </div>
        </div>

        {/* Steps */}
        <div style={s.stepsSection}>
          <div style={s.sectionTitle}>PRODUCTION STEPS</div>

          {data.steps.map((step, idx) => (
            <div key={step.step_id} style={{ ...s.stepRow, pageBreakInside: 'avoid' }}>

              {/* Step info */}
              <div style={s.stepInfo}>
                <div style={s.stepSeq}>STEP {step.sequence_no}</div>
                <div style={s.stepName}>
                  {STEP_TYPE_ICON[step.step_type] || '🔧'} {step.step_name}
                </div>
                <div style={s.stepMeta}>
                  {step.step_type.toUpperCase()} · {fmtDuration(step.duration_minutes)}
                </div>
              </div>

              {/* START QR */}
              <div style={s.qrBlock}>
                <div style={s.qrLabel}>▶ START</div>
                <div style={s.qrWrapper}>
                  <QRCode
                    value={`${SCAN_BASE}/scan?token=${step.start_token}`}
                    size={120}
                    level="M"
                    renderAs="svg"
                  />
                </div>
                <div style={s.qrHint}>Scan to start</div>
              </div>

              {/* COMPLETE QR */}
              <div style={s.qrBlock}>
                <div style={{ ...s.qrLabel, color: '#16a34a' }}>✅ DONE</div>
                <div style={s.qrWrapper}>
                  <QRCode
                    value={`${SCAN_BASE}/scan?token=${step.complete_token}`}
                    size={120}
                    level="M"
                    renderAs="svg"
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

      {/* Print CSS */}
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { margin: 0; background: white; }
          @page { margin: 1.5cm; size: A4 portrait; }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  loadPage: {
    minHeight: '100vh', display: 'flex', alignItems: 'center',
    justifyContent: 'center', background: '#f8fafc',
  },
  loadCard: {
    background: '#fff', borderRadius: '1rem', padding: '2rem',
    textAlign: 'center', boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
  },
  spinner: {
    width: '40px', height: '40px',
    border: '4px solid #e2e8f0', borderTop: '4px solid #3b82f6',
    borderRadius: '50%', animation: 'spin 0.8s linear infinite',
    margin: '0 auto 1rem',
  },
  toolbar: {
    position: 'sticky', top: 0, zIndex: 10,
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0.75rem 1.5rem',
    background: '#fff', borderBottom: '1px solid #e2e8f0',
    boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
  },
  toolbarTitle: { fontWeight: 600, color: '#1e293b', fontSize: '0.95rem' },
  btnPrimary: {
    padding: '0.5rem 1.25rem', background: '#2563eb', color: '#fff',
    border: 'none', borderRadius: '0.5rem', fontWeight: 600,
    cursor: 'pointer', fontSize: '0.875rem',
  },
  btnSecondary: {
    padding: '0.5rem 1.25rem', background: '#f1f5f9', color: '#374151',
    border: '1px solid #e2e8f0', borderRadius: '0.5rem', fontWeight: 500,
    cursor: 'pointer', fontSize: '0.875rem',
  },
  page: {
    maxWidth: '800px', margin: '2rem auto', padding: '0 1.5rem 3rem',
    fontFamily: 'system-ui, sans-serif',
  },
  jobHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
    background: '#0f172a', color: '#fff',
    borderRadius: '0.75rem', padding: '1.5rem 2rem', marginBottom: '1.5rem',
  },
  jobHeaderLeft: { flex: 1 },
  jobId: { fontSize: '0.75rem', letterSpacing: '0.1em', color: '#94a3b8', marginBottom: '0.25rem' },
  jobName: { fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' },
  jobMeta: { fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' },
  expiry: { fontSize: '0.8rem', color: '#fbbf24' },
  jobHeaderRight: {
    textAlign: 'center', background: 'rgba(255,255,255,0.1)',
    borderRadius: '0.5rem', padding: '0.75rem 1.25rem',
  },
  stepsCount: { fontSize: '2rem', fontWeight: 800 },
  stepsLabel: { fontSize: '0.75rem', color: '#94a3b8', letterSpacing: '0.05em' },
  stepsSection: { marginBottom: '1.5rem' },
  sectionTitle: {
    fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.1em',
    color: '#64748b', marginBottom: '1rem', paddingBottom: '0.5rem',
    borderBottom: '2px solid #e2e8f0',
  },
  stepRow: {
    display: 'flex', alignItems: 'center', gap: '1.5rem',
    padding: '1rem 1.25rem', marginBottom: '0.75rem',
    border: '1px solid #e2e8f0', borderRadius: '0.75rem',
    background: '#fff',
  },
  stepInfo: { flex: 1, minWidth: 0 },
  stepSeq: { fontSize: '0.7rem', fontWeight: 700, color: '#64748b', letterSpacing: '0.08em', marginBottom: '0.25rem' },
  stepName: { fontSize: '1rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' },
  stepMeta: { fontSize: '0.75rem', color: '#64748b' },
  qrBlock: { textAlign: 'center', flexShrink: 0 },
  qrLabel: { fontSize: '0.7rem', fontWeight: 700, color: '#2563eb', letterSpacing: '0.05em', marginBottom: '0.4rem' },
  qrWrapper: {
    padding: '0.5rem', background: '#fff',
    border: '1px solid #e2e8f0', borderRadius: '0.5rem',
    display: 'inline-block',
  },
  qrHint: { fontSize: '0.65rem', color: '#94a3b8', marginTop: '0.3rem' },
  cardFooter: {
    display: 'flex', justifyContent: 'space-between',
    padding: '0.75rem 0', borderTop: '1px solid #e2e8f0',
    fontSize: '0.7rem', color: '#94a3b8',
  },
}
