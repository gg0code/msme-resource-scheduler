# app/routers/whatsapp_debug.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.19.1 operator-debug endpoints. Currently exposes one endpoint:
#
#   POST /api/v1/whatsapp/debug/dispatch
#       Operator-driven dispatch test for the v6.3.19 push v2 cadence.
#       Top-tier auth required. Gated behind
#       settings.DEBUG_DISPATCH_ENABLED so production deployments can
#       turn it off via env even when the binary ships with the
#       endpoint compiled in.
#
# v6.3.19.1 — all four dispatch types are now supported
# ('morning' / 'evening' / 'delay_alert' / 'conflict_alert'). The
# PUSH_V2_ENABLED shadow-mode gate was removed in the cutover release;
# every dispatch sends for real (mock-aware via WHATSAPP_MOCK_MODE).
# The `force_send` request field is retained as a no-op for backward
# compatibility with v6.3.19 operator scripts.
#
# WHO CALLS THIS FILE
# - app/main.py — registers via include_router.
# - Operator curl smoke tests (see docs/v6_3_19_smoke_tests.md once
#   slice 2D-tests lands).
# - tests/integration/test_2d_dispatcher.py — integration tests in
#   slice 2D-tests.
#
# WHAT THIS FILE CALLS
# - app.services.consolidated_briefing.dispatch_morning / dispatch_evening
# - app.core.dependencies.get_current_user
# - app.core.security.is_top_tier (via User.is_top_tier property)
# - app.config.settings.DEBUG_DISPATCH_ENABLED

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.auth import User
from app.services.consolidated_briefing import (
    DispatchResult,
    dispatch_conflict_alert,
    dispatch_delay_alert,
    dispatch_evening,
    dispatch_morning,
)


router = APIRouter(
    prefix="/api/v1/whatsapp/debug",
    tags=["whatsapp-debug"],
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class DispatchRequest(BaseModel):
    """Body for POST /dispatch.

    type        — Which dispatcher to invoke. v6.3.19 supports
                  'morning' and 'evening' only; 'delay_alert' /
                  'conflict_alert' are reserved for v6.3.19.1 and
                  the endpoint rejects them with a 400.
    tenant_id   — Tenant to dispatch for. The caller's own tenant
                  must match (operators cannot cross-tenant probe).
    now         — ISO-8601 datetime to use as the dispatch's `now`
                  kwarg. Lets operators reproduce scheduled-time
                  decisions without waiting for the wall clock.
    force_send  — Retained for v6.3.19 backward compatibility. As of
                  v6.3.19.1 the dispatchers always send for real
                  (the shadow-mode flag PUSH_V2_ENABLED was removed),
                  so this parameter is ignored. Kept in the schema so
                  existing operator scripts don't break.
    job_id      — Required when type='delay_alert'. The specific Job to
                  alert about. The endpoint validates that the Job
                  belongs to tenant_id.
    conflict_payload — Required when type='conflict_alert'. Caller-
                  computed payload with job_a / job_b / resource /
                  window keys. Typically operators don't drive this
                  manually; the cron-fired push_v2_tick computes it
                  internally via _get_conflicts_for_dispatch.
    """

    type: Literal[
        "morning", "evening", "delay_alert", "conflict_alert",
    ] = Field(..., description="Dispatcher to invoke.")
    tenant_id: int = Field(..., gt=0)
    now: datetime
    force_send: bool = False
    job_id: int | None = None
    conflict_payload: dict | None = None


class DispatchResponse(BaseModel):
    """Response for POST /dispatch.

    actually_sent        — True when the dispatcher's send loop
                           reached at least one recipient successfully
                           and no skip branch fired. v6.3.19.1: the
                           shadow-mode flag was removed; every
                           dispatch sends for real.
    skip_reason          — Forwarded from DispatchResult; populated
                           when the dispatcher took a skip branch.
    would_send_to        — List of phone numbers the dispatcher
                           resolved as recipients. Empty on skip paths
                           that returned before recipient resolution.
    rendered_message     — Full Meta-bound template string. None when
                           a skip path returned before rendering.
    sent_count           — Number of phones the send loop reached.
    shadow_log_event_id  — Primary key of the events row written by
                           this dispatch (push.{kind}_sent on success,
                           push.{kind}_skipped_* on skip, etc.). Field
                           name retained from v6.3.19 for backward
                           compatibility with operator scripts; no
                           shadow_log rows exist post-cutover.
    """

    actually_sent: bool
    skip_reason: str | None
    would_send_to: list[str]
    rendered_message: str | None
    sent_count: int
    success: bool
    shadow_log_event_id: int | None


# ---------------------------------------------------------------------------
# POST /api/v1/whatsapp/debug/dispatch
# ---------------------------------------------------------------------------

@router.post("/dispatch", response_model=DispatchResponse)
async def debug_dispatch(
    payload: DispatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DispatchResponse:
    """Operator-driven shadow / force-send dispatch test.

    Called by:    operator curl + slice 2D-tests integration tests.
    Calls into:   dispatch_morning / dispatch_evening.
    Side effects: writes one events row (push.shadow_log or
                  push.{kind}_*) per call. May call Meta send when
                  force_send=True.

    AUTH RULES
    - settings.DEBUG_DISPATCH_ENABLED must be True (defaults True in
      dev, set False in prod via env). Returns 503 otherwise.
    - current_user.is_top_tier must be True. Returns 403 otherwise.
    - current_user.tenant_id must equal payload.tenant_id. Returns
      403 otherwise (operators cannot cross-tenant probe).

    SCOPE
    v6.3.19.1 — all four dispatch types are now supported. The
    PUSH_V2_ENABLED shadow-mode flag was removed; the dispatchers
    always send for real. `force_send` is retained as a no-op
    parameter for backward compatibility with v6.3.19 operator
    scripts.
    """
    if not settings.DEBUG_DISPATCH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEBUG_DISPATCH_ENABLED is False on this deployment.",
        )

    if not current_user.is_top_tier:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Top-tier role required for debug dispatch.",
        )

    if current_user.tenant_id != payload.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot dispatch for a different tenant than the caller.",
        )

    # v6.3.19.1 — all four dispatch types routed; no shadow mode.
    if payload.type == "morning":
        result: DispatchResult = await dispatch_morning(
            payload.tenant_id, payload.now, db,
        )
    elif payload.type == "evening":
        result = await dispatch_evening(
            payload.tenant_id, payload.now, db,
        )
    elif payload.type == "delay_alert":
        if payload.job_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="type='delay_alert' requires `job_id`.",
            )
        result = await dispatch_delay_alert(
            payload.tenant_id, payload.now, db, job_id=payload.job_id,
        )
    else:  # 'conflict_alert'
        if payload.conflict_payload is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "type='conflict_alert' requires `conflict_payload`."
                ),
            )
        result = await dispatch_conflict_alert(
            payload.tenant_id, payload.now, db,
            conflict_payload=payload.conflict_payload,
        )

    return DispatchResponse(
        actually_sent=result.sent_count > 0 and result.skip_reason is None,
        skip_reason=result.skip_reason,
        would_send_to=list(result.recipients),
        rendered_message=result.rendered_message,
        sent_count=result.sent_count,
        success=result.success,
        shadow_log_event_id=result.event_id,
    )
