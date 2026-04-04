"""Client portal API — management endpoints (internal) + client-facing endpoints."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.core.security import decode_token
from app.db.session import get_db

router = APIRouter(tags=["client-portal"])


# ===== Schemas =====

class InviteClientRequest(BaseModel):
    email: str
    full_name: str
    password: str
    company_name: str | None = None
    matter_ids: list[uuid.UUID] | None = None


class GrantAccessRequest(BaseModel):
    client_user_id: uuid.UUID
    matter_id: uuid.UUID
    can_view_documents: bool = True
    can_view_deadlines: bool = True
    can_view_status: bool = True
    can_view_notes: bool = False
    can_upload_documents: bool = True


class ClientLoginRequest(BaseModel):
    email: str
    password: str


# ===== Internal management endpoints (requires internal user auth) =====

@router.post("/portal/clients", status_code=status.HTTP_201_CREATED)
async def invite_client(
    request: InviteClientRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Invite a client to the portal. Creates their account and grants matter access."""
    from app.services.legal_features.client_portal import ClientPortalService
    service = ClientPortalService(db)
    client = await service.invite_client(
        organization_id=org.id,
        invited_by_id=user.id,
        email=request.email,
        full_name=request.full_name,
        password=request.password,
        company_name=request.company_name,
        matter_ids=request.matter_ids,
    )
    return {
        "id": str(client.id), "email": client.email, "full_name": client.full_name,
        "company_name": client.company_name, "is_active": client.is_active,
    }


@router.get("/portal/clients")
async def list_clients(user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    """List all client portal users for this organization."""
    from app.services.legal_features.client_portal import ClientPortalService
    service = ClientPortalService(db)
    clients = await service.list_clients(org.id)
    return [
        {"id": str(c.id), "email": c.email, "full_name": c.full_name,
         "company_name": c.company_name, "is_active": c.is_active,
         "last_login": c.last_login_at.isoformat() if c.last_login_at else None}
        for c in clients
    ]


@router.post("/portal/access")
async def grant_access(
    request: GrantAccessRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Grant a client user access to a specific matter with granular permissions."""
    from app.services.legal_features.client_portal import ClientPortalService
    service = ClientPortalService(db)
    access = await service.grant_matter_access(
        client_user_id=request.client_user_id,
        matter_id=request.matter_id,
        can_view_documents=request.can_view_documents,
        can_view_deadlines=request.can_view_deadlines,
        can_view_status=request.can_view_status,
        can_view_notes=request.can_view_notes,
        can_upload_documents=request.can_upload_documents,
    )
    return {"id": str(access.id), "granted": True}


@router.delete("/portal/access/{client_user_id}/{matter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_access(
    client_user_id: uuid.UUID,
    matter_id: uuid.UUID,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    from app.services.legal_features.client_portal import ClientPortalService
    service = ClientPortalService(db)
    await service.revoke_matter_access(client_user_id, matter_id)


# ===== Client-facing endpoints (separate auth) =====

async def get_current_client(
    db: AsyncSession = Depends(get_db),
    token: str = "",
) -> tuple:
    """Extract client user from JWT token. Returns (client_user, db)."""
    from app.models.legal_features import ClientUser
    # Token comes from Authorization header — parsed manually for client tokens
    return None, db  # placeholder — actual extraction happens in the endpoint


@router.post("/portal/login")
async def client_login(request: ClientLoginRequest, db: AsyncSession = Depends(get_db)):
    """Client portal login — returns a JWT token scoped to client access."""
    from app.services.legal_features.client_portal import ClientPortalService
    service = ClientPortalService(db)
    result = await service.authenticate_client(request.email, request.password)
    if not result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return result


@router.get("/portal/my/matters")
async def client_my_matters(
    db: AsyncSession = Depends(get_db),
    authorization: str = "",
):
    """Get all matters the authenticated client has access to."""
    client_id = _extract_client_id(authorization)
    from app.services.legal_features.client_portal import ClientPortalService
    service = ClientPortalService(db)
    return await service.get_client_matters(client_id)


@router.get("/portal/my/matters/{matter_id}")
async def client_matter_detail(
    matter_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    authorization: str = "",
):
    """Get matter detail from the client's perspective. Respects permission settings.
    Privileged documents are automatically excluded."""
    client_id = _extract_client_id(authorization)
    from app.services.legal_features.client_portal import ClientPortalService
    service = ClientPortalService(db)
    result = await service.get_client_matter_detail(client_id, matter_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found or access denied")
    return result


@router.post("/portal/my/matters/{matter_id}/upload")
async def client_upload_document(
    matter_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str = Form(""),
    db: AsyncSession = Depends(get_db),
    authorization: str = "",
):
    """Client uploads a document to a matter they have upload access to."""
    client_id = _extract_client_id(authorization)

    from app.models.legal_features import ClientMatterAccess, ClientUser
    from app.models.document import Document, DocumentType, ProcessingStatus
    from app.services.document_parser.parser import DocumentParserService
    from app.services.storage import StorageService
    from sqlalchemy import select, and_

    # Verify upload permission
    access_result = await db.execute(
        select(ClientMatterAccess).where(
            and_(
                ClientMatterAccess.client_user_id == client_id,
                ClientMatterAccess.matter_id == matter_id,
                ClientMatterAccess.can_upload_documents == True,  # noqa: E712
            )
        )
    )
    access = access_result.scalar_one_or_none()
    if not access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload not permitted for this matter")

    client = await db.get(ClientUser, client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client not found")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    content_hash = DocumentParserService.compute_hash(content)
    storage = StorageService()
    file_key = f"documents/{client.organization_id}/client-upload/{content_hash[:16]}/{file.filename}"
    await storage.upload_file(content, file_key, file.content_type)

    document = Document(
        organization_id=client.organization_id,
        uploaded_by_id=client.invited_by_id,  # attribute to the internal user who invited this client
        title=title or file.filename,
        description=f"Uploaded by client: {client.full_name} ({client.email})",
        document_type=DocumentType.OTHER,
        file_name=file.filename,
        file_path=file_key,
        file_size=len(content),
        mime_type=file.content_type or "application/octet-stream",
        content_hash=content_hash,
        matter_id=matter_id,
        processing_status=ProcessingStatus.PENDING,
    )
    db.add(document)
    await db.flush()
    await db.commit()

    from app.tasks.document_tasks import process_document_task
    process_document_task.delay(str(document.id))

    return {"document_id": str(document.id), "title": document.title, "status": "processing"}


def _extract_client_id(authorization: str) -> uuid.UUID:
    """Extract client user ID from the Authorization header."""
    from fastapi import Header
    if not authorization:
        # Try to get from a different source — in practice this comes from the request
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization required")

    token = authorization.replace("Bearer ", "").strip()
    payload = decode_token(token)
    if not payload or payload.get("type") != "client":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid client token")

    return uuid.UUID(payload["sub"])
