/**
 * frontend/src/components/onboarding/TourButton.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * A small circular "?" button rendered in the top header bar. Clicking it resets the
 * onboarding tour to the beginning — clearing all seen stops from localStorage and
 * restarting the CoachMark sequence. Wrapped in a Tooltip that says "Restart onboarding
 * tour". Rendered by Layout.tsx in the header. Tiny file, single responsibility.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : TourButton (default export)
 * Type         : React component
 * Purpose      : Header button to restart the onboarding tour.
 * Parameters   : none
 * Returns      : JSX.Element — circular "?" button with tooltip
 * Calls        : useOnboarding().resetTour() on click
 * DB/API       : none
 * Side effects : clears onboarding localStorage key via resetTour()
 *
 * WHO CALLS THIS FILE
 * - frontend/src/components/Layout.tsx — rendered in the header bar
 *
 * INTERN NOTES
 * - resetTour() is defined in OnboardingContext.tsx — it removes the localStorage
 *   key and resets seenStops to an empty Set. CoachMarks will re-appear on the
 *   next page navigation.
 * - The button has aria-label for accessibility — keep it.
 * - Design Principle 11: no props, no types to maintain here.
 */

// Small "?" button for the header. Resets the onboarding tour on click.

import { useOnboarding } from './OnboardingContext'
import Tooltip from './Tooltip'

export default function TourButton() {
  const { resetTour } = useOnboarding()

  return (
    <Tooltip content="Restart onboarding tour" position="bottom">
      <button
        onClick={resetTour}
        aria-label="Restart onboarding tour"
        className="
          inline-flex items-center justify-center
          h-7 w-7 rounded-full
          border border-gray-300
          text-sm font-semibold text-gray-500
          hover:text-blue-600 hover:border-blue-400
          transition-colors focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-offset-1
        "
      >
        ?
      </button>
    </Tooltip>
  )
}
