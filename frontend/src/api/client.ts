// src/api/client.ts — V1.1
// Axios instance with JWT Bearer token interceptor.
// Token is stored in tokenStore (set by AuthContext after login/refresh).
// On 401 → attempts silent refresh → retries once → redirects to /login.

import axios from 'axios'
import { tokenStore } from '../auth/apiClient'

const apiClient = axios.create({
  baseURL: '/',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,   // sends httpOnly refresh token cookie
})

// ── Request interceptor — attach Bearer token ─────────────────────────────
apiClient.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor — handle 401, silent refresh, retry ─────────────
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
        const res = await fetch('http://localhost:8000/auth/refresh', {
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
