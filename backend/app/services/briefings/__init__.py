# app/services/briefings/__init__.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Package marker for the v6.3.4 daily push briefings module. The package
# wires the cron-fired and manual-trigger briefing dispatch flows.
#
# WHO CALLS THIS FILE
# - app/services/whatsapp_alerts.py - imports dispatch_due_briefings to
#   register the 5-minute cron job.
# - app/services/whatsapp_intent.py - imports manual_trigger_briefing for
#   the WhatsApp request_briefing intent.
# - tests/test_briefings.py        - imports the public API directly.
#
# WHAT THIS FILE CALLS
# - Nothing at import time. The submodules below define the functions;
#   this __init__ only re-exports the public surface so callers do not
#   need to know the internal layout.
#
# PUBLIC SURFACE (re-exported)
# - dispatcher.dispatch_due_briefings  - cron entry point, every 5 min.
# - dispatcher.dispatch_briefing       - one (tenant, kind) dispatch.
# - dispatcher.manual_trigger_briefing - on-demand from WhatsApp intent.
# - dispatcher.resolve_recipients      - top-tier subscribed users.
# - dispatcher.is_working_day          - working-day checker.
# - dispatcher.compute_stagger_offset  - deterministic per-tenant offset.
# - dispatcher.DispatchSummary         - return type of dispatch_due_briefings.
# - dispatcher.BriefingDispatchResult  - return type of dispatch_briefing.

from app.services.briefings.dispatcher import (
    BriefingDispatchResult,
    DispatchSummary,
    compute_stagger_offset,
    dispatch_briefing,
    dispatch_due_briefings,
    is_working_day,
    manual_trigger_briefing,
    resolve_recipients,
)

__all__ = [
    "BriefingDispatchResult",
    "DispatchSummary",
    "compute_stagger_offset",
    "dispatch_briefing",
    "dispatch_due_briefings",
    "is_working_day",
    "manual_trigger_briefing",
    "resolve_recipients",
]
