import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
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


class ConfidentialityLevel(str, enum.Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    HIGHLY_CONFIDENTIAL = "highly_confidential"


class MatterAccessLevel(str, enum.Enum):
    FULL = "full"
    LIMITED = "limited"
    READ_ONLY = "read_only"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class Matter(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "matters"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    matter_code: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)  # firm's internal code
    description: Mapped[str | None] = mapped_column(Text)
    matter_type: Mapped[MatterType] = mapped_column(Enum(MatterType), nullable=False, index=True)
    status: Mapped[MatterStatus] = mapped_column(Enum(MatterStatus), default=MatterStatus.ACTIVE, index=True)
    practice_area: Mapped[str | None] = mapped_column(String(100), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1=critical, 2=high, 3=medium, 4=low

    # Legal context
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    governing_law: Mapped[str | None] = mapped_column(String(255))
    counterparty: Mapped[str | None] = mapped_column(String(500))
    client_name: Mapped[str | None] = mapped_column(String(500))

    # Team
    lead_lawyer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"))
    confidentiality_level: Mapped[ConfidentialityLevel] = mapped_column(Enum(ConfidentialityLevel), default=ConfidentialityLevel.CONFIDENTIAL)

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
    matter_members: Mapped[list["MatterMembership"]] = relationship(back_populates="matter", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="matter", cascade="all, delete-orphan")
    time_entries: Mapped[list["TimeEntry"]] = relationship(back_populates="matter", cascade="all, delete-orphan")
    calendar_events: Mapped[list["CalendarEvent"]] = relationship(back_populates="matter", cascade="all, delete-orphan")


class MatterMembership(Base, UUIDMixin, TimestampMixin):
    """Controls who can access a matter and with what permissions."""
    __tablename__ = "matter_memberships"

    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_on_matter: Mapped[str] = mapped_column(String(50), default="contributor")  # lead, contributor, reviewer, viewer
    access_level: Mapped[MatterAccessLevel] = mapped_column(Enum(MatterAccessLevel), default=MatterAccessLevel.FULL)

    matter: Mapped["Matter"] = relationship(back_populates="matter_members")


class MatterDocument(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "matter_documents"

    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)

    matter: Mapped["Matter"] = relationship(back_populates="documents")


class MatterNote(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "matter_notes"

    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str | None] = mapped_column(String(50))

    matter: Mapped["Matter"] = relationship(back_populates="notes")


class MatterDeadline(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "matter_deadlines"

    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[DeadlineStatus] = mapped_column(Enum(DeadlineStatus), default=DeadlineStatus.PENDING)
    priority: Mapped[int] = mapped_column(Integer, default=2)
    reminder_days_before: Mapped[int] = mapped_column(Integer, default=3)
    is_court_deadline: Mapped[bool] = mapped_column(Boolean, default=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"))

    matter: Mapped["Matter"] = relationship(back_populates="deadlines")


# --- Tasks ---

class Task(Base, UUIDMixin, TimestampMixin):
    """Work items assigned to team members within a matter."""
    __tablename__ = "tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.PENDING, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1=critical, 2=high, 3=medium, 4=low
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # Links
    linked_document_ids: Mapped[list | None] = mapped_column(JSONB)
    tags: Mapped[list | None] = mapped_column(JSONB)

    # Workflow
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    matter: Mapped["Matter"] = relationship(back_populates="tasks")


# --- Time Tracking ---

class TimeEntry(Base, UUIDMixin, TimestampMixin):
    """Billable and non-billable time entries."""
    __tablename__ = "time_entries"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))

    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True)
    rate: Mapped[float | None] = mapped_column(Float)  # hourly rate
    amount: Mapped[float | None] = mapped_column(Float)  # hours * rate
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), index=True)

    matter: Mapped["Matter"] = relationship(back_populates="time_entries")


# --- Invoicing ---

class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    PARTIALLY_PAID = "partially_paid"


class Invoice(Base, UUIDMixin, TimestampMixin):
    """Client invoices generated from time entries."""
    __tablename__ = "invoices"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    issue_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.DRAFT, index=True)

    # Amounts
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    amount_paid: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="NGN")

    # Line items (denormalized for invoice snapshot)
    line_items: Mapped[list | None] = mapped_column(JSONB)  # [{description, hours, rate, amount}]
    notes: Mapped[str | None] = mapped_column(Text)
    payment_terms: Mapped[str | None] = mapped_column(String(255))

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Calendar Events ---

class EventType(str, enum.Enum):
    HEARING = "hearing"
    CONFERENCE = "conference"
    DEADLINE = "deadline"
    MEETING = "meeting"
    FILING = "filing"
    DEPOSITION = "deposition"
    MEDIATION = "mediation"
    ARBITRATION = "arbitration"
    OTHER = "other"


class CalendarEvent(Base, UUIDMixin, TimestampMixin):
    """Calendar events linked to matters."""
    __tablename__ = "calendar_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), default=EventType.MEETING, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)

    location: Mapped[str | None] = mapped_column(String(500))
    attendee_ids: Mapped[list | None] = mapped_column(JSONB)  # user UUIDs
    reminders: Mapped[list | None] = mapped_column(JSONB)  # [{minutes_before: 30, type: "notification"}]
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(255))  # iCal RRULE

    matter: Mapped["Matter"] = relationship(back_populates="calendar_events")


# Resolve forward references
from app.models.user import Organization  # noqa: E402
from app.models.memory import MatterMemory  # noqa: E402
