// frontend/src/auth/AuthContext.tsx
// Auth state, login, logout, register, token refresh.
// Provides useAuth() hook to all components.

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

// -- Types --------------------------------------------------------------------
export type Role = "proprietor" | "scheduler" | "viewer";

export interface AuthUser {
  id:            number;
  email:         string;
  role:          Role;
  tenant_id:     number;
  industry_type: string;   // v4.0.2 - loaded from tenant at login
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

// -- Context -------------------------------------------------------------------
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    accessToken: null,
    isLoading: true,
  });

  const refreshTimerRef    = useRef<ReturnType<typeof setTimeout> | null>(null)
  const silentRefreshRef   = useRef<(() => void) | null>(null);

  // -- Helpers ----------------------------------------------------------------
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

  // -- Silent refresh (called on load + timer) --------------------------------
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

  // -- Auth actions -----------------------------------------------------------
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

// -- Hook ----------------------------------------------------------------------
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

// -- Internal helper -----------------------------------------------------------
async function fetchMe(accessToken: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error("Failed to fetch user");
  return res.json();
}
