// src/api/client.ts — v3.9.5
// Axios instance with JWT Bearer token interceptor.
// Token is stored in tokenStore (set by AuthContext after login/refresh).
// On 401 → attempts silent refresh → retries once → redirects to /login.
//
// Base URL is read from VITE_API_BASE_URL environment variable.
// Local dev:  set VITE_API_BASE_URL=http://localhost:8000 in frontend/.env
// AWS:        set VITE_API_BASE_URL=https://your-api-domain.com in the build pipeline
// Never hardcode a port or domain here.

import axios from 'axios'
import { tokenStore } from '../auth/apiClient'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,   // sends httpOnly refresh token cookie
})

// ── Request interceptor — attach Bearer token ───────────────────────────────
apiClient.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor — handle 401, silent refresh, retry ───────────────
let isRefreshing = false
let failedQueue: Array<{ resolve: (t: string) => void; reject: (e: any) => void }> = []

function processQueue(error: any, token: string | null) {
  failedQueue.forEach(p => error ? p.reject(error) : p.resolve(token!))
  failedQueue = []
}

apiClient.interceptors.response.use(
  response => response,
  async error => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // Queue requests while refresh is in progress
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
        // Use API_BASE so refresh endpoint works in all environments
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
        })
        if (!res.ok) throw new Error('Refresh failed')
        const { access_token } = await res.json()
        tokenStore.set(access_token)
        processQueue(null, access_token)
        originalRequest.headers.Authorization = `Bearer ${access_token}`
        return apiClient(originalRequest)
      } catch (err) {
        processQueue(err, null)
        tokenStore.set(null)
        window.location.href = '/login'
        return Promise.reject(err)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
