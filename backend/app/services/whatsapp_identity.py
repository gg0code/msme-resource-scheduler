"""
FILE:    whatsapp_identity.py
PATH:    backend/app/services/whatsapp_identity.py
PURPOSE: Resolves an incoming WhatsApp phone number to a ZetaOps tenant
         and user. This is the first thing that runs after signature
         verification on every inbound message. If the phone number is
         not registered, the message is rejected before touching the AI.

         Think of this as the doorman — it checks who is knocking before
         letting anyone into the system.

         Three functions are provided:
           resolve_identity()  — main lookup, called on every message
           check_consent()     — checks if owner agreed to data logging
           record_consent()    — called when owner replies HAAN (yes)

BRANCH:  v5-whatsapp
VERSION: v5.0
CREATED: 2026-03

DEPENDENCIES:
  app/models/whatsapp.py  — PhoneTenantMap SQLAlchemy model
  app/database.py         — AsyncSession database dependency
  migration 017           — phone_tenant_map table must exist before
                            this service can be used

USAGE:
  from app.services.whatsapp_identity import (
      resolve_identity, check_consent, record_consent
  )

  # Resolve phone to tenant on every inbound message
  identity = await resolve_identity(phone_number="+919876543210", db=db)
  if identity is None:
      return  # Phone not registered — reject silently

  # Check consent before logging conversation
  if identity.consent_given:
      # safe to log to whatsapp_conversations table

  # Record consent when owner replies HAAN
  await record_consent(phone_number="+919876543210", db=db)
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.sql import func

from app.models.whatsapp import PhoneTenantMap

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
                       Every DB query must filter by this value.
        user_id:       The specific user who linked this phone number.
                       Usually the factory owner (admin role).
        industry_type: The factory's industry vertical e.g. 'printing'.
                       Used by the AI to load the right tools and terminology.
        phone_number:  The E.164 phone number that was looked up.
        consent_given: Whether the owner has consented to conversation logging.
                       If False, conversations must NOT be saved to DB.
    """

    def __init__(
        self,
        tenant_id: int,
        user_id: int,
        industry_type: str,
        phone_number: str,
        consent_given: bool
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.industry_type = industry_type
        self.phone_number = phone_number
        self.consent_given = consent_given

    def __repr__(self) -> str:
        """
        String representation for logging — never logs sensitive data.

        We intentionally show only the last 4 digits of the phone number.
        Enough to identify in logs, not enough to constitute a data leak.
        """
        masked_phone = f"****{self.phone_number[-4:]}"
        return (
            f"IdentityResult(phone={masked_phone}, "
            f"tenant_id={self.tenant_id}, "
            f"industry={self.industry_type})"
        )


# ---------------------------------------------------------------------------
# FUNCTION 1 — resolve_identity()
# ---------------------------------------------------------------------------

async def resolve_identity(
    phone_number: str,
    db: AsyncSession
) -> IdentityResult | None:
    """
    Look up a WhatsApp phone number and return the matching tenant identity.

    This is called on every single inbound WhatsApp message, before any
    AI processing happens. It answers the question: "Which factory is
    this message from, and are they allowed to use this system?"

    Args:
        phone_number: WhatsApp phone number in E.164 format (+919876543210).
                      Meta/Interakt always sends numbers in this format.
                      E.164 = international format, starts with +, max 15 digits.
        db:           AsyncSession from FastAPI dependency injection.
                      Injected by the router — do not create sessions here.

    Returns:
        IdentityResult if the phone is registered and active.
        None if the phone is not found or the mapping is inactive.

        The caller (routers/whatsapp.py) must handle the None case by
        returning a 200 OK to Meta (to stop Meta from retrying) but
        NOT processing the message any further.

    Side effects:
        Updates last_seen_at timestamp on the phone_tenant_map row.
        This lightweight write tracks when each factory owner last
        used the WhatsApp Copilot — useful for pilot analytics.
    """

    # Guard: phone number must start with + (E.164 format).
    # Meta always sends in E.164 but we validate defensively.
    # A number without + means something went wrong upstream.
    if not phone_number or not phone_number.startswith("+"):
        logger.warning(
            f"Rejected phone number not in E.164 format: '{phone_number}'. "
            f"Expected format: +919876543210. "
            f"Check Interakt webhook configuration if this keeps happening."
        )
        return None

    # Query phone_tenant_map for this phone number.
    # We only return ACTIVE mappings — is_active=False means the owner
    # has unlinked their number via the LinkWhatsApp.tsx page.
    lookup_query = (
        select(PhoneTenantMap)
        .where(
            PhoneTenantMap.phone_number == phone_number,
            PhoneTenantMap.is_active == True  # noqa: E712 — SQLAlchemy needs == not 'is'
        )
    )

    query_result = await db.execute(lookup_query)

    # scalars().first() returns the first matching row as a Python object,
    # or None if no rows matched the WHERE conditions.
    phone_mapping = query_result.scalars().first()

    # If no mapping found, this phone is not registered with any ZetaOps tenant.
    # This is a normal case — someone might accidentally message the wrong number.
    if phone_mapping is None:
        logger.info(
            f"Phone ****{phone_number[-4:]} not found in phone_tenant_map. "
            f"Owner needs to link their number via the LinkWhatsApp page in ZetaOps. "
            f"No further processing for this message."
        )
        return None

    # Update last_seen_at to track when this owner last sent a message.
    # We use a direct UPDATE query instead of modifying the loaded object
    # because it avoids a second DB round-trip (load → modify → save).
    await db.execute(
        update(PhoneTenantMap)
        .where(PhoneTenantMap.id == phone_mapping.id)
        .values(last_seen_at=func.now())
    )
    await db.commit()

    logger.info(
        f"Identity resolved: ****{phone_number[-4:]} → "
        f"tenant_id={phone_mapping.tenant_id}, "
        f"industry={phone_mapping.industry_type}"
    )

    # Return a clean IdentityResult object — not the raw SQLAlchemy row.
    # This decouples all other services from the DB model structure.
    # If columns are renamed in the DB, only this return statement changes.
    return IdentityResult(
        tenant_id=phone_mapping.tenant_id,
        user_id=phone_mapping.user_id,
        # Default to 'manufacturing' if industry_type was never set on the tenant.
        # This should not happen in normal use but prevents None from
        # reaching the AI system prompt builder.
        industry_type=phone_mapping.industry_type or "manufacturing",
        phone_number=phone_number,
        consent_given=phone_mapping.consent_given
    )


# ---------------------------------------------------------------------------
# FUNCTION 2 — check_consent()
# ---------------------------------------------------------------------------

async def check_consent(
    phone_number: str,
    db: AsyncSession
) -> bool:
    """
    Check if a phone number has given consent for conversation logging.

    Called before writing any message to whatsapp_conversations table.
    If this returns False, the conversation must NOT be logged —
    the owner has not agreed to their data being used for Factory GPT training.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210
        db:           AsyncSession from FastAPI dependency injection.

    Returns:
        True if consent_given is True in phone_tenant_map.
        False if phone not found, mapping inactive, or consent not yet given.

        When in doubt, return False — never log without explicit consent.

    Side effects:
        None — read-only query. Does not modify any data.
    """

    # Query only the consent_given column — no need to load the full row.
    # This is more efficient than loading the entire PhoneTenantMap object.
    consent_query = (
        select(PhoneTenantMap.consent_given)
        .where(
            PhoneTenantMap.phone_number == phone_number,
            PhoneTenantMap.is_active == True  # noqa: E712
        )
    )

    result = await db.execute(consent_query)

    # scalar_one_or_none() returns a single value (not a row object),
    # or None if no matching row was found.
    consent_value = result.scalar_one_or_none()

    # Treat a missing row as no consent — the safest default.
    # We must never log data without confirmed consent.
    if consent_value is None:
        return False

    return consent_value


# ---------------------------------------------------------------------------
# FUNCTION 3 — record_consent()
# ---------------------------------------------------------------------------

async def record_consent(
    phone_number: str,
    db: AsyncSession
) -> bool:
    """
    Record that a factory owner has given consent for conversation logging.

    Called when the owner replies HAAN (yes) to the consent message
    sent on their first WhatsApp interaction with ZetaOps.

    After this is called, check_consent() will return True for this
    phone number and conversations will be logged to whatsapp_conversations.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210
        db:           AsyncSession from FastAPI dependency injection.

    Returns:
        True if consent was recorded successfully.
        False if the phone number was not found in phone_tenant_map.
                This should not happen in normal flow since the owner
                must have sent a message (and been resolved) before
                they can reply HAAN.

    Side effects:
        Sets consent_given = True and consent_at = now()
        on the phone_tenant_map row for this phone number.
        This change is permanent — consent cannot be revoked via WhatsApp.
        (Future: add a web UI option to revoke consent in LinkWhatsApp.tsx)
    """

    # First verify the mapping exists and is active before updating.
    # We query only the id column — we just need to confirm existence.
    check_query = (
        select(PhoneTenantMap.id)
        .where(
            PhoneTenantMap.phone_number == phone_number,
            PhoneTenantMap.is_active == True  # noqa: E712
        )
    )

    result = await db.execute(check_query)
    mapping_id = result.scalar_one_or_none()

    # If no active mapping found, we cannot record consent.
    # Log a warning — this indicates something unexpected happened in the flow.
    if mapping_id is None:
        logger.warning(
            f"Cannot record consent — phone ****{phone_number[-4:]} "
            f"not found in phone_tenant_map or mapping is inactive. "
            f"Owner must link their phone via LinkWhatsApp page first."
        )
        return False

    # Update both the consent flag and the timestamp in a single query.
    # consent_at records exactly when consent was given — for compliance audit.
    await db.execute(
        update(PhoneTenantMap)
        .where(PhoneTenantMap.id == mapping_id)
        .values(
            consent_given=True,
            consent_at=func.now()
        )
    )
    await db.commit()

    logger.info(
        f"Consent recorded for phone ****{phone_number[-4:]}. "
        f"Conversation logging is now active for this owner. "
        f"Data will be saved to whatsapp_conversations table."
    )
    return True
