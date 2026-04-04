"""Team / department management."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.models.user import Team

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
async def create_team(request: TeamCreate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
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
