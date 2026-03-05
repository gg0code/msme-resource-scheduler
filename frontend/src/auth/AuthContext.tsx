// frontend/src/auth/AuthContext.tsx
//
// Access token stored in React state (memory) — never localStorage.
// Refresh token lives in httpOnly cookie (set by backend).
// On page reload, /auth/refresh is called automatically to restore session.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { tokenStore } from "./apiClient";   // keeps axios in sync

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────
export type Role = "proprietor" | "scheduler" | "viewer";

export interface AuthUser {
  id: number;
  email: string;
  role: Role;
  tenant_id: number;
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
  email: string;
  password: string;
  company_name: string;
  slug: string;
}

// ── Context ───────────────────────────────────────────────────────────────────
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    accessToken: null,
    isLoading: true,
  });

  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const scheduleRefresh = (ms: number) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => silentRefresh(), ms);
  };

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

  // Restore session on mount
  useEffect(() => { silentRefresh(); }, [silentRefresh]);

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
