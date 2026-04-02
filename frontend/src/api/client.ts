/**
 * frontend/src/api/client.ts — v4.0.9
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * This is the single Axios HTTP client used by every API call in the ZetaOps Copilot
 * frontend. It is the most critical file in the frontend API layer — every api_*.ts
 * file imports from here and never creates its own Axios instance. It also exports
 * tokenStore, which is the single source of truth for the in-memory JWT access token.
 * AuthContext calls tokenStore.set() after login/refresh; Axios interceptors read it
 * on every request. Introduced in v4.0.9, exists in both branches.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Reads VITE_API_BASE_URL from environment, falls back to http://localhost:8000.
 * 2. Declares a module-level private variable _accessToken (never persisted to disk).
 * 3. Exports tokenStore object with get/set methods — the only way to read or write
 *    the access token outside this file.
 * 4. Creates an Axios instance (apiClient) with baseURL and withCredentials: true
 *    so the httpOnly refresh cookie is always sent.
 * 5. Adds a request interceptor that reads tokenStore.get() and attaches the JWT
 *    as an Authorization: Bearer header on every outgoing request.
 * 6. Adds a response interceptor that catches 401 errors and attempts a silent token
 *    refresh via POST /auth/refresh (which uses the httpOnly cookie).
 * 7. If refresh succeeds: retries the original failed request with the new token.
 * 8. If refresh fails: clears the token and redirects to /login.
 * 9. Queues concurrent requests that arrive during an in-progress refresh, then
 *    replays them all once the new token is available.
 * 10. Exports apiClient as default — used by all api_*.ts files.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 *
 * Name         : tokenStore
 * Type         : exported object (get/set)
 * Purpose      : In-memory store for the JWT access token. The ONLY place in the
 *                frontend where the access token lives. get() returns current token
 *                or null. set() replaces it. AuthContext calls set() after login,
 *                register, refresh, and logout.
 * Parameters   : get() → string | null. set(t: string | null) → void
 * Returns      : Current token string or null
 * Calls        : nothing — pure in-memory store
 * DB/API       : none
 * Side effects : set() mutates the module-level _accessToken variable
 *
 * Name         : apiClient (Axios instance)
 * Type         : Axios instance (default export)
 * Purpose      : Pre-configured Axios instance shared by all api_*.ts files.
 *                withCredentials: true ensures the httpOnly refresh cookie is
 *                included on every request (required for silent token refresh).
 * Parameters   : baseURL, withCredentials
 * Returns      : Axios instance
 * Calls        : Axios interceptors (request + response)
 * DB/API       : All HTTP calls in the application go through this instance
 * Side effects : none at creation — interceptors fire on every request/response
 *
 * Name         : request interceptor
 * Type         : Axios interceptor (anonymous)
 * Purpose      : Attaches the current JWT as Authorization: Bearer <token> header
 *                to every outgoing request. If no token is set (user not logged in),
 *                the header is omitted — public endpoints like /scan will still work.
 * Parameters   : Axios RequestConfig
 * Returns      : Modified RequestConfig with Authorization header
 * Calls        : tokenStore.get()
 * DB/API       : none
 * Side effects : none
 *
 * Name         : response interceptor (401 handler)
 * Type         : Axios interceptor (anonymous)
 * Purpose      : Catches 401 Unauthorized responses and attempts a single silent
 *                token refresh. Uses a queue (failedQueue) to hold concurrent requests
 *                that 401 during a refresh in progress, then replays them all after
 *                the new token arrives. If refresh itself fails, clears auth and
 *                redirects to /login.
 * Parameters   : Axios Response or AxiosError
 * Returns      : Original response (pass-through) or retried request with new token
 * Calls        : axios.post('/auth/refresh'), tokenStore.set(), processQueue()
 * DB/API       : POST /auth/refresh (uses httpOnly cookie, no body needed)
 * Side effects : sets new token via tokenStore.set(), may redirect to /login,
 *                drains failedQueue
 *
 * Name         : processQueue
 * Type         : internal function
 * Purpose      : Drains the failedQueue after a refresh attempt. On success: resolves
 *                all queued promises with the new token. On failure: rejects them all
 *                with the refresh error.
 * Parameters   : error: unknown, token: string | null
 * Returns      : void
 * Calls        : resolve/reject on each queued promise
 * DB/API       : none
 * Side effects : empties failedQueue array
 *
 * WHO CALLS THIS FILE
 * - frontend/src/api/api_dashboard.ts
 * - frontend/src/api/api_employees.ts
 * - frontend/src/api/api_gantt.ts
 * - frontend/src/api/api_jobs.ts
 * - frontend/src/api/api_machines.ts
 * - frontend/src/api/api_resource_availability.ts
 * - frontend/src/api/api_skills.ts
 * - frontend/src/api/api_timer.ts
 * - frontend/src/auth/AuthContext.tsx (tokenStore only)
 *
 * IMPORTS EXPLAINED
 * - axios from 'axios': HTTP client library. Used to create the shared instance
 *   and also for a direct axios.post() call to /auth/refresh (separate from
 *   apiClient to avoid infinite 401 loop during refresh).
 *
 * INTERN NOTES
 * - NEVER store the access token in localStorage or sessionStorage. _accessToken is
 *   a module-level variable. If the page is refreshed, it is gone — that is intentional.
 *   The refresh cookie (httpOnly) restores the session silently on reload via AuthContext.
 * - The _retry flag on originalRequest prevents infinite 401 loops: if the retried
 *   request also returns 401, it is NOT retried again.
 * - failedQueue exists because multiple components often fire API calls simultaneously.
 *   Without the queue, a burst of 401s would trigger multiple refresh calls. The queue
 *   ensures only ONE refresh is attempted, then all queued requests are replayed.
 * - withCredentials: true is required for the httpOnly cookie to be sent cross-origin
 *   in development (localhost:5173 → localhost:8000). Both the Vite dev server proxy
 *   and the FastAPI CORS config must allow credentials.
 * - Design Principle 3: The token is never persisted. This file never touches localStorage.
 * - If all API calls are failing with 401 after login: check that tokenStore.set() is
 *   being called by AuthContext after a successful login response.
 */

import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// ── In-memory token store ─────────────────────────────────────────────────────
// Exported so AuthContext can set/clear the token after login/logout/refresh.
// Never persisted to localStorage or sessionStorage.

let _accessToken: string | null = null

export const tokenStore = {
  get: (): string | null => _accessToken,
  set: (t: string | null): void => { _accessToken = t },
}

// ── Axios instance ────────────────────────────────────────────────────────────

const apiClient = axios.create({
  baseURL:         API_BASE,
  withCredentials: true,   // sends httpOnly refresh cookie
})

// Attach Bearer token to every request
apiClient.interceptors.request.use(config => {
  const token = tokenStore.get()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// On 401: attempt silent refresh once, then redirect to /login
let isRefreshing = false
let failedQueue: Array<{
  resolve: (token: string) => void
  reject:  (err: unknown)  => void
}> = []

function processQueue(error: unknown, token: string | null): void {
  failedQueue.forEach(p => error ? p.reject(error) : p.resolve(token!))
  failedQueue = []
}

apiClient.interceptors.response.use(
  response => response,
  async error => {
    const originalRequest = error.config

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then(token => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return apiClient(originalRequest)
        })
      }

      originalRequest._retry = true
      isRefreshing = true

      try {
        const res = await axios.post(
          `${API_BASE}/auth/refresh`,
          {},
          { withCredentials: true }
        )
        const newToken: string = res.data.access_token
        tokenStore.set(newToken)
        processQueue(null, newToken)
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return apiClient(originalRequest)
      } catch (refreshError) {
        processQueue(refreshError, null)
        tokenStore.set(null)
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export default apiClient
