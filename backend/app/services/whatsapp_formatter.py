# app/services/whatsapp_formatter.py
# Branch: v5-whatsapp
# Iteration: v6.3.18 — reduced to a re-export shim
#
# FILE PURPOSE
# Backwards-compatibility shim. The implementation that used to live
# in this file (markdown -> WhatsApp post-processor + language
# heuristic) was folded into `app/services/message_formatters.py`
# during the v6.3.18 styling pass. Existing callers that import
# `format_for_whatsapp` or `detect_language` from this module keep
# working without edits because the names are re-exported below.
#
# WHO CALLS THIS FILE
# - app/routers/whatsapp.py (imports format_for_whatsapp, detect_language)
# - app/services/whatsapp_alerts.py (late-imports format_for_whatsapp
#   inside three private helpers)
# - app/services/whatsapp_checkin.py (imports format_for_whatsapp)
# - any future caller — but new code SHOULD import from
#   `app.services.message_formatters` directly. This shim is here only
#   to absorb the v6.3.18 file move with zero churn at the call sites.
#
# WHAT THIS FILE CALLS
# - app.services.message_formatters — single re-export source.
#
# DESIGN NOTE
# Keep this file's surface narrow: the public symbols that v5.0..v6.3.17
# callers used. Do not add new symbols here — add them in
# message_formatters and let new callers import from the canonical
# location. When the last legacy import is migrated, delete this file
# in a single follow-up commit.

from app.services.message_formatters import (
    BULLET_REPLACEMENT,
    MAX_MESSAGE_LENGTH,
    TRUNCATION_SUFFIX,
    detect_language,
    format_for_whatsapp,
)

__all__ = [
    "BULLET_REPLACEMENT",
    "MAX_MESSAGE_LENGTH",
    "TRUNCATION_SUFFIX",
    "detect_language",
    "format_for_whatsapp",
]
