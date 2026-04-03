import uuid
from datetime import datetime

from pydantic import BaseModel


class PreferenceCreate(BaseModel):
    category: str
    key: str
    value: dict
    description: str | None = None


class PreferenceOut(BaseModel):
    id: uuid.UUID
    category: str
    key: str
    value: dict
    description: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PreferenceUpdate(BaseModel):
    value: dict | None = None
    description: str | None = None
    is_active: bool | None = None


class MatterMemoryCreate(BaseModel):
    memory_type: str
    content: str
    structured_data: dict | None = None
    source: str | None = "user_input"
    importance: int = 5


class MatterMemoryOut(BaseModel):
    id: uuid.UUID
    matter_id: uuid.UUID
    memory_type: str
    content: str
    structured_data: dict | None
    source: str | None
    importance: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
