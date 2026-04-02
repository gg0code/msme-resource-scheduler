from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# ---------------------------------------------------------------------------
# Alembic revision identifiers - do not change these manually
# ---------------------------------------------------------------------------

# Unique ID for this migration - Alembic uses this to track which
# migrations have been applied to the database
revision = "017"

# The migration that must be applied before this one can run.
# 016 is the last migration from v4.0.9 (the base we branched from).
down_revision = "016"

# Standard Alembic fields - leave as-is
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Apply this migration — create both WhatsApp tables.

    Called by: alembic upgrade head
    Safe to run multiple times? No — will error if tables already exist.
    Check current state with: alembic current
    """

    # -----------------------------------------------------------------------
    # TABLE 1: phone_tenant_map
    # -----------------------------------------------------------------------
    # Maps a WhatsApp phone number to a ZetaOps tenant and user.
    # When an inbound WhatsApp message arrives, whatsapp_identity.py
    # queries this table to find out which factory is messaging.
    #
    # A factory owner links their phone number using the LinkWhatsApp.tsx
    # page in the ZetaOps web UI (built in v5.5).

    op.create_table(
        "phone_tenant_map",

        # Primary key - standard auto-increment integer ID
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),

        # The WhatsApp phone number in E.164 format: +919876543210
        # E.164 = international format with + prefix and country code.
        # UNIQUE because one phone number can only belong to one tenant.
        sa.Column(
            "phone_number",
            sa.String(20),
            nullable=False,
            unique=True,
            comment="WhatsApp phone in E.164 format e.g. +919876543210"
        ),

        # Which ZetaOps tenant (factory) owns this phone number.
        # References the existing tenants table from v4.0.9.
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            comment="The factory/tenant this phone number belongs to"
        ),

        # Which specific user within that tenant linked their phone.
        # Usually the factory owner (admin role).
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="The user who linked this phone number"
        ),

        # Soft-delete flag. Set to False to disable a phone without
        # deleting the record. Useful if an owner changes their number.
        sa.Column(
            "is_active",
            sa.Boolean,
            default=True,
            nullable=False,
            server_default="true",
            comment="False = phone unlinked but record kept for audit trail"
        ),

        # Cached copy of the tenant's industry type.
        # Stored here so whatsapp_identity.py can return everything
        # in one DB query instead of joining to the tenants table.
        # e.g. 'printing', 'manufacturing', 'fabrication', 'chemical', 'field_service'
        sa.Column(
            "industry_type",
            sa.String(50),
            nullable=True,
            comment="Cached from tenant — avoids extra join on every message"
        ),

        # Timestamps
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the owner linked their phone number"
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Updated every time a message arrives from this phone"
        ),

        # Consent tracking - REQUIRED for Factory GPT training data use.
        # If consent_given is False, conversations are NOT logged to
        # whatsapp_conversations table.
        # Owner gives consent by replying HAAN to the first welcome message.
        sa.Column(
            "consent_given",
            sa.Boolean,
            default=False,
            nullable=False,
            server_default="false",
            comment="TRUE only after owner replies HAAN to consent message"
        ),
        sa.Column(
            "consent_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of when consent was given"
        ),

        # Alert preferences - JSON object storing which alert types are ON/OFF.
        # Default is all alerts ON for the pilot.
        # Example: {"morning_briefing": true, "job_delay": true,
        #           "machine_down": true, "conflict": false}
        sa.Column(
            "alert_preferences",
            JSONB,
            nullable=True,
            server_default='{"morning_briefing": true, "job_delay": true, '
                           '"machine_down": true, "conflict": true}',
            comment="Per-tenant alert opt-in/out settings stored as JSON"
        ),
    )

    # Index on phone_number - this is the lookup key on every inbound message.
    # Without this index, every WhatsApp message triggers a full table scan.
    op.create_index(
        "idx_phone_tenant_map_phone",
        "phone_tenant_map",
        ["phone_number"],
        unique=True  # Enforces uniqueness at DB level as well as column constraint
    )

    # Index on tenant_id - used when loading all phones for a tenant
    # (e.g. when sending proactive alerts to all users of a factory)
    op.create_index(
        "idx_phone_tenant_map_tenant",
        "phone_tenant_map",
        ["tenant_id"]
    )

    # -----------------------------------------------------------------------
    # TABLE 2: whatsapp_conversations
    # -----------------------------------------------------------------------
    # Stores every message sent and received during the 90-day pilot.
    # This is the Factory GPT training dataset.
    #
    # Each row is ONE message (either from user or from assistant).
    # A full conversation is reconstructed by grouping on session_id.
    #
    # IMPORTANT: rows are only written if consent_given = TRUE on the
    # corresponding phone_tenant_map record.

    op.create_table(
        "whatsapp_conversations",

        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),

        # Which factory this conversation belongs to - for multi-tenant isolation
        sa.Column(
            "tenant_id",
            sa.Integer,
            nullable=False,
            comment="Factory that sent/received this message"
        ),

        # The phone number - links back to phone_tenant_map
        sa.Column(
            "phone_number",
            sa.String(20),
            nullable=False,
            comment="WhatsApp phone in E.164 format"
        ),

        # 'user' = message from factory owner
        # 'assistant' = response from ZetaOps AI
        sa.Column(
            "role",
            sa.String(10),
            nullable=False,
            comment="'user' or 'assistant' — matches OpenAI/Groq conversation format"
        ),

        # The actual message text.
        # For voice notes: contains the Whisper transcription,
        # prefixed with [Voice] so we know it was originally spoken.
        sa.Column(
            "content",
            sa.Text,
            nullable=False,
            comment="Message text. Voice notes stored as '[Voice] transcribed text'"
        ),

        # How the message arrived - text typed, voice note, or outbound alert
        # 'text'  = owner typed a message
        # 'voice' = owner sent a voice note (content is transcription)
        # 'alert' = proactive alert sent by ZetaOps (no user input)
        sa.Column(
            "content_type",
            sa.String(20),
            nullable=False,
            server_default="text",
            comment="'text', 'voice', or 'alert'"
        ),

        # Language detection result - used for training data filtering.
        # 'hindi'    = Devanagari script
        # 'hinglish' = Hindi words in Latin script mixed with English
        # 'english'  = Full English
        # NULL = not yet detected (detection happens async)
        sa.Column(
            "language",
            sa.String(20),
            nullable=True,
            comment="'hindi', 'hinglish', 'english', or NULL if not detected"
        ),

        # Industry vertical at time of message - for training data segmentation.
        # Copied from phone_tenant_map.industry_type at write time.
        sa.Column(
            "industry_type",
            sa.String(50),
            nullable=True,
            comment="Copied from tenant at write time — for training data filtering"
        ),

        # Groups all messages in one conversation together.
        # Format: whatsapp:session:{phone_number}:{timestamp_of_session_start}
        # Matches the Redis session key pattern from whatsapp_session.py.
        sa.Column(
            "session_id",
            sa.String(100),
            nullable=True,
            comment="Groups messages in same conversation. Matches Redis session key."
        ),

        # Consent flag - copied from phone_tenant_map at write time.
        # A row should NEVER exist here if consent_given was False.
        # This column is a safety double-check for the training pipeline.
        sa.Column(
            "consent_given",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="Safety check — must be TRUE for this row to be used in training"
        ),

        # When this message was sent or received
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Message timestamp in UTC"
        ),
    )

    # Index on tenant_id - for loading all conversations of a factory
    op.create_index(
        "idx_whatsapp_conv_tenant",
        "whatsapp_conversations",
        ["tenant_id"]
    )

    # Index on phone_number + created_at - for loading conversation history
    # in chronological order for a specific owner
    op.create_index(
        "idx_whatsapp_conv_phone_time",
        "whatsapp_conversations",
        ["phone_number", "created_at"]
    )

    # Index on session_id - for reconstructing a full conversation
    # from individual message rows
    op.create_index(
        "idx_whatsapp_conv_session",
        "whatsapp_conversations",
        ["session_id"]
    )


def downgrade() -> None:
    """
    Undo this migration — drop both WhatsApp tables.

    Called by: alembic downgrade -1
    WARNING: This permanently deletes all conversation log data.
    Only run this in development. Never run on production pilot data.
    """

    # Drop whatsapp_conversations first - it has no tables depending on it.
    # Dropping phone_tenant_map first would fail if FK references existed.
    op.drop_index("idx_whatsapp_conv_session", table_name="whatsapp_conversations")
    op.drop_index("idx_whatsapp_conv_phone_time", table_name="whatsapp_conversations")
    op.drop_index("idx_whatsapp_conv_tenant", table_name="whatsapp_conversations")
    op.drop_table("whatsapp_conversations")

    # Now safe to drop phone_tenant_map
    op.drop_index("idx_phone_tenant_map_tenant", table_name="phone_tenant_map")
    op.drop_index("idx_phone_tenant_map_phone", table_name="phone_tenant_map")
    op.drop_table("phone_tenant_map")