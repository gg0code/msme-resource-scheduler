/**
 * frontend/src/main.tsx
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * This is the main entry point for the ZetaOps Copilot React frontend application.
 * It bootstraps the entire React application by setting up global providers, routing
 * infrastructure, and API state management. Introduced in v4.0.9, it sits at the
 * absolute root of the React component tree and establishes the foundational context
 * that all other components depend on. It is loaded directly by Vite via index.html.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Imports React 18 StrictMode for development double-render checks and warnings.
 * 2. Imports createRoot from react-dom/client — the React 18 concurrent rendering API.
 * 3. Sets up BrowserRouter for client-side routing via the HTML5 history API.
 * 4. Creates a TanStack Query client with retry=1 and staleTime=30s defaults.
 * 5. Finds the #root DOM element in index.html and mounts the React tree onto it.
 * 6. Renders the provider hierarchy: StrictMode → QueryClientProvider → BrowserRouter → App.
 *
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 * Name         : queryClient
 * Type         : TanStack Query client instance
 * Purpose      : Manages all server state, caching, background refetching, and API request
 *                lifecycle for the entire application. retry=1 means failed requests are
 *                retried once before surfacing an error. staleTime=30_000 means cached
 *                data is considered fresh for 30 seconds before a background refetch fires.
 * Parameters   : defaultOptions.queries: { retry: 1, staleTime: 30_000 }
 * Returns      : QueryClient instance consumed by QueryClientProvider
 * Calls        : TanStack Query QueryClient constructor
 * DB/API       : No direct calls — manages all API calls made by child components
 * Side effects : Creates a global query cache shared across all components
 *
 * WHO CALLS THIS FILE
 * - frontend/index.html loads this as <script type="module" src="/src/main.tsx">
 * - No TypeScript file imports this — it is the application root
 *
 * IMPORTS EXPLAINED
 * - StrictMode from 'react': Enables extra runtime checks in dev mode only
 * - createRoot from 'react-dom/client': React 18 mounting API replacing legacy ReactDOM.render
 * - BrowserRouter from 'react-router-dom': Enables client-side routing with HTML5 history
 * - QueryClient, QueryClientProvider from '@tanstack/react-query': Server state management
 * - './index.css': Global styles including TailwindCSS base utilities
 * - App from './App': Root application component containing all routing and providers
 *
 * INTERN NOTES
 * - FeatureFlagProvider is NOT here — it lives inside App.tsx inside AuthProvider because
 *   feature flags require a logged-in tenant context to fetch from the backend.
 * - Never move BrowserRouter inside App.tsx — React Router hooks (useNavigate etc.) require
 *   BrowserRouter to be an ancestor, and App.tsx uses those hooks.
 * - Changing staleTime to 0 causes every component mount to fire an API call — leave at 30s.
 * - StrictMode causes every component to render twice in development — this is intentional
 *   and does NOT happen in production builds.
 * - Design principle #11: This file is the root of the strict TypeScript tree. Any type
 *   error here blocks the entire build.
 * - If the app shows a blank white screen: check browser console for "Cannot find #root" —
 *   it means index.html is missing <div id="root"></div>.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
