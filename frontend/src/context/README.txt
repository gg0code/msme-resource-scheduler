AUTO-GENERATED — frontend/src/context/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/context/
PURPOSE: React context providers for cross-cutting application concerns.

FILES
  FeatureFlags.tsx   — Fetches feature flags from /api/features, caches for
                       5 minutes, provides via useFeatureFlags() hook.
                       All flags default to false until API responds.
                       Branch: both.
  IndustryContext.tsx — Loads industry config from config/industries/,
                        applies theme-{industry} class to body, provides
                        config and labels via useIndustry() and useLabels().
                        Branch: both.

ARCHITECTURE NOTES
Both providers are mounted inside AuthProvider in App.tsx because both need
the logged-in user context. FeatureFlagProvider needs the JWT token to call
/api/features. IndustryProvider needs user.industry_type to load the correct
config. The mounting order in App.tsx is: AuthProvider > FeatureFlagProvider >
IndustryProvider > SchedulerProvider > OnboardingProvider > Layout.

DESIGN PRINCIPLES
Principle 8: FeatureFlags.tsx is the frontend enforcement point for feature
  gating. Every gated feature must check useFeatureFlags() before rendering.
Principle 11: Both files export their context value types. useIndustry() throws
  if called outside provider. useFeatureFlags() returns DEFAULT_FLAGS safely.

DEPENDENCIES
  This folder imports from:
    ../auth/AuthContext.tsx        — IndustryContext reads user.industry_type
    ../api/client.ts               — FeatureFlags calls /api/features
    ../config/industries/index.ts  — IndustryContext loads config
    @tanstack/react-query          — FeatureFlags uses useQuery

  This folder is imported by:
    frontend/src/App.tsx           — both providers wrapped here
    frontend/src/components/Layout.tsx — useFeatureFlags, useIndustry, useLabels
    frontend/src/components/AICopilot.tsx — useLabels
    frontend/src/components/onboarding/GettingStarted.tsx — useLabels
    frontend/src/components/common/CsvImport.tsx — useLabels
    All pages — useLabels() for page titles and button labels

GOTCHAS
1. FeatureFlagProvider must be inside AuthProvider — it calls apiClient which
   needs the JWT token. Moving it outside will cause 401 errors on /api/features.
2. IndustryContext uses (user as any)?.industry_type — a deliberate type cast.
   If AuthUser in AuthContext.tsx is updated to include industry_type more strictly,
   remove the cast.
3. Theme classes (theme-printing, theme-manufacturing etc) are applied to
   document.body. If multiple IndustryProviders mount simultaneously (should not
   happen), the last one wins. The cleanup function removes the class on unmount.
