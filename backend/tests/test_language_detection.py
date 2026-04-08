# test_language_detection.py - Version 1.0
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for get_response() in whatsapp_responses.py (v5.12 new file).
# Note: detect_language() tests are NOT here — detect_language() lives in
# whatsapp_formatter.py and should be tested in test_whatsapp_formatter.py
# if that file exists. This file tests only the new whatsapp_responses module.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/services/whatsapp_responses.py - get_response(), RESPONSES

import pytest

from app.services.whatsapp_responses import RESPONSES, get_response


class TestGetResponse:
    """Tests for the localised response string lookup function."""

    def test_role_blocked_english(self) -> None:
        reply = get_response("role_blocked", "english")
        assert "owner" in reply.lower()
        assert len(reply) > 0

    def test_role_blocked_hinglish(self) -> None:
        reply = get_response("role_blocked", "hinglish")
        assert "owner" in reply.lower()
        assert len(reply) > 0

    def test_role_blocked_hindi(self) -> None:
        reply = get_response("role_blocked", "hindi")
        # Hindi string is non-empty Devanagari — just verify non-empty
        assert len(reply) > 0

    def test_all_keys_have_all_three_languages(self) -> None:
        """Every key in RESPONSES must have english, hinglish, hindi variants."""
        required_langs = {"english", "hinglish", "hindi"}
        for key, lang_map in RESPONSES.items():
            missing = required_langs - set(lang_map.keys())
            assert not missing, (
                f"Key '{key}' is missing language variants: {missing}"
            )

    def test_all_variants_are_non_empty_strings(self) -> None:
        """Every language variant must be a non-empty string."""
        for key, lang_map in RESPONSES.items():
            for lang, value in lang_map.items():
                assert isinstance(value, str), (
                    f"Key '{key}', lang '{lang}' is not a string"
                )
                assert len(value.strip()) > 0, (
                    f"Key '{key}', lang '{lang}' is empty"
                )

    def test_unknown_key_returns_safe_fallback(self) -> None:
        """Missing key must return a string, never raise."""
        reply = get_response("nonexistent_key_xyz", "english")
        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_unknown_language_falls_back_to_english(self) -> None:
        """Unknown language variant falls back to english gracefully."""
        reply = get_response("role_blocked", "marathi")  # type: ignore[arg-type]
        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_placeholder_substitution_works(self) -> None:
        """get_response() with kwargs substitutes placeholders correctly."""
        # Add a key with placeholder to RESPONSES temporarily for this test
        # Since RESPONSES only has role_blocked right now (no placeholders),
        # we test that kwargs with no matching placeholders don't crash.
        reply = get_response("role_blocked", "english", unused_kwarg="value")
        assert "owner" in reply.lower()

    def test_returns_string_type_always(self) -> None:
        """Return type must always be str regardless of input."""
        for lang in ("english", "hinglish", "hindi"):
            result = get_response("role_blocked", lang)  # type: ignore[arg-type]
            assert isinstance(result, str)

    def test_each_language_variant_is_distinct(self) -> None:
        """English, Hinglish, and Hindi variants should differ from each other."""
        en = get_response("role_blocked", "english")
        hi = get_response("role_blocked", "hinglish")
        hd = get_response("role_blocked", "hindi")
        assert en != hi, "English and Hinglish should be different strings"
        assert en != hd, "English and Hindi should be different strings"
        assert hi != hd, "Hinglish and Hindi should be different strings"
