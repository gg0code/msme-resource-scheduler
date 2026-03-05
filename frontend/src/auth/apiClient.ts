// frontend/src/auth/apiClient.ts
//
// Drop-in replacement for your existing frontend/src/api/client.ts pattern.
// Attaches Bearer token to every request automatically.
// On 401 → silently refreshes token → retries once.
// On second 401 → redirects to /login.
//
// Usage (replaces raw fetch calls in your api_*.ts files):
//   import { apiClient } from "@/auth/apiClient"
//   const res = await apiClient.get("/api/employees")
//   const data = await res.json()

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// In-memory token store — AuthContext sets this after login/refresh
let _accessToken: string | null = null;

export const tokenStore = {
  get: () => _accessToken,
  set: (t: string | null) => { _accessToken = t; },
};

// ── Silent token refresh ──────────────────────────────────────────────────────
async function refreshTokens(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include", // sends httpOnly cookie
    });
    if (!res.ok) return null;
    const { access_token } = await res.json();
    tokenStore.set(access_token);
    return access_token;
  } catch {
    return null;
  }
}

// ── Core request function ─────────────────────────────────────────────────────
async function request(
  method: string,
  path: string,
  body?: unknown,
  retry = true,
): Promise<Response> {
  const token = tokenStore.get();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  // Token expired → refresh and retry once
  if (res.status === 401 && retry) {
    const newToken = await refreshTokens();
    if (!newToken) {
      // Refresh also failed → send to login
      window.location.href = "/login";
      return res;
    }
    return request(method, path, body, false);
  }

  return res;
}

// ── Public API ────────────────────────────────────────────────────────────────
export const apiClient = {
  get:    (path: string)                => request("GET",    path),
  post:   (path: string, body: unknown) => request("POST",   path, body),
  put:    (path: string, body: unknown) => request("PUT",    path, body),
  patch:  (path: string, body: unknown) => request("PATCH",  path, body),
  delete: (path: string)                => request("DELETE", path),
};

// ── How to update your existing api_*.ts files ────────────────────────────────
//
// BEFORE (your existing pattern in api/client.ts):
//   const res = await fetch(`${BASE_URL}/api/employees`, { ... })
//
// AFTER:
//   import { apiClient } from "@/auth/apiClient"
//   const res = await apiClient.get("/api/employees")
//
// That's the only change needed in each api_*.ts file.
