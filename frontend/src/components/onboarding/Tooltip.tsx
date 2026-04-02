/**
 * frontend/src/components/onboarding/Tooltip.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * A styled hover tooltip component. Replaces the native browser title attribute with
 * a consistently styled dark bubble. Used by TourButton and any component that needs
 * a hover explanation without the browser's plain tooltip. Supports four positions.
 * Shows with a 300ms delay to avoid flicker on mouse-over. Pure presentational —
 * no state management, no API calls.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Wraps children in a relative inline-block div.
 * 2. On mouseenter: starts a 300ms timer, sets visible=true after delay.
 * 3. On mouseleave: clears the timer, sets visible=false immediately.
 * 4. When visible: renders an absolute-positioned dark bubble with the content string
 *    and a CSS triangle arrow pointing back at the anchor.
 * 5. Position prop controls which side the bubble appears on.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : Tooltip (default export)
 * Type         : React component
 * Purpose      : Hover tooltip with configurable position and 300ms show delay.
 * Parameters   : content: string — text to display in the bubble
 *                children: ReactNode — the element that triggers the tooltip on hover
 *                position?: 'top'|'bottom'|'left'|'right' — default 'top'
 * Returns      : JSX.Element
 * Calls        : nothing
 * DB/API       : none
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/components/onboarding/TourButton.tsx
 * - Any component needing a hover tooltip
 * - frontend/src/components/onboarding/index.ts — re-exports it
 *
 * INTERN NOTES
 * - pointer-events-none on the tooltip bubble prevents it from interfering with
 *   mouse events on nearby elements.
 * - The 300ms delay (SHOW_DELAY_MS) prevents the tooltip from flickering when the
 *   mouse passes over a button quickly. Do not set to 0.
 * - max-w-48 on the bubble limits width. Long content strings will wrap.
 * - Design Principle 11: TooltipProps is typed — never pass non-string content.
 */

// Styled hover tooltip — not the native browser `title` attribute.

import {
  useRef,
  useState,
  type ReactNode,
} from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

type Position = 'top' | 'bottom' | 'left' | 'right'

interface TooltipProps {
  content: string
  children: ReactNode
  position?: Position
}

// ── Position styles ───────────────────────────────────────────────────────────

const containerPositionClass: Record<Position, string> = {
  top:    'bottom-full left-1/2 -translate-x-1/2 mb-2',
  bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
  left:   'right-full top-1/2 -translate-y-1/2 mr-2',
  right:  'left-full top-1/2 -translate-y-1/2 ml-2',
}

// Arrow positioned on the side facing the anchor element
const arrowClass: Record<Position, string> = {
  top:    'absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-800',
  bottom: 'absolute bottom-full left-1/2 -translate-x-1/2 border-4 border-transparent border-b-gray-800',
  left:   'absolute left-full top-1/2 -translate-y-1/2 border-4 border-transparent border-l-gray-800',
  right:  'absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-gray-800',
}

// ── Component ─────────────────────────────────────────────────────────────────

const SHOW_DELAY_MS = 300

export default function Tooltip({
  content,
  children,
  position = 'top',
}: TooltipProps) {
  const [visible, setVisible] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function handleMouseEnter() {
    timerRef.current = setTimeout(() => setVisible(true), SHOW_DELAY_MS)
  }

  function handleMouseLeave() {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    setVisible(false)
  }

  return (
    <div
      className="relative inline-block"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {children}

      {visible && (
        <div
          className={`absolute z-50 pointer-events-none ${containerPositionClass[position]}`}
        >
          {/* Bubble */}
          <div className="relative bg-gray-800 text-white text-xs rounded px-2 py-1 max-w-48 whitespace-normal text-center shadow-lg">
            {content}
            {/* Arrow */}
            <span className={arrowClass[position]} />
          </div>
        </div>
      )}
    </div>
  )
}
