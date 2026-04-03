"""API endpoints for all legal feature services:
- Document redline
- Privilege tagging
- Conflict-of-interest checking
- Multi-jurisdiction comparison
- Regulatory change monitoring
- Citation validation
"""

import uuid
from datetime import date as date_type, datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.services.audit.service import AuditService

router = APIRouter(tags=["legal-features"])


# ===================== SCHEMAS =====================

class RedlineRequest(BaseModel):
    document_id_1: uuid.UUID
    document_id_2: uuid.UUID
    focus_areas: list[str] | None = None


class VersionRedlineRequest(BaseModel):
    document_id: uuid.UUID
    version_from: int
    version_to: int


class PrivilegeTagRequest(BaseModel):
    privilege_type: str  # attorney_client, work_product, common_interest, litigation_hold, confidential
    basis: str
    document_id: uuid.UUID | None = None
    matter_id: uuid.UUID | None = None
    analysis_id: uuid.UUID | None = None
    scope_description: str | None = None
    attorney_name: str | None = None
    client_name: str | None = None


class PrivilegeWaiverRequest(BaseModel):
    reason: str
    scope: str = "full"  # full or partial


class PrivilegeReviewRequest(BaseModel):
    status: str  # asserted, waived, disputed, under_review
    notes: str | None = None


class ConflictCheckRequest(BaseModel):
    party_names: list[str]
    matter_id: uuid.UUID | None = None


class PartyRegisterRequest(BaseModel):
    name: str
    party_type: str | None = None  # individual, company, government, trust
    jurisdiction: str | None = None
    aliases: list[str] | None = None
    registration_number: str | None = None


class PartyLinkRequest(BaseModel):
    matter_id: uuid.UUID
    party_id: uuid.UUID
    role: str  # client, counterparty, opposing_counsel, co-party, witness
    is_adverse: bool = False


class ConflictResolveRequest(BaseModel):
    resolution: str
    new_status: str = "cleared"  # cleared, waived


class MultiJurisdictionRequest(BaseModel):
    topic: str
    jurisdictions: list[str]
    document_ids: list[uuid.UUID] | None = None
    content_type: str | None = None


class MonitorCreateRequest(BaseModel):
    title: str
    jurisdiction: str
    source_type: str  # statute, regulation, case_law, guidance
    description: str | None = None
    source_identifier: str | None = None
    keywords: list[str] | None = None
    topics: list[str] | None = None
    check_frequency_hours: int = 24
    affected_matter_ids: list[uuid.UUID] | None = None


class AlertActionRequest(BaseModel):
    notes: str | None = None


class CitationValidateRequest(BaseModel):
    citation: str
    jurisdiction: str | None = None


class BatchCitationValidateRequest(BaseModel):
    citations: list[str]
    jurisdiction: str | None = None


# ===================== REDLINE =====================

@router.post("/redline/compare")
async def generate_redline(
    request: RedlineRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Generate a tracked-changes redline between two documents.

    Returns structured diff with legal commentary, markdown redline, and HTML redline.
    """
    from app.services.legal_features.redline import RedlineService
    service = RedlineService(db)
    result = await service.generate_redline(
        document_id_1=request.document_id_1,
        document_id_2=request.document_id_2,
        organization_id=org.id,
        user_id=user.id,
        focus_areas=request.focus_areas,
    )
    return result


@router.post("/redline/version")
async def generate_version_redline(
    request: VersionRedlineRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Generate a redline between two versions of the same document."""
    from app.services.legal_features.redline import RedlineService
    service = RedlineService(db)
    result = await service.redline_version(
        document_id=request.document_id,
        version_from=request.version_from,
        version_to=request.version_to,
        organization_id=org.id,
        user_id=user.id,
    )
    return result


# ===================== PRIVILEGE =====================

@router.post("/privilege/tag", status_code=status.HTTP_201_CREATED)
async def tag_privilege(
    request: PrivilegeTagRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Assert attorney-client privilege, work product, or other confidentiality marking."""
    from app.services.legal_features.privilege import PrivilegeService
    from app.models.legal_features import PrivilegeType
    service = PrivilegeService(db)
    tag = await service.tag_privilege(
        organization_id=org.id,
        user_id=user.id,
        privilege_type=PrivilegeType(request.privilege_type),
        basis=request.basis,
        document_id=request.document_id,
        matter_id=request.matter_id,
        analysis_id=request.analysis_id,
        scope_description=request.scope_description,
        attorney_name=request.attorney_name,
        client_name=request.client_name,
    )

    audit = AuditService(db)
    await audit.log(
        organization_id=org.id, user_id=user.id,
        action="assert_privilege", resource_type="privilege_tag",
        resource_id=str(tag.id),
        description=f"Privilege asserted: {request.privilege_type}",
    )
    return {"id": str(tag.id), "privilege_type": tag.privilege_type.value, "status": tag.status.value}


@router.post("/privilege/{tag_id}/waive")
async def waive_privilege(
    tag_id: uuid.UUID,
    request: PrivilegeWaiverRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Waive a privilege assertion. This action is logged and irreversible."""
    from app.services.legal_features.privilege import PrivilegeService
    service = PrivilegeService(db)
    tag = await service.waive_privilege(tag_id, user.id, request.reason, request.scope)

    audit = AuditService(db)
    await audit.log(
        organization_id=org.id, user_id=user.id,
        action="waive_privilege", resource_type="privilege_tag",
        resource_id=str(tag_id),
        description=f"Privilege waived: {request.reason}",
    )
    return {"id": str(tag.id), "status": tag.status.value, "waived_at": tag.waived_at.isoformat()}


@router.patch("/privilege/{tag_id}/review")
async def review_privilege(
    tag_id: uuid.UUID,
    request: PrivilegeReviewRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    from app.services.legal_features.privilege import PrivilegeService
    from app.models.legal_features import PrivilegeStatus
    service = PrivilegeService(db)
    tag = await service.review_privilege(tag_id, user.id, PrivilegeStatus(request.status), request.notes)
    return {"id": str(tag.id), "status": tag.status.value}


@router.get("/privilege/document/{document_id}")
async def get_document_privileges(
    document_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None,
):
    from app.services.legal_features.privilege import PrivilegeService
    service = PrivilegeService(db)
    tags = await service.get_document_privileges(document_id)
    return [{"id": str(t.id), "type": t.privilege_type.value, "status": t.status.value, "basis": t.basis} for t in tags]


@router.get("/privilege/matter/{matter_id}/log")
async def generate_privilege_log(
    matter_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None,
):
    """Generate a privilege log for discovery responses."""
    from app.services.legal_features.privilege import PrivilegeService
    service = PrivilegeService(db)
    return await service.generate_privilege_log(matter_id, org.id)


@router.post("/privilege/auto-detect/{document_id}")
async def auto_detect_privilege(
    document_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None,
):
    """Use AI to detect potentially privileged content in a document."""
    from app.services.legal_features.privilege import PrivilegeService
    service = PrivilegeService(db)
    return {"findings": await service.auto_detect_privilege(document_id, org.id)}


# ===================== CONFLICTS =====================

@router.post("/conflicts/check")
async def check_conflicts(
    request: ConflictCheckRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Run a conflict-of-interest check against all matters in the organization."""
    from app.services.legal_features.conflicts import ConflictCheckingService
    service = ConflictCheckingService(db)
    check = await service.check_conflicts(org.id, user.id, request.party_names, request.matter_id)

    audit = AuditService(db)
    await audit.log(
        organization_id=org.id, user_id=user.id,
        action="conflict_check", resource_type="conflict_check",
        resource_id=str(check.id),
        description=f"Conflict check: {', '.join(request.party_names[:3])}",
        metadata={"status": check.status.value, "conflicts": len(check.conflicts_found or [])},
    )

    return {
        "id": str(check.id),
        "status": check.status.value,
        "parties_checked": request.party_names,
        "conflicts_found": check.conflicts_found or [],
        "conflict_count": len(check.conflicts_found or []),
    }


@router.post("/conflicts/parties", status_code=status.HTTP_201_CREATED)
async def register_party(
    request: PartyRegisterRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    from app.services.legal_features.conflicts import ConflictCheckingService
    service = ConflictCheckingService(db)
    party = await service.register_party(
        org.id, request.name, request.party_type, request.jurisdiction, request.aliases, request.registration_number,
    )
    return {"id": str(party.id), "name": party.name, "normalized_name": party.normalized_name}


@router.post("/conflicts/parties/link")
async def link_party_to_matter(
    request: PartyLinkRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    from app.services.legal_features.conflicts import ConflictCheckingService
    service = ConflictCheckingService(db)
    link = await service.link_party_to_matter(request.matter_id, request.party_id, request.role, request.is_adverse)
    return {"id": str(link.id), "linked": True}


@router.get("/conflicts/parties/{party_name}/history")
async def get_party_history(
    party_name: str,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    from app.services.legal_features.conflicts import ConflictCheckingService
    service = ConflictCheckingService(db)
    return await service.get_party_history(org.id, party_name)


@router.post("/conflicts/{check_id}/resolve")
async def resolve_conflict(
    check_id: uuid.UUID,
    request: ConflictResolveRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    from app.services.legal_features.conflicts import ConflictCheckingService
    from app.models.legal_features import ConflictStatus
    service = ConflictCheckingService(db)
    check = await service.resolve_conflict(check_id, user.id, request.resolution, ConflictStatus(request.new_status))
    return {"id": str(check.id), "status": check.status.value, "resolved": True}


@router.post("/conflicts/{check_id}/approve")
async def approve_conflict_clearance(
    check_id: uuid.UUID,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    from app.services.legal_features.conflicts import ConflictCheckingService
    service = ConflictCheckingService(db)
    check = await service.approve_conflict_clearance(check_id, user.id)
    return {"id": str(check.id), "approved": True, "approved_at": check.approved_at.isoformat()}


# ===================== MULTI-JURISDICTION =====================

@router.post("/multi-jurisdiction/compare")
async def compare_jurisdictions(
    request: MultiJurisdictionRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Compare how a legal topic is treated across multiple jurisdictions.

    Example: compare termination rights under Nigerian law vs English law vs Delaware law.
    """
    from app.services.legal_features.multi_jurisdiction import MultiJurisdictionService
    service = MultiJurisdictionService(db)
    return await service.compare_jurisdictions(
        topic=request.topic,
        jurisdictions=request.jurisdictions,
        organization_id=org.id,
        user_id=user.id,
        document_ids=request.document_ids,
        content_type=request.content_type,
    )


# ===================== REGULATORY MONITORING =====================

@router.post("/regulatory/monitors", status_code=status.HTTP_201_CREATED)
async def create_regulatory_monitor(
    request: MonitorCreateRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Subscribe to monitor a regulation, statute, or legal area for changes."""
    from app.services.legal_features.regulatory_monitor import RegulatoryMonitorService
    service = RegulatoryMonitorService(db)
    monitor = await service.create_monitor(
        organization_id=org.id, user_id=user.id,
        title=request.title, jurisdiction=request.jurisdiction,
        source_type=request.source_type, description=request.description,
        source_identifier=request.source_identifier, keywords=request.keywords,
        topics=request.topics, check_frequency_hours=request.check_frequency_hours,
        affected_matter_ids=request.affected_matter_ids,
    )
    return {
        "id": str(monitor.id), "title": monitor.title,
        "jurisdiction": monitor.jurisdiction, "source_adapter": monitor.source_adapter,
    }


@router.get("/regulatory/monitors")
async def list_regulatory_monitors(
    user: CurrentUser = None, org: CurrentOrg = None, db: DB = None,
    jurisdiction: str | None = None,
):
    from app.services.legal_features.regulatory_monitor import RegulatoryMonitorService
    service = RegulatoryMonitorService(db)
    monitors = await service.list_monitors(org.id, jurisdiction)
    return [
        {
            "id": str(m.id), "title": m.title, "jurisdiction": m.jurisdiction,
            "source_type": m.source_type, "is_active": m.is_active,
            "last_checked_at": m.last_checked_at.isoformat() if m.last_checked_at else None,
            "last_change_at": m.last_change_detected_at.isoformat() if m.last_change_detected_at else None,
        }
        for m in monitors
    ]


@router.post("/regulatory/monitors/{monitor_id}/check")
async def trigger_regulatory_check(
    monitor_id: uuid.UUID,
    user: CurrentUser = None, org: CurrentOrg = None, db: DB = None,
):
    """Manually trigger a check on a monitored regulation."""
    from app.services.legal_features.regulatory_monitor import RegulatoryMonitorService
    service = RegulatoryMonitorService(db)
    alerts = await service.check_for_changes(monitor_id)
    return {"alerts_generated": len(alerts), "alerts": [
        {"id": str(a.id), "title": a.title, "risk_level": a.risk_level, "alert_type": a.alert_type}
        for a in alerts
    ]}


@router.get("/regulatory/alerts")
async def get_regulatory_alerts(
    user: CurrentUser = None, org: CurrentOrg = None, db: DB = None,
    unread_only: bool = Query(False),
    jurisdiction: str | None = None,
    limit: int = Query(50, le=200),
):
    from app.services.legal_features.regulatory_monitor import RegulatoryMonitorService
    service = RegulatoryMonitorService(db)
    alerts = await service.get_alerts(org.id, unread_only, jurisdiction, limit)
    return [
        {
            "id": str(a.id), "alert_type": a.alert_type, "title": a.title,
            "summary": a.summary, "risk_level": a.risk_level,
            "source_url": a.source_url, "source_citation": a.source_citation,
            "is_read": a.is_read, "created_at": a.created_at.isoformat(),
        }
        for a in alerts
    ]


@router.post("/regulatory/alerts/{alert_id}/action")
async def action_regulatory_alert(
    alert_id: uuid.UUID, request: AlertActionRequest,
    user: CurrentUser = None, org: CurrentOrg = None, db: DB = None,
):
    from app.services.legal_features.regulatory_monitor import RegulatoryMonitorService
    service = RegulatoryMonitorService(db)
    alert = await service.mark_alert_actioned(alert_id, user.id, request.notes)
    return {"id": str(alert.id), "actioned": True}


# ===================== CITATION VALIDATION =====================

@router.post("/citations/validate")
async def validate_citation(
    request: CitationValidateRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Check if a legal citation is still good law.

    This is MyDenning's equivalent of Shepard's Citations / KeyCite.
    Checks internal knowledge graph + external sources + LLM assessment.
    """
    from app.services.legal_features.citation_validator import CitationValidatorService
    service = CitationValidatorService(db)
    return await service.validate_citation(
        citation=request.citation,
        jurisdiction=request.jurisdiction,
        organization_id=org.id,
        user_id=user.id,
    )


@router.post("/citations/validate/batch")
async def validate_citations_batch(
    request: BatchCitationValidateRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Validate multiple citations at once."""
    from app.services.legal_features.citation_validator import CitationValidatorService
    service = CitationValidatorService(db)
    results = await service.validate_multiple(request.citations, request.jurisdiction, org.id, user.id)
    bad_law = [r for r in results if not r.get("is_good_law", True)]
    return {
        "total_checked": len(results),
        "all_good_law": len(bad_law) == 0,
        "bad_law_count": len(bad_law),
        "results": results,
    }


@router.post("/citations/validate/analysis/{analysis_id}")
async def validate_analysis_citations(
    analysis_id: uuid.UUID,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Validate all citations used in a specific analysis result.

    Checks whether any cited authority has been overruled, repealed, or questioned.
    """
    from app.services.legal_features.citation_validator import CitationValidatorService
    service = CitationValidatorService(db)
    return await service.validate_analysis_citations(analysis_id, org.id, user.id)
