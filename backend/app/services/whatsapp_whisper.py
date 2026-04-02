"""
```python
"""
FILE PURPOSE:
    Voice note transcription service for the WhatsApp Copilot feature in ZetaOps v5.x. 
    When factory owners send voice messages instead of typing, this service downloads 
    the audio from Meta's API and transcribes it to text using Groq's Whisper API. 
    Introduced in v5-whatsapp branch as part of the WhatsApp integration to make 
    voice-driven factory scheduling more accessible for owners who prefer speaking 
    over typing on mobile devices.

WHAT THIS FILE DOES — step by step:
    1. Receives a Meta media_id when webhook detects audio message type
    2. Downloads audio file from Meta Graph API using two-step process (get URL, then download)
    3. Validates audio file size against MAX_AUDIO_BYTES safety limit (10MB)
    4. Sends audio bytes to Groq Whisper API using whisper-large-v3 model
    5. Returns transcribed text as plain string to be passed into normal AI pipeline
    6. Handles mock mode bypass for development testing without real API calls
    7. Provides direct audio bytes transcription for simulator endpoint testing

KEY FUNCTIONS / CLASSES / COMPONENTS:

    Name         : transcribe_voice_note
    Type         : async function (exported)
    Purpose      : Main entry point for transcribing WhatsApp voice notes. Downloads 
                   audio from Meta API using media_id, then transcribes using Groq Whisper.
                   Returns None on failure so caller can send error message to owner.
    Parameters   : media_id (str) - Meta media ID from webhook payload, 
                   access_token (str) - WHATSAPP_ACCESS_TOKEN for Meta API authentication
    Returns      : str | None - transcribed text string or None if download/transcription failed
    Calls        : _download_meta_audio(), _transcribe_with_groq()
    DB/API       : Meta Graph API (2 calls: get URL, download file), Groq Whisper API
    Side effects : Logs transcription success/failure, holds audio in memory (never disk)

    Name         : transcribe_audio_bytes
    Type         : async function (exported)
    Purpose      : Direct transcription bypass for simulator endpoint testing. Accepts 
                   raw audio bytes instead of downloading from Meta API, allowing 
                   development testing with local audio files.
    Parameters   : audio_bytes (bytes) - raw audio file data, 
                   filename (str) - filename with extension for format detection (default: "voice_note.ogg")
    Returns      : str | None - transcribed text string or None if transcription failed
    Calls        : _transcribe_with_groq()
    DB/API       : Groq Whisper API only (no Meta API calls)
    Side effects : Logs mock mode behavior, bypasses Meta download step entirely

    Name         : _download_meta_audio
    Type         : async function (private helper)
    Purpose      : Two-step Meta Graph API download process. First gets download URL 
                   from media_id, then downloads actual audio bytes. Includes safety 
                   checks for file size and HTTP status codes.
    Parameters   : media_id (str) - Meta media identifier, 
                   access_token (str) - Meta API authentication token
    Returns      : bytes | None - raw audio file bytes or None if any download step failed
    Calls        : httpx.AsyncClient for HTTP requests
    DB/API       : Meta Graph API v18.0 (GET /media_id, GET download_url)
    Side effects : Logs download progress/errors, enforces MAX_AUDIO_BYTES limit

    Name         : _transcribe_with_groq
    Type         : async function (private helper)
    Purpose      : Sends audio bytes to Groq Whisper API for transcription. Uses 
                   asyncio.run_in_executor to wrap synchronous Groq SDK calls and 
                   avoid blocking FastAPI's event loop.
    Parameters   : audio_bytes (bytes) - raw audio data, 
                   filename (str) - filename with extension for Groq format detection
    Returns      : str | None - transcribed text or None if Groq API call failed
    Calls        : Groq SDK client, asyncio.get_running_loop().run_in_executor()
    DB/API       : Groq Whisper API (whisper-large-v3 model)
    Side effects : Wraps audio in BytesIO object, runs sync API call in thread pool

WHO CALLS THIS FILE:
    backend/app/routers/whatsapp_router.py - webhook handler calls transcribe_voice_note() 
    when message type is 'audio' in _extract_message_from_payload()
    
    backend/app/routers/whatsapp_simulator.py - test endpoint calls transcribe_audio_bytes() 
    for development testing with uploaded audio files

IMPORTS EXPLAINED:
    io - BytesIO wrapper for audio bytes, required by Groq SDK file upload interface
    logging - Module-level logger for transcription progress and error tracking
    httpx - Async HTTP client for downloading audio from Meta Graph API endpoints
    groq - Groq SDK client for Whisper API calls, already installed for AI chat service
    app.config - Settings object containing GROQ_API_KEY, WHATSAPP_MOCK_MODE, access tokens

INTERN NOTES:
    • Easiest thing to break: Missing GROQ_API_KEY in .env will cause all transcriptions 
      to fail with None return - always check settings.GROQ_API_KEY is set
    • Non-obvious design decision: Audio never touches disk, only held in memory as BytesIO 
      objects to avoid multi-tenant file cleanup issues and security risks
    • Most common mistake: Forgetting that Groq SDK is synchronous - must use 
      run_in_executor() wrapper to avoid blocking FastAPI's async event loop
    • Implements design principle #9: WhatsApp services use sync Session, bridge uses 
      run_in_executor() for async compatibility with FastAPI
    • If transcription behaves unexpectedly: Check WHATSAPP_MOCK_MODE setting, verify 
      Groq API key validity, and confirm Meta access token has media download permissions
    • v5-whatsapp merge note: This entire file is new in v5, check that GROQ_API_KEY 
      and WHATSAPP_MOCK_MODE are added to v4-dev settings when merging
"""
```
"""

import io
import logging

import httpx
from groq import Groq

from app.config import settings

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

# Groq Whisper model — best quality, free on Groq
WHISPER_MODEL = "whisper-large-v3"

# Meta Graph API base URL for downloading media
META_MEDIA_URL = "https://graph.facebook.com/v18.0"

# Maximum audio file size to download — 10MB safety limit
# WhatsApp limits voice notes to 16MB but we keep a lower limit
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10MB

# Filename sent to Groq — it uses the extension to detect format
# WhatsApp sends .ogg files by default
DEFAULT_AUDIO_FILENAME = "voice_note.ogg"


# ---------------------------------------------------------------------------
# MAIN TRANSCRIPTION FUNCTION
# ---------------------------------------------------------------------------

async def transcribe_voice_note(
    media_id: str,
    access_token: str,
) -> str | None:
    """
    Download a WhatsApp voice note and transcribe it using Groq Whisper.

    Called from the webhook handler when message type is 'audio'.
    Returns plain transcribed text ready to pass into the AI pipeline.

    In mock mode (WHATSAPP_MOCK_MODE=True): returns placeholder text
    without making any API calls. Useful for dev testing.

    Args:
        media_id:     The Meta media ID from the WhatsApp webhook payload.
                      Format: a long numeric string e.g. "123456789012345"
        access_token: Meta Graph API access token for downloading the audio.
                      This is the WHATSAPP_ACCESS_TOKEN from .env.

    Returns:
        Transcribed text string if successful.
        None if download or transcription failed — caller handles None
        by sending an error message to the owner.

    Side effects:
        Makes HTTP GET to Meta Graph API to download audio.
        Makes HTTP POST to Groq API for transcription.
        Audio data held in memory (BytesIO) — never written to disk.
    """

    # Mock mode — skip real API calls during development
    if settings.WHATSAPP_MOCK_MODE:
        logger.info(
            f"[MOCK WHISPER] Skipping real transcription for media_id={media_id}. "
            f"Returning placeholder text."
        )
        return "[Voice note received — transcription skipped in mock mode]"

    # Step 1: Get the audio download URL from Meta
    audio_bytes = await _download_meta_audio(
        media_id=media_id,
        access_token=access_token
    )

    if audio_bytes is None:
        logger.error(
            f"Failed to download audio for media_id={media_id}. "
            f"Transcription aborted. Check WHATSAPP_ACCESS_TOKEN in .env."
        )
        return None

    # Step 2: Transcribe the audio using Groq Whisper
    transcribed_text = await _transcribe_with_groq(audio_bytes=audio_bytes)

    if transcribed_text:
        logger.info(
            f"Voice note transcribed successfully. "
            f"media_id={media_id}, "
            f"length={len(transcribed_text)} chars, "
            f"preview='{transcribed_text[:50]}'"
        )
    else:
        logger.error(
            f"Groq Whisper transcription failed for media_id={media_id}. "
            f"Check GROQ_API_KEY in .env and Groq API status."
        )

    return transcribed_text


async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = DEFAULT_AUDIO_FILENAME) -> str | None:
    """
    Transcribe raw audio bytes directly — used by the simulator endpoint.

    This bypasses the Meta media download step, allowing the simulator
    to test transcription by uploading a local audio file directly.

    Args:
        audio_bytes: Raw audio file bytes (ogg, mp3, wav, m4a supported).
        filename:    Filename with extension — Groq uses this to detect format.
                     Default: "voice_note.ogg" (WhatsApp default format).

    Returns:
        Transcribed text string if successful, None if failed.

    Side effects:
        Makes HTTP POST to Groq API for transcription.
    """

    if settings.WHATSAPP_MOCK_MODE:
        logger.info("[MOCK WHISPER] Returning placeholder for direct audio bytes.")
        return "[Voice note received — transcription skipped in mock mode]"

    return await _transcribe_with_groq(
        audio_bytes=audio_bytes,
        filename=filename
    )


# ---------------------------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------------------------

async def _download_meta_audio(
    media_id: str,
    access_token: str,
) -> bytes | None:
    """
    Download audio file from Meta Graph API using the media_id.

    Meta's audio download is a two-step process:
      Step 1: GET /media_id — returns a JSON with the download URL
      Step 2: GET download_url — returns the raw audio bytes

    Args:
        media_id:     The media ID from the WhatsApp webhook payload.
        access_token: Meta Graph API access token.

    Returns:
        Raw audio bytes if successful, None if any step failed.

    Side effects:
        Makes two HTTP GET requests to Meta Graph API.
        Logs errors if download fails.
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:

            # Step 1: Get the download URL for the media
            meta_url = f"{META_MEDIA_URL}/{media_id}"
            url_response = await client.get(
                meta_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if url_response.status_code != 200:
                logger.error(
                    f"Meta media URL fetch failed. "
                    f"Status: {url_response.status_code}, "
                    f"media_id: {media_id}. "
                    f"Response: {url_response.text[:200]}"
                )
                return None

            # Parse the download URL from Meta's response
            url_data = url_response.json()
            download_url = url_data.get("url")

            if not download_url:
                logger.error(
                    f"Meta media response missing 'url' field. "
                    f"media_id={media_id}. "
                    f"Response: {url_data}"
                )
                return None

            # Step 2: Download the actual audio file
            audio_response = await client.get(
                download_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if audio_response.status_code != 200:
                logger.error(
                    f"Audio download failed. "
                    f"Status: {audio_response.status_code}, "
                    f"URL: {download_url[:100]}"
                )
                return None

            # Safety check — reject files that are too large
            audio_bytes = audio_response.content
            if len(audio_bytes) > MAX_AUDIO_BYTES:
                logger.error(
                    f"Audio file too large: {len(audio_bytes)} bytes "
                    f"(limit: {MAX_AUDIO_BYTES} bytes). "
                    f"media_id={media_id}. Transcription skipped."
                )
                return None

            logger.debug(
                f"Audio downloaded: {len(audio_bytes)} bytes "
                f"for media_id={media_id}"
            )
            return audio_bytes

    except httpx.TimeoutException:
        logger.error(
            f"Timeout downloading audio from Meta for media_id={media_id}. "
            f"Meta API may be slow. Owner should try again."
        )
        return None

    except Exception as e:
        logger.error(
            f"Unexpected error downloading audio from Meta: {e}. "
            f"media_id={media_id}. "
            f"Check network connectivity and access token validity."
        )
        return None


async def _transcribe_with_groq(
    audio_bytes: bytes,
    filename: str = DEFAULT_AUDIO_FILENAME
) -> str | None:
    """
    Send audio bytes to Groq Whisper API and return transcribed text.

    Uses whisper-large-v3 model — best quality, free on Groq.
    Audio is sent as a BytesIO object — never written to disk.

    Args:
        audio_bytes: Raw audio file bytes.
        filename:    Filename with extension for format detection.
                     Groq uses the extension (ogg, mp3, wav etc.)
                     to determine the audio format.

    Returns:
        Transcribed text string if successful.
        None if Groq API call failed.

    Side effects:
        Makes HTTP POST to Groq API.
        Uses GROQ_API_KEY from settings.
    """

    if not settings.GROQ_API_KEY:
        logger.error(
            "GROQ_API_KEY not set in .env. "
            "Cannot transcribe voice note. "
            "Add GROQ_API_KEY to backend/.env."
        )
        return None

    try:
        # Groq SDK is synchronous — wrap in thread pool to avoid blocking
        # FastAPI's async event loop (same pattern as run_ai_chat())
        import asyncio

        loop = asyncio.get_running_loop()

        def _call_groq_sync() -> str:
            """Run Groq Whisper synchronously in thread pool."""
            client = Groq(api_key=settings.GROQ_API_KEY)

            # Wrap bytes in BytesIO — Groq SDK accepts file-like objects
            # Tuple format: (filename, file_object, mime_type)
            audio_file = (filename, io.BytesIO(audio_bytes), "audio/ogg")

            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model=WHISPER_MODEL,
                response_format="text",  # Return plain text, not JSON
                language="hi",           # Hint: Hindi — improves accuracy
                                         # Whisper still handles Hinglish/English
            )

            # response_format="text" returns a string directly
            return transcription if isinstance(transcription, str) else str(transcription)

        # Run sync Groq call in thread pool — same pattern as run_ai_chat()
        transcribed_text = await loop.run_in_executor(None, _call_groq_sync)

        return transcribed_text.strip() if transcribed_text else None

    except Exception as e:
        logger.error(
            f"Groq Whisper transcription failed: {e}. "
            f"Check GROQ_API_KEY validity and Groq API status at status.groq.com."
        )
        return None
