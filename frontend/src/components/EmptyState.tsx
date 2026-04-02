/**
 * frontend/src/components/EmptyState.tsx — v3.8
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * A reusable zero-data placeholder component shown whenever a page or section
 * has no data to display. Introduced in v3.8 to replace silent blank tables and
 * empty divs with a consistent, friendly prompt that guides the user to take the
 * first action. Used across Employees, Machines, Skills, Jobs, and any other page
 * that can have an empty state. Sits in the shared components layer — no page logic,
 * no API calls, pure presentational.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines EmptyStateProps interface with icon, title, description, and optional
 *    actionLabel + onAction for a call-to-action button.
 * 2. Renders a centered column layout: icon box → title → description → button.
 * 3. Icon is wrapped in a rounded box with a subtle gray background.
 * 4. Action button only renders if both actionLabel and onAction are provided.
 * 5. All styling uses TailwindCSS utility classes.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : EmptyState (default export)
 * Type         : React component
 * Purpose      : Displays a friendly empty state with an icon, title, description,
 *                and optional action button. Used when a list or table has no rows
 *                to show. Prevents blank white screens that confuse new users.
 * Parameters   : icon: ReactNode — any icon component (e.g. <Users size={32} />)
 *                title: string — short headline e.g. "No employees yet"
 *                description: string — one-line guidance e.g. "Add employees to assign them to jobs"
 *                actionLabel?: string — button text e.g. "Add First Employee"
 *                onAction?: () => void — callback when button is clicked
 * Returns      : JSX.Element — centered flex column layout
 * Calls        : nothing — pure presentational
 * DB/API       : none
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/pages/Employees.tsx
 * - frontend/src/pages/Machines.tsx
 * - frontend/src/pages/Skills.tsx
 * - frontend/src/pages/Jobs.tsx
 * - Any page that renders a list and needs an empty state fallback
 *
 * IMPORTS EXPLAINED
 * - ReactNode from 'react': Type for the icon prop — accepts any JSX element,
 *   including Lucide icon components passed as <Users size={32} />.
 *
 * INTERN NOTES
 * - The action button only renders when BOTH actionLabel AND onAction are provided.
 *   Passing only one of them silently shows no button — this is intentional for
 *   read-only contexts (e.g. viewer role cannot create employees).
 * - The icon prop accepts any ReactNode — not just Lucide icons. You can pass an
 *   <img>, an emoji span, or any custom SVG.
 * - Design Principle 11: This file has no TypeScript issues. The ReactNode type
 *   import uses 'import type' to satisfy strict mode.
 * - Do not add API calls or business logic here. If a page needs to check whether
 *   the empty state is due to a filter vs truly no data, handle that in the page
 *   component and conditionally render EmptyState with different props.
 * - If the button does not appear: check that both actionLabel and onAction are
 *   passed. A missing onAction prop (even with actionLabel set) skips the button.
 */

import { type ReactNode } from 'react'

interface EmptyStateProps {
  icon:        ReactNode
  title:       string
  description: string
  actionLabel?: string
  onAction?:   () => void
}

export default function EmptyState({
  icon, title, description, actionLabel, onAction,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-gray-50 border border-gray-100 flex items-center justify-center text-gray-300 mb-4">
        {icon}
      </div>
      <h3 className="text-sm font-semibold text-gray-700 mb-1">{title}</h3>
      <p className="text-sm text-gray-400 max-w-xs leading-relaxed mb-5">{description}</p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-xl transition-colors"
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}
