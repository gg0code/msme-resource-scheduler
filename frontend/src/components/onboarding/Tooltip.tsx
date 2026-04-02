// frontend/src/components/onboarding/Tooltip.tsx
// Styled hover tooltip with 300ms delay. Pure presentational.

import {
  useRef,
  useState,
  type ReactNode,
} from 'react'

// -- Types ---------------------------------------------------------------------

type Position = 'top' | 'bottom' | 'left' | 'right'

interface TooltipProps {
  content: string
  children: ReactNode
  position?: Position
}

// -- Position styles -----------------------------------------------------------

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

// -- Component -----------------------------------------------------------------

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
