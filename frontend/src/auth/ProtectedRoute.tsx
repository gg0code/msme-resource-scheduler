/**
 * frontend/src/auth/ProtectedRoute.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * This component is the frontend authentication and role-based access control gate.
 * It wraps React Router routes in App.tsx to prevent unauthenticated or unauthorised
 * users from accessing protected pages. It handles three cases: session still loading
 * (show spinner), user not logged in (redirect to /login), user logged in but wrong
 * role (redirect to /unauthorized). Introduced in v4.0.9, stable in both branches.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Imports Navigate, Outlet, useLocation from react-router-dom for routing control.
 * 2. Imports useAuth and the Role type from AuthContext.tsx.
 * 3. Defines Props interface with optional roles array.
 * 4. Reads user and isLoading from useAuth().
 * 5. If isLoading is true: renders a full-screen spinner while session is being restored.
 * 6. If user is null (not logged in): redirects to /login, preserving the intended
 *    destination in location.state.from so LoginPage can redirect back after login.
 * 7. If roles prop is set and user.role is not in the array: redirects to /unauthorized.
 * 8. Otherwise: renders <Outlet /> which renders the matched child route.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : ProtectedRoute
 * Type         : React component
 * Purpose      : Route guard that blocks access based on auth status and role.
 *                Used in App.tsx as a wrapper around protected route groups.
 *                When used without roles prop: any logged-in user passes through.
 *                When used with roles prop: only users with matching roles pass through.
 * Parameters   : roles?: Role[] — optional array of allowed roles
 * Returns      : JSX — spinner | <Navigate> redirect | <Outlet>
 * Calls        : useAuth() from AuthContext.tsx, useLocation() from react-router-dom
 * DB/API       : none — reads auth state already loaded by AuthContext
 * Side effects : none — navigates declaratively via React Router Navigate component
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — wraps protected route groups
 *   Usage patterns in App.tsx:
 *     <Route element={<ProtectedRoute />}>           — any logged-in user
 *     <Route element={<ProtectedRoute roles={['proprietor']} />}>  — proprietor only
 *
 * IMPORTS EXPLAINED
 * - Navigate from 'react-router-dom': Declarative redirect component. replace prop
 *   prevents the login page from appearing in browser history after redirect.
 * - Outlet from 'react-router-dom': Renders the matched child route. This is how
 *   React Router nested routes work — ProtectedRoute renders Outlet if checks pass.
 * - useLocation from 'react-router-dom': Gets the current URL. Passed as state.from
 *   to the /login redirect so LoginPage can navigate back after successful login.
 * - useAuth, Role from './AuthContext': Auth state and the Role type definition.
 *
 * INTERN NOTES
 * - The isLoading spinner is critical. Without it, the component would redirect to
 *   /login on every page refresh before the silent token refresh completes — even
 *   for logged-in users. Always preserve the isLoading check.
 * - state={{ from: location }} on the /login redirect enables "redirect after login".
 *   LoginPage reads location.state?.from and navigates there after successful login.
 *   If you remove this, users always land on /dashboard after login regardless of
 *   which page they were trying to reach.
 * - ProtectedRoute uses <Outlet /> not {children}. This is required for React Router
 *   nested routes. Do not change it to children — it will break routing.
 * - Design Principle 8: Role-based access is enforced here at the route level.
 *   The Skills page uses <ProtectedRoute roles={['proprietor']} /> — only owners
 *   can access it. This is in addition to backend RBAC enforcement.
 * - If users see a blank screen after login: check that isLoading becomes false
 *   after silentRefresh completes in AuthContext. The spinner may be stuck.
 * - This component does NOT check feature flags — only auth and role. Feature flag
 *   checks happen inside individual page components via useFeatureFlags().
 */

import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth, type Role } from "./AuthContext";

interface Props {
  roles?: Role[];
}

export function ProtectedRoute({ roles }: Props) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  // Session restore in progress — show spinner
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2" />
          <span className="text-gray-500 text-sm">Loading…</span>
        </div>
      </div>
    );
  }

  // Not logged in → redirect to login, preserve intended destination
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Logged in but wrong role → redirect to unauthorized page
  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/unauthorized" replace />;
  }

  return <Outlet />;
}
