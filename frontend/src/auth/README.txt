AUTO-GENERATED - frontend/src/auth/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/auth/
PURPOSE: JWT authentication state management and route-level access control.

WHAT IT DOES
This two-file folder handles the entire authentication layer of the ZetaOps Copilot
frontend. AuthContext.tsx manages the full user session lifecycle - login, register,
logout, and automatic silent token refresh. ProtectedRoute.tsx uses that session
state to guard React Router routes, redirecting unauthenticated users to /login and
unauthorised users (wrong role) to /unauthorized. Together they enforce all frontend
authentication and RBAC without any other file needing to think about tokens or roles.

FILES
  AuthContext.tsx    - React context + provider for auth state. Exports AuthProvider
                       (used in App.tsx), useAuth hook (used everywhere else), and
                       the AuthUser, Role, RegisterPayload TypeScript types.
                       Branch: both.
  ProtectedRoute.tsx - React Router route guard component. Reads useAuth() state and
                       conditionally renders Outlet or redirects. Accepts optional
                       roles prop for role-based access control.
                       Branch: both.

ARCHITECTURE NOTES
The auth system is split across two files that depend on each other and on client.ts.
AuthContext.tsx imports tokenStore from api/client.ts and calls tokenStore.set() every
time a new access token is obtained. This keeps the Axios interceptor in sync so
every subsequent API call carries the correct Bearer token. AuthContext uses native
fetch() (not Axios) for its own /auth/* calls to avoid circular dependency with the
Axios 401 interceptor. ProtectedRoute.tsx only reads from useAuth() - it never
modifies auth state. The separation means route protection logic is cleanly isolated
from session management logic.

DESIGN PRINCIPLES
Principle 3: Access token stored in React state and in tokenStore (_accessToken
  module variable in client.ts). Never in localStorage or sessionStorage.
  httpOnly refresh cookie is the persistence mechanism - managed entirely by the browser.
Principle 8: Role-based route gating is the first enforcement layer. Backend RBAC
  is the second. Both must pass for access to succeed.
Principle 11: Both files must pass tsc --noEmit. Role type and AuthUser interface
  are exported and used by many other files - changes here cascade widely.

DEPENDENCIES
  This folder imports from:
    ../api/client.ts           - tokenStore (to sync JWT with Axios)
    react-router-dom           - Navigate, Outlet, useLocation

  This folder is imported by:
    frontend/src/App.tsx               - AuthProvider wraps entire app,
                                         ProtectedRoute wraps protected routes
    frontend/src/context/FeatureFlags.tsx  - useAuth() for tenant context
    frontend/src/context/IndustryContext.tsx - useAuth() for industry_type
    frontend/src/components/Layout.tsx - useAuth() for user display and logout
    frontend/src/pages/LoginPage.tsx   - useAuth().login()
    frontend/src/pages/RegisterPage.tsx - useAuth().register()
    All pages that need user.role for conditional UI rendering

GOTCHAS
1. The isLoading spinner in ProtectedRoute is critical. Without it, every page
   refresh redirects to /login for a fraction of a second before silentRefresh
   completes. Never remove the isLoading check.
2. AuthContext uses native fetch() not Axios. This prevents a circular loop where
   the Axios 401 interceptor tries to refresh, which calls auth endpoints, which
   get a 401, which triggers another refresh, infinitely.
3. silentRefreshRef exists to avoid stale closure bugs. The 29-minute timer captures
   a reference to silentRefresh - without the ref, it would call a stale version
   that has closed over outdated state.
