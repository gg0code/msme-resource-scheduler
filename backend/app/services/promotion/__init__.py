# app/services/promotion/__init__.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Public surface of the v6.3.15 (revised) candidate-promotion service.
#
# The package no longer silently inserts candidates into employees /
# machines on the nightly tick. Instead, the 02:00 IST cron evaluates
# candidates (fuzzy-match short-circuit only), the 19:00 IST cron asks
# the owner via a single WhatsApp message per tenant, and the inbound
# webhook hook applies confirmation decisions.
#
# WHO IMPORTS THIS PACKAGE
# - app/services/whatsapp_alerts.py - schedules evaluate_for_all_tenants
#   (02:00 IST) AND send_confirmations_for_all_tenants (19:00 IST).
# - app/routers/whatsapp.py - imports parse_reply,
#   apply_confirmation_decisions, find_inflight_batch_for_tenant,
#   compose_ack for the new Step 2.5 confirmation reply branch.
# - backend/inspect_extractions.py - uses EVENT_* constants and the
#   per-state filtering for --show-confirmations.
# - backend/tests/services/test_promotion_*.py - exercises the public
#   functions directly with fixtures.
#
# WHAT THIS PACKAGE EXPORTS
#  Cron entry points (async):
#   - evaluate_for_all_tenants            (02:00 IST tick)
#   - send_confirmations_for_all_tenants  (19:00 IST tick)
#  Per-tenant entry points (sync):
#   - evaluate_for_tenant
#   - compose_confirmation_for_tenant
#   - record_confirmation_sent
#   - apply_confirmation_decisions
#   - process_timeouts_for_tenant         (re-export from timeout_handler)
#   - find_inflight_batch_for_tenant      (used by the reply router)
#  Reply-path utilities:
#   - parse_reply                         (re-export from reply_parser)
#   - ParsedReply, Decision, Strategy
#   - compose_ack                         (re-export from confirmation_composer)
#  Telemetry shapes:
#   - EvaluationSummary
#   - BatchToSend
#   - ApplyConfirmationsSummary
#   - TimeoutSummary                      (re-export from timeout_handler)
#   - ComposedMessage                     (re-export from confirmation_composer)
#  Audit-event constants:
#   - EVENT_PROMOTED, EVENT_CONFIRMED, EVENT_SKIPPED
#   - EVENT_CONFIRMATION_REQUESTED, EVENT_CONFIRMATION_RECEIVED,
#     EVENT_CONFIRMATION_TIMEOUT
#   - REASON_DAILY_CAP, REASON_NO_TABLE, REASON_NO_TOP_TIER_PHONE
#  Helpers:
#   - fuzzy_best_match                    (string-similarity helper)

from app.services.promotion.confirmation_composer import (
    ComposedMessage,
    compose_ack,
    compose_message,
)
from app.services.promotion.fuzzy_match import fuzzy_best_match
from app.services.promotion.promoter import (
    ApplyConfirmationsSummary,
    BatchToSend,
    EVENT_CONFIRMATION_RECEIVED,
    EVENT_CONFIRMATION_REQUESTED,
    EVENT_CONFIRMATION_TIMEOUT,
    EVENT_CONFIRMED,
    EVENT_PROMOTED,
    EVENT_SKIPPED,
    EvaluationSummary,
    REASON_DAILY_CAP,
    REASON_NO_TABLE,
    REASON_NO_TOP_TIER_PHONE,
    apply_confirmation_decisions,
    compose_confirmation_for_tenant,
    evaluate_for_all_tenants,
    evaluate_for_tenant,
    find_inflight_batch_for_tenant,
    record_confirmation_sent,
    send_confirmations_for_all_tenants,
)
from app.services.promotion.reply_parser import (
    Decision,
    ParsedReply,
    Strategy,
    parse_reply,
)
from app.services.promotion.timeout_handler import (
    TimeoutSummary,
    process_timeouts_for_tenant,
)

__all__ = [
    # Cron entry points
    "evaluate_for_all_tenants",
    "send_confirmations_for_all_tenants",
    # Per-tenant entry points
    "evaluate_for_tenant",
    "compose_confirmation_for_tenant",
    "record_confirmation_sent",
    "apply_confirmation_decisions",
    "process_timeouts_for_tenant",
    "find_inflight_batch_for_tenant",
    # Reply-path utilities
    "parse_reply",
    "ParsedReply",
    "Decision",
    "Strategy",
    "compose_ack",
    "compose_message",
    # Telemetry shapes
    "EvaluationSummary",
    "BatchToSend",
    "ApplyConfirmationsSummary",
    "TimeoutSummary",
    "ComposedMessage",
    # Event constants
    "EVENT_PROMOTED",
    "EVENT_CONFIRMED",
    "EVENT_SKIPPED",
    "EVENT_CONFIRMATION_REQUESTED",
    "EVENT_CONFIRMATION_RECEIVED",
    "EVENT_CONFIRMATION_TIMEOUT",
    "REASON_DAILY_CAP",
    "REASON_NO_TABLE",
    "REASON_NO_TOP_TIER_PHONE",
    # Helpers
    "fuzzy_best_match",
]
