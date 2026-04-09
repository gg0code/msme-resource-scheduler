/**
 * frontend/src/App.tsx - Main React Application Router and Provider Setup
 * 
 * FILE PURPOSE
 * This is the root component of the ZetaOps Copilot React application, serving as the main
 * entry point for all routing and context provider initialization. Introduced in v3.7.3,
 * this file orchestrates the authentication flow, feature flag loading, and page routing
 * for the entire manufacturing workforce scheduling web app. It sits at the top of the
 * React component hierarchy and establishes the provider chain that all child components
 * depend on for authentication, feature flags, industry context, and scheduling state.
 * 
 * WHAT THIS FILE DOES - step by step
 * 1. Wraps the entire application in AuthProvider to handle JWT authentication state
 * 2. Defines public routes (login, register, unauthorized) that don't require authentication
 * 3. Creates a special /scan route for QR code scanning that bypasses authentication and layout
 * 4. Sets up print routes (/jobs/:jobId/print) that require auth but have no sidebar layout
 * 5. Establishes the main protected route structure with nested provider hierarchy
 * 6. Wraps authenticated routes in FeatureFlagProvider, IndustryProvider, SchedulerProvider, and OnboardingProvider
 * 7. Applies the main Layout component (with sidebar/header) to all standard app pages
 * 8. Routes individual pages like Dashboard, Jobs, Employees, Machines, Gantt, WhatsApp
 * 9. Implements role-based route protection for proprietor-only pages like Skills
 * 10. Sets up catch-all route redirect to dashboard for unknown URLs
 * 
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 * Name         : App
 * Type         : React component (default export)
 * Purpose      : Root application component that sets up React Router routing and context
 *                provider hierarchy. Manages the authentication flow and determines which
 *                pages users can access based on their login status and role. Establishes
 *                the provider chain that enables feature flags, industry settings, and
 *                scheduling context throughout the application.
 * Parameters   : None (React functional component with no props)
 * Returns      : JSX.Element containing the complete application routing structure wrapped
 *                in necessary context providers
 * Calls        : All imported page components (LoginPage, Dashboard, Jobs, etc.), all
 *                imported context providers (AuthProvider, FeatureFlagProvider, etc.),
 *                ProtectedRoute for authentication checks, Layout for main app structure
 * DB/API       : No direct database or API calls - delegates to child providers and components
 * Side effects : Establishes React Router navigation, initializes authentication state,
 *                triggers feature flag fetching, sets up global application context
 * 
 * WHO CALLS THIS FILE
 * - frontend/src/main.tsx imports and renders this as the root React component
 * - No other files directly import this component (it's the application root)
 * 
 * IMPORTS EXPLAINED
 * - Routes, Route, Navigate from react-router-dom: Core React Router components for defining application navigation and URL routing
 * - AuthProvider from ./auth/AuthContext: Context provider that manages JWT authentication state, user login/logout, and token refresh
 * - ProtectedRoute from ./auth/ProtectedRoute: Wrapper component that blocks access to routes requiring authentication or specific roles
 * - OnboardingProvider from ./components/onboarding: Context provider that manages new user onboarding flow and tutorial state
 * - SchedulerProvider from ./scheduler/SchedulerContext: Context provider that manages scheduling engine state and job/resource data
 * - FeatureFlagProvider from ./context/FeatureFlags: Context provider that fetches and manages feature flag state from backend
 * - IndustryProvider from ./context/IndustryContext: Context provider that manages industry-specific settings and UI customization
 * - Layout from ./components/Layout: Main application layout component with sidebar navigation and header
 * - LoginPage, RegisterPage, UnauthorizedPage: Authentication-related page components for user access control
 * - Dashboard, Skills, Employees, Machines, Jobs, GanttPage, LinkWhatsApp: Main application page components for different features
 * - ScanPage, PrintJobCard: Special page components that bypass normal layout (QR scanning and print views)
 * 
 * INTERN NOTES
 * - Easiest thing to break: Changing the provider nesting order - FeatureFlagProvider MUST be inside AuthProvider because it needs authentication to fetch flags from the backend
 * - Non-obvious design decision: The /scan route is intentionally outside ProtectedRoute to allow factory workers to scan QR codes without logging in first
 * - Most common mistake: Adding new protected routes outside the nested provider structure, which breaks feature flags, industry context, or scheduling state access
 * - Design principle implemented: Principle #8 (Feature flags gate all optional features) - FeatureFlagProvider ensures all child components can access FEATURE_FLAGS
 * - What to check if behaving unexpectedly: Verify the provider hierarchy order and ensure authentication is working before feature flags load
 * - Branch consideration: This is v4-dev stable - when merging v5-whatsapp features, new WhatsApp-related routes should be added inside the protected route structure with feature flag guards
 */

import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { OnboardingProvider } from './components/onboarding'
import { SchedulerProvider } from './scheduler/SchedulerContext'
import { FeatureFlagProvider } from './context/FeatureFlags'
import { IndustryProvider } from './context/IndustryContext'
import Layout from './components/Layout'

// Auth pages
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import UnauthorizedPage from './pages/UnauthorizedPage'

// App pages
import Dashboard from './pages/Dashboard'
import Skills from './pages/Skills'
import Employees from './pages/Employees'
import Machines from './pages/Machines'
import Jobs from './pages/Jobs'
import GanttPage from './pages/GanttPage'
import LinkWhatsApp from './pages/LinkWhatsApp'
import OnboardingSetup from './pages/OnboardingSetup'

// Scheduling engine pages - removed in v3.9.5 (merged into /jobs)

// Block 2 - QR Execution
import ScanPage from './pages/ScanPage'
import PrintJobCard from './pages/PrintJobCard'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public routes */}
        <Route path="/login"        element={<LoginPage />} />
        <Route path="/register"     element={<RegisterPage />} />
        <Route path="/unauthorized" element={<UnauthorizedPage />} />

        {/* -- Block 2: Scan page - no auth, no sidebar -- */}
        <Route path="/scan" element={<ScanPage />} />

        {/* Print pages - auth required, no sidebar */}
        <Route element={<ProtectedRoute />}>
          <Route path="/jobs/:jobId/print" element={<PrintJobCard />} />
        </Route>

        {/* Onboarding - auth required, no sidebar (full screen setup flow) */}
        <Route element={<ProtectedRoute />}>
          <Route path="/onboarding" element={<OnboardingSetup />} />
        </Route>

        {/* Protected routes with layout */}
        <Route element={<ProtectedRoute />}>
          <Route element={
            <FeatureFlagProvider>
              <IndustryProvider>
              <SchedulerProvider>
                <OnboardingProvider>
                  <Layout />
                </OnboardingProvider>
              </SchedulerProvider>
              </IndustryProvider>
            </FeatureFlagProvider>
          }>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard"    element={<Dashboard />} />
            <Route path="jobs"         element={<Jobs />} />
            <Route path="employees"    element={<Employees />} />
            <Route path="machines"     element={<Machines />} />
            <Route path="gantt"        element={<GanttPage />} />
            <Route path="whatsapp" element={<LinkWhatsApp />} />


            {/* Skills - proprietor only */}
            <Route element={<ProtectedRoute roles={['proprietor']} />}>
              <Route path="skills" element={<Skills />} />
            </Route>
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  )
}
