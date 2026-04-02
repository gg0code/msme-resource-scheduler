FOLDER: backend/app/services
PURPOSE: All WhatsApp business logic services. Each file owns exactly one concern.
         These files sit between the WhatsApp channel (routers/whatsapp.py)
         and the AI backend (ai_chat.py). They are the core of the v5-whatsapp
         feature and are designed to be independently readable and testable.
BRANCH:  v5-whatsapp
CREATED: 2026-03
UPDATED: 2026-03

---------------------------------------------------------------------------
FILES
---------------------------------------------------------------------------

whatsapp_bridge.py
  THE most important file in this folder.
  Wraps run_ai_chat() behind a Python Protocol interface called AIChannelBridge.
  The entire WhatsApp codebase calls active_bridge.process_message() — never
  run_ai_chat() directly. When Factory GPT agents are ready, only this file
  changes — a new class is written and one line is updated.
  Current implementation: GroqDirectBridge → calls run_ai_chat() directly.
  Future implementation:  SupervisorAgentBridge → calls Factory GPT Supervisor Agent.
  Template for future swap is commented out at the bottom of the file.

whatsapp_identity.py
  Resolves a WhatsApp phone number to a ZetaOps tenant_id, user_id,
  and industry_type by querying the phone_tenant_map table (migration 017).
  Returns an IdentityResult object (not the raw DB row) to keep other
  services decoupled from the SQLAlchemy model.
  Also handles consent tracking — check_consent() and record_consent().
  Called on EVERY inbound message before any AI processing happens.
  Returns None if phone is not registered → message is silently ignored.

whatsapp_session.py
  Manages conversation history (last 10 messages) per phone number in Redis.
  Gives the AI memory within a conversation window.
  Session TTL: 30 minutes from last message — expires automatically.
  Sliding window: oldest messages dropped when 11th message arrives.
  Mock mode: when UPSTASH_REDIS_URL is empty in .env, sessions are stored
  in an in-memory Python dict (_mock_sessions) instead of Redis.
  Mock mode is the default during development — no Redis setup needed.
  Key functions:
    get_session()              — load history from Redis or memory
    save_session()             — save history, reset TTL, apply sliding window
    clear_session()            — delete session (reset/naya command or timeout)
    add_message_to_session()   — convenience: load + append + save in one call
    get_ai_history()           — return history stripped of timestamps (Groq-safe)

whatsapp_formatter.py  [TO BE BUILT — v5.1]
  Strips markdown from AI responses and formats them for WhatsApp plain text.
  run_ai_chat() returns responses with markdown (**, ###, -, ```).
  WhatsApp does not render markdown the same way as a web UI.
  Responsibilities:
    - Remove ** bold markers
    - Remove ### headers (replace with newline)
    - Convert - bullet points to • bullets
    - Remove ``` code blocks
    - Truncate responses longer than 1500 characters
    - Convert markdown tables to line-by-line plain text

whatsapp_actions.py  [TO BE BUILT — v5.3]
  Confirmation state machine for write actions.
  When the AI detects a write intent (mark absent, create job, update status),
  the response is held in a PENDING_CONFIRMATION state.
  Owner must reply HAAN/yes/ok to confirm before any DB write happens.
  Timeout: 5 minutes — if no reply, action is auto-cancelled.
  No DB write ever happens without passing through this service.

whatsapp_alerts.py  [TO BE BUILT — v5.4]
  Proactive alert scheduler using APScheduler running inside FastAPI process.
  Sends alerts to factory owners without them asking first.
  Alert types:
    BRIEFING     — 7am IST daily morning summary
    JOB_DELAY    — sent when a job falls behind schedule
    MACHINE_DOWN — sent when machine status changes to maintenance/breakdown
    CONFLICT     — sent when a scheduling conflict is detected
  Each alert type can be opted out per tenant via alert_preferences JSON
  column in phone_tenant_map table.

---------------------------------------------------------------------------
DEPENDENCIES
---------------------------------------------------------------------------

  app/models/whatsapp.py      — PhoneTenantMap and WhatsAppConversation models
  app/models/auth.py          — Tenant and User models (referenced via ForeignKey)
  app/database.py             — AsyncSession database dependency
  app/config.py               — Settings object (UPSTASH_REDIS_URL, WHATSAPP_MOCK_MODE etc.)
  app/services/ai_chat.py     — existing run_ai_chat() function — DO NOT MODIFY
  migration 017               — phone_tenant_map and whatsapp_conversations tables
  redis (pip package)         — pip install redis
  Upstash Redis (cloud)       — free tier at upstash.com, set UPSTASH_REDIS_URL in .env

---------------------------------------------------------------------------
RULES FOR THIS FOLDER
---------------------------------------------------------------------------

  1. Never call run_ai_chat() directly from any file in this folder.
     Always go through active_bridge in whatsapp_bridge.py.

  2. Never import Redis directly outside of whatsapp_session.py.
     All session operations go through the functions in whatsapp_session.py.

  3. Never write to the DB outside of whatsapp_actions.py and whatsapp_identity.py.
     whatsapp_bridge.py, whatsapp_session.py, and whatsapp_formatter.py are read-only.

  4. Never log a conversation to whatsapp_conversations without checking
     consent_given first via whatsapp_identity.check_consent().

  5. Every function in this folder must have a docstring.
     Every non-obvious line must have an inline comment.
     See DOCUMENTATION STANDARDS in ZetaOps_WhatsApp_Context_Prompt.md.

---------------------------------------------------------------------------
FACTORY GPT SWAP POINT
---------------------------------------------------------------------------

  When Factory GPT Supervisor Agent is ready (planned Month 2-3):
    1. Open whatsapp_bridge.py only
    2. Write SupervisorAgentBridge class (template at bottom of that file)
    3. Change: active_bridge = SupervisorAgentBridge()
    4. Done — all files in this folder continue working unchanged

---------------------------------------------------------------------------
NOTES
---------------------------------------------------------------------------

  Migration numbering collision:
    Factory GPT branch plans migrations 017-022 for its own tables.
    This v5-whatsapp branch also uses 017.
    When merging into main, renumber this migration to 023 or higher.
    Tracked in V4_ALERTS.md at repo root.

  Redis mock mode:
    UPSTASH_REDIS_URL empty in .env = mock mode active.
    Sessions stored in memory, lost on restart.
    Acceptable for development and simulator testing (v5.0-v5.4).
    Must configure real Redis before pilot goes live (v5.6).

  Whisper voice pipeline:
    Not yet in this folder — being added in v5.2.
    Will live in whatsapp_voice.py (new file, not listed above yet).
    README.txt will be updated when that file is added.
