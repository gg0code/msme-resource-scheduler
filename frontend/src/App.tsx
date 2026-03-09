// src/App.tsx — V3.0
// - Removed /availability and /checker routes (superseded by auto-scheduler)

import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
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

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public routes */}
        <Route path="/login"        element={<LoginPage />} />
        <Route path="/register"     element={<RegisterPage />} />
        <Route path="/unauthorized" element={<UnauthorizedPage />} />

        {/* Protected routes — any authenticated user */}
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="jobs"      element={<Jobs />} />
            <Route path="gantt"     element={<GanttPage />} />
            <Route path="employees" element={<Employees />} />
            <Route path="machines"  element={<Machines />} />

            {/* Skills — proprietor only */}
            <Route element={<ProtectedRoute roles={['proprietor']} />}>
              <Route path="skills" element={<Skills />} />
            </Route>
          </Route>
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  )
}
