// frontend/src/pages/ConnectWhatsApp.tsx
//
// PURPOSE
// Placeholder route shown to users who completed signup as whatsapp_first
// (1-15) or hybrid (16-50). Replaces nothing in v6.3.2 — full QR-scan +
// WhatsApp onboarding flow lands in v6.3.5. Until then this page exists
// only so the post-signup redirect from RegisterPage has a real
// destination URL instead of a 404.
//
// CALLED BY
// - react-router via App.tsx route /connect-whatsapp.
// - RegisterPage.tsx submit handler when backend returns
//   next_step === 'connect_whatsapp'.
//
// CALLS INTO
// - Nothing. Static content + a single Link back to /dashboard.

import { Link } from 'react-router-dom'

export default function ConnectWhatsAppPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-sm border border-gray-200 p-8 text-center">
        <h1 className="text-2xl font-bold text-gray-900 mb-3">Connect WhatsApp</h1>
        <p className="text-sm text-gray-600 mb-6">
          Coming soon — your WhatsApp connection step. For now, you can use
          the dashboard.
        </p>
        <Link
          to="/dashboard"
          className="inline-block py-2.5 px-5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors"
        >
          Go to dashboard
        </Link>
      </div>
    </div>
  )
}
