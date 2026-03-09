// src/components/onboarding/TourButton.tsx
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
