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
from app.models.legal_features import ScheduledDigest
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


class NegotiationRequest(BaseModel):
    document_id: uuid.UUID
    playbook_id: uuid.UUID
    counterparty_name: str | None = None
    matter_id: uuid.UUID | None = None
    priorities: list[str] | None = None  # e.g. ["limit liability", "retain IP rights", "short term"]
    deal_context: str | None = None  # e.g. "Key vendor, we need this deal but can't accept uncapped liability"


class WebhookCreateRequest(BaseModel):
    name: str
    url: str
    events: list[str]  # document.processed, deadline.approaching, regulatory.alert, etc.
    secret: str | None = None


class DigestCreateRequest(BaseModel):
    name: str
    schedule: str  # daily_9am, weekly_monday, weekly_friday
    webhook_id: str | None = None
    include_deadlines: bool = True
    include_regulatory_alerts: bool = True
    include_pending_reviews: bool = True
    include_matter_updates: bool = True
    include_feedback_stats: bool = False


class FeedbackRequest(BaseModel):
    resource_type: str  # analysis, draft, review, redline, conversation
    resource_id: str
    rating: str  # positive, negative
    comment: str | None = None
    correction: str | None = None
    correction_type: str | None = None  # wrong_answer, wrong_citation, wrong_risk, missing_info, other
    query: str | None = None
    jurisdiction: str | None = None
    clause_type: str | None = None
    analysis_id: str | None = None
    conversation_message_id: str | None = None


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


# ===================== NEGOTIATION =====================

@router.post("/negotiation/strategy")
async def generate_negotiation_strategy(
    request: NegotiationRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Generate a smart negotiation strategy for a counterparty's contract.

    Analyzes the counterparty's positions against your playbook, looks up
    prior dealings with this counterparty, predicts pushback areas, and
    produces a complete strategy memo with exact counter-language and
    ordered fallback positions for each clause.
    """
    from app.services.legal_features.negotiation import NegotiationAssistant
    service = NegotiationAssistant(db)
    result = await service.generate_strategy(
        document_id=request.document_id,
        playbook_id=request.playbook_id,
        organization_id=org.id,
        user_id=user.id,
        counterparty_name=request.counterparty_name,
        matter_id=request.matter_id,
        priorities=request.priorities,
        deal_context=request.deal_context,
    )

    audit = AuditService(db)
    await audit.log(
        organization_id=org.id,
        user_id=user.id,
        action="negotiation_strategy",
        resource_type="analysis",
        resource_id=str(result["id"]),
        description=f"Negotiation strategy: {request.counterparty_name or 'counterparty'}",
    )

    return result


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


# ===================== FEEDBACK =====================

@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    request: FeedbackRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Submit feedback (thumbs up/down) on any AI-generated output.

    Optionally include a correction for negative feedback — this helps
    the system learn your organization's preferences over time.
    """
    from app.services.legal_features.feedback import FeedbackService
    from app.models.legal_features import FeedbackRating

    service = FeedbackService(db)
    fb = await service.submit(
        organization_id=org.id,
        user_id=user.id,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        rating=FeedbackRating(request.rating),
        comment=request.comment,
        correction=request.correction,
        correction_type=request.correction_type,
        query=request.query,
        jurisdiction=request.jurisdiction,
        clause_type=request.clause_type,
        analysis_id=uuid.UUID(request.analysis_id) if request.analysis_id else None,
        conversation_message_id=uuid.UUID(request.conversation_message_id) if request.conversation_message_id else None,
    )

    return {
        "id": str(fb.id),
        "rating": fb.rating.value,
        "resource_type": fb.resource_type,
        "resource_id": fb.resource_id,
    }


@router.get("/feedback/stats")
async def get_feedback_stats(
    resource_type: str | None = None,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Get aggregate feedback statistics for the organization."""
    from app.services.legal_features.feedback import FeedbackService
    service = FeedbackService(db)
    return await service.get_stats(org.id, resource_type)


# ===================== WEBHOOKS =====================

@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
async def register_webhook(
    request: WebhookCreateRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Register a webhook URL to receive event notifications.

    Events: document.processed, document.failed, deadline.approaching,
    deadline.overdue, regulatory.alert, analysis.completed, conflict.detected, digest.scheduled
    """
    from app.services.legal_features.webhooks import WebhookService
    service = WebhookService(db)
    webhook = await service.register(org.id, user.id, request.name, request.url, request.events, request.secret)
    return {
        "id": str(webhook.id), "name": webhook.name, "url": webhook.url,
        "events": webhook.events, "is_active": webhook.is_active,
    }


@router.get("/webhooks")
async def list_webhooks(user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    from app.services.legal_features.webhooks import WebhookService
    service = WebhookService(db)
    webhooks = await service.list_webhooks(org.id)
    return [
        {
            "id": str(w.id), "name": w.name, "url": w.url, "events": w.events,
            "is_active": w.is_active, "consecutive_failures": w.consecutive_failures,
            "last_triggered_at": w.last_triggered_at.isoformat() if w.last_triggered_at else None,
            "last_status_code": w.last_status_code,
        }
        for w in webhooks
    ]


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(webhook_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    from app.services.legal_features.webhooks import WebhookService
    service = WebhookService(db)
    await service.delete(webhook_id)


@router.post("/webhooks/{webhook_id}/reset")
async def reset_webhook(webhook_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    """Re-enable a webhook that was disabled after consecutive failures."""
    from app.services.legal_features.webhooks import WebhookService
    service = WebhookService(db)
    webhook = await service.reset_webhook(webhook_id)
    return {"id": str(webhook.id), "is_active": webhook.is_active, "consecutive_failures": webhook.consecutive_failures}


@router.get("/webhooks/{webhook_id}/deliveries")
async def get_webhook_deliveries(webhook_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    from app.services.legal_features.webhooks import WebhookService
    service = WebhookService(db)
    deliveries = await service.get_deliveries(webhook_id)
    return [
        {
            "id": str(d.id), "event_type": d.event_type, "success": d.success,
            "status_code": d.status_code, "duration_ms": d.duration_ms,
            "created_at": d.created_at.isoformat(),
        }
        for d in deliveries
    ]


# ===================== SCHEDULED DIGESTS =====================

@router.post("/digests", status_code=status.HTTP_201_CREATED)
async def create_digest(
    request: DigestCreateRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Create a scheduled digest — periodic summaries of deadlines, alerts, and activity.

    Schedules: daily_9am, weekly_monday, weekly_friday.
    Delivers via webhook if webhook_id is provided.
    """
    from app.services.legal_features.digests import DigestService
    service = DigestService(db)
    digest = await service.create_digest(
        organization_id=org.id, user_id=user.id,
        name=request.name, schedule=request.schedule,
        webhook_id=uuid.UUID(request.webhook_id) if request.webhook_id else None,
        include_deadlines=request.include_deadlines,
        include_regulatory_alerts=request.include_regulatory_alerts,
        include_pending_reviews=request.include_pending_reviews,
        include_matter_updates=request.include_matter_updates,
        include_feedback_stats=request.include_feedback_stats,
    )
    return {
        "id": str(digest.id), "name": digest.name, "schedule": digest.schedule,
        "is_active": digest.is_active,
    }


@router.get("/digests")
async def list_digests(user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    from app.services.legal_features.digests import DigestService
    service = DigestService(db)
    digests = await service.list_digests(org.id)
    return [
        {
            "id": str(d.id), "name": d.name, "schedule": d.schedule,
            "is_active": d.is_active,
            "last_sent_at": d.last_sent_at.isoformat() if d.last_sent_at else None,
        }
        for d in digests
    ]


@router.post("/digests/{digest_id}/trigger")
async def trigger_digest(digest_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    """Manually trigger a scheduled digest (for testing or on-demand)."""
    from app.services.legal_features.digests import DigestService
    service = DigestService(db)
    payload = await service.generate_digest(digest_id)

    # Deliver via webhook if configured
    digest = await db.get(ScheduledDigest, digest_id)
    if digest and digest.webhook_id:
        from app.services.legal_features.webhooks import WebhookService
        wh_service = WebhookService(db)
        await wh_service.fire_event(org.id, "digest.scheduled", payload)

    return payload
