# test_whatsapp_router.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for pure helper functions in app/routers/whatsapp.py.
# Original tests referenced _mock_response from the old whatsapp_pipeline.py.
# The mock-mode send behaviour is now embedded in _send_whatsapp_message()
# in the router. That function is async and hits external APIs in production,
# so we test the payload extraction helper instead — it is pure and testable.
#
# _extract_message_from_payload: Parses Meta's nested webhook payload dict
# into a flat {phone_number, text, type, media_id?} result. It is the first
# function called on every inbound webhook event.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/routers/whatsapp.py  - _extract_message_from_payload

import pytest

from app.routers.whatsapp import _extract_message_from_payload


# ---------------------------------------------------------------------------
# Helpers — build minimal Meta-style webhook payloads
# ---------------------------------------------------------------------------

def _text_payload(phone: str, text: str) -> dict:
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": phone,
                        "type": "text",
                        "text": {"body": text},
                    }]
                }
            }]
        }]
    }


def _audio_payload(phone: str, media_id: str) -> dict:
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": phone,
                        "type": "audio",
                        "audio": {"id": media_id},
                    }]
                }
            }]
        }]
    }


def _image_payload(phone: str) -> dict:
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": phone,
                        "type": "image",
                        "image": {"id": "img_abc"},
                    }]
                }
            }]
        }]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractMessageFromPayload:
    """
    Tests for _extract_message_from_payload.
    This replaced _mock_response from the old whatsapp_pipeline.py — that
    function returned a canned response; this one parses the real Meta payload.
    All tests are pure (no DB, no network).
    """

    def test_extracts_text_message(self):
        payload = _text_payload("+919876543210", "aaj ka schedule kya hai")
        result = _extract_message_from_payload(payload)
        assert result is not None
        assert result["phone_number"] == "+919876543210"
        assert result["text"] == "aaj ka schedule kya hai"
        assert result["type"] == "text"

    def test_result_has_required_keys_for_text(self):
        payload = _text_payload("+919876543210", "hello")
        result = _extract_message_from_payload(payload)
        assert "phone_number" in result
        assert "text" in result
        assert "type" in result

    def test_returns_none_for_empty_messages_list(self):
        # No messages -> None (status update, read receipt etc.)
        payload = {
            "entry": [{"changes": [{"value": {"messages": []}}]}]
        }
        result = _extract_message_from_payload(payload)
        assert result is None

    def test_returns_none_for_missing_entry_key(self):
        result = _extract_message_from_payload({})
        assert result is None

    def test_returns_none_for_empty_payload(self):
        result = _extract_message_from_payload({"entry": []})
        assert result is None

    def test_extracts_audio_as_voice_type(self):
        # v5.2: audio type is renamed to 'voice' so rest of pipeline is uniform
        payload = _audio_payload("+919876543210", "media_abc123")
        result = _extract_message_from_payload(payload)
        assert result is not None
        assert result["type"] == "voice"

    def test_audio_message_includes_media_id(self):
        payload = _audio_payload("+919876543210", "media_abc123")
        result = _extract_message_from_payload(payload)
        assert result is not None
        assert result.get("media_id") == "media_abc123"

    def test_audio_message_text_is_empty_string(self):
        # text is empty for audio — filled after Whisper transcription
        payload = _audio_payload("+919876543210", "media_abc123")
        result = _extract_message_from_payload(payload)
        assert result is not None
        assert result["text"] == ""

    def test_returns_none_for_image_type(self):
        # Image is unsupported — should return None
        payload = _image_payload("+919876543210")
        result = _extract_message_from_payload(payload)
        assert result is None

    def test_returns_none_for_empty_text_body(self):
        # Text message with blank body must be ignored
        payload = _text_payload("+919876543210", "")
        result = _extract_message_from_payload(payload)
        assert result is None

    def test_returns_none_when_phone_missing(self):
        # No 'from' field -> can't process the message
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "type": "text",
                            "text": {"body": "hello"},
                        }]
                    }
                }]
            }]
        }
        result = _extract_message_from_payload(payload)
        assert result is None

    def test_phone_number_preserved_exactly(self):
        # Phone number must not be modified (E.164 format)
        payload = _text_payload("+911234567890", "test")
        result = _extract_message_from_payload(payload)
        assert result["phone_number"] == "+911234567890"

    def test_deeply_nested_payload_parsed_correctly(self):
        # Meta wraps messages in entry->changes->value->messages
        # Verify the full nesting is traversed
        payload = _text_payload("+919999999999", "deep test")
        result = _extract_message_from_payload(payload)
        assert result is not None
        assert result["text"] == "deep test"

    def test_malformed_nested_payload_returns_none(self):
        # Missing 'value' key — should not raise, should return None
        payload = {
            "entry": [{"changes": [{}]}]
        }
        result = _extract_message_from_payload(payload)
        assert result is None
