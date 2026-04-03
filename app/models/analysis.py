import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class AnalysisType(str, enum.Enum):
    QUESTION_ANSWER = "question_answer"
    CLAUSE_EXTRACTION = "clause_extraction"
    DEVIATION_CHECK = "deviation_check"
    DOCUMENT_COMPARISON = "document_comparison"
    MEMO_DRAFT = "memo_draft"
    RISK_ASSESSMENT = "risk_assessment"
    DEADLINE_EXTRACTION = "deadline_extraction"
    RESEARCH = "research"


class RiskLevel(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AnalysisResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "analysis_results"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), index=True)

    analysis_type: Mapped[AnalysisType] = mapped_column(Enum(AnalysisType), nullable=False, index=True)
    query: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Structured output
    summary: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[RiskLevel | None] = mapped_column(Enum(RiskLevel))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    citations_used: Mapped[list | None] = mapped_column(JSONB)
    sources_consulted: Mapped[list | None] = mapped_column(JSONB)

    # Model info
    model_used: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(50))
    token_count_input: Mapped[int | None] = mapped_column(Integer)
    token_count_output: Mapped[int | None] = mapped_column(Integer)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)

    # Review
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)


class ClauseExtraction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "clause_extractions"

    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_results.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"))

    clause_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    clause_number: Mapped[str | None] = mapped_column(String(50))
    clause_title: Mapped[str | None] = mapped_column(String(500))
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)

    # Extracted details
    parties_involved: Mapped[list | None] = mapped_column(JSONB)
    obligations: Mapped[list | None] = mapped_column(JSONB)
    dates: Mapped[list | None] = mapped_column(JSONB)
    monetary_values: Mapped[list | None] = mapped_column(JSONB)
    conditions: Mapped[list | None] = mapped_column(JSONB)

    risk_level: Mapped[RiskLevel | None] = mapped_column(Enum(RiskLevel))
    risk_notes: Mapped[str | None] = mapped_column(Text)
    is_standard: Mapped[bool | None] = mapped_column()
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


class DeviationReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "deviation_reports"

    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_results.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    playbook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True)
    playbook_clause_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("playbook_clauses.id", ondelete="SET NULL"))

    clause_type: Mapped[str] = mapped_column(String(100), nullable=False)
    document_clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    playbook_clause_text: Mapped[str] = mapped_column(Text, nullable=False)

    deviation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # missing, weaker, different, additional
    deviation_description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_language: Mapped[str | None] = mapped_column(Text)
    requires_approval: Mapped[bool] = mapped_column(default=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
