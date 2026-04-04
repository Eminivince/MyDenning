import uuid

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.schemas.analysis import (
    AskRequest, AskResponse,
    CompareRequest, CompareResponse,
    DraftRequest, DraftResponse,
    ResearchRequest, ResearchResponse,
    ReviewDocumentRequest, ReviewResponse,
)
from app.services.audit.service import AuditService
from app.services.document_intelligence.service import DocumentIntelligenceService
from app.services.output.generator import OutputGenerator
from app.services.reasoning.orchestrator import LegalReasoningOrchestrator

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    orchestrator = LegalReasoningOrchestrator(db)
    result = await orchestrator.answer_question(
        question=request.question,
        organization_id=org.id,
        user_id=user.id,
        document_ids=request.document_ids,
        matter_id=request.matter_id,
        jurisdiction=request.jurisdiction,
    )

    audit = AuditService(db)
    await audit.log_ai_operation(
        organization_id=org.id,
        user_id=user.id,
        action="ask_question",
        resource_type="analysis",
        resource_id=str(result["id"]),
        model_used=result.get("model_used", ""),
        sources_used=result.get("citations", []),
        confidence_score=result.get("confidence_score", 0.0),
        description=f"Question: {request.question[:100]}",
    )

    return result


@router.post("/research", response_model=ResearchResponse)
async def research(
    request: ResearchRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    orchestrator = LegalReasoningOrchestrator(db)
    result = await orchestrator.research(
        query=request.query,
        organization_id=org.id,
        user_id=user.id,
        jurisdiction=request.jurisdiction,
        source_types=request.source_types,
        court_level=request.court_level,
        binding_only=request.binding_only,
        max_results=request.max_results,
    )

    audit = AuditService(db)
    await audit.log_ai_operation(
        organization_id=org.id,
        user_id=user.id,
        action="research",
        resource_type="analysis",
        resource_id=str(result["id"]),
        model_used="anthropic",
        sources_used=[],
        confidence_score=0.0,
        description=f"Research: {request.query[:100]}",
    )

    return result


@router.post("/review", response_model=ReviewResponse)
async def review_document(
    request: ReviewDocumentRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    doc_intel = DocumentIntelligenceService(db)
    result = await doc_intel.extract_clauses(
        document_id=request.document_id,
        organization_id=org.id,
        user_id=user.id,
        focus_areas=request.focus_areas,
    )

    audit = AuditService(db)
    await audit.log_ai_operation(
        organization_id=org.id,
        user_id=user.id,
        action="review_document",
        resource_type="analysis",
        resource_id=str(result["id"]),
        model_used="anthropic",
        sources_used=[],
        confidence_score=result.get("confidence_score", 0.0),
        description=f"Document review: {request.document_id}",
    )

    return result


@router.post("/compare", response_model=CompareResponse)
async def compare_documents(
    request: CompareRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    doc_intel = DocumentIntelligenceService(db)

    if request.compare_to_playbook_id:
        result = await doc_intel.detect_deviations(
            document_id=request.document_id,
            playbook_id=request.compare_to_playbook_id,
            organization_id=org.id,
            user_id=user.id,
        )
    elif request.compare_to_document_id:
        result = await doc_intel.compare_documents(
            document_id=request.document_id,
            compare_to_id=request.compare_to_document_id,
            organization_id=org.id,
            user_id=user.id,
            focus_areas=request.focus_areas,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either compare_to_document_id or compare_to_playbook_id",
        )

    return result


@router.post("/draft", response_model=DraftResponse)
async def generate_draft(
    request: DraftRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    generator = OutputGenerator(db)
    result = await generator.generate_draft(
        draft_type=request.draft_type,
        instructions=request.instructions,
        organization_id=org.id,
        user_id=user.id,
        document_ids=request.document_ids,
        matter_id=request.matter_id,
        jurisdiction=request.jurisdiction,
        tone=request.tone,
    )

    audit = AuditService(db)
    await audit.log_ai_operation(
        organization_id=org.id,
        user_id=user.id,
        action="generate_draft",
        resource_type="analysis",
        resource_id=str(result["id"]),
        model_used="anthropic",
        sources_used=[],
        confidence_score=result.get("confidence_score", 0.0),
        description=f"Draft: {request.draft_type}",
    )

    return result


@router.post("/deadlines/{document_id}")
async def extract_deadlines(
    document_id: uuid.UUID,
    matter_id: uuid.UUID | None = None,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    doc_intel = DocumentIntelligenceService(db)
    return await doc_intel.extract_deadlines(
        document_id=document_id,
        organization_id=org.id,
        user_id=user.id,
        matter_id=matter_id,
    )


@router.post("/risk-matrix/{document_id}")
async def generate_risk_matrix(
    document_id: uuid.UUID,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    generator = OutputGenerator(db)
    return await generator.generate_risk_matrix(
        document_id=document_id,
        organization_id=org.id,
        user_id=user.id,
    )


@router.post("/issue-checklist/{matter_id}")
async def generate_issue_checklist(
    matter_id: uuid.UUID,
    document_ids: list[uuid.UUID] | None = None,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    generator = OutputGenerator(db)
    return await generator.generate_issue_checklist(
        matter_id=matter_id,
        organization_id=org.id,
        user_id=user.id,
        document_ids=document_ids,
    )


# ===================== EXPORT TO .DOCX =====================

@router.get("/export/{analysis_id}")
async def export_analysis(
    analysis_id: uuid.UUID,
    format: str = Query("docx", regex="^(docx)$"),
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Export any analysis result as a .docx file.

    Supports: drafts, reviews, redlines, risk matrices, and privilege logs.
    """
    from app.models.analysis import AnalysisResult, AnalysisType
    from app.services.output.export import ExportService

    result = await db.get(AnalysisResult, analysis_id)
    if not result or result.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    exporter = ExportService()
    data = result.result or {}

    if result.analysis_type == AnalysisType.MEMO_DRAFT:
        docx_bytes = exporter.export_draft(data)
        filename = f"draft-{result.analysis_type.value}-{str(analysis_id)[:8]}.docx"
    elif result.analysis_type == AnalysisType.CLAUSE_EXTRACTION:
        doc_title = ""
        if result.document_id:
            from app.models.document import Document
            doc = await db.get(Document, result.document_id)
            doc_title = doc.title if doc else ""
        docx_bytes = exporter.export_review(data, doc_title)
        filename = f"review-{str(analysis_id)[:8]}.docx"
    elif result.analysis_type == AnalysisType.DOCUMENT_COMPARISON:
        docx_bytes = exporter.export_redline(data)
        filename = f"redline-{str(analysis_id)[:8]}.docx"
    elif result.analysis_type == AnalysisType.RISK_ASSESSMENT:
        doc_title = ""
        if result.document_id:
            from app.models.document import Document
            doc = await db.get(Document, result.document_id)
            doc_title = doc.title if doc else ""
        docx_bytes = exporter.export_risk_matrix(data, doc_title)
        filename = f"risk-matrix-{str(analysis_id)[:8]}.docx"
    else:
        # Generic: export as a draft-style document
        docx_bytes = exporter.export_draft({
            "draft_type": result.analysis_type.value,
            "content": result.summary or str(data),
            "confidence_score": result.confidence_score,
        })
        filename = f"analysis-{str(analysis_id)[:8]}.docx"

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
