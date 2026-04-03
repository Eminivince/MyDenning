import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.models.document import Document, DocumentType, ProcessingStatus
from app.schemas.document import DocumentCreate, DocumentListOut, DocumentOut
from app.services.audit.service import AuditService
from app.services.document_parser.parser import DocumentParserService
from app.services.storage import StorageService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: DocumentType = Form(...),
    description: str | None = Form(None),
    matter_id: uuid.UUID | None = Form(None),
    jurisdiction: str | None = Form(None),
    governing_law: str | None = Form(None),
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    if len(content) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large (max 50MB)")

    content_hash = DocumentParserService.compute_hash(content)

    storage = StorageService()
    file_key = f"documents/{org.id}/{content_hash[:16]}/{file.filename}"
    await storage.upload_file(content, file_key, file.content_type)

    document = Document(
        organization_id=org.id,
        uploaded_by_id=user.id,
        title=title,
        description=description,
        document_type=document_type,
        file_name=file.filename,
        file_path=file_key,
        file_size=len(content),
        mime_type=file.content_type or "application/octet-stream",
        content_hash=content_hash,
        jurisdiction=jurisdiction or org.default_jurisdiction,
        governing_law=governing_law or org.default_governing_law,
        matter_id=matter_id,
        processing_status=ProcessingStatus.PENDING,
    )
    db.add(document)
    await db.flush()

    # Trigger async processing
    from app.tasks.document_tasks import process_document_task
    process_document_task.delay(str(document.id))

    # Audit
    audit = AuditService(db)
    await audit.log(
        organization_id=org.id,
        user_id=user.id,
        action="upload",
        resource_type="document",
        resource_id=str(document.id),
        description=f"Uploaded document: {title}",
    )

    return document


@router.get("", response_model=list[DocumentListOut])
async def list_documents(
    org: CurrentOrg = None,
    db: DB = None,
    document_type: DocumentType | None = None,
    matter_id: uuid.UUID | None = None,
    jurisdiction: str | None = None,
    status_filter: ProcessingStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conditions = [Document.organization_id == org.id, Document.is_active == True]  # noqa: E712
    if document_type:
        conditions.append(Document.document_type == document_type)
    if matter_id:
        conditions.append(Document.matter_id == matter_id)
    if jurisdiction:
        conditions.append(Document.jurisdiction == jurisdiction)
    if status_filter:
        conditions.append(Document.processing_status == status_filter)

    stmt = (
        select(Document)
        .where(*conditions)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
):
    document = await db.get(Document, document_id)
    if not document or document.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    document = await db.get(Document, document_id)
    if not document or document.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    document.is_active = False
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        organization_id=org.id,
        user_id=user.id,
        action="delete",
        resource_type="document",
        resource_id=str(document_id),
        description=f"Deleted document: {document.title}",
    )


@router.post("/{document_id}/reprocess", response_model=DocumentOut)
async def reprocess_document(
    document_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
):
    document = await db.get(Document, document_id)
    if not document or document.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    document.processing_status = ProcessingStatus.PENDING
    document.processing_error = None
    await db.flush()

    from app.tasks.document_tasks import process_document_task
    process_document_task.delay(str(document.id))

    return document


@router.get("/{document_id}/download")
async def get_download_url(
    document_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
):
    document = await db.get(Document, document_id)
    if not document or document.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    storage = StorageService()
    url = await storage.get_presigned_url(document.file_path)
    return {"download_url": url, "file_name": document.file_name}
