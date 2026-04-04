"""Client management — legal CRM core."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.models.user import Client, ClientType, ClientStatus
from app.models.matter import Matter

router = APIRouter(prefix="/clients", tags=["clients"])


class ClientCreate(BaseModel):
    name: str
    client_type: str = "company"
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    industry: str | None = None
    jurisdiction: str | None = None
    risk_rating: int | None = None
    billing_preferences: dict | None = None
    notes: str | None = None
    tags: list[str] | None = None


class ClientUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None
    industry: str | None = None
    risk_rating: int | None = None
    notes: str | None = None
    tags: list[str] | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_client(request: ClientCreate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    client = Client(
        organization_id=org.id,
        created_by_id=user.id,
        name=request.name,
        client_type=ClientType(request.client_type),
        email=request.email,
        phone=request.phone,
        address=request.address,
        primary_contact_name=request.primary_contact_name,
        primary_contact_email=request.primary_contact_email,
        industry=request.industry,
        jurisdiction=request.jurisdiction,
        risk_rating=request.risk_rating,
        billing_preferences=request.billing_preferences,
        notes=request.notes,
        tags=request.tags,
    )
    db.add(client)
    await db.flush()

    # Auto-run conflict check on the new client name
    conflict_warning = None
    try:
        from app.services.legal_features.conflicts import ConflictCheckingService
        conflict_service = ConflictCheckingService(db)

        # Register as a conflict party for future checks
        await conflict_service.register_party(
            organization_id=org.id,
            name=request.name,
            party_type=request.client_type,
            jurisdiction=request.jurisdiction,
        )

        # Run conflict check
        check = await conflict_service.check_conflicts(
            organization_id=org.id,
            user_id=user.id,
            party_names=[request.name],
        )
        if check.conflicts_found:
            conflict_warning = {
                "status": check.status.value,
                "conflicts": check.conflicts_found,
                "check_id": str(check.id),
            }
    except Exception:
        pass  # conflict check failure should not block client creation

    result = _client_dict(client)
    if conflict_warning:
        result["conflict_warning"] = conflict_warning
    return result


@router.get("")
async def list_clients(
    org: CurrentOrg = None, db: DB = None,
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conditions = [Client.organization_id == org.id]
    if status_filter:
        conditions.append(Client.status == ClientStatus(status_filter))
    if q:
        conditions.append(Client.name.ilike(f"%{q}%"))

    count_result = await db.execute(select(func.count()).where(and_(*conditions)))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Client).where(and_(*conditions))
        .order_by(Client.name.asc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    clients = result.scalars().all()

    # Get matter counts per client
    client_ids = [c.id for c in clients]
    matter_counts = {}
    if client_ids:
        mc_result = await db.execute(
            select(Matter.client_id, func.count().label("count"))
            .where(Matter.client_id.in_(client_ids))
            .group_by(Matter.client_id)
        )
        matter_counts = {row.client_id: row.count for row in mc_result.all()}

    return {
        "items": [{**_client_dict(c), "matter_count": matter_counts.get(c.id, 0)} for c in clients],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{client_id}")
async def get_client(client_id: uuid.UUID, org: CurrentOrg = None, db: DB = None):
    client = await db.get(Client, client_id)
    if not client or client.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get matters for this client
    matters_result = await db.execute(
        select(Matter).where(and_(Matter.client_id == client_id, Matter.organization_id == org.id))
        .order_by(Matter.created_at.desc())
    )
    matters = matters_result.scalars().all()

    return {
        **_client_dict(client),
        "matters": [
            {"id": str(m.id), "title": m.title, "status": m.status.value, "type": m.matter_type.value, "reference": m.reference_number}
            for m in matters
        ],
    }


@router.patch("/{client_id}")
async def update_client(client_id: uuid.UUID, request: ClientUpdate, org: CurrentOrg = None, db: DB = None):
    client = await db.get(Client, client_id)
    if not client or client.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Client not found")

    data = request.model_dump(exclude_unset=True)
    if "status" in data:
        data["status"] = ClientStatus(data["status"])
    for k, v in data.items():
        setattr(client, k, v)
    await db.flush()
    return _client_dict(client)


def _client_dict(c: Client) -> dict:
    return {
        "id": str(c.id), "name": c.name, "client_type": c.client_type.value,
        "email": c.email, "phone": c.phone, "industry": c.industry,
        "jurisdiction": c.jurisdiction, "status": c.status.value,
        "risk_rating": c.risk_rating, "primary_contact_name": c.primary_contact_name,
        "notes": c.notes, "tags": c.tags, "created_at": c.created_at.isoformat(),
    }
