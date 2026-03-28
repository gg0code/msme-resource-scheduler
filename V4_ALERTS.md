\# V4\_ALERTS.md

\# Tracks changes made in v5-whatsapp that must also be cherry-picked to v4-dev.

\# Review this file every Monday before the weekly v4-dev → v5-whatsapp merge.

\# See V4-DEV ALERT PROTOCOL section in ZetaOps\_WhatsApp\_Context\_Prompt.md.



| Date | Commit | File | Change summary | Status |

|------|--------|------|----------------|--------|

| —    | —      | —    | No alerts yet  | —      |

```



\*\*Step 1 — create backend/app/services/README.txt:\*\*



Create this file at `backend/app/services/README.txt`:

```

FOLDER: backend/app/services

PURPOSE: All WhatsApp business logic services. Each file owns exactly one concern.

&#x20;        These files are the core of the v5-whatsapp feature. They sit between the

&#x20;        WhatsApp channel (routers/whatsapp.py) and the AI backend (ai\_chat.py).

BRANCH:  v5-whatsapp

CREATED: 2026-03



FILES:

&#x20; whatsapp\_bridge.py     — THE SEAM: wraps run\_ai\_chat() today, swaps to Factory GPT later.

&#x20;                          This is the ONLY file that changes when Factory GPT agents arrive.

&#x20; whatsapp\_identity.py   — Resolves a WhatsApp phone number to tenant\_id + user\_id.

&#x20;                          Looks up phone\_tenant\_map table in PostgreSQL.

&#x20; whatsapp\_session.py    — Manages conversation history in Redis (last 10 messages, 30 min TTL).

&#x20;                          Gives the AI memory within a conversation window.

&#x20; whatsapp\_formatter.py  — Strips markdown from AI responses for WhatsApp plain text.

&#x20;                          Truncates long responses. Converts bullet points.

&#x20; whatsapp\_actions.py    — Confirmation state machine for write actions (mark absent, create job).

&#x20;                          No DB write happens without explicit owner confirmation.

&#x20; whatsapp\_alerts.py     — APScheduler proactive alerts (morning briefing, job delay, machine down).

&#x20;                          Runs on cron schedule inside FastAPI process.



DEPENDENCIES:

&#x20; app/db/models.py          — SQLAlchemy models (PhoneTenantMap, WhatsAppConversation)

&#x20; app/services/ai\_chat.py   — existing run\_ai\_chat() function — DO NOT MODIFY THIS FILE

&#x20; app/core/config.py        — environment variables (UPSTASH\_REDIS\_URL, WHATSAPP\_APP\_SECRET)

&#x20; Upstash Redis             — external session store, free tier, see UPSTASH\_REDIS\_URL in .env



NOTES:

&#x20; - whatsapp\_bridge.py is the Factory GPT swap point. Touch nothing else when agents arrive.

&#x20; - Never call run\_ai\_chat() directly from any file other than whatsapp\_bridge.py.

&#x20; - Never import Redis directly in any file other than whatsapp\_session.py.

&#x20; - All functions that write to the DB must go through whatsapp\_actions.py only.

