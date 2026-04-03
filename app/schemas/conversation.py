import uuid
from datetime import datetime

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    mode: str = "ask"
    matter_id: uuid.UUID | None = None
    title: str | None = None
    document_ids: list[uuid.UUID] | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    mode: str
    matter_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    content: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sequence_number: int
    model_used: str | None
    sources_used: list | None
    created_at: datetime

    model_config = {"from_attributes": True}
