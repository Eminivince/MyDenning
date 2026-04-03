import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class MatterStatus(str, enum.Enum):
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    CLOSED = "closed"
    ARCHIVED = "archived"


class MatterType(str, enum.Enum):
    LITIGATION = "litigation"
    TRANSACTION = "transaction"
    ADVISORY = "advisory"
    REGULATORY = "regulatory"
    CORPORATE = "corporate"
    EMPLOYMENT = "employment"
    IP = "ip"
    REAL_ESTATE = "real_estate"
    OTHER = "other"


class DeadlineStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class Matter(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "matters"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    matter_type: Mapped[MatterType] = mapped_column(Enum(MatterType), nullable=False, index=True)
    status: Mapped[MatterStatus] = mapped_column(Enum(MatterStatus), default=MatterStatus.ACTIVE, index=True)

    # Legal context
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    governing_law: Mapped[str | None] = mapped_column(String(255))
    counterparty: Mapped[str | None] = mapped_column(String(500))
    client_name: Mapped[str | None] = mapped_column(String(500))

    # Dates
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Structured data
    tags: Mapped[list | None] = mapped_column(JSONB)
    custom_fields: Mapped[dict | None] = mapped_column(JSONB)

    organization: Mapped["Organization"] = relationship(back_populates="matters")
    documents: Mapped[list["MatterDocument"]] = relationship(back_populates="matter", cascade="all, delete-orphan")
    notes: Mapped[list["MatterNote"]] = relationship(back_populates="matter", cascade="all, delete-orphan")
    deadlines: Mapped[list["MatterDeadline"]] = relationship(back_populates="matter", cascade="all, delete-orphan")
    memories: Mapped[list["MatterMemory"]] = relationship(back_populates="matter", cascade="all, delete-orphan")


class MatterDocument(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "matter_documents"

    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(100))  # e.g., "primary_agreement", "amendment", "exhibit"
    notes: Mapped[str | None] = mapped_column(Text)

    matter: Mapped["Matter"] = relationship(back_populates="documents")


class MatterNote(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "matter_notes"

    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str | None] = mapped_column(String(50))  # research, strategy, update, etc.

    matter: Mapped["Matter"] = relationship(back_populates="notes")


class MatterDeadline(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "matter_deadlines"

    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[DeadlineStatus] = mapped_column(Enum(DeadlineStatus), default=DeadlineStatus.PENDING)
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1=critical, 2=high, 3=medium, 4=low
    reminder_days_before: Mapped[int] = mapped_column(Integer, default=3)
    is_court_deadline: Mapped[bool] = mapped_column(Boolean, default=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"))

    matter: Mapped["Matter"] = relationship(back_populates="deadlines")


# Resolve forward references
from app.models.user import Organization  # noqa: E402
from app.models.memory import MatterMemory  # noqa: E402
