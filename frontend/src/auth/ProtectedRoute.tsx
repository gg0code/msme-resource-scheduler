// frontend/src/auth/ProtectedRoute.tsx
//
// Wraps React Router routes.
//
// Usage in your App.tsx:
//   <ProtectedRoute />                                  - any logged-in user
//   <ProtectedRoute roles={["proprietor"]} />           - proprietor only
//   <ProtectedRoute roles={["proprietor","scheduler"]} /> - either role

import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth, type Role } from "./AuthContext";

interface Props {
  roles?: Role[];
}

export function ProtectedRoute({ roles }: Props) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  // Session restore in progress - show spinner
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
