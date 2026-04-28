// frontend/src/auth/useAuth.ts
//
// PURPOSE
// Hook + types for the auth surface. Split out of AuthContext.tsx in v6.3.2.1
// so the Provider file has only component exports and Vite's Fast Refresh
// works on save without a full-page reload.
//
// CALLED BY
// - LoginPage, RegisterPage (indirectly), ProtectedRoute, Layout, IndustryContext,
//   OnboardingContext, GettingStarted, LinkWhatsApp, UnauthorizedPage,
//   any component that gates UI on auth state or role.
//
// CALLS INTO
// - React's createContext + useContext primitives only. The context value is
//   produced by AuthProvider in ./AuthContext.tsx — that's where the actual
//   state machine lives.

import { createContext, useContext } from 'react'

// -- Types --------------------------------------------------------------------
export type Role = "proprietor" | "scheduler" | "viewer";

export interface AuthUser {
  id:            number;
  email:         string;
  role:          Role;
  tenant_id:     number;
  industry_type: string;   // v4.0.2 - loaded from tenant at login
}

export interface RegisterPayload {
  email:         string;
  password:      string;
  company_name:  string;
  slug:          string;
  industry_type: string;   // v4.0.2
}

export interface AuthContextValue {
  user:        AuthUser | null;
  accessToken: string | null;
  isLoading:   boolean;
  login:    (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout:   () => Promise<void>;
  hasRole:  (...roles: Role[]) => boolean;
}

// -- Context object -----------------------------------------------------------
// Lives here (not in AuthContext.tsx) so the Provider file stays
// component-only for Vite Fast Refresh. AuthProvider imports this.
export const AuthContext = createContext<AuthContextValue | null>(null);

// -- Hook ---------------------------------------------------------------------
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
