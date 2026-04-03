import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.document import DocumentType, ProcessingStatus


class DocumentCreate(BaseModel):
    title: str
    description: str | None = None
    document_type: DocumentType
    matter_id: uuid.UUID | None = None
    jurisdiction: str | None = None
    governing_law: str | None = None


class DocumentOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    description: str | None
    document_type: DocumentType
    file_name: str
    file_size: int
    mime_type: str
    jurisdiction: str | None
    governing_law: str | None
    effective_date: datetime | None
    expiry_date: datetime | None
    parties: dict | None
    extracted_metadata: dict | None
    processing_status: ProcessingStatus
    page_count: int | None
    matter_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListOut(BaseModel):
    id: uuid.UUID
    title: str
    document_type: DocumentType
    file_name: str
    processing_status: ProcessingStatus
    jurisdiction: str | None
    matter_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionOut(BaseModel):
    id: uuid.UUID
    version_number: int
    file_size: int
    content_hash: str
    change_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentChunkOut(BaseModel):
    id: uuid.UUID
    chunk_index: int
    content: str
    page_number: int | None
    section_title: str | None
    clause_number: str | None
    clause_type: str | None

    model_config = {"from_attributes": True}
