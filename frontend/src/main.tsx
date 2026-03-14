// src/main.tsx — V3.7
// Added: FeatureFlagProvider — wraps entire app so flags are available everywhere
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FeatureFlagProvider } from './context/FeatureFlags'
import './index.css'
import App from './App'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <FeatureFlagProvider>
          <App />
        </FeatureFlagProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
