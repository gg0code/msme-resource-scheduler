// src/App.tsx — V3.2 (Block 2)
// Added: /scan and /jobs/:jobId/print routes

import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { OnboardingProvider } from './components/onboarding'
import { SchedulerProvider } from './scheduler/SchedulerContext'
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
import Availability from './pages/Availability'
import Checker from './pages/Checker'
import GanttPage from './pages/GanttPage'

// Scheduling engine pages
import SchedJobsPage from './pages/SchedJobsPage'
import SchedStepsPage from './pages/SchedStepsPage'
import JobPrintPage from './pages/JobPrintPage'

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
          <Route path="/sched-jobs/:jobId/print" element={<JobPrintPage />} />
          <Route path="/jobs/:jobId/print"        element={<PrintJobCard />} />
        </Route>

        {/* Protected routes with layout */}
        <Route element={<ProtectedRoute />}>
          <Route element={
            <SchedulerProvider>
              <OnboardingProvider>
                <Layout />
              </OnboardingProvider>
            </SchedulerProvider>
          }>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard"    element={<Dashboard />} />
            <Route path="jobs"         element={<Jobs />} />
            <Route path="employees"    element={<Employees />} />
            <Route path="machines"     element={<Machines />} />
            <Route path="availability" element={<Availability />} />
            <Route path="checker"      element={<Checker />} />
            <Route path="gantt"        element={<GanttPage />} />

            {/* Scheduling engine */}
            <Route path="sched-jobs"              element={<SchedJobsPage />} />
            <Route path="sched-jobs/:jobId/steps" element={<SchedStepsPage />} />

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
