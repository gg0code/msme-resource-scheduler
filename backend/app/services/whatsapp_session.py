"""
```python
"""
FILE PURPOSE
This file manages conversation history for WhatsApp messages using Redis as temporary storage.
It provides a sliding window of the last 10 messages per factory owner with a 30-minute TTL
(time to live), giving the AI memory within conversations so owners can reference previous
messages like "reschedule that job". Introduced in v5-whatsapp branch as part of the WhatsApp
Copilot feature. Sits in the services layer between WhatsApp message handlers and the AI service,
providing session state management without requiring permanent database storage.

WHAT THIS FILE DOES — step by step
1. Creates an async Redis client using UPSTASH_REDIS_URL from environment settings
2. Falls back to in-memory dictionary storage when Redis URL is not configured (development mode)
3. Defines session constants: 30-minute TTL, 10-message sliding window, Redis key prefix
4. Provides functions to load, save, and clear conversation history per phone number
5. Implements sliding window logic that drops oldest messages when limit is exceeded
6. Handles Redis connection failures gracefully by returning empty history instead of crashing
7. Logs all session operations with phone number masking for privacy (shows only last 4 digits)

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _create_redis_client
Type         : function (private helper)
Purpose      : Creates and configures an async Redis client using the Upstash URL from settings.
               Returns None if UPSTASH_REDIS_URL is not set, triggering mock mode for development.
               Logs warning when running in mock mode so developers know sessions won't persist.
Parameters   : None
Returns      : aioredis.Redis client instance if Redis URL configured, None for mock mode
Calls        : app.config.settings to read UPSTASH_REDIS_URL environment variable
DB/API       : Connects to Upstash Redis service via URL
Side effects : Logs warning message when UPSTASH_REDIS_URL is not configured

Name         : _build_session_key
Type         : function (private helper)
Purpose      : Constructs Redis key string for a phone number's session using namespaced format.
               Uses Redis colon convention for easy key discovery in Upstash dashboard.
Parameters   : phone_number (str) - E.164 format phone number like +919876543210
Returns      : Redis key string in format "whatsapp:session:+919876543210"
Calls        : No other functions
DB/API       : None
Side effects : None - pure string formatting function

Name         : get_session
Type         : async function (public)
Purpose      : Loads conversation history for a phone number from Redis or memory fallback.
               Returns messages in chronological order (oldest first) as expected by Groq API.
               Handles missing sessions gracefully by returning empty list for fresh conversations.
Parameters   : phone_number (str) - E.164 format phone number like +919876543210
Returns      : list[dict] - Message history with format [{"role": "user"|"assistant", "content": "..."}], empty list if no session
Calls        : _build_session_key(), redis_client.get(), clear_session() on corrupted data
DB/API       : Redis GET operation to retrieve JSON session data
Side effects : Logs debug messages, may clear corrupted session data, returns copy of history to prevent mutations

Name         : save_session
Type         : async function (public)
Purpose      : Saves conversation history to Redis with sliding window trimming and TTL reset.
               Ensures active conversations never expire by resetting TTL on every save.
               Applies MAX_SESSION_MESSAGES limit by dropping oldest messages when exceeded.
Parameters   : phone_number (str) - E.164 format phone number, history (list[dict]) - full conversation including new message
Returns      : bool - True if saved successfully, False if Redis operation failed
Calls        : _build_session_key(), redis_client.set(), json.dumps() for serialization
DB/API       : Redis SET operation with EX (expiry) parameter
Side effects : Writes to Redis or _mock_sessions dict, resets TTL, trims history, logs operations

WHO CALLS THIS FILE
- backend/app/services/whatsapp_service.py - imports get_session, save_session, add_message_to_session
- backend/app/routers/whatsapp_router.py - imports session functions for message handling endpoints
- backend/app/services/ai_service.py - imports get_ai_history to retrieve conversation context for Groq

IMPORTS EXPLAINED
- json: Serializes conversation history to JSON strings for Redis storage and deserializes on retrieval
- logging: Provides module logger for debugging session operations with phone number masking for privacy
- datetime, timezone: Used for timestamp handling in message history (imported but not used in shown code)
- redis.asyncio as aioredis: Async Redis client library for non-blocking Redis operations with Upstash
- app.config.settings: Application settings object that reads UPSTASH_REDIS_URL from environment variables

INTERN NOTES
- Easiest thing to break: Forgetting that get_session() returns a copy - modifying it won't save automatically, must call save_session()
- Non-obvious design decision: Uses Redis instead of PostgreSQL because session data is temporary and Redis TTL handles cleanup automatically without background jobs
- Most common mistake: Not handling Redis connection failures gracefully - always provide fallback behavior rather than crashing the conversation
- Design principle #9: WhatsApp services use sync Session, but this file uses async Redis client bridged with run_in_executor() in calling code
- What to check if behaving unexpectedly: Verify UPSTASH_REDIS_URL is set correctly and Upstash Redis instance is accessible, check Redis logs for connection errors
- v5-whatsapp merge note: This entire file is v5-only and should not be merged into v4-dev until WhatsApp Copilot feature is complete and stable
"""
```
"""

import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.config import settings

# ---------------------------------------------------------------------------
# Module logger — all messages prefixed with module name for easy filtering
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SESSION CONSTANTS — all tunable values defined here, never buried in logic
# ---------------------------------------------------------------------------

# How long a session lives without any new message (seconds).
# 1800 = 30 minutes. Timer resets on every new message.
# After this idle period, session expires and next message starts fresh.
SESSION_TTL_SECONDS = 1800

# Maximum messages to keep per session.
# 10 gives the AI enough context without bloating the Groq API request.
# Oldest messages are dropped when this limit is exceeded (sliding window).
MAX_SESSION_MESSAGES = 10

# Redis key namespace prefix.
# Full key format: whatsapp:session:+919876543210
# Colons are Redis convention for namespacing — makes keys easy to find
# in the Upstash dashboard and avoids collisions with other Redis keys.
SESSION_KEY_PREFIX = "whatsapp:session"


# ---------------------------------------------------------------------------
# REDIS CLIENT SETUP
# ---------------------------------------------------------------------------

def _create_redis_client() -> aioredis.Redis | None:
    """
    Create and return an async Redis client using the Upstash URL from .env.

    Returns None if UPSTASH_REDIS_URL is not set — this triggers mock mode
    where session history is stored in memory instead of Redis.
    Mock mode is fine for all development and simulator testing (v5.0-v5.4).
    In production (v5.6), UPSTASH_REDIS_URL must be set.

    Returns:
        Async Redis client if UPSTASH_REDIS_URL is set, None otherwise.

    Side effects:
        Logs a warning if running in mock mode so the developer knows
        sessions will not persist across server restarts.
    """
    if not settings.UPSTASH_REDIS_URL:
        # Mock mode — log a warning but do not crash.
        # This is expected during development before Upstash is configured.
        logger.warning(
            "UPSTASH_REDIS_URL not set in .env — running in mock mode. "
            "Session history stored in memory only (lost on restart). "
            "Sign up at upstash.com and set UPSTASH_REDIS_URL in .env "
            "before going live with pilot factories."
        )
        return None

    # decode_responses=True means Redis returns Python strings not bytes.
    # Without this, every value would need .decode('utf-8') after reading.
    return aioredis.from_url(
        settings.UPSTASH_REDIS_URL,
        decode_responses=True
    )


# Shared Redis client for the entire application.
# None = mock mode (UPSTASH_REDIS_URL not configured).
# Created once at module load — do not recreate inside functions.
redis_client = _create_redis_client()


# ---------------------------------------------------------------------------
# IN-MEMORY FALLBACK — used only when Redis is not configured
# ---------------------------------------------------------------------------
# When redis_client is None (mock mode), sessions are stored in this dict.
# Key = Redis key string, Value = list of message dicts.
# This dict is lost on every server restart — acceptable for development.
# NEVER use this in production with real pilot factories.
_mock_sessions: dict[str, list] = {}


# ---------------------------------------------------------------------------
# PRIVATE HELPER
# ---------------------------------------------------------------------------

def _build_session_key(phone_number: str) -> str:
    """
    Build the Redis key for a given phone number's session.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210

    Returns:
        Redis key string e.g. "whatsapp:session:+919876543210"
    """
    return f"{SESSION_KEY_PREFIX}:{phone_number}"


# ---------------------------------------------------------------------------
# PUBLIC FUNCTIONS
# ---------------------------------------------------------------------------

async def get_session(phone_number: str) -> list[dict]:
    """
    Load the conversation history for a phone number from Redis (or memory).

    Returns the last N messages in chronological order — oldest first,
    newest last. This is the format Groq expects for conversation history.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210

    Returns:
        List of message dicts: [{"role": "user"|"assistant", "content": "..."}]
        Returns empty list [] if no session exists or TTL has expired.
        Empty list = fresh conversation start — this is normal and expected.

    Side effects:
        None — read only. Does not reset the TTL.
        TTL resets only when save_session() is called.
    """
    session_key = _build_session_key(phone_number)

    # Mock mode — read from in-memory dict instead of Redis
    if redis_client is None:
        history = _mock_sessions.get(session_key, [])
        logger.debug(
            f"Mock session GET for ****{phone_number[-4:]} — "
            f"{len(history)} messages in history"
        )
        # Return a copy so caller mutations do not affect the stored data
        return list(history)

    # Real Redis mode
    try:
        # GET returns the stored JSON string, or None if key does not exist
        raw_session_data = await redis_client.get(session_key)

        if raw_session_data is None:
            # No session found — normal for new conversations or after TTL expiry
            logger.debug(
                f"No session in Redis for ****{phone_number[-4:]} — "
                f"fresh conversation"
            )
            return []

        # Parse JSON string back into a Python list
        history = json.loads(raw_session_data)

        logger.debug(
            f"Session loaded from Redis for ****{phone_number[-4:]} — "
            f"{len(history)} messages"
        )
        return history

    except json.JSONDecodeError as e:
        # Redis returned data that is not valid JSON — should never happen
        # in normal operation but could occur if data was manually edited.
        logger.error(
            f"Corrupted session data for ****{phone_number[-4:]} — "
            f"clearing and starting fresh. Error: {e}"
        )
        await clear_session(phone_number)
        return []

    except Exception as e:
        # Redis connection failure — return empty list so conversation
        # can continue without history rather than failing completely.
        logger.error(
            f"Redis GET failed for ****{phone_number[-4:]}. "
            f"AI will respond without conversation context. "
            f"Check UPSTASH_REDIS_URL in .env. Error: {e}"
        )
        return []


async def save_session(
    phone_number: str,
    history: list[dict]
) -> bool:
    """
    Save conversation history for a phone number to Redis (or memory).

    Applies the sliding window — drops oldest messages if history
    exceeds MAX_SESSION_MESSAGES. Resets TTL on every save so active
    conversations never expire mid-conversation.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210
        history:      Full conversation history list including the new message.
                      Format: [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        True if saved successfully, False if save failed.
        Caller can continue on False — session loss is not fatal,
        the AI just loses context for this conversation.

    Side effects:
        Writes to Redis or _mock_sessions.
        Resets TTL to SESSION_TTL_SECONDS.
        Drops oldest messages if history exceeds MAX_SESSION_MESSAGES.
    """
    session_key = _build_session_key(phone_number)

    # Apply sliding window — keep only the most recent MAX_SESSION_MESSAGES.
    # Drop from the front (oldest) not the back (newest).
    if len(history) > MAX_SESSION_MESSAGES:
        messages_to_drop = len(history) - MAX_SESSION_MESSAGES
        history = history[messages_to_drop:]
        logger.debug(
            f"Session trimmed for ****{phone_number[-4:]} — "
            f"dropped {messages_to_drop} oldest, keeping {MAX_SESSION_MESSAGES}"
        )

    # Mock mode — write to in-memory dict instead of Redis
    if redis_client is None:
        _mock_sessions[session_key] = history
        logger.debug(
            f"Mock session SET for ****{phone_number[-4:]} — "
            f"{len(history)} messages stored"
        )
        return True

    # Real Redis mode
    try:
        # Serialise to JSON — ensure_ascii=False preserves Hindi characters
        session_json = json.dumps(history, ensure_ascii=False)

        # SET with EX resets the TTL on every save.
        # Active conversations never expire — 30 min counts from LAST message.
        await redis_client.set(
            session_key,
            session_json,
            ex=SESSION_TTL_SECONDS
        )

        logger.debug(
            f"Session saved to Redis for ****{phone_number[-4:]} — "
            f"{len(history)} messages, TTL reset to {SESSION_TTL_SECONDS}s"
        )
        return True

    except Exception as e:
        logger.error(
            f"Redis SET failed for ****{phone_number[-4:]}. "
            f"Session not saved — next message will lose context. "
            f"Check UPSTASH_REDIS_URL in .env. Error: {e}"
        )
        return False


async def clear_session(phone_number: str) -> bool:
    """
    Delete the conversation session for a phone number.

    Called when owner types 'reset'/'naya'/'clear', a confirmation
    times out, or a corrupted session is detected.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210

    Returns:
        True if cleared successfully or key did not exist.
        False if deletion failed.

    Side effects:
        Removes key from Redis or _mock_sessions.
        Does NOT affect whatsapp_conversations DB table —
        logged messages in PostgreSQL are never deleted here.
    """
    session_key = _build_session_key(phone_number)

    # Mock mode — remove from in-memory dict
    if redis_client is None:
        # pop with None default = no error if key does not exist
        _mock_sessions.pop(session_key, None)
        logger.debug(f"Mock session CLEAR for ****{phone_number[-4:]}")
        return True

    # Real Redis mode
    try:
        await redis_client.delete(session_key)
        logger.info(
            f"Session cleared for ****{phone_number[-4:]} — "
            f"next message starts a fresh conversation"
        )
        return True

    except Exception as e:
        logger.error(
            f"Redis DELETE failed for ****{phone_number[-4:]}. "
            f"Session may still exist. "
            f"Check UPSTASH_REDIS_URL in .env. Error: {e}"
        )
        return False


async def add_message_to_session(
    phone_number: str,
    role: str,
    content: str
) -> list[dict]:
    """
    Convenience function — load session, append one message, save, return history.

    This is the function most callers should use instead of calling
    get_session() and save_session() separately. Handles the full
    load-append-save cycle in one call.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210
        role:         'user' for owner messages, 'assistant' for AI responses.
        content:      Message text. For voice notes prefix with [Voice]:
                      e.g. "[Voice] aaj ka schedule kya hai"

    Returns:
        Updated history list after appending the new message.
        Pass this to whatsapp_bridge.process_message() as conversation_history.

    Side effects:
        Reads from and writes to Redis or _mock_sessions.
        Resets session TTL.
    """
    # Validate role — only these two values are valid in conversation history.
    # System prompts are handled inside whatsapp_bridge.py, not here.
    if role not in ("user", "assistant"):
        raise ValueError(
            f"Invalid role '{role}'. "
            f"Must be 'user' or 'assistant'. "
            f"System prompts belong in whatsapp_bridge.py not session history."
        )

    # Load current history
    history = await get_session(phone_number)

    # Build new message dict.
    # We store timestamp for analytics — stripped before sending to Groq.
    # See get_ai_history() which returns Groq-safe history without timestamps.
    new_message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    history.append(new_message)

    # Save updated history (applies sliding window automatically)
    await save_session(phone_number, history)

    return history


async def get_ai_history(phone_number: str) -> list[dict]:
    """
    Return session history in the exact format Groq API expects.

    Groq only accepts 'role' and 'content' fields. Our session also
    stores 'timestamp' for analytics — this function strips it.

    Args:
        phone_number: E.164 format phone number e.g. +919876543210

    Returns:
        List of {role, content} dicts only — safe to pass directly
        to run_ai_chat() as the conversation_history argument.

    Side effects:
        None — read only.
    """
    full_history = await get_session(phone_number)

    # Strip timestamp field — Groq rejects unknown fields in message history
    ai_history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in full_history
        # Safety check — skip any malformed entries missing required fields
        if "role" in msg and "content" in msg
    ]

    return ai_history