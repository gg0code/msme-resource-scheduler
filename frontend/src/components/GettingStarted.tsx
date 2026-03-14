// src/components/GettingStarted.tsx — V3.8
//
// Getting Started checklist widget shown on the Dashboard for new users.
// Derives completion state from real app data — no manual marking.
// Auto-hides once all 5 steps are complete (with a brief celebration).
// Permanently dismisses on X click or on completion.
//
// Usage:
//   <GettingStarted
//     employeeCount={employees}
//     machineCount={machines}
//     jobCount={jobs}
//     assignedJobCount={assignedJobs}
//     activeJobCount={activeJobs}
//   />

import { useNavigate } from 'react-router-dom'
import { CheckCircle2, Circle, X, ChevronRight } from 'lucide-react'
import { useOnboarding } from '../hooks/useOnboarding'

interface Props {
  employeeCount:    number
  machineCount:     number
  jobCount:         number
  assignedJobCount: number
  activeJobCount:   number
}

interface Step {
  key:         keyof ReturnType<typeof useOnboarding>['steps']
  label:       string
  description: string
  action:      string
  path:        string
}

const STEPS: Step[] = [
  {
    key:         'add_employee',
    label:       'Add your first employee',
    description: 'Add the workers who will be assigned to jobs.',
    action:      'Go to Employees',
    path:        '/employees',
  },
  {
    key:         'add_machine',
    label:       'Add your first machine',
    description: 'Register the machines used in your production.',
    action:      'Go to Machines',
    path:        '/machines',
  },
  {
    key:         'create_job',
    label:       'Create your first job',
    description: 'Add the work order you need to track.',
    action:      'Go to Jobs',
    path:        '/jobs',
  },
  {
    key:         'assign_resources',
    label:       'Assign employee and machine to a job',
    description: 'Open a job and click Assign to link resources.',
    action:      'Go to Jobs',
    path:        '/jobs',
  },
  {
    key:         'mark_in_progress',
    label:       'Mark a job as In Progress',
    description: 'Start the timer on a job to begin tracking production.',
    action:      'Go to Dashboard',
    path:        '/dashboard',
  },
]

export default function GettingStarted({
  employeeCount, machineCount, jobCount, assignedJobCount, activeJobCount,
}: Props) {
  const navigate = useNavigate()
  const onboarding = useOnboarding({
    employeeCount,
    machineCount,
    jobCount,
    assignedJobCount,
    activeJobCount,
  })

  // Don't render if dismissed
  if (onboarding.dismissed) return null

  const pct = Math.round((onboarding.completedCount / 5) * 100)

  return (
    <div className="bg-white border border-blue-100 rounded-2xl shadow-sm overflow-hidden">

      {/* Header */}
      <div className="px-5 py-4 bg-gradient-to-r from-blue-50 to-white flex items-start justify-between">
        <div>
          <h3 className="text-sm font-bold text-blue-900">
            {onboarding.allComplete ? '🎉 You\'re all set!' : '👋 Getting Started'}
          </h3>
          <p className="text-xs text-blue-600 mt-0.5">
            {onboarding.allComplete
              ? 'Your shop floor is ready. Have a great production day!'
              : `${onboarding.completedCount} of 5 steps complete`
            }
          </p>
        </div>
        <button
          onClick={onboarding.dismiss}
          className="text-gray-400 hover:text-gray-600 transition-colors mt-0.5"
          title="Dismiss"
        >
          <X size={16} />
        </button>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-gray-100">
        <div
          className="h-full bg-blue-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Steps */}
      <div className="divide-y divide-gray-50">
        {STEPS.map((step) => {
          const done = onboarding.steps[step.key]
          return (
            <div
              key={step.key}
              className={`flex items-center gap-3 px-5 py-3 transition-colors
                ${done ? 'opacity-50' : 'hover:bg-blue-50/40 cursor-pointer'}`}
              onClick={() => !done && navigate(step.path)}
            >
              {/* Check icon */}
              <div className="shrink-0">
                {done
                  ? <CheckCircle2 size={18} className="text-green-500" />
                  : <Circle      size={18} className="text-gray-300" />
                }
              </div>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${done ? 'line-through text-gray-400' : 'text-gray-800'}`}>
                  {step.label}
                </p>
                {!done && (
                  <p className="text-xs text-gray-400 mt-0.5">{step.description}</p>
                )}
              </div>

              {/* Arrow */}
              {!done && (
                <ChevronRight size={15} className="text-gray-300 shrink-0" />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
