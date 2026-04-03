import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ClausePosition(str, enum.Enum):
    PREFERRED = "preferred"
    ACCEPTABLE = "acceptable"
    FALLBACK = "fallback"
    UNACCEPTABLE = "unacceptable"


class Playbook(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "playbooks"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "nda", "service_agreement"
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(default=True)

    organization: Mapped["Organization"] = relationship(back_populates="playbooks")
    clauses: Mapped[list["PlaybookClause"]] = relationship(back_populates="playbook", cascade="all, delete-orphan")


class PlaybookClause(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "playbook_clauses"

    playbook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True)

    clause_type: Mapped[str] = mapped_column(String(100), nullable=False)  # indemnity, liability_cap, termination, etc.
    clause_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[ClausePosition] = mapped_column(Enum(ClausePosition), nullable=False)

    # The actual clause language
    standard_language: Mapped[str] = mapped_column(Text, nullable=False)
    fallback_language: Mapped[str | None] = mapped_column(Text)
    unacceptable_patterns: Mapped[list | None] = mapped_column(JSONB)  # patterns that should be flagged

    # Guidance
    negotiation_notes: Mapped[str | None] = mapped_column(Text)
    risk_if_deviated: Mapped[str | None] = mapped_column(Text)
    approval_required_if: Mapped[str | None] = mapped_column(Text)

    # Scoring
    importance_weight: Mapped[float] = mapped_column(Float, default=1.0)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    playbook: Mapped["Playbook"] = relationship(back_populates="clauses")


from app.models.user import Organization  # noqa: E402
