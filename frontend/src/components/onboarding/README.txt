AUTO-GENERATED — frontend/src/components/onboarding/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/components/onboarding/
PURPOSE: New-user onboarding tour system — coach marks, checklist, and tour controls.

FILES
  OnboardingContext.tsx — React context managing which tour stops have been seen.
                          Persists per-user in localStorage. Exposes markSeen,
                          resetTour, isSeen, isNewUser via useOnboarding() hook.
                          Branch: both.
  CoachMark.tsx         — Popover that highlights a UI element with a ring, backdrop,
                          and "Got it →" button. Only first unseen stop per page
                          is active at a time. Branch: both.
  GettingStarted.tsx    — Persistent 8-step checklist panel (bottom-left corner).
                          Auto-detects completion from TanStack Query cache.
                          Branch: both.
  Tooltip.tsx           — Styled hover tooltip with 300ms delay and arrow.
                          Pure presentational. Branch: both.
  TourButton.tsx        — "?" button in header bar. Resets tour on click. Branch: both.
  index.ts              — Barrel export for all onboarding symbols. Branch: both.

ARCHITECTURE NOTES
OnboardingContext.tsx is the foundation — all other files depend on it. CoachMark
and GettingStarted both call isSeen/markSeen/resetTour from useOnboarding(). The
context stores stop IDs as a Set<string> in localStorage keyed by user ID. CoachMark
uses a module-level pageRegistry to ensure only the first unseen stop is active on
each page. GettingStarted uses TanStack Query cache (not API calls) to detect when
steps like "add employees" are complete — it reads the cached data arrays directly.

DESIGN PRINCIPLES
Principle 3: Only stop IDs (strings) are stored in localStorage — never tokens or PII.
Principle 8: The 'ai' step in GettingStarted references the AI Copilot feature.
  It shows regardless of flag state — the flag may be enabled before the user
  reaches that step.
Principle 11: All files typed strictly. ReactNode used for children props.

DEPENDENCIES
  This folder imports from:
    ../../auth/AuthContext.tsx     — user.id for localStorage namespacing
    ../../context/IndustryContext.tsx — useLabels for industry-aware step text
    @tanstack/react-query          — GettingStarted reads query cache
    react-router-dom               — GettingStarted uses useNavigate

  This folder is imported by:
    frontend/src/App.tsx           — OnboardingProvider wraps authenticated routes
    frontend/src/components/Layout.tsx — GettingStarted, TourButton rendered here
    Any page using CoachMark

GOTCHAS
1. CoachMark uses a module-level registrationCounter. If the same stop ID is
   mounted twice simultaneously, behaviour is undefined. Always use unique IDs.
2. GettingStarted polls the TanStack Query cache every 3 seconds. It uses the
   exact query keys from page components — if a page changes its queryKey,
   update the checkKey in GettingStarted's steps array.
3. Dismissed and manual-done states are per-user localStorage keys. Calling
   resetTour() removes the onboarding key but NOT the gs_done_* keys or the
   gs_dismissed_* key. handleReset() in GettingStarted clears all of them.
