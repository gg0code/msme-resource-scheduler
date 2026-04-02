/**
 * frontend/src/auth/AuthContext.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * This is the authentication backbone of the ZetaOps Copilot frontend. It manages
 * the entire user session lifecycle: login, register, logout, silent token refresh,
 * and role-based access checks. The access token is stored in React state (memory only —
 * never localStorage). The refresh token lives in an httpOnly cookie set by the backend.
 * On every page load, AuthContext silently calls /auth/refresh to restore the session
 * from the cookie. All other components that need to know who is logged in consume
 * the useAuth() hook exported from this file. Introduced in v4.0.9, stable in both branches.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Defines the Role type ('proprietor' | 'scheduler' | 'viewer').
 * 2. Defines AuthUser interface — the decoded user object stored in React state.
 * 3. Defines AuthState interface — { user, accessToken, isLoading }.
 * 4. Defines AuthContextValue interface — AuthState + login/register/logout/hasRole.
 * 5. Defines RegisterPayload interface — fields needed for new tenant registration.
 * 6. Creates the AuthContext React context (null default, typed).
 * 7. Exports AuthProvider component that wraps the app and manages all auth state.
 * 8. setAuth() helper: stores token in tokenStore (for Axios) and in React state,
 *    then schedules a refresh 29 minutes from now (tokens expire at 30 min).
 * 9. clearAuth() helper: clears tokenStore and React state, cancels refresh timer.
 * 10. scheduleRefresh() helper: sets a setTimeout that fires silentRefresh after ms.
 * 11. silentRefresh(): POSTs to /auth/refresh with the httpOnly cookie, on success
 *     calls fetchMe() then setAuth(), on failure calls clearAuth().
 * 12. useEffect on mount: calls silentRefresh() to restore session on page load.
 * 13. login(): POSTs credentials, gets access token, calls fetchMe(), calls setAuth().
 * 14. register(): POSTs registration payload, same flow as login.
 * 15. logout(): POSTs to /auth/logout, calls clearAuth().
 * 16. hasRole(): checks if current user's role is in the provided role list.
 * 17. Exports useAuth() hook — throws if called outside AuthProvider.
 * 18. Internal fetchMe() helper: calls /auth/me with a given token, returns AuthUser.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : AuthProvider
 * Type         : React component
 * Purpose      : Top-level provider that wraps the entire application (in App.tsx).
 *                Manages all authentication state and exposes it to any descendant
 *                via useAuth(). Handles the silent refresh on mount and scheduled
 *                token rotation every 29 minutes.
 * Parameters   : { children: ReactNode }
 * Returns      : JSX — AuthContext.Provider wrapping children
 * Calls        : silentRefresh (on mount), setAuth, clearAuth, fetchMe
 * DB/API       : POST /auth/refresh, POST /auth/login, POST /auth/register,
 *                POST /auth/logout, GET /auth/me
 * Side effects : writes to tokenStore (Axios bearer token), schedules/cancels timers
 *
 * Name         : useAuth
 * Type         : React hook
 * Purpose      : The public API for consuming auth state in any component. Returns
 *                user, accessToken, isLoading, login, register, logout, hasRole.
 *                Throws a descriptive error if called outside AuthProvider to help
 *                developers catch missing provider wrapper early.
 * Parameters   : none
 * Returns      : AuthContextValue
 * Calls        : useContext(AuthContext)
 * DB/API       : none
 * Side effects : none
 *
 * Name         : login
 * Type         : async function (inside AuthProvider)
 * Purpose      : Authenticates a user with email and password. On success, stores
 *                the token and user. Throws an Error with a human-readable message
 *                on failure — the calling component should catch and display this.
 * Parameters   : email: string, password: string
 * Returns      : Promise<void>
 * Calls        : fetch POST /auth/login, fetchMe(), setAuth()
 * DB/API       : POST /auth/login, GET /auth/me
 * Side effects : sets access token, user state, schedules refresh timer
 *
 * Name         : silentRefresh
 * Type         : async function (inside AuthProvider)
 * Purpose      : Restores session on page load and on the 29-minute timer. Uses the
 *                httpOnly cookie automatically included by withCredentials. On failure
 *                (cookie expired or missing) calls clearAuth() — user sees login page.
 * Parameters   : none
 * Returns      : Promise<void>
 * Calls        : fetch POST /auth/refresh, fetchMe(), setAuth(), clearAuth()
 * DB/API       : POST /auth/refresh, GET /auth/me
 * Side effects : may set or clear auth state
 *
 * Name         : hasRole
 * Type         : function (inside AuthProvider)
 * Purpose      : Returns true if the current user's role matches any of the provided
 *                roles. Used by ProtectedRoute and by components that conditionally
 *                render UI based on role (e.g. show delete button only for proprietors).
 * Parameters   : ...roles: Role[]
 * Returns      : boolean
 * Calls        : nothing
 * DB/API       : none
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/App.tsx — wraps the entire app in <AuthProvider>
 * - frontend/src/auth/ProtectedRoute.tsx — calls useAuth() for user and isLoading
 * - frontend/src/components/Layout.tsx — calls useAuth() for user display and logout
 * - frontend/src/pages/LoginPage.tsx — calls useAuth().login()
 * - frontend/src/pages/RegisterPage.tsx — calls useAuth().register()
 * - frontend/src/context/FeatureFlags.tsx — calls useAuth() to get tenant context
 * - frontend/src/context/IndustryContext.tsx — calls useAuth() for industry_type
 * - All pages that need user.role for conditional rendering
 *
 * IMPORTS EXPLAINED
 * - createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode
 *   from 'react': Core React hooks and context API for state management.
 * - tokenStore from '../api/client': The in-memory JWT store. setAuth() must call
 *   tokenStore.set() so the Axios interceptor attaches the token to every request.
 *
 * INTERN NOTES
 * - The access token is NEVER in localStorage. If you add localStorage anywhere in
 *   this file you are introducing a security vulnerability (XSS can steal the token).
 * - silentRefreshRef exists to avoid stale closure issues. scheduleRefresh() is called
 *   inside setAuth() which is memoized with useCallback — without the ref, the timer
 *   would hold a stale reference to an old silentRefresh function.
 * - isLoading=true on initial render. ProtectedRoute shows a spinner during this time.
 *   Never render protected content while isLoading is true.
 * - Design Principle 3: No secrets or tokens in localStorage or sessionStorage.
 *   Token lives in memory (_accessToken in client.ts) and React state here.
 * - AuthContext uses native fetch(), not apiClient (Axios). This is intentional —
 *   the auth endpoints run before apiClient's token interceptor is set up.
 * - If users are being logged out unexpectedly: check the 29-minute timer in
 *   scheduleRefresh — it should fire before the 30-minute token expiry.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { tokenStore } from "../api/client"  // single HTTP client source of truth

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────
export type Role = "proprietor" | "scheduler" | "viewer";

export interface AuthUser {
  id:            number;
  email:         string;
  role:          Role;
  tenant_id:     number;
  industry_type: string;   // v4.0.2 — loaded from tenant at login
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

export interface RegisterPayload {
  email:         string;
  password:      string;
  company_name:  string;
  slug:          string;
  industry_type: string;   // v4.0.2
}

// ── Context ───────────────────────────────────────────────────────────────────
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    accessToken: null,
    isLoading: true,
  });

  const refreshTimerRef    = useRef<ReturnType<typeof setTimeout> | null>(null)
  const silentRefreshRef   = useRef<(() => void) | null>(null);

  // ── Helpers ────────────────────────────────────────────────────────────────
  const setAuth = useCallback((accessToken: string, user: AuthUser) => {
    tokenStore.set(accessToken);             // keep axios interceptor in sync
    setState({ user, accessToken, isLoading: false });
    scheduleRefresh(29 * 60 * 1000);
  }, []);

  const clearAuth = useCallback(() => {
    tokenStore.set(null);                    // clear axios token too
    setState({ user: null, accessToken: null, isLoading: false });
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
  }, []);

  const scheduleRefresh = useCallback((ms: number) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => { silentRefreshRef.current?.() }, ms);
  }, []);

  // ── Silent refresh (called on load + timer) ────────────────────────────────
  const silentRefresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include", // sends httpOnly cookie
      });
      if (!res.ok) { clearAuth(); return; }

      const { access_token } = await res.json();
      const me = await fetchMe(access_token);
      setAuth(access_token, me);
    } catch {
      clearAuth();
    }
  }, [clearAuth, setAuth]);

  // Keep ref in sync so scheduleRefresh can call it without circular deps
  silentRefreshRef.current = silentRefresh

  // Restore session on mount
  useEffect(() => { silentRefresh() }, [silentRefresh]);

  // ── Auth actions ───────────────────────────────────────────────────────────
  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail ?? "Login failed");
    }
    const { access_token } = await res.json();
    const me = await fetchMe(access_token);
    setAuth(access_token, me);
  }, [setAuth]);

  const register = useCallback(async (payload: RegisterPayload) => {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail ?? "Registration failed");
    }
    const { access_token } = await res.json();
    const me = await fetchMe(access_token);
    setAuth(access_token, me);
  }, [setAuth]);

  const logout = useCallback(async () => {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    clearAuth();
  }, [clearAuth]);

  const hasRole = useCallback(
    (...roles: Role[]) => !!state.user && roles.includes(state.user.role),
    [state.user]
  );

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

// ── Internal helper ───────────────────────────────────────────────────────────
async function fetchMe(accessToken: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error("Failed to fetch user");
  return res.json();
}
