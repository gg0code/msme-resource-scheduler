// frontend/src/api/client.ts
// Axios instance with JWT auth, token refresh, and tenant headers.
// All API calls go through this instance.

import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// -- In-memory token store -----------------------------------------------------
// Exported so AuthContext can set/clear the token after login/logout/refresh.
// Never persisted to localStorage or sessionStorage.

let _accessToken: string | null = null

export const tokenStore = {
  get: (): string | null => _accessToken,
  set: (t: string | null): void => { _accessToken = t },
}

// -- Axios instance ------------------------------------------------------------

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
