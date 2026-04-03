import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class SourceType(str, enum.Enum):
    CASE_LAW = "case_law"
    STATUTE = "statute"
    REGULATION = "regulation"
    GUIDANCE = "guidance"
    SECONDARY = "secondary"
    TREATY = "treaty"


class AuthorityLevel(str, enum.Enum):
    BINDING = "binding"
    PERSUASIVE = "persuasive"
    SECONDARY = "secondary"


class CitationRelationType(str, enum.Enum):
    CITES = "cites"
    CITED_BY = "cited_by"
    OVERRULES = "overrules"
    OVERRULED_BY = "overruled_by"
    DISTINGUISHES = "distinguishes"
    FOLLOWS = "follows"
    APPLIES = "applies"
    INTERPRETS = "interprets"
    AMENDS = "amends"
    REPEALS = "repeals"


class LegalSource(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "legal_sources"

    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False, index=True)
    authority_level: Mapped[AuthorityLevel] = mapped_column(Enum(AuthorityLevel), nullable=False)

    # Identification
    citation: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    alt_citations: Mapped[list | None] = mapped_column(JSONB)
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)

    # Jurisdiction and court
    jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    court: Mapped[str | None] = mapped_column(String(255))
    court_level: Mapped[int | None] = mapped_column(Integer)  # 1=supreme, 2=appeal, 3=high, 4=district
    issuing_body: Mapped[str | None] = mapped_column(String(255))

    # Dates
    date_decided: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    date_enacted: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_effective: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_repealed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Content
    full_text: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    headnote: Mapped[str | None] = mapped_column(Text)
    key_passages: Mapped[list | None] = mapped_column(JSONB)

    # Topics/tags
    topics: Mapped[list | None] = mapped_column(JSONB)
    keywords: Mapped[list | None] = mapped_column(JSONB)

    # Status
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    superseded_by: Mapped[str | None] = mapped_column(String(500))

    # Document link (if uploaded)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"))

    outgoing_citations: Mapped[list["CitationRelationship"]] = relationship(
        back_populates="source",
        foreign_keys="CitationRelationship.source_id",
        cascade="all, delete-orphan",
    )
    incoming_citations: Mapped[list["CitationRelationship"]] = relationship(
        back_populates="target",
        foreign_keys="CitationRelationship.target_id",
        cascade="all, delete-orphan",
    )


class LegalCitation(Base, UUIDMixin, TimestampMixin):
    """Extracted citations from document chunks."""
    __tablename__ = "legal_citations"

    document_chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    citation_text: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_citation: Mapped[str | None] = mapped_column(String(500), index=True)
    legal_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_sources.id", ondelete="SET NULL"))
    context: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    position_start: Mapped[int | None] = mapped_column(Integer)
    position_end: Mapped[int | None] = mapped_column(Integer)


class CitationRelationship(Base, UUIDMixin, TimestampMixin):
    """Relationship between legal sources in the knowledge graph."""
    __tablename__ = "citation_relationships"

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type: Mapped[CitationRelationType] = mapped_column(Enum(CitationRelationType), nullable=False)
    context: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    source: Mapped["LegalSource"] = relationship(back_populates="outgoing_citations", foreign_keys=[source_id])
    target: Mapped["LegalSource"] = relationship(back_populates="incoming_citations", foreign_keys=[target_id])
