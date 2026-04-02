/**
 * ScanPage.tsx - Block 2 V3.1
 * Mobile-first QR scan execution page.
 * Route: /scan?token=...
 * No login required. No navbar.
 */

import { useEffect, useState, type CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

type PageState =
  | { stage: 'loading' }
  | { stage: 'confirm'; action: string; stepName: string; jobName: string; canExecute: boolean; reason?: string }
  | { stage: 'success'; message: string; jobCompleted: boolean; nextStepName?: string }
  | { stage: 'error'; reason: 'expired' | 'invalid' | 'wrong_status' | 'locked' | 'already_complete' | string }

const ACTION_LABEL: Record<string, { verb: string; color: string; emoji: string }> = {
  start_step:    { verb: 'Start',    color: '#2563eb', emoji: '▶️' },
  complete_step: { verb: 'Complete', color: '#16a34a', emoji: '✅' },
}

export default function ScanPage() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const [state, setState] = useState<PageState>({ stage: 'loading' })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!token) {
      setState({ stage: 'error', reason: 'invalid' })
      return
    }
    fetch(`${API}/api/scan/verify?token=${encodeURIComponent(token)}`)
      .then(r => r.json())
      .then(data => {
        if (!data.valid) {
          setState({ stage: 'error', reason: data.reason || 'invalid' })
          return
        }
        setState({
          stage: 'confirm',
          action: data.action,
          stepName: data.step_name,
          jobName: data.job_name,
          canExecute: data.can_execute,
          reason: data.reason,
        })
      })
      .catch(() => setState({ stage: 'error', reason: 'invalid' }))
  }, [token])

  const execute = async () => {
    setSubmitting(true)
    try {
      const res = await fetch(`${API}/api/scan/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      const data = await res.json()
      if (!res.ok) {
        const err = data.detail?.error || 'wrong_status'
        setState({ stage: 'error', reason: err })
        return
      }
      setState({
        stage: 'success',
        message: data.message,
        jobCompleted: data.job_completed,
        nextStepName: data.next_step_name,
      })
    } catch {
      setState({ stage: 'error', reason: 'invalid' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        {/* Header */}
        <div style={styles.header}>
          <span style={styles.logo}>⚙️ ZetaOps Copilot</span>
        </div>

        {state.stage === 'loading' && (
          <div style={styles.center}>
            <div style={styles.spinner} />
            <p style={styles.hint}>Validating QR code...</p>
          </div>
        )}

        {state.stage === 'confirm' && (() => {
          const meta = ACTION_LABEL[state.action] || { verb: 'Execute', color: '#6366f1', emoji: '⚡' }
          return (
            <div>
              <p style={styles.jobLabel}>{state.jobName}</p>
              <h2 style={styles.stepName}>{state.stepName}</h2>

              {state.canExecute ? (
                <>
                  <p style={styles.hint}>
                    {state.action === 'start_step'
                      ? 'Tap the button below to mark this step as started.'
                      : 'Tap the button below to mark this step as complete.'}
                  </p>
                  <button
                    style={{ ...styles.actionBtn, background: meta.color, opacity: submitting ? 0.7 : 1 }}
                    onClick={execute}
                    disabled={submitting}
                  >
                    {submitting ? 'Processing...' : `${meta.emoji} ${meta.verb} Step`}
                  </button>
                </>
              ) : (
                <div style={styles.warningBox}>
                  {state.reason === 'locked' && (
                    <p>🔒 This step is <strong>locked</strong>. Complete the previous step first.</p>
                  )}
                  {state.reason === 'already_complete' && (
                    <p>✅ This step is already <strong>completed</strong>.</p>
                  )}
                  {state.reason === 'wrong_status' && (
                    <p>⚠️ This step cannot be {state.action === 'start_step' ? 'started' : 'completed'} right now.</p>
                  )}
                </div>
              )}
            </div>
          )
        })()}

        {state.stage === 'success' && (
          <div style={styles.center}>
            <div style={styles.successIcon}>
              {state.jobCompleted ? '🎉' : '✅'}
            </div>
            <h2 style={styles.successTitle}>
              {state.jobCompleted ? 'Job Completed!' : 'Done!'}
            </h2>
            <p style={styles.successMsg}>{state.message}</p>
            {state.nextStepName && !state.jobCompleted && (
              <div style={styles.nextBox}>
                <span style={styles.nextLabel}>Next step ready:</span>
                <span style={styles.nextName}>{state.nextStepName}</span>
              </div>
            )}
          </div>
        )}

        {state.stage === 'error' && (
          <div style={styles.center}>
            <div style={styles.errorIcon}>
              {state.reason === 'expired' ? '⏰' : '❌'}
            </div>
            <h2 style={styles.errorTitle}>
              {state.reason === 'expired' ? 'QR Code Expired' : 'Cannot Complete'}
            </h2>
            <p style={styles.errorMsg}>
              {state.reason === 'expired' && 'This QR code has expired. Ask the manager to reprint the job card.'}
              {state.reason === 'invalid' && 'This QR code is invalid or has already been used.'}
              {state.reason === 'wrong_status' && 'This step is not ready to be actioned right now.'}
              {state.reason === 'locked' && 'This step is locked. Complete the previous step first.'}
              {state.reason === 'already_complete' && 'This step is already completed.'}
              {!['expired','invalid','wrong_status','locked','already_complete'].includes(state.reason) && 'Something went wrong. Please try again.'}
            </p>
          </div>
        )}

        <div style={styles.footer}>Shop Floor Scanner · ZetaOps Copilot</div>
      </div>
    </div>
  )
}

// -- Styles --------------------------------------------------------------------
const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: '100vh',
    background: '#f1f5f9',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '1rem',
    fontFamily: 'system-ui, sans-serif',
  },
  card: {
    background: '#fff',
    borderRadius: '1rem',
    padding: '2rem',
    width: '100%',
    maxWidth: '420px',
    boxShadow: '0 4px 24px rgba(0,0,0,0.10)',
  },
  header: {
    marginBottom: '1.5rem',
    borderBottom: '1px solid #e2e8f0',
    paddingBottom: '1rem',
  },
  logo: {
    fontSize: '0.875rem',
    fontWeight: 600,
    color: '#64748b',
    letterSpacing: '0.02em',
  },
  jobLabel: {
    fontSize: '0.875rem',
    color: '#64748b',
    margin: '0 0 0.25rem',
  },
  stepName: {
    fontSize: '1.5rem',
    fontWeight: 700,
    color: '#0f172a',
    margin: '0 0 1rem',
    lineHeight: 1.2,
  },
  hint: {
    color: '#475569',
    fontSize: '0.95rem',
    marginBottom: '1.5rem',
    lineHeight: 1.5,
  },
  actionBtn: {
    width: '100%',
    padding: '1rem',
    border: 'none',
    borderRadius: '0.75rem',
    color: '#fff',
    fontSize: '1.1rem',
    fontWeight: 700,
    cursor: 'pointer',
    letterSpacing: '0.01em',
    transition: 'opacity 0.15s',
  },
  warningBox: {
    background: '#fef3c7',
    border: '1px solid #fbbf24',
    borderRadius: '0.75rem',
    padding: '1rem 1.25rem',
    color: '#92400e',
    fontSize: '0.95rem',
    lineHeight: 1.5,
  },
  center: {
    textAlign: 'center',
    padding: '1rem 0',
  },
  spinner: {
    width: '48px',
    height: '48px',
    border: '4px solid #e2e8f0',
    borderTop: '4px solid #3b82f6',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
    margin: '0 auto 1rem',
  },
  successIcon: { fontSize: '4rem', marginBottom: '0.75rem' },
  successTitle: { fontSize: '1.5rem', fontWeight: 700, color: '#15803d', margin: '0 0 0.5rem' },
  successMsg: { color: '#475569', fontSize: '0.95rem', lineHeight: 1.5 },
  nextBox: {
    marginTop: '1.25rem',
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
    borderRadius: '0.75rem',
    padding: '0.75rem 1rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  nextLabel: { fontSize: '0.75rem', color: '#3b82f6', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' },
  nextName: { fontSize: '1rem', fontWeight: 600, color: '#1e40af' },
  errorIcon: { fontSize: '4rem', marginBottom: '0.75rem' },
  errorTitle: { fontSize: '1.5rem', fontWeight: 700, color: '#dc2626', margin: '0 0 0.5rem' },
  errorMsg: { color: '#475569', fontSize: '0.95rem', lineHeight: 1.5 },
  footer: {
    marginTop: '2rem',
    paddingTop: '1rem',
    borderTop: '1px solid #f1f5f9',
    fontSize: '0.75rem',
    color: '#94a3b8',
    textAlign: 'center',
  },
}
