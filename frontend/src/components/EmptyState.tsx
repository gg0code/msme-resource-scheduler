// frontend/src/components/EmptyState.tsx - v3.8
// Reusable empty state with icon, title, description, optional action button.

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
