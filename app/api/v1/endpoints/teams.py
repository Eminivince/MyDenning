"""Team / department management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, and_

from app.api.deps import CurrentOrg, CurrentUser, DB, require_role, ADMIN_ROLES
from app.models.user import Team, OrganizationMember

router = APIRouter(prefix="/teams", tags=["teams"])


class TeamCreate(BaseModel):
    name: str
    description: str | None = None
    head_user_id: uuid.UUID | None = None
    practice_area: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    head_user_id: uuid.UUID | None = None
    practice_area: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(request: TeamCreate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None, _role=Depends(require_role(ADMIN_ROLES))):
    team = Team(
        organization_id=org.id,
        name=request.name,
        description=request.description,
        head_user_id=request.head_user_id,
        practice_area=request.practice_area,
    )
    db.add(team)
    await db.flush()
    return {"id": str(team.id), "name": team.name, "practice_area": team.practice_area}


@router.get("")
async def list_teams(org: CurrentOrg = None, db: DB = None):
    result = await db.execute(
        select(Team).where(Team.organization_id == org.id, Team.is_active == True).order_by(Team.name)  # noqa: E712
    )
    return [
        {"id": str(t.id), "name": t.name, "description": t.description, "practice_area": t.practice_area,
         "head_user_id": str(t.head_user_id) if t.head_user_id else None}
        for t in result.scalars().all()
    ]


@router.patch("/{team_id}")
async def update_team(team_id: uuid.UUID, request: TeamUpdate, org: CurrentOrg = None, db: DB = None):
    team = await db.get(Team, team_id)
    if not team or team.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Team not found")
    data = request.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(team, k, v)
    await db.flush()
    return {"id": str(team.id), "name": team.name, "practice_area": team.practice_area}


# ===== Team Members =====

@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
    _role=Depends(require_role(ADMIN_ROLES)),
):
    """Add a user to a team by setting their department."""
    team = await db.get(Team, team_id)
    if not team or team.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Team not found")

    membership = await db.execute(
        select(OrganizationMember).where(and_(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == user_id,
        ))
    )
    member = membership.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="User is not an organization member")

    member.department = team.name
    await db.flush()
    return {"user_id": str(user_id), "team_id": str(team_id), "team_name": team.name}


@router.get("/{team_id}/members")
async def list_team_members(team_id: uuid.UUID, org: CurrentOrg = None, db: DB = None):
    """List all members of a team."""
    team = await db.get(Team, team_id)
    if not team or team.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Team not found")

    from app.models.user import User
    result = await db.execute(
        select(OrganizationMember, User)
        .join(User, OrganizationMember.user_id == User.id)
        .where(and_(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.department == team.name,
        ))
    )
    return [
        {"user_id": str(row[1].id), "full_name": row[1].full_name, "email": row[1].email,
         "role": row[0].role.value, "title": row[0].member_title}
        for row in result.all()
    ]


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: uuid.UUID, user_id: uuid.UUID,
    org: CurrentOrg = None, db: DB = None,
    _role=Depends(require_role(ADMIN_ROLES)),
):
    result = await db.execute(
        select(OrganizationMember).where(and_(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == user_id,
        ))
    )
    member = result.scalar_one_or_none()
    if member:
        member.department = None
        await db.flush()
