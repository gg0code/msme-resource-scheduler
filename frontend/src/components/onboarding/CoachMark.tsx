// src/components/onboarding/CoachMark.tsx
// First-visit guided coach mark. Auto-shows on mount if the stop hasn't been seen.
// Supports sequential page tours - only the first unseen stop on the page is active.

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useOnboarding } from './OnboardingContext'

// -- Types ---------------------------------------------------------------------

type Position = 'top' | 'bottom' | 'left' | 'right'

interface CoachMarkProps {
  id: string
  title: string
  description: string
  position?: Position
  children: ReactNode
  step?: number
  totalSteps?: number
}

// -- Popover positioning -------------------------------------------------------

// The popover card is placed relative to the wrapper div
const popoverPositionClass: Record<Position, string> = {
  top:    'bottom-full left-1/2 -translate-x-1/2 mb-3',
  bottom: 'top-full left-1/2 -translate-x-1/2 mt-3',
  left:   'right-full top-1/2 -translate-y-1/2 mr-3',
  right:  'left-full top-1/2 -translate-y-1/2 ml-3',
}

// Arrow pointing back toward the anchor
const arrowClass: Record<Position, string> = {
  top:    'absolute top-full left-1/2 -translate-x-1/2 border-8 border-transparent border-t-white drop-shadow-sm',
  bottom: 'absolute bottom-full left-1/2 -translate-x-1/2 border-8 border-transparent border-b-white drop-shadow-sm',
  left:   'absolute left-full top-1/2 -translate-y-1/2 border-8 border-transparent border-l-white drop-shadow-sm',
  right:  'absolute right-full top-1/2 -translate-y-1/2 border-8 border-transparent border-r-white drop-shadow-sm',
}

// -- Page-level registry so only the first unseen stop is active ---------------
// Each stop registers itself; the one with the lowest registration order wins.

const pageRegistry: Map<string, number> = new Map()
let registrationCounter = 0

function useIsFirstUnseen(id: string, seen: boolean): boolean {
  const orderRef = useRef<number | null>(null)
  const [firstUnseen, setFirstUnseen] = useState(false)

  // Register this stop on mount, unregister on unmount
  useEffect(() => {
    if (orderRef.current === null) {
      orderRef.current = registrationCounter++
    }
    pageRegistry.set(id, orderRef.current)

    return () => {
      pageRegistry.delete(id)
    }
  }, [id])

  // Recalculate whenever seen changes
  useEffect(() => {
    if (seen) {
      setFirstUnseen(false)
      return
    }

    // Find the unseen stop with the smallest registration order
    let minOrder = Infinity
    pageRegistry.forEach((order, _stopId) => {
      // We consider a stop "unseen" if it's not in the registry as seen
      // The parent context tracks that - here we just look at order
      if (order < minOrder) minOrder = order
    })

    setFirstUnseen(orderRef.current === minOrder)
  }, [seen, id])

  return firstUnseen
}

// -- Component -----------------------------------------------------------------

export default function CoachMark({
  id,
  title,
  description,
  position = 'bottom',
  children,
  step,
  totalSteps,
}: CoachMarkProps) {
  const { isSeen, markSeen } = useOnboarding()
  const seen = isSeen(id)

  // isActive: this stop is not seen AND it's the first unseen stop on the page
  const isFirst = useIsFirstUnseen(id, seen)
  const isActive = !seen && isFirst

  // Scroll into view when this stop becomes active
  const wrapperRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (isActive && wrapperRef.current) {
      wrapperRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [isActive])

  // Pass-through when already seen
  if (seen) {
    return <>{children}</>
  }

  return (
    <div ref={wrapperRef} className="relative inline-block">
      {/* Highlight ring around the target element */}
      <div
        className={
          isActive
            ? 'rounded ring-2 ring-blue-400 ring-offset-2'
            : ''
        }
      >
        {children}
      </div>

      {/* Popover - only shown when this is the active stop */}
      {isActive && (
        <>
          {/* Backdrop scrim to draw focus */}
          <div className="fixed inset-0 z-40 bg-black/10 pointer-events-none" />

          <div
            className={`absolute z-50 ${popoverPositionClass[position]}`}
            // Keep popover within viewport horizontally for left/right positions
          >
            <div className="relative bg-white rounded-lg shadow-xl border border-gray-100 p-4 w-64">
              {/* Arrow */}
              <span className={arrowClass[position]} />

              {/* Step counter */}
              {step !== undefined && totalSteps !== undefined && (
                <p className="text-xs text-blue-500 font-medium mb-1">
                  {step} of {totalSteps}
                </p>
              )}

              {/* Title */}
              <p className="font-semibold text-gray-900 text-sm mb-1">{title}</p>

              {/* Description */}
              <p className="text-xs text-gray-600 mb-3 leading-relaxed">{description}</p>

              {/* Dismiss button */}
              <button
                onClick={() => markSeen(id)}
                className="inline-flex items-center gap-1 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 px-3 py-1.5 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-1"
              >
                Got it →
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
