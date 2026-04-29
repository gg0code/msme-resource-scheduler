AUTO-GENERATED - frontend/src/components/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/components/
PURPOSE: Shared reusable UI components used across multiple pages.

WHAT IT DOES
This folder contains components that are too specific to be a generic UI library
but too general to live inside a single page file. Every file here is used by
at least two different pages or by Layout itself. They handle things like empty
states, plan limit enforcement, the main app shell, the AI chat panel, and the job
completion modal. Pages import from here; this folder never imports from pages/.
Sub-folders handle more specialised component groups (common/ for data management
UI, onboarding/ for the new-user tour).

FILES
  AICopilot.tsx        - Sliding AI chat panel. Sends messages to /api/ai/chat,
                         displays conversation history, shows usage quota.
                         Feature-flagged (flags.ai_copilot). Branch: both.
  EmptyState.tsx       - Zero-data placeholder with icon, title, description,
                         and optional action button. Branch: both.
  EndJobModal.tsx      - Job completion modal. Loads actual hours, lets user
                         adjust resource selection, shows live cost preview,
                         and confirms job completion. Branch: both.
  Layout.tsx           - Main application shell. Sidebar navigation, top header,
                         Outlet for page content. Industry-aware labels, CSS theme
                         variables, feature-flagged nav items. Branch: both.
  PlanLimitGuard.tsx   - Plan limit hook (usePlanLimits) + three components:
                         PlanLimitBanner, RawMaterialLimitHint, LimitedButton.
                         Branch: both.

  (DELETED in v6.3.6: UpgradePrompt.tsx and ZeroZetaLogo.tsx - never imported.)

ARCHITECTURE NOTES
Layout.tsx is the most important file in this folder - it is the shell that wraps
every authenticated page. All other components are rendered either inside Layout
(GettingStarted, AICopilot button) or inside individual pages (EmptyState,
EndJobModal, PlanLimitGuard). AICopilot.tsx is the "floating" component that uses
fixed positioning over the full screen. PlanLimitGuard.tsx is the only file here
that exports a hook (usePlanLimits) in addition to components - this keeps all
plan limit logic in one place.

DESIGN PRINCIPLES
Principle 1: AICopilot.tsx calls /api/ai/chat and displays what the backend returns.
  It never computes scheduling logic client-side.
Principle 8: Layout.tsx gates Gantt, WhatsApp, and AI Copilot nav items behind
  feature flags. PlanLimitGuard.tsx enforces free-plan resource caps.
Principle 11: All files must pass tsc --noEmit. Layout.tsx imports many components -
  any type error in a dependency will surface here.

DEPENDENCIES
  This folder imports from:
    ../api/client.ts               - PlanLimitGuard (plan limits fetch)
    ../api/api_timer.ts            - EndJobModal (summary + end calls)
    ../auth/AuthContext.tsx         - Layout (user, logout, hasRole)
    ../context/FeatureFlags.tsx     - Layout (flags), AICopilot (flags)
    ../context/IndustryContext.tsx  - Layout (labels, config)
    ../scheduler/SchedulerToolbar.tsx - Layout
    ./onboarding/GettingStarted.tsx - Layout
    ./onboarding/TourButton.tsx     - Layout
    @tanstack/react-query          - PlanLimitGuard (useQuery)

  This folder is imported by:
    frontend/src/App.tsx           - imports Layout
    frontend/src/pages/*           - all pages import from here as needed

GOTCHAS
1. Layout.tsx uses CSS variables (--brand-sidebar-bg etc.) not Tailwind classes for
   sidebar theming. These variables are set by IndustryContext on :root. If the
   sidebar appears unstyled, check that IndustryContext is mounted above Layout
   in App.tsx and that the CSS variables are being set.
2. PlanLimitGuard.tsx calls /dashboard/plan-limits WITHOUT the /api/ prefix.
   This is the one exception to the /api/ prefix rule. Do not add /api/ to it.
3. AICopilot.tsx uses fixed positioning and requires z-40 or higher to appear above
   page content. If it appears behind other elements, check z-index values.
