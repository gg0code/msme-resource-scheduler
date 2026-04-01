// src/api/client.ts — v4.0.9
// ─────────────────────────────────────────────────────────────────────────────
// Axios instance used by all pages and api_*.ts files.
// tokenStore is the single source of truth for the in-memory JWT.
// AuthContext calls tokenStore.set() after login/refresh.
//
// Rules:
//   - Token stored in memory only — never localStorage or cookies
//   - On 401: silent refresh attempted once, then redirect to /login
//   - All api_*.ts files import apiClient from this file only
// ─────────────────────────────────────────────────────────────────────────────

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
