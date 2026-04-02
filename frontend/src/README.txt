AUTO-GENERATED — frontend/src/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/
PURPOSE: Root source folder for the ZetaOps Copilot React frontend application.

WHAT IT DOES
This folder contains the two files that bootstrap the entire frontend: main.tsx
which mounts the React app onto the HTML page, and App.tsx which defines all
routes and wraps the app in the correct provider hierarchy. Every other file in
frontend/src/ is a subfolder — pages, components, api, hooks, types, context,
auth, scheduler, and config. Nothing runs without these two files working first.

FILES
  App.tsx     — Root React component. Defines all routes and provider hierarchy.
                Branch: both.
  main.tsx    — Vite entry point. Mounts React tree, sets up TanStack Query
                client and BrowserRouter. Branch: both.

ARCHITECTURE NOTES
App.tsx and main.tsx form a two-file bootstrap chain. main.tsx is loaded by
Vite directly from index.html. It creates the QueryClient (API state manager)
and BrowserRouter (URL routing), then renders App. App.tsx takes over and
establishes the full provider stack: AuthProvider wraps everything, then
FeatureFlagProvider (needs auth), IndustryProvider, SchedulerProvider, and
OnboardingProvider wrap all protected pages inside Layout. Public routes
(login, register, scan) sit outside this stack intentionally. The /scan page
has no auth requirement so factory workers can scan QR codes without logging
in (Design Principle 10).

DESIGN PRINCIPLES
Principle 8:  FeatureFlagProvider is nested inside AuthProvider — feature flags
              require a logged-in tenant to load from the backend.
Principle 10: /scan route bypasses ProtectedRoute entirely — printed QR cards
              must always work regardless of login state.
Principle 11: Both files must pass tsc --noEmit with zero errors before any
              build or deploy.

DEPENDENCIES
  This folder imports from:
    ./auth/AuthContext.tsx
    ./auth/ProtectedRoute.tsx
    ./components/Layout.tsx
    ./components/onboarding/index.ts
    ./context/FeatureFlags.tsx
    ./context/IndustryContext.tsx
    ./scheduler/SchedulerContext.tsx
    ./pages/* (all page components)

  This folder is imported by:
    frontend/index.html (loads main.tsx as module entry point)

GOTCHAS
1. Provider order in App.tsx is load-bearing. FeatureFlagProvider MUST be inside
   AuthProvider. Moving it outside will cause feature flag API calls to fire
   without a JWT token and return 401 errors.
2. The /scan route MUST remain outside ProtectedRoute. This is intentional —
   do not add auth guards to it.
3. main.tsx must never import context providers directly. They belong in App.tsx
   where auth context is available. main.tsx only sets up infrastructure
   (QueryClient, BrowserRouter, StrictMode).
