# app/routers/team_management.py - /api/team endpoints (v6.3.3)
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
# - Frontend: frontend/src/pages/settings/TeamAndRoles.tsx
# - app/main.py mounts this router at prefix /api/team.
#
# WHAT THIS FILE CALLS
# - app/core/dependencies: require_top_tier (GET/POST/PATCH gate),
#                          require_role('proprietor', 'owner') (DELETE gate)
# - app/services/team_service: list_team_members, invite_member,
#                              change_member_role, delete_member
# - app/schemas/team: InviteRequest, RoleChangeRequest, TeamMemberOut,
#                     InviteResponse
#
# DESIGN NOTES
# - Permission layering: require_top_tier passes any of TOP_TIER_ROLES.
#   The service layer (team_service) ADDITIONALLY enforces "only
#   owner/proprietor can grant top-tier" inside invite/change_role
#   handlers - that finer-grained check is necessary on top of, not
#   replaced by, the dependency-level gate.
# - DELETE uses require_role('proprietor', 'owner') directly. Even
#   factory_manager and co_owner cannot remove team members - that is
#   irreversible enough to keep on the strictest gate per SRS Section
#   6.28.6 commercial-action ladder.

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
) -> list[User]:
    """
    GET /api/team - list every user in the caller's tenant.

    Called by: frontend Settings -> Team & Roles page.
    Calls into: team_service.list_team_members.
    Returns: list of TeamMemberOut, ordered by id ascending.
    """
    return team_service.list_team_members(current_user.tenant_id, db)


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

    Permission: require_top_tier passes any TOP_TIER role. team_service
    additionally enforces "only owner/proprietor can grant top-tier".
    factory_manager / co_owner can invite manager / scheduler / viewer.

    Called by: frontend Team & Roles invite modal.
    Calls into: team_service.invite_member.
    Returns: { member: TeamMemberOut, temp_password: str | None }
             temp_password is None for phone-only invites (whatsapp-first).
    """
    new_user, temp_password = team_service.invite_member(
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role,
        payload=payload,
        db=db,
    )
    return InviteResponse(
        member=TeamMemberOut.model_validate(new_user),
        temp_password=temp_password,
    )


@router.patch("/{user_id}/role", response_model=TeamMemberOut)
def change_role(
    user_id: int,
    payload: RoleChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_top_tier()),
) -> User:
    """
    PATCH /api/team/{user_id}/role - update a team member's role.

    Permission: same layered model as invite. Demoting the last top-tier
    user out of top-tier is blocked with 400 (last-owner protection).

    Called by: frontend Team & Roles inline role-change dropdown.
    Calls into: team_service.change_member_role.
    Returns: the updated TeamMemberOut.
    """
    updated = team_service.change_member_role(
        tenant_id=current_user.tenant_id,
        target_user_id=user_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role,
        payload=payload,
        db=db,
    )
    return updated


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("proprietor", "owner")),
) -> None:
    """
    DELETE /api/team/{user_id} - soft-delete a team member (sets is_active=False).

    Permission: tightest gate - owner/proprietor only, even
    factory_manager and co_owner cannot remove members per SRS Section
    6.28.6. Last-owner protection: refuses with 400 if the target is
    the sole active top-tier user.

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
