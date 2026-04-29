// frontend/src/pages/PostSignupLanding.tsx
//
// PURPOSE
// v6.3.5 minimal landing page for whatsapp_first / hybrid proprietors
// straight after register. Per SRS Section 6.28 the message is "WhatsApp is
// home base, NOT the dashboard". Replaces the deleted ConnectWhatsApp.tsx.
//
// CALLED BY
// - frontend/src/App.tsx mounts this at /welcome.
// - frontend/src/pages/RegisterPage.tsx redirects here when
//   useAuth().register() returns next_step='connect_whatsapp'.
//
// CALLS INTO
// - apiClient.get(WHATSAPP.botNumber) - one fetch on mount for the wa.me
//   deep-link target. CTA renders disabled if the backend returned "".
// - apiClient.get(DASHBOARD.root) - "Today on the floor" stats card. The
//   landing page MUST tolerate a stats failure - per the prompt, render
//   "--" in any cell that errors instead of breaking the whole page.
// - useAuth() for the user's first name (woven into the title).
// - react-router Link for "Bookmark dashboard" + footer links.
//
// DESIGN NOTES
// - Stats fetch: react-query with retry: 1 + a 5s timeout via the existing
//   apiClient. Failures render "--", never a 500-style page.
// - Bot number fetch: also react-query, separate cache key. When the
//   number is empty string, primary CTA is disabled with an explanatory
//   tooltip - the rest of the page still works.
// - No top-bar, no sidebar - this page sits OUTSIDE Layout (App.tsx
//   places it as a public route since the user has just completed
//   registration and may not yet have full provider state).

import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { Bookmark, MessageCircle, Settings as SettingsIcon, Users } from 'lucide-react'

import apiClient from '../api/client'
import { DASHBOARD, WHATSAPP } from '../api/api_endpoints'
import { useAuth } from '../auth/useAuth'


interface BotNumberResponse {
  bot_number: string
}

interface DashboardSummary {
  total_active_jobs:   number
  available_employees: number
  // The landing only renders these three; the rest of DashboardData is
  // intentionally not typed here so an upstream shape change does not
  // break the build of this page.
}


function formatRevenuePlaceholder(): string {
  // v6.3.5 has no weekly-revenue endpoint yet (open item carried into
  // v6.5+). Render an em-dash placeholder so the cell does not look
  // broken. ASCII-only per Lesson 16/36.
  return '--'
}


export default function PostSignupLanding() {
  const navigate = useNavigate()
  const { user } = useAuth()

  // First name from email local-part if no display name is available.
  // Tolerates an undefined user (the route is technically public so a
  // direct visit before login is possible - we degrade gracefully).
  const firstName = (() => {
    if (!user?.email) return 'there'
    const local = user.email.split('@')[0] ?? ''
    if (!local) return 'there'
    // Capitalise the first letter for the title only.
    return local.charAt(0).toUpperCase() + local.slice(1)
  })()

  // -- Bot number ---------------------------------------------------------
  const botNumberQuery = useQuery<BotNumberResponse>({
    queryKey: ['whatsapp-bot-number'],
    queryFn:  () => apiClient.get<BotNumberResponse>(WHATSAPP.botNumber).then(r => r.data),
    retry:    1,
    staleTime: 60_000,
  })
  const botNumber = botNumberQuery.data?.bot_number ?? ''
  const waHref = botNumber
    ? `https://wa.me/${botNumber}?text=Hi`
    : undefined

  // -- Stats card (graceful fallback) -------------------------------------
  const statsQuery = useQuery<DashboardSummary>({
    queryKey: ['post-signup-stats'],
    queryFn:  () => apiClient.get<DashboardSummary>(DASHBOARD.root).then(r => r.data),
    retry:    1,
    staleTime: 30_000,
  })

  const jobsInProgress = statsQuery.isError
    ? '--'
    : statsQuery.isLoading
    ? '...'
    : String(statsQuery.data?.total_active_jobs ?? '--')

  const operatorsOnShift = statsQuery.isError
    ? '--'
    : statsQuery.isLoading
    ? '...'
    : String(statsQuery.data?.available_employees ?? '--')

  const revenue = formatRevenuePlaceholder()

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-50 to-amber-50 flex items-center justify-center p-5">
      <div className="w-full max-w-2xl">
        <div className="bg-white border border-gray-200 rounded-2xl shadow-md p-8 sm:p-10 text-center">
          {/* WhatsApp icon hero */}
          <div className="w-14 h-14 mx-auto mb-5 rounded-2xl bg-gradient-to-br from-green-500 to-green-700 grid place-items-center text-white">
            <MessageCircle size={28} />
          </div>

          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 tracking-tight mb-1.5">
            You&apos;re set up, {firstName}.
          </h1>
          <p className="text-base text-gray-500 mb-7">
            Your floor runs from WhatsApp now.
          </p>

          {/* CTA row */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center mb-8">
            {waHref ? (
              <a
                href={waHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 text-white font-semibold text-sm px-5 py-3 rounded-lg shadow-sm transition-colors"
              >
                <MessageCircle size={16} />
                Open WhatsApp
              </a>
            ) : (
              <button
                disabled
                title="Bot number not configured. Ask your admin to set WHATSAPP_BOT_NUMBER."
                className="inline-flex items-center justify-center gap-2 bg-green-600/40 text-white font-semibold text-sm px-5 py-3 rounded-lg cursor-not-allowed"
              >
                <MessageCircle size={16} />
                Open WhatsApp
              </button>
            )}
            <button
              onClick={() => navigate('/dashboard')}
              className="inline-flex items-center justify-center gap-2 bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 font-semibold text-sm px-5 py-3 rounded-lg transition-colors"
            >
              <Bookmark size={16} />
              Bookmark dashboard
            </button>
          </div>

          {/* Stats card */}
          <div className="bg-stone-100 rounded-xl p-5 mb-6 text-left">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-stone-500 mb-3">
              Today on the floor
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="text-xl font-bold text-gray-900">{jobsInProgress}</div>
                <div className="text-xs text-gray-500 mt-0.5">jobs in progress</div>
              </div>
              <div>
                <div className="text-xl font-bold text-gray-900">{operatorsOnShift}</div>
                <div className="text-xs text-gray-500 mt-0.5">operators on shift</div>
              </div>
              <div>
                <div className="text-xl font-bold text-gray-900">{revenue}</div>
                <div className="text-xs text-gray-500 mt-0.5">revenue this week</div>
              </div>
            </div>
          </div>

          {/* Footer links */}
          <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-gray-500">
            <Link to="/dashboard" className="hover:text-gray-800 underline-offset-2 hover:underline">
              View full dashboard
            </Link>
            <Link to="/settings/team" className="hover:text-gray-800 inline-flex items-center gap-1 underline-offset-2 hover:underline">
              <Users size={12} /> View team
            </Link>
            <Link to="/settings/team" className="hover:text-gray-800 inline-flex items-center gap-1 underline-offset-2 hover:underline">
              <SettingsIcon size={12} /> Settings
            </Link>
          </div>
        </div>

        <p className="text-center mt-4 text-xs text-stone-500">
          Tip: most days you&apos;ll never see this page. Tap &quot;Open WhatsApp&quot;
          once and the rest of your work happens there.
        </p>
      </div>
    </div>
  )
}
