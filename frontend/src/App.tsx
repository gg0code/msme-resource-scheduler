// src/App.tsx — V3.7.3
// FeatureFlagProvider moved here — inside AuthProvider, wrapping Layout only
// This ensures flags are fetched after auth is established

import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { OnboardingProvider } from './components/onboarding'
import { SchedulerProvider } from './scheduler/SchedulerContext'
import { FeatureFlagProvider } from './context/FeatureFlags'
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

// Scheduling engine pages — removed in v3.9.5 (merged into /jobs)
import JobPrintPage from './pages/JobPrintPage' // kept for backwards compat — remove in v4

// Block 2 — QR Execution
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

        {/* ── Block 2: Scan page — no auth, no sidebar ── */}
        <Route path="/scan" element={<ScanPage />} />

        {/* Print pages — auth required, no sidebar */}
        <Route element={<ProtectedRoute />}>
          <Route path="/jobs/:jobId/print" element={<PrintJobCard />} />
        </Route>

        {/* Protected routes with layout */}
        <Route element={<ProtectedRoute />}>
          <Route element={
            <FeatureFlagProvider>
              <SchedulerProvider>
                <OnboardingProvider>
                  <Layout />
                </OnboardingProvider>
              </SchedulerProvider>
            </FeatureFlagProvider>
          }>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard"    element={<Dashboard />} />
            <Route path="jobs"         element={<Jobs />} />
            <Route path="employees"    element={<Employees />} />
            <Route path="machines"     element={<Machines />} />
            <Route path="gantt"        element={<GanttPage />} />

            {/* Skills — proprietor only */}
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
