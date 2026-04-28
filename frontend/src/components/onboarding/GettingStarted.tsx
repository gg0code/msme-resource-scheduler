// src/components/onboarding/GettingStarted.tsx - v4.1
//
// Persistent getting started checklist for first-time users.
// Shows a collapsible panel with logical onboarding steps.
// Auto-detects completion by checking TanStack Query cache.
// Persists dismissed/completed state per user in localStorage.
//
// Steps follow the logical order:
//   1. Add Skills → 2. Add Employees → 3. Add Machines →
//   4. Create first Job → 5. Assign resources → 6. Run Auto-Schedule →
//   7. Check Dashboard → 8. Try AI Copilot

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Circle, ChevronDown, ChevronUp, X, Rocket, RotateCcw } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { useLabels } from '../../context/IndustryContext'
import { useOnboarding } from './OnboardingContext'

// -- Storage helpers -----------------------------------------------------------

function dismissedKey(userId: number) { return `gs_dismissed_${userId}` }
function isDismissed(userId: number) {
  try { return localStorage.getItem(dismissedKey(userId)) === '1' } catch { return false }
}
function persistDismissed(userId: number) {
  try { localStorage.setItem(dismissedKey(userId), '1') } catch { /* storage full or blocked - dismissal is non-critical */ }
}
function clearDismissed(userId: number) {
  try { localStorage.removeItem(dismissedKey(userId)) } catch { /* storage blocked - non-critical */ }
}

// -- Step definition -----------------------------------------------------------

interface Step {
  id:          string
  label:       string
  description: string
  route:       string
  checkKey:    string | null   // TanStack Query key to check for data
}

// -- Component -----------------------------------------------------------------

export default function GettingStarted() {
  const { user }      = useAuth()
  const labels        = useLabels()
  const qc            = useQueryClient()
  const navigate      = useNavigate()
  const { resetTour } = useOnboarding()

  const [collapsed,  setCollapsed]  = useState(false)
  const [dismissed,  setDismissedState] = useState(false)
  const [, setTick] = useState(0)   // write-only - forces re-render to recheck cache

  // Load dismissed state on mount
  useEffect(() => {
    if (user) setDismissedState(isDismissed(user.id))
  }, [user?.id])

  // Recheck completion every 3 seconds while panel is open
  useEffect(() => {
    if (dismissed || collapsed) return
    const t = setInterval(() => setTick(n => n + 1), 3000)
    return () => clearInterval(t)
  }, [dismissed, collapsed])

  // Define steps using industry labels
  const steps: Step[] = [
    {
      id: 'skills', route: '/skills',
      label: `Add your ${labels.skills}`,
      description: `${labels.skills} link ${labels.jobs.toLowerCase()} to the right ${labels.employees.toLowerCase()}.`,
      checkKey: 'skills',
    },
    {
      id: 'employees', route: '/employees',
      label: `Add ${labels.employees}`,
      description: `Add your ${labels.employees.toLowerCase()} with their roles and ${labels.skills.toLowerCase()}.`,
      checkKey: 'employees',
    },
    {
      id: 'machines', route: '/machines',
      label: `Add ${labels.machines}`,
      description: `Register your ${labels.machines.toLowerCase()} with hourly costs and location.`,
      checkKey: 'machines',
    },
    {
      id: 'job', route: '/jobs',
      label: `Create your first ${labels.job}`,
      description: `Add a ${labels.job.toLowerCase()} with dates, priority and ${labels.materials.toLowerCase()}.`,
      checkKey: 'jobs',
    },
    {
      id: 'assign', route: '/jobs',
      label: `Assign resources to a ${labels.job}`,
      description: `Link ${labels.employees.toLowerCase()} and ${labels.machines.toLowerCase()} to your ${labels.job.toLowerCase()}.`,
      checkKey: null,   // manual check - hard to auto-detect
    },
    {
      id: 'schedule', route: '/jobs',
      label: 'Run Auto-Schedule',
      description: `Go to Jobs page then click the Auto-Schedule button in the top bar.`,
      checkKey: 'schedule-entries',
    },
    {
      id: 'dashboard', route: '/dashboard',
      label: 'Check your Dashboard',
      description: `See live KPIs, alerts, and ${labels.jobs.toLowerCase()} status at a glance.`,
      checkKey: null,
    },
    {
      id: 'ai', route: '/dashboard',
      label: 'Try the AI Copilot',
      description: `Ask about your ${labels.jobs.toLowerCase()}, ${labels.materials.toLowerCase()}, or schedule.`,
      checkKey: null,
    },
  ]

  // Auto-detect completion from query cache
  function isComplete(step: Step): boolean {
    // Manual steps - check localStorage
    const manualKey = `gs_done_${user?.id}_${step.id}`
    try { if (localStorage.getItem(manualKey) === '1') return true } catch { /* storage blocked - fall through to query-cache check */ }

    if (!step.checkKey) return false
    const data = qc.getQueryData<unknown[]>([step.checkKey])
    return Array.isArray(data) && data.length > 0
  }

  function markManualDone(stepId: string) {
    if (!user) return
    try { localStorage.setItem(`gs_done_${user.id}_${stepId}`, '1') } catch { /* storage blocked - tick still triggers re-render so UI reflects intent */ }
    setTick(n => n + 1)
  }

  function handleDismiss() {
    if (user) persistDismissed(user.id)
    setDismissedState(true)
  }

  function handleReset() {
    if (!user) return
    resetTour()
    clearDismissed(user.id)
    // Clear manual done flags
    steps.forEach(s => {
      try { localStorage.removeItem(`gs_done_${user.id}_${s.id}`) } catch { /* storage blocked - reset still proceeds for in-memory state */ }
    })
    setDismissedState(false)
    setTick(n => n + 1)
  }

  const completedCount = steps.filter(s => isComplete(s)).length
  const allDone        = completedCount === steps.length
  const pct            = Math.round((completedCount / steps.length) * 100)

  // Auto-dismiss when all steps done (after a short delay)
  useEffect(() => {
    if (allDone) {
      const t = setTimeout(() => { if (user) { persistDismissed(user.id); setDismissedState(true) } }, 5000)
      return () => clearTimeout(t)
    }
  }, [allDone, user])

  if (dismissed || !user) return null

  return (
    <div className="fixed bottom-6 left-4 z-20 w-72 bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden">

      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer select-none"
        style={{ backgroundColor: 'var(--brand-primary)', opacity: 1 }}
        onClick={() => setCollapsed(c => !c)}
      >
        <div className="flex items-center gap-2">
          <Rocket size={15} className="text-white" />
          <span className="text-white text-sm font-semibold">Getting Started</span>
          <span className="text-white/70 text-xs">{completedCount}/{steps.length}</span>
        </div>
        <div className="flex items-center gap-2">
          {collapsed
            ? <ChevronUp size={14} className="text-white/80" />
            : <ChevronDown size={14} className="text-white/80" />
          }
          <button
            onClick={e => { e.stopPropagation(); handleDismiss() }}
            className="text-white/70 hover:text-white"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Progress bar */}
      {!collapsed && (
        <div className="h-1 bg-gray-100">
          <div
            className="h-full transition-all duration-500"
            style={{ width: `${pct}%`, backgroundColor: 'var(--brand-primary)' }}
          />
        </div>
      )}

      {/* Steps list */}
      {!collapsed && (
        <div className="max-h-80 overflow-y-auto">
          {allDone ? (
            <div className="px-4 py-6 text-center">
              <p className="text-2xl mb-2">🎉</p>
              <p className="text-sm font-semibold text-gray-800">All done!</p>
              <p className="text-xs text-gray-500 mt-1">Closing in a moment…</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-50">
              {steps.map((step, idx) => {
                const done = isComplete(step)
                return (
                  <div
                    key={step.id}
                    className={`flex items-start gap-3 px-4 py-3 transition-colors ${
                      done ? 'opacity-50' : 'hover:bg-gray-50'
                    }`}
                  >
                    {/* Check icon */}
                    <div className="shrink-0 mt-0.5">
                      {done
                        ? <CheckCircle2 size={16} className="text-green-500" />
                        : <Circle size={16} className="text-gray-300" />
                      }
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <p className={`text-xs font-semibold leading-tight ${done ? 'line-through text-gray-400' : 'text-gray-800'}`}>
                        {idx + 1}. {step.label}
                      </p>
                      {!done && (
                        <p className="text-[11px] text-gray-400 mt-0.5 leading-relaxed">
                          {step.description}
                        </p>
                      )}
                    </div>

                    {/* Go button */}
                    {!done && (
                      <button
                        onClick={() => {
                          navigate(step.route)
                          if (!step.checkKey) markManualDone(step.id)
                        }}
                        className="shrink-0 text-[10px] font-bold px-2 py-1 rounded-md text-white transition-colors"
                        style={{ backgroundColor: 'var(--brand-primary)' }}
                      >
                        Go →
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Footer */}
          <div className="px-4 py-2.5 border-t border-gray-100 flex items-center justify-between">
            <span className="text-[10px] text-gray-400">{pct}% complete</span>
            <button
              onClick={handleReset}
              className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600"
            >
              <RotateCcw size={10} /> Restart tour
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
