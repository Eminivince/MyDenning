import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class OrganizationPreference(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organization_preferences"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    set_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    organization: Mapped["Organization"] = relationship(back_populates="preferences")


class MatterMemory(Base, UUIDMixin, TimestampMixin):
    """Contextual memory entries for matters - tracks decisions, preferences, and context."""
    __tablename__ = "matter_memories"

    matter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    memory_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # decision, preference, context, fact
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str | None] = mapped_column(String(100))  # user_input, extracted, inferred
    importance: Mapped[int] = mapped_column(Integer, default=5)  # 1-10
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    matter: Mapped["Matter"] = relationship(back_populates="memories")


from app.models.user import Organization  # noqa: E402
