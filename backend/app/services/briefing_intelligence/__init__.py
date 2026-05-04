# app/services/briefing_intelligence/__init__.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.11 pattern-aware briefing intelligence — public surface.
# Signal-driven replacement for the v6.3.4 templated morning/evening
# briefing, gated per-tenant by PATTERN_BRIEFING_TENANT_IDS.
#
# WHO CALLS THIS FILE
# - app/services/briefings/dispatcher.py — _build_content_for_kind()
#   wraps compose_briefing() in a feature-flag check + try/except
#   fallthrough so failure here NEVER breaks the v6.3.4 templated path.
# - tests/test_briefing_intelligence_*.py
#
# WHAT THIS FILE CALLS
# - .composer.compose_briefing
# - .feature_flag.is_pattern_briefing_enabled
# - .signals.SignalResult
#
# DESIGN NOTES
# - Default behavior: OFF for every tenant. Until a tenant id is added
#   to settings.PATTERN_BRIEFING_TENANT_IDS, this package is inert and
#   the existing v6.3.4 templated dispatcher path runs unchanged.
# - Section E.1 of v6_3_11_signals_spec.md sketches the full module
#   layout (catalog/{attendance, machine, job, customer, tenancy,
#   health}.py). Session 2B ships only catalog/job.py (one evaluator,
#   detect_delayed_jobs). Session 2C extends ALL_DETECTORS.

from app.services.briefing_intelligence.composer import compose_briefing
from app.services.briefing_intelligence.feature_flag import (
    is_pattern_briefing_enabled,
)
from app.services.briefing_intelligence.signals import SignalResult

__all__ = [
    "compose_briefing",
    "is_pattern_briefing_enabled",
    "SignalResult",
]
