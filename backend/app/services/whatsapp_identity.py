"""
FILE:    whatsapp_identity.py
PATH:    backend/app/services/whatsapp_identity.py
PURPOSE: Resolves an incoming WhatsApp phone number to a ZetaOps tenant
         and user. This is the first thing that runs after signature
         verification on every inbound message. If the phone number is
         not registered, the message is rejected before touching the AI.

         Think of this as the doorman — it checks who is knocking before
         letting anyone into the system.

BRANCH:  v5-whatsapp
VERSION: v5.0
CREATED: 2026-03

DEPENDENCIES:
  app/db/models.py        — PhoneTenantMap SQLAlchemy model
  app/db/database.py      — AsyncSession database dependency
  migration 017           — phone_tenant_map table must exist

USAGE:
  from app.services.whatsapp_identity import resolve_identity
  identity = await resolve_identity(phone_number="+919876543210", db=db)
  if identity is None:
      # Phone not registered — reject the message
  else:
      # identity.tenant_id, identity.user_id, identity.industry_type
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.sql import func

from app.db.models import PhoneTenantMap

# ---------------------------------------------------------------------------
# Module logger — all log messages from this file are prefixed with
# the module name so they are easy to find when debugging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DATA CLASS — what resolve_identity() returns
# ---------------------------------------------------------------------------
# We return a simple object instead of the raw SQLAlchemy row.
# This keeps the rest of the codebase decoupled from the DB model.
# If the DB schema changes, only this file needs updating.

class IdentityResult:
    """
    The resolved identity of an inbound WhatsApp message sender.

    Returned by resolve_identity() when a phone number is found
    in the phone_tenant_map table and the mapping is active.

    Attributes:
        tenant_id:     The ZetaOps tenant (factory) this phone belongs to.
        user_id:       The specific user who linked this phone number.
        industry_type: The factory's industry vertical e.g. 'printing'.
                       Used by the AI to load the rig