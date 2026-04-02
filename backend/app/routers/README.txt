FOLDER: backend/app/routers
PURPOSE: FastAPI route handlers for the WhatsApp Copilot feature.
         Each file defines API endpoints for one concern.
         Routers receive HTTP requests, call services, return responses.
BRANCH:  v5-whatsapp
CREATED: 2026-03

FILES:
  whatsapp.py  — Two endpoints:
                 POST /api/v1/whatsapp/webhook  — receives inbound messages
                   from Meta/Interakt, verifies signature, routes to AI,
                   sends response back to factory owner via Interakt.
                 POST /api/v1/whatsapp/simulate — development only endpoint,
                   simulates a full inbound message without real WhatsApp.
                   Used for all testing through v5.0-v5.4.
                 GET  /api/v1/whatsapp/webhook  — Meta webhook verification
                   handshake (required by Meta when registering webhook URL).

DEPENDENCIES:
  app/services/whatsapp_identity.py  — resolve phone to tenant
  app/services/whatsapp_session.py   — load/save conversation history
  app/services/whatsapp_bridge.py    — call AI backend
  app/services/whatsapp_formatter.py — format response for WhatsApp
  app/services/whatsapp_actions.py   — handle confirmation state machine
  app/services/whatsapp_alerts.py    — start/stop scheduler
  app/models/whatsapp.py             — WhatsAppConversation for logging
  app/database.py                    — database session dependency

NOTES:
  - Signature verification uses WHATSAPP_APP_SECRET from .env
  - WHATSAPP_MOCK_MODE=True skips Interakt and logs to console
  - /simulate endpoint is disabled in production (WHATSAPP_MOCK_MODE=False)
  - All endpoints return 200 OK to Meta even on errors — Meta retries
    on non-200 responses which causes duplicate message processing