import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Conversation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversations"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), index=True)

    title: Mapped[str | None] = mapped_column(String(500))
    mode: Mapped[str] = mapped_column(String(50), default="ask")  # ask, research, review, compare, draft, monitor
    context: Mapped[dict | None] = mapped_column(JSONB)  # active document IDs, filters, etc.
    is_active: Mapped[bool] = mapped_column(default=True)

    messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationMessage.sequence_number")


class ConversationMessage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversation_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # AI metadata
    model_used: Mapped[str | None] = mapped_column(String(100))
    token_count_input: Mapped[int | None] = mapped_column(Integer)
    token_count_output: Mapped[int | None] = mapped_column(Integer)
    sources_used: Mapped[list | None] = mapped_column(JSONB)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("analysis_results.id", ondelete="SET NULL"))

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
