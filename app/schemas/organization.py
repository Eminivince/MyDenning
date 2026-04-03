import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.user import OrgRole


class OrganizationCreate(BaseModel):
    name: str
    domain: str | None = None
    default_jurisdiction: str | None = None
    default_governing_law: str | None = None


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    domain: str | None
    default_jurisdiction: str | None
    default_governing_law: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    default_jurisdiction: str | None = None
    default_governing_law: str | None = None


class MemberAdd(BaseModel):
    user_id: uuid.UUID
    role: OrgRole = OrgRole.MEMBER


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role: OrgRole
    user_email: str | None = None
    user_name: str | None = None

    model_config = {"from_attributes": True}
