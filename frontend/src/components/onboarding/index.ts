/**
 * frontend/src/components/onboarding/index.ts
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Barrel export file for the onboarding sub-system. Re-exports all public symbols
 * from the onboarding folder so consumers can import from one path instead of five.
 * App.tsx imports OnboardingProvider from here. Layout.tsx imports GettingStarted
 * and TourButton from here. Any component using CoachMark or Tooltip imports from here.
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — imports OnboardingProvider
 * - frontend/src/components/Layout.tsx — imports GettingStarted, TourButton
 * - Any component using CoachMark or Tooltip
 */
export { OnboardingProvider, useOnboarding } from './OnboardingContext'
export { default as Tooltip } from './Tooltip'
export { default as CoachMark } from './CoachMark'
export { default as TourButton } from './TourButton'
export { default as GettingStarted } from './GettingStarted'
