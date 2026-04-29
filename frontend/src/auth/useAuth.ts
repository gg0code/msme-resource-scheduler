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
// v6.3.3: Role union extended to the full SRS Section 6.28.6 taxonomy.
//   - Top-tier (require_top_tier on backend): owner, proprietor (legacy
//     synonym), factory_manager, co_owner.
//   - Mid-tier operator (require_operational): scheduler (legacy synonym),
//     manager.
//   - Read-only: viewer.
// 'proprietor' and 'scheduler' are kept as synonyms for the v6.4 names
// until the v6.5+ data consolidation runs - see backend
// app/models/auth.py header notes and memory/feedback_role_synonyms.md.
// TOP_TIER_ROLES below mirrors backend app.models.auth.TOP_TIER_ROLES
// for client-side role badge styling and nav gating.
export type Role =
  | "owner" | "proprietor" | "factory_manager" | "co_owner"
  | "scheduler" | "manager"
  | "viewer";

export const TOP_TIER_ROLES: readonly Role[] = [
  "owner", "proprietor", "factory_manager", "co_owner",
] as const;

export function isTopTier(role: Role | undefined | null): boolean {
  return role !== undefined && role !== null && (TOP_TIER_ROLES as readonly string[]).includes(role);
}

export interface AuthUser {
  id:            number;
  email:         string;
  role:          Role;
  tenant_id:     number;
  industry_type: string;   // v4.0.2 - loaded from tenant at login
}

export interface RegisterPayload {
  // v6.3.2: email + password are conditionally required per team_size.
  // Backend Pydantic schema validates the conditional rules; the type
  // simply allows undefined so whatsapp_first signups can omit them.
  email?:        string;
  password?:     string;
  company_name:  string;
  slug:          string;
  industry_type: string;   // v4.0.2
  // v6.3.2 entry-gate fields (SRS Section 6.28). team_size drives the
  // backend's entry_mode + size_segment + next_step.
  team_size:     '1-15' | '16-50' | '51+';
  phone_e164?:   string;   // required when team_size != '51+'
}

// Returned by register() so the caller (RegisterPage) can route to
// /dashboard or /connect-whatsapp based on the backend's response.
export interface RegisterResult {
  next_step?: 'dashboard' | 'connect_whatsapp';
}

export interface AuthContextValue {
  user:        AuthUser | null;
  accessToken: string | null;
  isLoading:   boolean;
  login:    (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<RegisterResult>;
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
