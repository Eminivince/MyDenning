import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.analysis import AnalysisType, RiskLevel


class AskRequest(BaseModel):
    question: str
    document_ids: list[uuid.UUID] | None = None
    matter_id: uuid.UUID | None = None
    jurisdiction: str | None = None
    include_sources: bool = True


class ResearchRequest(BaseModel):
    query: str
    jurisdiction: str | None = None
    court_level: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    source_types: list[str] | None = None
    binding_only: bool = False
    max_results: int = 20


class ReviewDocumentRequest(BaseModel):
    document_id: uuid.UUID
    playbook_id: uuid.UUID | None = None
    focus_areas: list[str] | None = None  # e.g., ["indemnity", "termination", "liability"]


class CompareRequest(BaseModel):
    document_id: uuid.UUID
    compare_to_document_id: uuid.UUID | None = None
    compare_to_playbook_id: uuid.UUID | None = None
    focus_areas: list[str] | None = None


class DraftRequest(BaseModel):
    draft_type: str  # memo, contract, board_resolution, legal_email, negotiation_fallback
    matter_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] | None = None
    instructions: str
    jurisdiction: str | None = None
    tone: str | None = None  # formal, advisory, internal


class CitationOut(BaseModel):
    citation_text: str
    source_title: str | None = None
    source_type: str | None = None
    jurisdiction: str | None = None
    authority_level: str | None = None
    relevant_passage: str | None = None
    confidence: float = 1.0


class IssueAnalysis(BaseModel):
    issue: str
    rule: str
    authority: list[CitationOut]
    analysis: str
    uncertainty: str | None = None
    recommendation: str
    risk_level: RiskLevel
    confidence: float


class AskResponse(BaseModel):
    id: uuid.UUID
    question: str
    answer: str
    issues: list[IssueAnalysis]
    citations: list[CitationOut]
    confidence_score: float
    risk_flags: list[str]
    follow_up_questions: list[str]
    model_used: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClauseExtractionOut(BaseModel):
    clause_type: str
    clause_number: str | None
    clause_title: str | None
    clause_text: str
    parties_involved: list | None
    obligations: list | None
    dates: list | None
    monetary_values: list | None
    conditions: list | None
    risk_level: RiskLevel | None
    risk_notes: str | None
    is_standard: bool | None
    confidence: float


class ReviewResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    summary: str
    clauses: list[ClauseExtractionOut]
    risk_flags: list[dict[str, Any]]
    missing_clauses: list[str]
    unusual_terms: list[str]
    key_dates: list[dict[str, Any]]
    key_obligations: list[dict[str, Any]]
    overall_risk_level: RiskLevel
    confidence_score: float
    created_at: datetime


class DeviationOut(BaseModel):
    clause_type: str
    document_clause_text: str
    playbook_clause_text: str
    deviation_type: str
    deviation_description: str
    risk_level: RiskLevel
    recommendation: str
    suggested_language: str | None
    requires_approval: bool
    confidence: float


class CompareResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    compared_to: str  # document title or playbook name
    summary: str
    deviations: list[DeviationOut]
    risk_score: float
    overall_risk_level: RiskLevel
    approval_required: bool
    created_at: datetime


class DraftResponse(BaseModel):
    id: uuid.UUID
    draft_type: str
    content: str
    citations: list[CitationOut]
    assumptions: list[str]
    risk_flags: list[str]
    confidence_score: float
    created_at: datetime


class ResearchResponse(BaseModel):
    id: uuid.UUID
    query: str
    results: list[dict[str, Any]]
    summary: str
    jurisdiction_notes: str | None
    total_results: int
    created_at: datetime
