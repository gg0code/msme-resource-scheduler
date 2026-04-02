/**
 * frontend/src/pages/UnauthorizedPage.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Shown when a logged-in user tries to access a route their role cannot access.
 * Redirected here by ProtectedRoute when the user is authenticated but their role
 * is not in the allowed roles list. Simple full-screen error page with back button.
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — registered as /unauthorized route
 * - frontend/src/auth/ProtectedRoute.tsx — redirects here on role mismatch
 *
 * INTERN NOTES
 * - Reads user.role from useAuth() to display current role in the error message.
 * - Design Principle 8: access control happens in ProtectedRoute. This page only
 *   displays the error — it never makes access decisions.
 */
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function UnauthorizedPage() {
  const { user } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="text-center">
        <div className="text-6xl mb-4">🔒</div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h1>
        <p className="text-gray-500 mb-1">
          Your role <span className="font-medium text-gray-700">({user?.role})</span> doesn't have permission to view this page.
        </p>
        <p className="text-gray-400 text-sm mb-6">Contact your Proprietor to request access.</p>
        <button
          onClick={() => navigate('/dashboard')}
          className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-6 rounded-lg text-sm transition-colors"
        >
          Back to Dashboard
        </button>
      </div>
    </div>
  )
}