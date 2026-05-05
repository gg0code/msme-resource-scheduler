# app/services/extraction/__init__.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.14 entity extractor — public surface. The package writes
# inbound-WhatsApp entity candidates (employee / machine / customer /
# skill / material / job / issue) to the extraction_candidates table
# (migration 029) for v6.3.15+ promotion. Per-tenant gated by
# ENTITY_EXTRACTION_TENANT_IDS; default OFF for everyone.
#
# WHO CALLS THIS FILE
# - app/routers/whatsapp.py — `_process_inbound_message` schedules
#   `entity_extractor.schedule_extraction` after a message has cleared
#   role / consent / write-intent gates.
# - backend/inspect_extractions.py — dev tool, reads from the table.
# - backend/tests/services/test_entity_extractor.py
# - backend/tests/services/test_extraction_feature_flag.py
#
# WHAT THIS FILE CALLS
# - .feature_flag.is_entity_extraction_enabled
# - .entity_extractor.schedule_extraction (the only handle the router
#   needs; the rest is internal).
#
# DESIGN NOTES
# - Default: OFF for every tenant. Until a tenant id is added to
#   settings.ENTITY_EXTRACTION_TENANT_IDS this package is inert and
#   the WhatsApp pipeline behaves identically to v6.3.13.
# - Layout mirrors briefing_intelligence/ — feature_flag in its own
#   module so it can be reused by tests and future consumers without
#   importing the heavier extractor module.

from app.services.extraction.feature_flag import (
    is_entity_extraction_enabled,
)
from app.services.extraction.entity_extractor import (
    schedule_extraction,
)

__all__ = [
    "is_entity_extraction_enabled",
    "schedule_extraction",
]
