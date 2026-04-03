import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.matter import DeadlineStatus, MatterStatus, MatterType


class MatterCreate(BaseModel):
    title: str
    description: str | None = None
    matter_type: MatterType
    jurisdiction: str | None = None
    governing_law: str | None = None
    counterparty: str | None = None
    client_name: str | None = None
    tags: list[str] | None = None


class MatterOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    reference_number: str | None
    description: str | None
    matter_type: MatterType
    status: MatterStatus
    jurisdiction: str | None
    governing_law: str | None
    counterparty: str | None
    client_name: str | None
    tags: list | None
    opened_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MatterUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: MatterStatus | None = None
    jurisdiction: str | None = None
    governing_law: str | None = None
    counterparty: str | None = None
    client_name: str | None = None
    tags: list[str] | None = None


class DeadlineCreate(BaseModel):
    title: str
    description: str | None = None
    due_date: datetime
    priority: int = 2
    reminder_days_before: int = 3
    is_court_deadline: bool = False
    source_document_id: uuid.UUID | None = None


class DeadlineOut(BaseModel):
    id: uuid.UUID
    matter_id: uuid.UUID
    title: str
    description: str | None
    due_date: datetime
    status: DeadlineStatus
    priority: int
    is_court_deadline: bool
    source_document_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DeadlineUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_date: datetime | None = None
    status: DeadlineStatus | None = None
    priority: int | None = None


class NoteCreate(BaseModel):
    content: str
    note_type: str | None = None


class NoteOut(BaseModel):
    id: uuid.UUID
    matter_id: uuid.UUID
    content: str
    note_type: str | None
    created_by_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
