# whatsapp_responses.py - Version 1.0
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Centralises all hardcoded WhatsApp outbound strings that are NOT generated
# by the AI. Every string that must be sent in a specific language regardless
# of AI output lives here. Language detection stays in whatsapp_formatter.py
# to avoid breaking existing imports.
#
# WHO CALLS THIS FILE
#   app/services/whatsapp_intent.py  - get_response('role_blocked', lang)
#                                      when a role check blocks an action
#   app/routers/whatsapp.py          - may call get_response() for future
#                                      hardcoded replies
#
# WHAT THIS FILE CALLS
#   Nothing - pure data module. No imports beyond stdlib typing.
#
# KEY DESIGN DECISIONS
#   - detect_language() is NOT here. It lives in whatsapp_formatter.py.
#     Moving it would break existing imports across the codebase.
#     This file only owns the response string lookup.
#   - Every key must have all three language variants: en, hinglish, hindi.
#     Missing a variant falls back to 'en' gracefully via get_response().
#   - Hindi values use escaped Unicode so the file has no non-ASCII characters.
#     Per dev rules: no non-ASCII in source files.
#   - Placeholder substitution uses str.format_map() with a safe fallback dict
#     so missing kwargs never raise KeyError.
#   - Never add logic here. This is a pure data + lookup module.

from typing import Literal

# ---------------------------------------------------------------------------
# Language type — matches detect_language() return values in whatsapp_formatter.py
# ---------------------------------------------------------------------------
Language = Literal["english", "hinglish", "hindi"]

# ---------------------------------------------------------------------------
# RESPONSES
# Hardcoded outbound strings keyed by (response_key, language).
#
# language values must match detect_language() in whatsapp_formatter.py:
#   'english', 'hinglish', 'hindi'
#
# Hindi unicode escapes decode as:
#   \u092f\u0939 = यह
#   \u0915\u093e\u092e = काम
#   \u0938\u093f\u0930\u094d\u092b = सिर्फ
#   \u092e\u093e\u0932\u093f\u0915 = मालिक
#   \u0915\u0930 = कर
#   \u0938\u0915\u0924\u093e = सकता
#   \u0939\u0948 = है
# ---------------------------------------------------------------------------
RESPONSES: dict[str, dict[Language, str]] = {
    "role_blocked": {
        "english":  "This action is only available to the owner.",
        "hinglish": "Ye query sirf owner kar sakta hai, bhai.",
        "hindi":    (
            "\u092f\u0939 \u0915\u093e\u092e \u0938\u093f\u0930\u094d\u092b "
            "\u092e\u093e\u0932\u093f\u0915 \u0915\u0930 \u0938\u0915\u0924\u093e "
            "\u0939\u0948\u0964"
        ),
    },
}


def get_response(key: str, lang: Language, **kwargs: str) -> str:
    """
    Returns the localised hardcoded response string for a given key and language.

    Called by:   app/services/whatsapp_intent.py - for 'role_blocked' reply.
    Calls:       str.format_map() for placeholder substitution.
    Args:
        key:     Response key. Must exist in RESPONSES dict.
                 Current valid values: 'role_blocked'
        lang:    Language string matching detect_language() output.
                 Valid values: 'english', 'hinglish', 'hindi'.
        **kwargs: Placeholder values for str.format_map().
                  Unused kwargs are silently ignored.
    Returns:
        Formatted string ready to send via WhatsApp.
        Falls back to 'english' variant if lang not found for key.
        Returns a safe fallback string if key not found at all.
    Side effects:
        None - pure function.
    """
    lang_map = RESPONSES.get(key)
    if lang_map is None:
        # Key not found - return safe fallback rather than raising
        return "Sorry, something went wrong. Please try again."

    # Fall back to English if the specific language variant is missing
    template = lang_map.get(lang) or lang_map.get("english", "")

    if not kwargs:
        return template

    # Safe format: missing placeholder keys render as {key} rather than raising
    class _SafeDict(dict):  # type: ignore[type-arg]
        def __missing__(self, k: str) -> str:
            return f"{{{k}}}"

    return template.format_map(_SafeDict(kwargs))
