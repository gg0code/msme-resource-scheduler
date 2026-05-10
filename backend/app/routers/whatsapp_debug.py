# app/routers/whatsapp_debug.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# v6.3.19 slice 2D-shadow operator-debug endpoints. Currently exposes
# one endpoint:
#
#   POST /api/v1/whatsapp/debug/dispatch
#       Operator-driven shadow / force-send dispatch test for the
#       v6.3.19 push v2 cadence. Top-tier auth required. Gated behind
#       settings.DEBUG_DISPATCH_ENABLED so production deployments can
#       turn it off via env even when the binary ships with the
#       endpoint compiled in.
#
# Per slice 2D scope reduction (D4): the `type` parameter accepts only
# 'morning' and 'evening' in v6.3.19. 'delay_alert' / 'conflict_alert'
# are reserved vocabulary for v6.3.19.1 and return 400 with an
# explanatory message — surfaces the deferred-feature scope to ops
# without a silent missing-route 404.
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
    force_send  — When False (default) the dispatcher runs in shadow
                  mode regardless of settings.PUSH_V2_ENABLED. When
                  True, forces a real send — useful for end-to-end
                  smoke tests in dev/staging where mock-mode
                  WHATSAPP_MOCK_MODE captures the [MOCK ALERT] log
                  line without hitting Meta.
    """

    type: Literal[
        "morning", "evening", "delay_alert", "conflict_alert",
    ] = Field(..., description="Dispatcher to invoke.")
    tenant_id: int = Field(..., gt=0)
    now: datetime
    force_send: bool = False


class DispatchResponse(BaseModel):
    """Response for POST /dispatch.

    actually_sent        — True only when force_send=True and the
                           dispatcher's send loop ran. Always False in
                           shadow mode.
    skip_reason          — Forwarded from DispatchResult; populated
                           when the dispatcher took a skip branch.
    would_send_to        — List of phone numbers the dispatcher
                           resolved as recipients. Same in shadow +
                           real modes. Empty on skip paths that
                           returned before recipient resolution.
    rendered_message     — Full Meta-bound template string. None when
                           a skip path returned before rendering.
    sent_count           — Number of phones the send loop reached.
                           Counts would-have-sent in shadow mode.
    shadow_log_event_id  — Primary key of the events row written by
                           this dispatch (push.shadow_log in shadow
                           mode, push.{kind}_* in real mode). None
                           when the dispatcher returned before any
                           events row was written.
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
    Per v6.3.19 slice 2D scope reduction (D4), `type` of
    'delay_alert' or 'conflict_alert' returns 400 — those dispatchers
    are scoped to v6.3.19.1 and not yet implemented.
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

    if payload.type in ("delay_alert", "conflict_alert"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"type={payload.type!r} is deferred to v6.3.19.1 — "
                "dispatch_delay_alert / dispatch_conflict_alert "
                "are not yet implemented. Use 'morning' or 'evening'."
            ),
        )

    shadow = not payload.force_send

    if payload.type == "morning":
        result: DispatchResult = await dispatch_morning(
            payload.tenant_id, payload.now, db, shadow=shadow,
        )
    else:  # 'evening' — Literal narrowed by the 400 above.
        result = await dispatch_evening(
            payload.tenant_id, payload.now, db, shadow=shadow,
        )

    return DispatchResponse(
        actually_sent=(not shadow) and result.sent_count > 0,
        skip_reason=result.skip_reason,
        would_send_to=list(result.recipients),
        rendered_message=result.rendered_message,
        sent_count=result.sent_count,
        success=result.success,
        shadow_log_event_id=result.event_id,
    )
