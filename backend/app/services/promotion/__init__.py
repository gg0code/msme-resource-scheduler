# app/services/promotion/__init__.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Public surface of the v6.3.15 candidate-promotion service. The package
# reads high-confidence, frequently-mentioned rows from
# extraction_candidates (written by v6.3.14 entity extractor) and
# materialises them into the canonical employees / machines tables.
# Customer promotion is intentionally out of scope (no `customers`
# table exists at v6.3.15 — see promoter.py header for full rationale).
#
# WHO IMPORTS THIS PACKAGE
# - app/services/whatsapp_alerts.py — schedules promote_for_all_tenants
#   on the existing AsyncIOScheduler at 02:00 IST nightly.
# - backend/inspect_extractions.py — uses promoter constants to render
#   --show-promotions output.
# - backend/tests/services/test_promotion_*.py — exercises the public
#   functions directly with fixtures.
#
# WHAT THIS PACKAGE EXPORTS
# - promote_for_tenant       (promoter.py) — entry point per tenant.
# - promote_for_all_tenants  (promoter.py) — APScheduler entry point.
# - PromotionSummary         (promoter.py) — per-run telemetry shape.
# - fuzzy_best_match         (fuzzy_match.py) — string-similarity helper.
# - EVENT_PROMOTED / EVENT_CONFIRMED / EVENT_SKIPPED — audit-event
#   type constants kept here so the inspection script can grep
#   without importing the whole promoter module.
from app.services.promotion.promoter import (
    EVENT_PROMOTED,
    EVENT_CONFIRMED,
    EVENT_SKIPPED,
    PromotionSummary,
    promote_for_all_tenants,
    promote_for_tenant,
)
from app.services.promotion.fuzzy_match import fuzzy_best_match

__all__ = [
    "EVENT_PROMOTED",
    "EVENT_CONFIRMED",
    "EVENT_SKIPPED",
    "PromotionSummary",
    "fuzzy_best_match",
    "promote_for_all_tenants",
    "promote_for_tenant",
]
