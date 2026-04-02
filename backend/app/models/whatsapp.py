"""
```python
"""
FILE PURPOSE
This file defines SQLAlchemy ORM models for the WhatsApp Copilot feature in ZetaOps v5.x.
It exists to enable factory owners to interact with their scheduling system via WhatsApp messages
in Hindi/Hinglish, expanding access beyond the web interface. Introduced in v5-whatsapp branch
as part of the AI-powered messaging system. These models sit at the data layer, providing the
foundation for phone number authentication and conversation logging that feeds Factory GPT training.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy column types, relationship utilities, and the Base class from app/database
2. Defines PhoneTenantMap model that maps WhatsApp phone numbers to ZetaOps tenants and users
3. Sets up foreign key relationships to Tenant and User models from app/models/auth.py
4. Includes consent tracking, activity monitoring, and alert preferences for each phone mapping
5. Defines WhatsAppConversation model that logs every message sent and received during conversations
6. Stores message content, role (user/assistant), language detection, and session grouping
7. Provides safe __repr__ methods that mask phone numbers in logs to prevent data leaks

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : PhoneTenantMap
Type         : SQLAlchemy ORM class
Purpose      : Maps WhatsApp phone numbers to ZetaOps tenants and users, serving as the authentication
               gateway for inbound messages. Stores consent status, activity tracking, and alert
               preferences. Acts as the doorway that determines which tenant receives each WhatsApp message.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)  
Calls        : N/A (data model only)
DB/API       : Creates phone_tenant_map table via migration 017
Side effects : Stores phone mappings, consent records, and last activity timestamps

Name         : PhoneTenantMap.__repr__
Type         : instance method
Purpose      : Provides safe string representation for logging that masks sensitive phone numbers.
               Shows only last 4 digits to allow identification while preventing data leaks in logs.
Parameters   : self (PhoneTenantMap instance)
Returns      : str - masked phone representation like "PhoneTenantMap(phone=****3210, tenant_id=1, active=True)"
Calls        : Built-in string formatting
DB/API       : None
Side effects : None (read-only)

Name         : WhatsAppConversation  
Type         : SQLAlchemy ORM class
Purpose      : Stores complete conversation history between factory owners and ZetaOps AI for Factory GPT
               training. Each row represents one message turn (user input or assistant response). This is
               the primary dataset for training industry-specific AI models on real Hindi/Hinglish factory conversations.
Parameters   : N/A (ORM model)
Returns      : N/A (ORM model)
Calls        : N/A (data model only) 
DB/API       : Creates whatsapp_conversations table via migration 017
Side effects : Logs all message content, language detection, and session metadata for ML training

Name         : WhatsAppConversation.__repr__
Type         : instance method  
Purpose      : Provides safe string representation that masks phone numbers and truncates message content
               to prevent sensitive data exposure in application logs while maintaining debugging utility.
Parameters   : self (WhatsAppConversation instance)
Returns      : str - masked representation like "WhatsAppConversation(phone=****3210, role=user, content='aaj ka schedule kya...')"
Calls        : Built-in string slicing and formatting
DB/API       : None
Side effects : None (read-only)

WHO CALLS THIS FILE
- backend/app/services/whatsapp_auth.py imports PhoneTenantMap for phone number lookups
- backend/app/services/whatsapp_session.py imports WhatsAppConversation for message logging  
- backend/app/routers/whatsapp_router.py imports both models for API endpoints
- backend/app/crud/whatsapp_crud.py imports both models for database operations
- backend/alembic/versions/017_create_whatsapp_tables.py references these table definitions

IMPORTS EXPLAINED
- sqlalchemy column types (Boolean, Column, DateTime, etc.): Define database column types and constraints for phone mappings and message storage
- sqlalchemy.dialects.postgresql.JSONB: Stores alert preferences as flexible JSON in PostgreSQL for per-user notification settings
- sqlalchemy.orm.relationship: Creates object relationships to Tenant and User models for easy navigation without explicit joins
- app.database.Base: The declarative base class that all ORM models inherit from, providing SQLAlchemy table creation functionality

INTERN NOTES
- Easiest thing to break: Writing WhatsAppConversation rows when consent_given=False - this violates privacy requirements and breaks compliance
- Non-obvious design decision: PhoneTenantMap.industry_type is intentionally denormalized from Tenant to avoid joins on every inbound message, trading storage for performance
- Most common mistake: Forgetting to mask phone numbers in logs or error messages - always use the __repr__ methods or manual masking
- Design principle implemented: #2 (tenant scoping) - both models include tenant_id for proper data isolation, and #8 (feature flags) via WhatsApp-specific gating
- What to check if behaving unexpectedly: Verify migration 017 ran successfully, check that consent_given is True before logging conversations, ensure phone numbers are in E.164 format (+919876543210)
- v5-whatsapp merge consideration: These models are additive-only and safe to merge - they don't modify existing v4-dev tables, only add new WhatsApp-specific functionality
"""
```
"""

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# MODEL 1 — PhoneTenantMap
# ---------------------------------------------------------------------------

class PhoneTenantMap(Base):
    """
    Maps a WhatsApp phone number to a ZetaOps tenant and user.

    One row per linked phone number. Created when a factory owner
    links their number via the LinkWhatsApp.tsx page (v5.5).

    The is_active flag is used for soft-delete — if an owner changes
    their number, set is_active=False rather than deleting the row.
    This preserves the audit trail and consent history.
    """

    __tablename__ = "phone_tenant_map"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # WhatsApp phone number in E.164 format: +919876543210
    # Unique constraint enforced at both column and index level.
    # E.164 = international format, always starts with +, max 15 digits.
    phone_number = Column(
        String(20),
        nullable=False,
        unique=True,
        index=True
    )

    # Which factory this phone belongs to.
    # CASCADE delete: if the tenant is deleted, their phone mappings go too.
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Which user within the tenant linked this phone.
    # Usually the factory owner (admin role).
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Soft-delete flag. False = owner unlinked their number.
    # We keep the row so consent history and audit trail are preserved.
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true"
    )

    # Cached copy of tenant.industry_type — avoids joining tenants table
    # on every single inbound message. Updated when tenant changes industry.
    # Values: printing | manufacturing | fabrication | chemical | field_service
    industry_type = Column(String(50), nullable=True)

    # When the owner first linked their phone number
    linked_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False
    )

    # Updated on every inbound message — tracks last activity per owner.
    # Useful for pilot analytics: which factories are most active?
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    # Consent tracking — REQUIRED before logging conversations for Factory GPT.
    # Set to True when owner replies HAAN to the first welcome message.
    # If False, whatsapp_conversations rows must NOT be written for this owner.
    consent_given = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false"
    )

    # Timestamp of when consent was given — for compliance audit trail
    consent_at = Column(DateTime(timezone=True), nullable=True)
        # Who is this phone number — human readable label.
    # Set by the owner when linking via LinkWhatsApp.tsx page.
    # Shows in logs so we know "Amit marked Ravi absent" not just a phone number.
    # Examples: "Rajesh (Owner)", "Amit (Son)", "Priya (Partner)", "Suresh (Manager)"
    display_name = Column(
        String(100),
        nullable=True,
        comment="Human label for this phone — who is messaging"
    )

    # Role for future RBAC — not enforced during pilot.
    # All roles currently have identical access (owner-level).
    # Will be enforced in v5.7.
    # Values: 'owner' | 'manager' | 'viewer'
    phone_role = Column(
        String(20),
        nullable=False,
        default="owner",
        server_default="owner",
        comment="owner|manager|viewer — reserved, not enforced until v5.7"
    )

    # Per-tenant alert preferences stored as JSON.
    # Controls which proactive alerts the owner receives.
    # Default: all alert types ON for the pilot.
    # Example: {"morning_briefing": true, "job_delay": true,
    #           "machine_down": true, "conflict": true}
    alert_preferences = Column(
        JSONB,
        nullable=True,
        server_default=text(
            """'{"morning_briefing": true, "job_delay": true, """
            """"machine_down": true, "conflict": true}'"""
        )
    )



    # Relationships — lets us do phone_mapping.tenant.name etc.
    # These are read-only references, not cascade-delete owners.
    tenant = relationship("Tenant")
    user = relationship("User")

    def __repr__(self) -> str:
        """Safe string representation — masks phone number for logs."""
        # Show only last 4 digits of phone — enough to identify, not enough to leak
        masked = f"****{self.phone_number[-4:]}" if self.phone_number else "unknown"
        return (
            f"PhoneTenantMap(phone={masked}, "
            f"tenant_id={self.tenant_id}, "
            f"active={self.is_active})"
        )


# ---------------------------------------------------------------------------
# MODEL 2 — WhatsAppConversation
# ---------------------------------------------------------------------------

class WhatsAppConversation(Base):
    """
    Stores every message sent and received during the WhatsApp pilot.

    Each row is ONE message — either from the factory owner (role='user')
    or from the ZetaOps AI (role='assistant'). A full conversation is
    reconstructed by grouping rows on session_id in chronological order.

    This table is the Factory GPT training dataset. After 90 days across
    5 factories, it will contain 500+ real Hindi/Hinglish factory
    conversations that general LLMs cannot replicate.

    IMPORTANT: Rows are only written when consent_given=True on the
    corresponding PhoneTenantMap row. Never write rows without consent.
    """

    __tablename__ = "whatsapp_conversations"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Which factory this message belongs to.
    # Indexed for fast per-tenant conversation queries.
    # No ForeignKey intentionally — conversations are permanent logs
    # that must survive even if a tenant account is deleted.
    tenant_id = Column(Integer, nullable=False, index=True)

    # The phone number — links back to phone_tenant_map logically
    # (not via FK) so history survives phone unlinking.
    phone_number = Column(String(20), nullable=False, index=True)

    # 'user'      = message typed or spoken by the factory owner
    # 'assistant' = response generated by ZetaOps AI
    # Matches the role format used by Groq/OpenAI conversation history.
    role = Column(String(10), nullable=False)

    # The full message text.
    # For voice notes: Whisper transcription prefixed with [Voice]
    # so the training pipeline knows this was originally spoken.
    # Example: "[Voice] aaj Ravi absent hai"
    content = Column(Text, nullable=False)

    # How the message arrived or was sent:
    # 'text'  = owner typed a text message
    # 'voice' = owner sent a voice note (content is Whisper transcription)
    # 'alert' = proactive alert sent by ZetaOps (no user input triggered it)
    content_type = Column(
        String(20),
        nullable=False,
        server_default="text"
    )

    # Detected language of the message — for training data segmentation.
    # 'hindi'    = Devanagari script (ΰ€†ΰ€œ ΰ€•ΰ€Ύ ΰ€Άΰ₯‡ΰ€Ήΰ€Ύΰ€―ΰ€Ύΰ€‚ ΰ€•ΰ₯ΰ€―ΰ€Ύ ΰ€Ήΰ₯ˆ)
    # 'hinglish' = Hindi in Latin script mixed with English (aaj ka schedule)
    # 'english'  = Full English
    # NULL       = not yet detected (detection runs async after logging)
    language = Column(String(20), nullable=True)

    # Industry type at time of message — copied from PhoneTenantMap.
    # Stored here so training data can be filtered by vertical
    # e.g. "give me all printing industry conversations"
    industry_type = Column(String(50), nullable=True)

    # Groups all messages in one conversation window together.
    # Format: whatsapp:session:{phone}:{session_start_timestamp}
    # Matches the Redis session key used in whatsapp_session.py.
    session_id = Column(String(100), nullable=True, index=True)

    # Safety double-check — copied from PhoneTenantMap.consent_given
    # at the time of writing. The training pipeline filters on this.
    # A row should NEVER exist here with consent_given=False.
    consent_given = Column(
        Boolean,
        nullable=False,
        server_default="false"
    )

    # Message timestamp in UTC
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
        index=True
    )

    def __repr__(self) -> str:
        """Safe string representation for logs."""
        masked = f"****{self.phone_number[-4:]}" if self.phone_number else "unknown"
        # Truncate content to 50 chars — enough context, not a data leak
        short_content = (self.content[:50] + "...") if len(self.content) > 50 else self.content
        return (
            f"WhatsAppConversation(phone={masked}, "
            f"role={self.role}, "
            f"content='{short_content}')"
        )