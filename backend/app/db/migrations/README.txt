FOLDER: backend/app/db/migrations
PURPOSE: Alembic database migrations for the v5-whatsapp feature.
         Each migration adds tables or columns needed by the WhatsApp channel.
BRANCH:  v5-whatsapp
CREATED: 2026-03

FILES:
  017_phone_tenant_map.py  — Creates phone_tenant_map table (phone → tenant/user mapping)
                             and whatsapp_conversations table (Factory GPT training data).
  018_phone_tenant_map_roles.py  — Adds display_name and phone_role to phone_tenant_map.
                                  Supports multiple named owners per factory.
                                  phone_role reserved for v5.7 RBAC — not enforced yet.

IMPORTANT — COLLISION WARNING:
  The Factory GPT branch (future) also plans to use migration numbers 017-022
  for its own new tables (sensor_readings, incidents, quality_records etc).
  When v5-whatsapp merges into main alongside Factory GPT, this migration
  must be renumbered to 023 or higher to avoid Alembic revision conflicts.
  This is tracked in V4_ALERTS.md at the repo root.

DEPENDENCIES:
  tenants table  — phone_tenant_map.tenant_id references tenants(id)
  users table    — phone_tenant_map.user_id references users(id)

NOTES:
  - All new columns are nullable or have defaults — no breaking changes to existing data.
  - consent_given must be TRUE before any conversation is used for Factory GPT training.