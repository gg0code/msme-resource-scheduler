"""
```python
"""
FILE PURPOSE:
WhatsApp identity resolution service that maps incoming WhatsApp phone numbers to ZetaOps 
tenants and users. This is the security gatekeeper for the WhatsApp Copilot feature introduced 
in v5-whatsapp branch. Every inbound WhatsApp message must pass through this service first 
to determine which factory (tenant) the message belongs to and whether the sender is authorized 
to use the system. Without successful identity resolution, messages are rejected before reaching 
the AI processing pipeline.

WHAT THIS FILE DOES — step by step:
1. Defines IdentityResult data class that encapsulates resolved phone number identity
2. Provides resolve_identity() function that looks up phone numbers in phone_tenant_map table
3. Updates last_seen_at timestamp when phone numbers are successfully resolved
4. Provides check_consent() function to verify if conversation logging is allowed
5. Provides record_consent() function to save user consent for data logging
6. Handles all error cases defensively (unregistered phones, invalid formats, inactive mappings)
7. Masks phone numbers in logs for privacy compliance

KEY FUNCTIONS / CLASSES / COMPONENTS:

IdentityResult
    Type         : Data class
    Purpose      : Encapsulates the resolved identity information for a WhatsApp phone number. 
                   Acts as a clean interface between the database model and business logic, 
                   preventing tight coupling to SQLAlchemy models.
    Parameters   : tenant_id (int), user_id (int), industry_type (str), phone_number (str), 
                   consent_given (bool), display_name (str|None), phone_role (str)
    Returns      : N/A (constructor creates instance)
    Calls        : None (pure data container)
    DB/API       : No database or API calls
    Side effects : None (immutable data holder)

resolve_identity
    Type         : Function
    Purpose      : Main entry point for phone number resolution. Validates E.164 format, 
                   queries phone_tenant_map table for active mappings, and returns tenant 
                   information. Also updates last_seen_at timestamp for analytics tracking.
    Parameters   : phone_number (str) - E.164 format like +919876543210, db (Session) - SQLAlchemy session
    Returns      : IdentityResult object if phone is registered and active, None if not found or inactive
    Calls        : SQLAlchemy select/update queries, logging functions
    DB/API       : SELECT from phone_tenant_map WHERE phone_number and is_active=True, 
                   UPDATE last_seen_at timestamp
    Side effects : Updates last_seen_at column in database, writes to application logs

check_consent
    Type         : Function
    Purpose      : Read-only function to verify if a phone number owner has consented to conversation 
                   logging. Used before writing any data to whatsapp_conversations table to ensure 
                   GDPR compliance and data privacy requirements.
    Parameters   : phone_number (str) - E.164 format phone number, db (Session) - SQLAlchemy session
    Returns      : True if consent given and mapping is active, False otherwise (defaults to False for safety)
    Calls        : SQLAlchemy select query
    DB/API       : SELECT consent_given FROM phone_tenant_map WHERE phone_number and is_active=True
    Side effects : None (read-only operation)

record_consent
    Type         : Function
    Purpose      : Records user consent for conversation logging when owner replies "HAAN" (yes) to 
                   initial consent prompt. Once called, future check_consent() calls return True 
                   and conversations will be logged for Factory GPT training.
    Parameters   : phone_number (str) - E.164 format phone number, db (Session) - SQLAlchemy session
    Returns      : True if consent successfully recorded, False if phone mapping not found
    Calls        : SQLAlchemy update query
    DB/API       : UPDATE phone_tenant_map SET consent_given=True WHERE phone_number and is_active=True
    Side effects : Modifies consent_given column in database, commits transaction

WHO CALLS THIS FILE:
- backend/app/routers/whatsapp.py (main WhatsApp webhook handler)
- backend/app/services/whatsapp_service.py (before processing messages)
- backend/app/services/whatsapp_conversation.py (before logging conversations)

IMPORTS EXPLAINED:
- logging: Python standard library for structured application logging with module-level loggers
- sqlalchemy.orm.Session: SQLAlchemy session type for database transactions and queries  
- sqlalchemy.select/update: SQLAlchemy query builder functions for SELECT and UPDATE statements
- sqlalchemy.sql.func: SQLAlchemy SQL functions like func.now() for database-level timestamps
- app.models.whatsapp.PhoneTenantMap: SQLAlchemy ORM model representing phone-to-tenant mappings

INTERN NOTES:
- Easiest thing to break: Forgetting tenant_id filtering in queries - this would leak data between factories and violate design principle #2
- Non-obvious design decision: Returns IdentityResult object instead of raw SQLAlchemy model to decouple business logic from database schema changes
- Most common mistake: Not handling None return from resolve_identity() in calling code, which should result in message rejection not error
- Design principle implemented: #2 (tenant scoping on ALL DB queries) and #9 (WhatsApp services use sync Session)
- What to check if behaving unexpectedly: E.164 phone number format validation, is_active=True filtering, and last_seen_at timestamp updates in database
- v5-whatsapp merge note: This entire file is new in v5 and requires migration 017 (phone_tenant_map table) to be applied before deployment
"""
```
"""

import logging
from sqlalchemy.orm import Session
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
        # Show display_name if set — makes logs much more readable
        name_part = f", name={self.display_name}" if self.display_name else ""
        return (
            f"IdentityResult(phone={masked_phone}, "
            f"tenant_id={self.tenant_id}, "
            f"industry={self.industry_type}"
            f"{name_part})"
        )


# ---------------------------------------------------------------------------
# FUNCTION 1 — resolve_identity()
# ---------------------------------------------------------------------------

def resolve_identity(
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
    # We only return ACTIVE mappings — is_active=False means the owner
    # has unlinked their number via the LinkWhatsApp.tsx page.
    lookup_query = (
        select(PhoneTenantMap)
        .where(
            PhoneTenantMap.phone_number == phone_number,
            PhoneTenantMap.is_active == True  # noqa: E712 — SQLAlchemy needs == not 'is'
        )
    )

    query_result = db.execute(lookup_query)

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
        consent_given=phone_mapping.consent_given,
        phone_role=phone_mapping.phone_role or "owner"  # NEW
    )


# ---------------------------------------------------------------------------
# FUNCTION 2 — check_consent()
# ---------------------------------------------------------------------------

def check_consent(
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

    # Query only the consent_given column — no need to load the full row.
    # This is more efficient than loading the entire PhoneTenantMap object.
    consent_query = (
        select(PhoneTenantMap.consent_given)
        .where(
            PhoneTenantMap.phone_number == phone_number,
            PhoneTenantMap.is_active == True  # noqa: E712
        )
    )

    result = db.execute(consent_query)

    # scalar_one_or_none() returns a single value (not a row object),
    # or None if no matching row was found.
    consent_value = result.scalars().first()

    # Treat a missing row as no consent — the safest default.
    # We must never log data without confirmed consent.
    if consent_value is None:
        return False

    return consent_value


# ---------------------------------------------------------------------------
# FUNCTION 3 — record_consent()
# ---------------------------------------------------------------------------

def record_consent(
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
    # We query only the id column — we just need to confirm existence.
    check_query = (
        select(PhoneTenantMap.id)
        .where(
            PhoneTenantMap.phone_number == phone_number,
            PhoneTenantMap.is_active == True  # noqa: E712
        )
    )

    result = db.execute(check_query)
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
    db.execute(
        update(PhoneTenantMap)
        .where(PhoneTenantMap.id == mapping_id)
        .values(
            consent_given=True,
            consent_at=func.now()
        )
    )
    db.commit()

    logger.info(
        f"Consent recorded for phone ****{phone_number[-4:]}. "
        f"Conversation logging is now active for this owner. "
        f"Data will be saved to whatsapp_conversations table."
    )
    return True
