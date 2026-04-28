// frontend/src/auth/AuthContext.tsx
//
// Access token stored in React state (memory) - never localStorage.
// Refresh token lives in httpOnly cookie (set by backend).
// On page reload, /auth/refresh is called automatically to restore session.
//
// v6.3.2.1: Hook + types + the React Context object live in ./useAuth.ts.
// This file exports only the AuthProvider component so Vite Fast Refresh
// can hot-swap the Provider without a full-page reload.

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { tokenStore } from "../api/client"  // single HTTP client source of truth
import { AUTH } from "../api/api_endpoints"
import { AuthContext, type AuthUser, type RegisterPayload } from "./useAuth"

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// -- Internal Provider state shape -------------------------------------------
// Private to AuthProvider — not exposed via the context value, so it stays
// in this file rather than moving to useAuth.ts with the public types.
interface AuthState {
  user:        AuthUser | null;
  accessToken: string | null;
  isLoading:   boolean;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    accessToken: null,
    isLoading: true,
  });

  const refreshTimerRef    = useRef<ReturnType<typeof setTimeout> | null>(null)
  const silentRefreshRef   = useRef<(() => void) | null>(null);

  // -- Helpers ----------------------------------------------------------------
  // scheduleRefresh is declared first so setAuth can list it in its dep array
  // without hitting the temporal-dead-zone trap that the previous ordering
  // had. Identity is stable (useCallback with []), so this does not cause
  // setAuth to re-create on every render.
  const scheduleRefresh = useCallback((ms: number) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => { silentRefreshRef.current?.() }, ms);
  }, []);

  const setAuth = useCallback((accessToken: string, user: AuthUser) => {
    tokenStore.set(accessToken);             // keep axios interceptor in sync
    setState({ user, accessToken, isLoading: false });
    scheduleRefresh(29 * 60 * 1000);
  }, [scheduleRefresh]);

  const clearAuth = useCallback(() => {
    tokenStore.set(null);                    // clear axios token too
    setState({ user: null, accessToken: null, isLoading: false });
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
  }, []);

  // -- Silent refresh (called on load + timer) --------------------------------
  const silentRefresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}${AUTH.refresh}`, {
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

  // Keep ref in sync so scheduleRefresh can call it without re-creating
  // the timer callback on every silentRefresh identity change. The ref
  // assignment runs in an effect (not during render) so React 18 StrictMode
  // double-renders cannot leave the ref pointing at a stale closure.
  useEffect(() => {
    silentRefreshRef.current = silentRefresh
  }, [silentRefresh]);

  // Restore session on mount
  useEffect(() => { silentRefresh() }, [silentRefresh]);

  // -- Auth actions -----------------------------------------------------------
  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}${AUTH.login}`, {
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
    const res = await fetch(`${API_BASE}${AUTH.register}`, {
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
    await fetch(`${API_BASE}${AUTH.logout}`, {
      method: "POST",
      credentials: "include",
    });
    clearAuth();
  }, [clearAuth]);

  const hasRole = useCallback(
    (...roles: Array<AuthUser["role"]>) => !!state.user && roles.includes(state.user.role),
    [state.user]
  );

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

// -- Internal helper -----------------------------------------------------------
async function fetchMe(accessToken: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}${AUTH.me}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error("Failed to fetch user");
  return res.json();
}
