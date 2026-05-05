# app/routers/onboarding.py - Version 1.0
# Branch: v5-whatsapp
# Iteration: v6.3.12 (Day-1 onboarding sequence)
#
# FILE PURPOSE
# Single endpoint that the frontend calls when an owner finishes adding
# their first employees + machines on /onboarding. The endpoint is
# fire-and-forget from the client's perspective: the frontend awaits
# completion only to log errors, not to gate UI navigation. The handler
# delegates straight to onboarding_message.send_if_unsent which owns
# idempotency, audit-event writing, and the actual WhatsApp dispatch.
#
# WHO CALLS THIS FILE
# - frontend/src/pages/OnboardingSetup.tsx - handleSave fires
#   apiClient.post(ONBOARDING.complete) after the Promise.all save resolves,
#   before navigating to /dashboard. The .catch() swallows errors so a
#   server-side failure does not block the user from reaching the
#   dashboard - the events table records what happened either way.
#
# WHAT THIS FILE CALLS
# - app.core.dependencies.require_top_tier - only the owner / proprietor /
#   factory_manager / co_owner who completed setup can fire this. A
#   regular operator who happens to navigate to /onboarding does not
#   trigger a confirmation message.
# - app.services.onboarding_message.send_if_unsent - the entire pipeline.
#
# DESIGN NOTES
# - Returns 204 No Content on every outcome (already_handled, sent,
#   pending_consent, skipped_no_phone). The outcome is recorded server-
#   side via the events audit table; surfacing it to the client would
#   leak operational state without giving the user anything actionable.
# - The route is async because send_if_unsent awaits the underlying
#   _send_whatsapp_message coroutine. DB session stays sync per CLAUDE.md
#   WhatsApp pipeline rule.
# - No request body. The tenant_id and actor_user_id come from the JWT
#   via require_top_tier - never trust client-supplied identity.

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_top_tier
from app.database import get_db
from app.models.auth import User
from app.services.onboarding_message import send_if_unsent

router = APIRouter()


@router.post("/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
) -> Response:
    """
    Mark Day-1 onboarding complete and dispatch the WhatsApp confirmation
    if the tenant has a consented owner phone, else stage or skip per
    onboarding_message rules.

    Called by:    frontend OnboardingSetup.tsx handleSave().
    Calls into:   onboarding_message.send_if_unsent (owns the full flow).
    Side effects: see send_if_unsent docstring. May write up to one event
                  row + one outbound WhatsApp send + one db.commit().

    Auth: top-tier roles only (owner / proprietor / factory_manager /
          co_owner). A regular scheduler hitting this endpoint receives
          403 from require_top_tier; we do not silently 204 because the
          frontend is gated separately and an unexpected 403 surfaces a
          real authorization bug.

    Returns:
        204 No Content on every successful outcome path. The eventual
        WhatsApp delivery state (sent / pending / skipped) lives in the
        events audit table, not the HTTP response.
    """
    await send_if_unsent(
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        db=db,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
