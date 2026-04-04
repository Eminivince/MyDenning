import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.models.matter import Matter, MatterDeadline, MatterNote, MatterStatus, DeadlineStatus
from app.schemas.matter import (
    DeadlineCreate, DeadlineOut, DeadlineUpdate,
    MatterCreate, MatterOut, MatterUpdate,
    NoteCreate, NoteOut,
)
from app.services.audit.service import AuditService

router = APIRouter(prefix="/matters", tags=["matters"])


def _generate_reference(org_slug: str, count: int) -> str:
    return f"{org_slug[:4].upper()}-{datetime.now(timezone.utc).year}-{count + 1:04d}"


@router.post("", response_model=MatterOut, status_code=status.HTTP_201_CREATED)
async def create_matter(
    request: MatterCreate,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    count_result = await db.execute(
        select(func.count()).where(Matter.organization_id == org.id)
    )
    count = count_result.scalar() or 0

    matter = Matter(
        organization_id=org.id,
        created_by_id=user.id,
        title=request.title,
        reference_number=_generate_reference(org.slug, count),
        description=request.description,
        matter_type=request.matter_type,
        jurisdiction=request.jurisdiction or org.default_jurisdiction,
        governing_law=request.governing_law or org.default_governing_law,
        counterparty=request.counterparty,
        client_name=request.client_name,
        tags=request.tags,
        opened_at=datetime.now(timezone.utc),
    )
    db.add(matter)
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        organization_id=org.id,
        user_id=user.id,
        action="create",
        resource_type="matter",
        resource_id=str(matter.id),
        description=f"Created matter: {matter.title}",
    )

    return matter


@router.get("", response_model=list[MatterOut])
async def list_matters(
    org: CurrentOrg = None,
    db: DB = None,
    status_filter: MatterStatus | None = Query(None, alias="status"),
    matter_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conditions = [Matter.organization_id == org.id]
    if status_filter:
        conditions.append(Matter.status == status_filter)
    if matter_type:
        conditions.append(Matter.matter_type == matter_type)

    stmt = (
        select(Matter)
        .where(and_(*conditions))
        .order_by(Matter.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{matter_id}", response_model=MatterOut)
async def get_matter(
    matter_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
):
    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")
    return matter


@router.patch("/{matter_id}", response_model=MatterOut)
async def update_matter(
    matter_id: uuid.UUID,
    request: MatterUpdate,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(matter, key, value)

    if request.status == MatterStatus.CLOSED:
        matter.closed_at = datetime.now(timezone.utc)

    await db.flush()
    return matter


# --- Deadlines ---

@router.post("/{matter_id}/deadlines", response_model=DeadlineOut, status_code=status.HTTP_201_CREATED)
async def create_deadline(
    matter_id: uuid.UUID,
    request: DeadlineCreate,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")

    deadline = MatterDeadline(
        matter_id=matter_id,
        created_by_id=user.id,
        title=request.title,
        description=request.description,
        due_date=request.due_date,
        priority=request.priority,
        reminder_days_before=request.reminder_days_before,
        is_court_deadline=request.is_court_deadline,
        source_document_id=request.source_document_id,
    )
    db.add(deadline)
    await db.flush()
    return deadline


@router.get("/{matter_id}/deadlines", response_model=list[DeadlineOut])
async def list_deadlines(
    matter_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
    status_filter: DeadlineStatus | None = Query(None, alias="status"),
):
    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")

    conditions = [MatterDeadline.matter_id == matter_id]
    if status_filter:
        conditions.append(MatterDeadline.status == status_filter)

    stmt = select(MatterDeadline).where(and_(*conditions)).order_by(MatterDeadline.due_date.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch("/{matter_id}/deadlines/{deadline_id}", response_model=DeadlineOut)
async def update_deadline(
    matter_id: uuid.UUID,
    deadline_id: uuid.UUID,
    request: DeadlineUpdate,
    org: CurrentOrg = None,
    db: DB = None,
):
    deadline = await db.get(MatterDeadline, deadline_id)
    if not deadline or deadline.matter_id != matter_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deadline not found")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(deadline, key, value)
    await db.flush()
    return deadline


# --- Notes ---

@router.post("/{matter_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    matter_id: uuid.UUID,
    request: NoteCreate,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")

    note = MatterNote(
        matter_id=matter_id,
        created_by_id=user.id,
        content=request.content,
        note_type=request.note_type,
    )
    db.add(note)
    await db.flush()
    return note


@router.get("/{matter_id}/notes", response_model=list[NoteOut])
async def list_notes(
    matter_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
):
    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")

    stmt = (
        select(MatterNote)
        .where(MatterNote.matter_id == matter_id)
        .order_by(MatterNote.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# --- Activity Feed ---

@router.get("/{matter_id}/activity")
async def get_matter_activity(
    matter_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """Get the activity feed for a matter — chronological timeline of all events."""
    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")

    from app.services.legal_features.activity_feed import ActivityFeedService
    service = ActivityFeedService(db)
    return await service.get_matter_feed(matter_id, org.id, limit, offset)


@router.get("/{matter_id}/stats")
async def get_matter_stats(
    matter_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Get quick stats for a matter — document count, deadline count, analyses, etc."""
    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")

    from app.services.legal_features.activity_feed import ActivityFeedService
    service = ActivityFeedService(db)
    return await service.get_matter_stats(matter_id)
