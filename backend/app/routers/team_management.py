# app/routers/team_management.py - /api/team endpoints (v6.3.3 + v6.3.5)
# Branch: v5-whatsapp
#
# FILE PURPOSE
# FastAPI router for the v6.3.3 Team & Roles UI. Four endpoints:
#   GET    /api/team              - list active+inactive members
#   POST   /api/team/invite       - create a new user, return temp password
#   PATCH  /api/team/{user_id}/role - change role
#   DELETE /api/team/{user_id}    - soft-delete (set is_active=False)
#
# WHO CALLS THIS FILE
# - Frontend: frontend/src/pages/settings/TeamAndRoles.tsx (v6.3.5 redesign)
# - app/main.py mounts this router at prefix /api/team.
#
# WHAT THIS FILE CALLS
# - app/core/dependencies: require_top_tier (GET/POST/PATCH gate),
#                          require_role('proprietor', 'owner') (DELETE gate)
# - app/services/team_service: list_team_members_with_status, invite_member,
#                              change_member_role, delete_member,
#                              serialise_member_for_response
# - app/schemas/team: InviteRequest, RoleChangeRequest, TeamMemberOut,
#                     InviteResponse
#
# v6.3.5 CHANGES
# - GET /api/team uses list_team_members_with_status so each row carries
#   whatsapp_status + name + nullable email.
# - POST /api/team/invite uses serialise_member_for_response on the new
#   user so the response body matches the GET shape (single round-trip
#   for the frontend's invalidateQueries -> rerender flow).
# - PATCH /api/team/{user_id}/role uses serialise_member_for_response too.

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_role, require_top_tier
from app.database import get_db
from app.models.auth import User
from app.schemas.team import (
    InviteRequest, InviteResponse, RoleChangeRequest, TeamMemberOut,
)
from app.services import team_service


router = APIRouter()


@router.get("/", response_model=list[TeamMemberOut])
def list_team(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
) -> list[TeamMemberOut]:
    """
    GET /api/team - list every user in the caller's tenant, enriched with
    v6.3.5 whatsapp_status + name fields.

    Called by: frontend Settings -> Team & Roles page.
    Calls into: team_service.list_team_members_with_status.
    Returns: list of TeamMemberOut, ordered by user.id ascending. Synthesised
             invite emails are returned as null so the UI renders the
             "(unnamed)" empty state instead of leaking placeholders.
    """
    return team_service.list_team_members_with_status(current_user.tenant_id, db)


@router.post(
    "/invite",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite(
    payload: InviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
) -> InviteResponse:
    """
    POST /api/team/invite - create a new user in the caller's tenant.

    v6.3.5 contract: payload may carry channel='whatsapp'/'desktop'. When
    omitted the service infers from email_or_phone shape (back-compat
    with v6.3.3 callers). WhatsApp channel triggers a [MOCK ALERT] welcome
    handshake in mock mode.

    Permission: require_top_tier passes any TOP_TIER role. team_service
    additionally enforces "only owner/proprietor can grant top-tier".
    factory_manager / co_owner can invite manager / scheduler / viewer.

    Called by: frontend Team & Roles invite modal.
    Calls into: team_service.invite_member +
                team_service.serialise_member_for_response.
    Returns: { member: TeamMemberOut, temp_password: str | None }
             temp_password is None for whatsapp channel invites (the
             recipient authenticates via WhatsApp HAAN handshake).
    """
    new_user, temp_password = team_service.invite_member(
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role,
        payload=payload,
        db=db,
    )
    return InviteResponse(
        member=team_service.serialise_member_for_response(new_user, db),
        temp_password=temp_password,
    )


@router.patch("/{user_id}/role", response_model=TeamMemberOut)
def change_role(
    user_id: int,
    payload: RoleChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
) -> TeamMemberOut:
    """
    PATCH /api/team/{user_id}/role - update a team member's role.

    Permission: same layered model as invite. Demoting the last top-tier
    user out of top-tier is blocked with 400 (last-owner protection).

    Called by: frontend Team & Roles inline role-change dropdown.
    Calls into: team_service.change_member_role +
                team_service.serialise_member_for_response.
    Returns: the updated TeamMemberOut with v6.3.5 enrichment.
    """
    updated = team_service.change_member_role(
        tenant_id=current_user.tenant_id,
        target_user_id=user_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role,
        payload=payload,
        db=db,
    )
    return team_service.serialise_member_for_response(updated, db)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "owner")),
) -> None:
    """
    DELETE /api/team/{user_id} - soft-delete a team member.

    Permission: tightest gate - owner/proprietor only.
    Last-owner protection: refuses with 400 if the target is the sole
    active top-tier user.

    Called by: frontend Team & Roles row action.
    Calls into: team_service.delete_member.
    Returns: 204 No Content.
    """
    team_service.delete_member(
        tenant_id=current_user.tenant_id,
        target_user_id=user_id,
        actor_user_id=current_user.id,
        db=db,
    )
    return None
