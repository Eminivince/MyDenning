import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.playbook import ClausePosition


class PlaybookClauseCreate(BaseModel):
    clause_type: str
    clause_name: str
    position: ClausePosition
    standard_language: str
    fallback_language: str | None = None
    unacceptable_patterns: list[str] | None = None
    negotiation_notes: str | None = None
    risk_if_deviated: str | None = None
    approval_required_if: str | None = None
    importance_weight: float = 1.0
    order_index: int = 0


class PlaybookCreate(BaseModel):
    name: str
    description: str | None = None
    document_type: str
    jurisdiction: str | None = None
    clauses: list[PlaybookClauseCreate] | None = None


class PlaybookClauseOut(BaseModel):
    id: uuid.UUID
    clause_type: str
    clause_name: str
    position: ClausePosition
    standard_language: str
    fallback_language: str | None
    unacceptable_patterns: list | None
    negotiation_notes: str | None
    risk_if_deviated: str | None
    approval_required_if: str | None
    importance_weight: float
    order_index: int

    model_config = {"from_attributes": True}


class PlaybookOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    document_type: str
    jurisdiction: str | None
    version: int
    is_active: bool
    clauses: list[PlaybookClauseOut] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class PlaybookUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    jurisdiction: str | None = None
