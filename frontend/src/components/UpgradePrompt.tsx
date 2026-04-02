/**
 * frontend/src/components/UpgradePrompt.tsx — v3.7
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * A modal dialog shown when a user attempts to access a feature that is not enabled
 * on their account. Introduced in v3.7 as part of the feature flag system. It uses
 * a warm, non-threatening tone — "Not active yet" rather than "Upgrade required" —
 * because the primary CTA for Indian MSME users is a WhatsApp message to the ZetaOps
 * team, not a self-serve payment flow. Sits in the shared components layer; called
 * from any page or component that detects a disabled feature and wants to show the
 * user a path to enabling it.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines FEATURE_COPY map: feature flag key → { title, description }.
 *    Contains copy for: scheduler, gantt, qr_scan, step_intelligence, csv_import, ai_copilot.
 * 2. Defines WHATSAPP_NUMBER constant — the WhatsApp number users contact to enable features.
 * 3. Renders a fixed-position modal with a semi-transparent backdrop.
 * 4. Shows a Lock icon, "Not active yet" label, feature title, and description.
 * 5. Renders a WhatsApp CTA button that opens wa.me with a pre-filled message
 *    naming the specific feature the user wants to enable.
 * 6. Renders a "Maybe later" dismiss button.
 * 7. Clicking the backdrop also dismisses the modal (calls onClose).
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : UpgradePrompt (default export)
 * Type         : React component
 * Purpose      : Feature gate modal with a WhatsApp CTA for enabling features.
 *                Uses friendly copy and a warm tone appropriate for Indian MSME users.
 *                The feature prop determines which copy from FEATURE_COPY is shown.
 * Parameters   : feature: string — the feature flag key e.g. 'scheduler', 'gantt'
 *                onClose: () => void — called when user dismisses the modal
 * Returns      : JSX.Element — fixed-position modal with backdrop
 * Calls        : nothing — all actions are links/buttons with no API calls
 * DB/API       : none
 * Side effects : opens WhatsApp (external link) on CTA click, calls onClose on dismiss
 *
 * WHO CALLS THIS FILE
 * - Any page or component that checks feature flags and wants to show a gate:
 *   e.g. frontend/src/pages/GanttPage.tsx, frontend/src/scheduler/SchedulerToolbar.tsx
 * - Typically called when require_feature() returns a non-null response and the
 *   frontend interprets it as a feature-disabled signal.
 *
 * IMPORTS EXPLAINED
 * - X, Lock from 'lucide-react': Close button icon and lock icon in the modal header.
 *
 * INTERN NOTES
 * - WHATSAPP_NUMBER must be updated to the real ZetaOps business WhatsApp number
 *   before going to production. It is currently a placeholder.
 * - FEATURE_COPY keys must match the feature flag keys used in FEATURE_FLAGS
 *   (backend/app/features_config.py). If a key is missing, the modal falls back
 *   to generic copy ("This Feature / This feature is not active on your account yet").
 * - The WhatsApp link uses wa.me format with a pre-filled URL-encoded message.
 *   The message names the feature title — e.g. "I'd like to enable the Auto-Scheduler".
 * - Design Principle 8: This component is the frontend face of feature flag gating.
 *   It should be shown whenever a feature-gated action is attempted.
 * - e.stopPropagation() on the modal div prevents backdrop click from closing when
 *   the user clicks inside the modal. Always keep this — removing it makes the modal
 *   impossible to interact with.
 * - If new features are added to FEATURE_FLAGS, add matching copy to FEATURE_COPY here.
 *   Missing copy shows generic text which is confusing for users.
 */

import { X, Lock } from 'lucide-react'

// ── Feature copy map ───────────────────────────────────────────────────────
const FEATURE_COPY: Record<string, { title: string; description: string }> = {
  scheduler: {
    title: 'Auto-Scheduler',
    description:
      'Plan your entire production week in one click. The scheduler assigns jobs to employees and machines automatically, avoiding conflicts and meeting deadlines.',
  },
  gantt: {
    title: 'Production Timeline',
    description:
      'See all your jobs on a visual timeline. Spot bottlenecks, track progress, and plan ahead at a glance.',
  },
  qr_scan: {
    title: 'QR Scan & Print Job Cards',
    description:
      'Print job cards with QR codes for each step. Workers scan to start and complete steps directly from the shop floor — no calls to the manager needed.',
  },
  step_intelligence: {
    title: 'Step Intelligence',
    description:
      'Break jobs into steps with sequence, duration, and status tracking. Know exactly where each job is in production at any moment.',
  },
  csv_import: {
    title: 'CSV / Excel Import',
    description:
      'Bulk-upload employees, machines, and jobs from your existing Excel sheets. No manual entry needed.',
  },
  ai_copilot: {
    title: 'AI Copilot',
    description:
      'Ask questions about your jobs, deadlines, and resources in plain language. Get instant answers based on your live production data.',
  },
}

const WHATSAPP_NUMBER = '919845539868' // ← Replace with actual ZetaOps WhatsApp number

// ── Component ──────────────────────────────────────────────────────────────
interface UpgradePromptProps {
  feature: string
  onClose: () => void
}

export default function UpgradePrompt({ feature, onClose }: UpgradePromptProps) {
  const copy = FEATURE_COPY[feature] ?? {
    title: 'This Feature',
    description: 'This feature is not active on your account yet.',
  }

  const waMessage = encodeURIComponent(
    `Hi, I'd like to enable the ${copy.title} feature on my ZetaOps Copilot account.`
  )
  const waLink = `https://wa.me/${WHATSAPP_NUMBER}?text=${waMessage}`

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={onClose}
    >
      <div
        className="relative bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6"
        onClick={e => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors"
        >
          <X size={18} />
        </button>

        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center shrink-0">
            <Lock size={18} className="text-blue-500" />
          </div>
          <div>
            <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">
              Not active yet
            </p>
            <h2 className="text-base font-semibold text-gray-800">{copy.title}</h2>
          </div>
        </div>

        <p className="text-sm text-gray-600 leading-relaxed mb-5">
          {copy.description}
        </p>

        <div className="flex flex-col gap-2">
          <a
            href={waLink}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 w-full py-2.5 bg-green-500 hover:bg-green-600 text-white text-sm font-medium rounded-xl transition-colors"
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4 fill-white" xmlns="http://www.w3.org/2000/svg">
              <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
            </svg>
            Contact us on WhatsApp to enable
          </a>
          <button
            onClick={onClose}
            className="w-full py-2.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            Maybe later
          </button>
        </div>
      </div>
    </div>
  )
}
