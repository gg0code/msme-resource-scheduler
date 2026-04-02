"""
FILE:    whatsapp_whisper.py
PATH:    backend/app/services/whatsapp_whisper.py
PURPOSE: Voice note transcription for WhatsApp Copilot.

         When a factory owner sends a voice note instead of typing,
         this service downloads the audio and transcribes it to text
         using Groq's Whisper API (whisper-large-v3 model).

         The transcribed text is then passed into the normal message
         pipeline exactly as if the owner had typed it — no special
         handling needed downstream.

         Flow:
           1. Meta webhook receives audio message
           2. _extract_message_from_payload() detects type=audio
           3. transcribe_voice_note() is called with the media_id
           4. Audio file downloaded from Meta API using media_id
           5. Audio sent to Groq Whisper API for transcription
           6. Transcribed text returned as plain string
           7. Router prefixes with [Voice] and passes to AI pipeline

         Supported audio formats from WhatsApp:
           - .ogg (Opus codec) — WhatsApp default
           - .mp3, .mp4, .wav, .m4a — also accepted by Whisper

         Cost: FREE — uses existing GROQ_API_KEY, no new accounts needed.
         Groq Whisper free tier: 28,800 seconds/day (~8 hours of audio).
         A typical factory voice note is 10-30 seconds.
         Pilot scale (5 factories, 50 voice notes/day) = ~25 minutes/day.
         Well within free tier.

BRANCH:  v5-whatsapp
VERSION: v5.2
CREATED: 2026-03-30

DEPENDENCIES:
  groq==0.9.0              — already installed, supports audio transcription
  httpx==0.27.0            — already installed, used to download audio from Meta
  app/config.py            — GROQ_API_KEY, WHATSAPP_APP_SECRET
  app/config.py            — WHATSAPP_MOCK_MODE for dev mode bypass

NOTES:
  - In mock mode (WHATSAPP_MOCK_MODE=True), transcription is skipped and
    a placeholder text is returned. This lets us test the pipeline without
    real audio files.
  - Meta audio download requires a valid access token. In development,
    the simulator endpoint accepts a pre-transcribed text directly.
  - Audio files are downloaded to memory (BytesIO) — never written to disk.
    This avoids temp file cleanup issues and is safer for multi-tenant use.
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
