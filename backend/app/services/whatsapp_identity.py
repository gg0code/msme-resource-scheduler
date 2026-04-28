import logging
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from sqlalchemy.sql import func

from app.models.auth import Tenant
from app.models.whatsapp import PhoneTenantMap

# ---------------------------------------------------------------------------
# Module logger - all log messages from this file are prefixed with
# the module name so they are easy to find when debugging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DATA CLASS - what resolve_identity() returns
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
        consent_given: bool,
        display_name: str | None = None,   # NEW — who is this person
        phone_role: str = "owner"          # NEW — their role (not enforced yet)
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.industry_type = industry_type
        self.phone_number = phone_number
        self.consent_given = consent_given
        self.display_name = display_name   # NEW
        self.phone_role = phone_role       # NEW

    def __repr__(self) -> str:
        """
        String representation for logging — never logs sensitive data.

        We intentionally show only the last 4 digits of the phone number.
        Enough to identify in logs, not enough to constitute a data leak.
        Shows display_name if set so logs show 'Amit' not just a phone number.
        """
        masked_phone = f"****{self.phone_number[-4:]}"
        # Show display_name if set - makes logs much more readable
        name_part = f", name={self.display_name}" if self.display_name else ""
        return (
            f"IdentityResult(phone={masked_phone}, "
            f"tenant_id={self.tenant_id}, "
            f"industry={self.industry_type}"
            f"{name_part})"
        )


# ---------------------------------------------------------------------------
# FUNCTION 1 - resolve_identity()
# ---------------------------------------------------------------------------

async def resolve_identity(
    phone_number: str,
    db: Session
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
    # We only return ACTIVE mappings - is_active=False means the owner
    # has unlinked their number via the LinkWhatsApp.tsx page.
    lookup_query = (
        select(PhoneTenantMap)
        .where(
            PhoneTenantMap.phone_number == phone_number,
            PhoneTenantMap.is_active == True  # noqa: E712 — SQLAlchemy needs == not 'is'
        )
    )

    query_result =  db.execute(lookup_query)

    # scalars().first() returns the first matching row as a Python object,
    # or None if no rows matched the WHERE conditions.
    phone_mapping = query_result.scalars().first()

    # If no mapping found, this phone is not registered with any ZetaOps tenant.
    # This is a normal case - someone might accidentally message the wrong number.
    if phone_mapping is None:
        logger.info(
            f"Phone ****{phone_number[-4:]} not found in phone_tenant_map. "
            f"Owner needs to link their number via the LinkWhatsApp page in ZetaOps. "
            f"No further processing for this message."
        )
        return None

    # Update last_seen_at to track when this owner last sent a message.
    # We use a direct UPDATE query instead of modifying the loaded object
    # because it avoids a second DB round-trip (load -> modify -> save).
    db.execute(
        update(PhoneTenantMap)
        .where(PhoneTenantMap.id == phone_mapping.id)
        .values(last_seen_at=func.now())
    )
    db.commit()

    logger.info(
        f"Identity resolved: ****{phone_number[-4:]} → "
        f"tenant_id={phone_mapping.tenant_id}, "
        f"industry={phone_mapping.industry_type}"
    )

    # Return a clean IdentityResult object - not the raw SQLAlchemy row.
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
        consent_given=phone_mapping.consent_given,
        phone_role=phone_mapping.phone_role or "owner"  # NEW
    )


# ---------------------------------------------------------------------------
# FUNCTION 2 - check_consent()
# ---------------------------------------------------------------------------

async def check_consent(
    phone_number: str,
    db: Session
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

    # Query only the consent_given column - no need to load the full row.
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

    # Treat a missing row as no consent - the safest default.
    # We must never log data without confirmed consent.
    if consent_value is None:
        return False

    return consent_value


# ---------------------------------------------------------------------------
# FUNCTION 3 - record_consent()
# ---------------------------------------------------------------------------

async def record_consent(
    phone_number: str,
    db: Session
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
    # We query only the id column - we just need to confirm existence.
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
    # Log a warning - this indicates something unexpected happened in the flow.
    if mapping_id is None:
        logger.warning(
            f"Cannot record consent — phone ****{phone_number[-4:]} "
            f"not found in phone_tenant_map or mapping is inactive. "
            f"Owner must link their phone via LinkWhatsApp page first."
        )
        return False

    # Update both the consent flag and the timestamp in a single query.
    # consent_at records exactly when consent was given - for compliance audit.
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


# ---------------------------------------------------------------------------
# FUNCTION 4 - link_phone_to_tenant() — v6.3.2
# ---------------------------------------------------------------------------

class PhoneAlreadyLinkedError(Exception):
    """Raised when the phone number is already linked to the given tenant.

    Callers translate this into the right HTTP status (409 from the
    link-phone endpoint, 400 from the v6.3.2 signup flow).
    """


def link_phone_to_tenant(
    db: Session,
    *,
    tenant_id: int,
    user_id: int,
    phone_number: str,
    phone_role: str = "owner",
    display_name: str | None = None,
    consent_given: bool = False,
) -> PhoneTenantMap:
    """
    Create a PhoneTenantMap row linking a WhatsApp phone number to a tenant.

    Single source of truth for PhoneTenantMap creation — both the v6.3.2
    signup flow and the LinkWhatsApp.tsx /api/v1/whatsapp/link-phone endpoint
    funnel through this. Encapsulates the BUG-6 industry-type lookup so
    callers cannot accidentally store a stale 'printing' default.

    Called by:
      - app/services/auth_service.register_tenant_and_user (v6.3.2 signup)
      - app/routers/whatsapp.link_phone (existing LinkWhatsApp.tsx endpoint)
    Calls into:
      - SQLAlchemy session (sync) — read tenant.industry_type, insert mapping.

    Args:
      db:            sync SQLAlchemy Session, NOT AsyncSession. The whatsapp
                     services are intentionally sync per CLAUDE.md.
      tenant_id:     destination tenant. Used to FK the row and to look up
                     industry_type so resolve_identity() returns the right
                     vertical on the very first inbound message.
      user_id:       which user inside the tenant linked this phone.
      phone_number:  E.164 string (validated by the schema layer).
      phone_role:    'owner' | 'manager' | etc. Defaults to 'owner' to match
                     the column server_default.
      display_name:  optional human label shown in logs.
      consent_given: whether the user has consented to conversation logging
                     at link time. Defaults to False; the WhatsApp HAAN flow
                     can flip this later via record_consent().

    Returns: the persisted PhoneTenantMap row, populated with PK after flush.

    Raises: PhoneAlreadyLinkedError if (phone_number, tenant_id) already
            exists. Caller decides how to surface this.

    Side effects: one INSERT into phone_tenant_map. The caller owns the
                  transaction boundary — this function flushes but does
                  NOT commit. The /link-phone router commits after; the
                  v6.3.2 signup flow commits once at the very end after
                  Tenant + User + PhoneTenantMap + RefreshToken are all
                  staged, preserving atomicity.
    """
    existing = (
        db.query(PhoneTenantMap)
        .filter(
            PhoneTenantMap.phone_number == phone_number,
            PhoneTenantMap.tenant_id == tenant_id,
        )
        .first()
    )
    if existing:
        raise PhoneAlreadyLinkedError(
            f"Phone {phone_number} is already linked to tenant {tenant_id}."
        )

    # BUG-6 fix: store the tenant's actual industry_type so the very first
    # inbound WhatsApp message resolves to the right vertical. Pre-BUG-6
    # code defaulted to 'printing' which broke fabrication / field_service
    # tenants whose AI then loaded the wrong tools and terminology.
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant_industry = tenant.industry_type if tenant else None

    new_mapping = PhoneTenantMap(
        phone_number=phone_number,
        tenant_id=tenant_id,
        user_id=user_id,
        is_active=True,
        industry_type=tenant_industry,
        consent_given=consent_given,
        display_name=display_name,
        phone_role=phone_role,
    )
    db.add(new_mapping)
    db.flush()

    logger.info(
        f"Phone linked: ****{phone_number[-4:]} -> "
        f"tenant_id={tenant_id}, role={phone_role}, "
        f"industry={tenant_industry}"
    )
    return new_mapping
