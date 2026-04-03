import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.models.playbook import Playbook, PlaybookClause
from app.schemas.playbook import PlaybookClauseCreate, PlaybookCreate, PlaybookOut, PlaybookUpdate

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


@router.post("", response_model=PlaybookOut, status_code=status.HTTP_201_CREATED)
async def create_playbook(
    request: PlaybookCreate,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    playbook = Playbook(
        organization_id=org.id,
        created_by_id=user.id,
        name=request.name,
        description=request.description,
        document_type=request.document_type,
        jurisdiction=request.jurisdiction,
    )
    db.add(playbook)
    await db.flush()

    if request.clauses:
        for clause_data in request.clauses:
            clause = PlaybookClause(
                playbook_id=playbook.id,
                clause_type=clause_data.clause_type,
                clause_name=clause_data.clause_name,
                position=clause_data.position,
                standard_language=clause_data.standard_language,
                fallback_language=clause_data.fallback_language,
                unacceptable_patterns=clause_data.unacceptable_patterns,
                negotiation_notes=clause_data.negotiation_notes,
                risk_if_deviated=clause_data.risk_if_deviated,
                approval_required_if=clause_data.approval_required_if,
                importance_weight=clause_data.importance_weight,
                order_index=clause_data.order_index,
            )
            db.add(clause)

    await db.flush()

    # Reload with clauses
    result = await db.execute(
        select(Playbook)
        .where(Playbook.id == playbook.id)
        .options(selectinload(Playbook.clauses))
    )
    return result.scalar_one()


@router.get("", response_model=list[PlaybookOut])
async def list_playbooks(
    org: CurrentOrg = None,
    db: DB = None,
    document_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conditions = [Playbook.organization_id == org.id, Playbook.is_active == True]  # noqa: E712
    if document_type:
        conditions.append(Playbook.document_type == document_type)

    stmt = (
        select(Playbook)
        .where(*conditions)
        .options(selectinload(Playbook.clauses))
        .order_by(Playbook.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{playbook_id}", response_model=PlaybookOut)
async def get_playbook(
    playbook_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
):
    result = await db.execute(
        select(Playbook)
        .where(Playbook.id == playbook_id, Playbook.organization_id == org.id)
        .options(selectinload(Playbook.clauses))
    )
    playbook = result.scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    return playbook


@router.patch("/{playbook_id}", response_model=PlaybookOut)
async def update_playbook(
    playbook_id: uuid.UUID,
    request: PlaybookUpdate,
    org: CurrentOrg = None,
    db: DB = None,
):
    result = await db.execute(
        select(Playbook)
        .where(Playbook.id == playbook_id, Playbook.organization_id == org.id)
        .options(selectinload(Playbook.clauses))
    )
    playbook = result.scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(playbook, key, value)

    await db.flush()
    return playbook


@router.post("/{playbook_id}/clauses", status_code=status.HTTP_201_CREATED)
async def add_clause(
    playbook_id: uuid.UUID,
    request: PlaybookClauseCreate,
    org: CurrentOrg = None,
    db: DB = None,
):
    playbook = await db.get(Playbook, playbook_id)
    if not playbook or playbook.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")

    clause = PlaybookClause(
        playbook_id=playbook_id,
        clause_type=request.clause_type,
        clause_name=request.clause_name,
        position=request.position,
        standard_language=request.standard_language,
        fallback_language=request.fallback_language,
        unacceptable_patterns=request.unacceptable_patterns,
        negotiation_notes=request.negotiation_notes,
        risk_if_deviated=request.risk_if_deviated,
        approval_required_if=request.approval_required_if,
        importance_weight=request.importance_weight,
        order_index=request.order_index,
    )
    db.add(clause)
    await db.flush()
    return {"id": clause.id, "clause_type": clause.clause_type}


@router.delete("/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook(
    playbook_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
):
    playbook = await db.get(Playbook, playbook_id)
    if not playbook or playbook.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")

    playbook.is_active = False
    await db.flush()
