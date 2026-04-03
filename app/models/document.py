import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class DocumentType(str, enum.Enum):
    CONTRACT = "contract"
    POLICY = "policy"
    MEMO = "memo"
    PLEADING = "pleading"
    BOARD_RESOLUTION = "board_resolution"
    NDA = "nda"
    EMPLOYMENT_AGREEMENT = "employment_agreement"
    COMPLIANCE_DOC = "compliance_doc"
    STATUTE = "statute"
    REGULATION = "regulation"
    CASE_LAW = "case_law"
    GUIDANCE = "guidance"
    OTHER = "other"


class ProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Legal metadata
    jurisdiction: Mapped[str | None] = mapped_column(String(100), index=True)
    governing_law: Mapped[str | None] = mapped_column(String(255))
    effective_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parties: Mapped[dict | None] = mapped_column(JSONB)
    extracted_metadata: Mapped[dict | None] = mapped_column(JSONB)

    # Processing
    processing_status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING)
    processing_error: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    organization: Mapped["Organization"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_number.desc()")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    document: Mapped["Document"] = relationship(back_populates="versions")


class DocumentChunk(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))

    # Structural metadata
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(500))
    clause_number: Mapped[str | None] = mapped_column(String(50))
    chunk_type: Mapped[str | None] = mapped_column(String(50))  # paragraph, clause, definition, schedule, etc.

    # Legal metadata
    clause_type: Mapped[str | None] = mapped_column(String(100))  # indemnity, termination, liability, etc.
    parties_mentioned: Mapped[list | None] = mapped_column(JSONB)
    dates_mentioned: Mapped[list | None] = mapped_column(JSONB)
    obligations: Mapped[list | None] = mapped_column(JSONB)
    citations: Mapped[list | None] = mapped_column(JSONB)

    token_count: Mapped[int | None] = mapped_column(Integer)

    document: Mapped["Document"] = relationship(back_populates="chunks")


# Resolve forward reference
from app.models.user import Organization  # noqa: E402
