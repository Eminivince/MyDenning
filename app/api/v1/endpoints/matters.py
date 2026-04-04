import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.models.matter import (
    Matter, MatterMembership, MatterDeadline, MatterNote,
    MatterStatus, MatterAccessLevel, DeadlineStatus, ConfidentialityLevel,
)
from app.schemas.matter import (
    DeadlineCreate, DeadlineOut, DeadlineUpdate,
    MatterCreate, MatterMemberAdd, MatterMemberOut, MatterOut, MatterUpdate,
    NoteCreate, NoteOut,
)
from app.services.audit.service import AuditService

router = APIRouter(prefix="/matters", tags=["matters"])


# ===== Access control helpers =====

async def _check_matter_access(
    db: AsyncSession,
    matter_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    min_access: MatterAccessLevel = MatterAccessLevel.READ_ONLY,
) -> Matter:
    """Verify user has access to a matter. Returns the matter or raises 404/403.

    Access granted if: creator, lead lawyer, explicit member, or org admin.
    """
    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")

    if matter.created_by_id == user_id or matter.lead_lawyer_id == user_id:
        return matter

    membership = await db.execute(
        select(MatterMembership).where(
            and_(MatterMembership.matter_id == matter_id, MatterMembership.user_id == user_id)
        )
    )
    member = membership.scalar_one_or_none()
    if member:
        hierarchy = {MatterAccessLevel.READ_ONLY: 1, MatterAccessLevel.LIMITED: 2, MatterAccessLevel.FULL: 3}
        if hierarchy.get(member.access_level, 0) >= hierarchy.get(min_access, 0):
            return matter
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient matter access")

    from app.models.user import OrganizationMember, OrgRole
    admin_result = await db.execute(
        select(OrganizationMember).where(and_(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.role.in_([OrgRole.SUPER_ADMIN, OrgRole.MANAGING_PARTNER, OrgRole.OWNER, OrgRole.ADMIN]),
        ))
    )
    if admin_result.scalar_one_or_none():
        return matter

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this matter")


def _generate_reference(org_slug: str, count: int) -> str:
    return f"{org_slug[:4].upper()}-{datetime.now(timezone.utc).year}-{count + 1:04d}"


# ===== Matter CRUD =====

@router.post("", response_model=MatterOut, status_code=status.HTTP_201_CREATED)
async def create_matter(request: MatterCreate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    count_result = await db.execute(select(func.count()).where(Matter.organization_id == org.id))
    count = count_result.scalar() or 0

    matter = Matter(
        organization_id=org.id, created_by_id=user.id, client_id=request.client_id,
        title=request.title, reference_number=_generate_reference(org.slug, count),
        description=request.description, matter_type=request.matter_type,
        practice_area=request.practice_area, priority=request.priority,
        jurisdiction=request.jurisdiction or org.default_jurisdiction,
        governing_law=request.governing_law or org.default_governing_law,
        counterparty=request.counterparty, client_name=request.client_name,
        lead_lawyer_id=request.lead_lawyer_id or user.id,
        team_id=request.team_id, confidentiality_level=request.confidentiality_level,
        tags=request.tags, opened_at=datetime.now(timezone.utc),
    )
    db.add(matter)
    await db.flush()

    # Auto-add creator as lead with full access
    db.add(MatterMembership(matter_id=matter.id, user_id=user.id, role_on_matter="lead", access_level=MatterAccessLevel.FULL))
    if request.lead_lawyer_id and request.lead_lawyer_id != user.id:
        db.add(MatterMembership(matter_id=matter.id, user_id=request.lead_lawyer_id, role_on_matter="lead", access_level=MatterAccessLevel.FULL))
    await db.flush()

    audit = AuditService(db)
    await audit.log(organization_id=org.id, user_id=user.id, action="create", resource_type="matter", resource_id=str(matter.id), description=f"Created matter: {matter.title}")
    return matter


@router.get("", response_model=list[MatterOut])
async def list_matters(
    org: CurrentOrg = None, user: CurrentUser = None, db: DB = None,
    status_filter: MatterStatus | None = Query(None, alias="status"),
    matter_type: str | None = None, client_id: uuid.UUID | None = None,
    practice_area: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    from app.models.user import OrganizationMember, OrgRole
    admin_check = await db.execute(select(OrganizationMember).where(and_(
        OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id,
        OrganizationMember.role.in_([OrgRole.SUPER_ADMIN, OrgRole.MANAGING_PARTNER, OrgRole.OWNER, OrgRole.ADMIN]),
    )))
    is_admin = admin_check.scalar_one_or_none() is not None

    conditions = [Matter.organization_id == org.id]
    if not is_admin:
        member_ids = select(MatterMembership.matter_id).where(MatterMembership.user_id == user.id)
        conditions.append(or_(Matter.id.in_(member_ids), Matter.created_by_id == user.id, Matter.lead_lawyer_id == user.id))

    if status_filter: conditions.append(Matter.status == status_filter)
    if matter_type: conditions.append(Matter.matter_type == matter_type)
    if client_id: conditions.append(Matter.client_id == client_id)
    if practice_area: conditions.append(Matter.practice_area == practice_area)

    result = await db.execute(select(Matter).where(and_(*conditions)).order_by(Matter.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return result.scalars().all()


@router.get("/{matter_id}", response_model=MatterOut)
async def get_matter(matter_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    return await _check_matter_access(db, matter_id, user.id, org.id)


@router.patch("/{matter_id}", response_model=MatterOut)
async def update_matter(matter_id: uuid.UUID, request: MatterUpdate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    matter = await _check_matter_access(db, matter_id, user.id, org.id, MatterAccessLevel.FULL)
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(matter, key, value)
    if request.status == MatterStatus.CLOSED:
        matter.closed_at = datetime.now(timezone.utc)
    await db.flush()
    return matter


# ===== Matter Members =====

@router.post("/{matter_id}/members", response_model=MatterMemberOut, status_code=status.HTTP_201_CREATED)
async def add_matter_member(matter_id: uuid.UUID, request: MatterMemberAdd, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    await _check_matter_access(db, matter_id, user.id, org.id, MatterAccessLevel.FULL)
    existing = await db.execute(select(MatterMembership).where(and_(MatterMembership.matter_id == matter_id, MatterMembership.user_id == request.user_id)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member")
    m = MatterMembership(matter_id=matter_id, user_id=request.user_id, role_on_matter=request.role_on_matter, access_level=request.access_level)
    db.add(m)
    await db.flush()
    return m


@router.get("/{matter_id}/members", response_model=list[MatterMemberOut])
async def list_matter_members(matter_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    await _check_matter_access(db, matter_id, user.id, org.id)
    result = await db.execute(select(MatterMembership).where(MatterMembership.matter_id == matter_id))
    return result.scalars().all()


@router.delete("/{matter_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_matter_member(matter_id: uuid.UUID, member_user_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    await _check_matter_access(db, matter_id, user.id, org.id, MatterAccessLevel.FULL)
    result = await db.execute(select(MatterMembership).where(and_(MatterMembership.matter_id == matter_id, MatterMembership.user_id == member_user_id)))
    m = result.scalar_one_or_none()
    if m:
        await db.delete(m)
        await db.flush()


# --- Deadlines ---

@router.post("/{matter_id}/deadlines", response_model=DeadlineOut, status_code=status.HTTP_201_CREATED)
async def create_deadline(matter_id: uuid.UUID, request: DeadlineCreate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    await _check_matter_access(db, matter_id, user.id, org.id, MatterAccessLevel.LIMITED)
    dl = MatterDeadline(matter_id=matter_id, created_by_id=user.id, title=request.title, description=request.description, due_date=request.due_date, priority=request.priority, reminder_days_before=request.reminder_days_before, is_court_deadline=request.is_court_deadline, source_document_id=request.source_document_id)
    db.add(dl)
    await db.flush()
    return dl


@router.get("/{matter_id}/deadlines", response_model=list[DeadlineOut])
async def list_deadlines(matter_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None, status_filter: DeadlineStatus | None = Query(None, alias="status")):
    await _check_matter_access(db, matter_id, user.id, org.id)
    conditions = [MatterDeadline.matter_id == matter_id]
    if status_filter: conditions.append(MatterDeadline.status == status_filter)
    result = await db.execute(select(MatterDeadline).where(and_(*conditions)).order_by(MatterDeadline.due_date.asc()))
    return result.scalars().all()


@router.patch("/{matter_id}/deadlines/{deadline_id}", response_model=DeadlineOut)
async def update_deadline(matter_id: uuid.UUID, deadline_id: uuid.UUID, request: DeadlineUpdate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    await _check_matter_access(db, matter_id, user.id, org.id, MatterAccessLevel.LIMITED)
    dl = await db.get(MatterDeadline, deadline_id)
    if not dl or dl.matter_id != matter_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deadline not found")
    for k, v in request.model_dump(exclude_unset=True).items(): setattr(dl, k, v)
    await db.flush()
    return dl


# --- Notes ---

@router.post("/{matter_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(matter_id: uuid.UUID, request: NoteCreate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    await _check_matter_access(db, matter_id, user.id, org.id, MatterAccessLevel.LIMITED)
    note = MatterNote(matter_id=matter_id, created_by_id=user.id, content=request.content, note_type=request.note_type)
    db.add(note)
    await db.flush()
    return note


@router.get("/{matter_id}/notes", response_model=list[NoteOut])
async def list_notes(matter_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    await _check_matter_access(db, matter_id, user.id, org.id)
    result = await db.execute(select(MatterNote).where(MatterNote.matter_id == matter_id).order_by(MatterNote.created_at.desc()))
    return result.scalars().all()


# --- Activity Feed ---

@router.get("/{matter_id}/activity")
async def get_matter_activity(matter_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None, limit: int = Query(50, le=200), offset: int = Query(0, ge=0)):
    await _check_matter_access(db, matter_id, user.id, org.id)
    from app.services.legal_features.activity_feed import ActivityFeedService
    return await ActivityFeedService(db).get_matter_feed(matter_id, org.id, limit, offset)


@router.get("/{matter_id}/stats")
async def get_matter_stats(matter_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    await _check_matter_access(db, matter_id, user.id, org.id)
    from app.services.legal_features.activity_feed import ActivityFeedService
    return await ActivityFeedService(db).get_matter_stats(matter_id)
