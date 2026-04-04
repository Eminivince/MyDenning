"""API endpoints for searching external legal sources and managing source data."""

import uuid
from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.services.audit.service import AuditService
from app.services.legal_sources import get_source_registry
from app.services.legal_sources.base import SourceContentType

router = APIRouter(prefix="/legal-sources", tags=["legal-sources"])


class ExternalSearchRequest(BaseModel):
    query: str
    jurisdiction: str | None = None
    content_type: str | None = None  # case_law, statute, regulation
    court_level: int | None = None
    date_from: date_type | None = None
    date_to: date_type | None = None
    binding_only: bool = False
    page: int = 1
    page_size: int = 20


class CitationLookupRequest(BaseModel):
    citation: str
    jurisdiction: str | None = None


class GoodLawCheckRequest(BaseModel):
    citation: str
    jurisdiction: str | None = None


@router.post("/search")
async def search_external_sources(
    request: ExternalSearchRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Search across all configured external legal sources.

    The system automatically selects the best source adapters based on
    the specified jurisdiction and content type. Results are aggregated
    from all matching sources.
    """
    registry = get_source_registry()

    content_type = None
    if request.content_type:
        try:
            content_type = SourceContentType(request.content_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid content_type. Valid values: {[ct.value for ct in SourceContentType]}",
            )

    results = await registry.search_all(
        query=request.query,
        jurisdiction=request.jurisdiction,
        content_type=content_type,
        date_from=request.date_from,
        date_to=request.date_to,
        page=request.page,
        page_size=request.page_size,
    )

    # Flatten and format results
    all_documents = []
    for result in results:
        for doc in result.documents:
            all_documents.append({
                "title": doc.title,
                "citation": doc.citation,
                "content_type": doc.content_type.value,
                "jurisdiction": doc.jurisdiction,
                "jurisdiction_code": doc.jurisdiction_code,
                "court_name": doc.court_name,
                "court_level": doc.court_level.value if doc.court_level else None,
                "date_decided": doc.date_decided.isoformat() if doc.date_decided else None,
                "date_enacted": doc.date_enacted.isoformat() if doc.date_enacted else None,
                "summary": doc.summary,
                "source_url": doc.source_url,
                "source_adapter": doc.source_adapter,
                "authority_level": doc.authority_level,
                "is_current": doc.is_current,
                "external_id": doc.external_id,
            })

    # Audit the search
    audit = AuditService(db)
    await audit.log(
        organization_id=org.id,
        user_id=user.id,
        action="external_legal_search",
        resource_type="legal_source",
        description=f"Searched external sources: {request.query[:100]}",
        metadata={
            "jurisdiction": request.jurisdiction,
            "content_type": request.content_type,
            "results_count": len(all_documents),
            "sources_queried": [r.source_adapter for r in results],
        },
    )

    return {
        "query": request.query,
        "jurisdiction": request.jurisdiction,
        "results": all_documents,
        "total_results": len(all_documents),
        "sources_queried": [
            {"adapter": r.source_adapter, "results": r.total_count, "time_ms": r.search_time_ms}
            for r in results
        ],
    }


@router.post("/citation-lookup")
async def lookup_citation(
    request: CitationLookupRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Look up a specific legal citation across all sources."""
    registry = get_source_registry()
    doc = await registry.find_by_citation(request.citation, request.jurisdiction)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Citation not found: {request.citation}",
        )

    return {
        "title": doc.title,
        "citation": doc.citation,
        "content_type": doc.content_type.value,
        "jurisdiction": doc.jurisdiction,
        "court_name": doc.court_name,
        "court_level": doc.court_level.value if doc.court_level else None,
        "date_decided": doc.date_decided.isoformat() if doc.date_decided else None,
        "full_text": doc.full_text[:5000] if doc.full_text else None,
        "summary": doc.summary,
        "source_url": doc.source_url,
        "source_adapter": doc.source_adapter,
        "authority_level": doc.authority_level,
        "is_current": doc.is_current,
        "cited_by_count": doc.cited_by_count,
    }


@router.post("/good-law-check")
async def check_good_law(
    request: GoodLawCheckRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Check if a legal citation is still good law (not overruled or repealed).

    This is the equivalent of Shepard's Citations or KeyCite —
    it verifies whether a case has been overruled, a statute repealed, etc.
    """
    registry = get_source_registry()
    result = await registry.check_good_law(request.citation, request.jurisdiction)

    audit = AuditService(db)
    await audit.log(
        organization_id=org.id,
        user_id=user.id,
        action="good_law_check",
        resource_type="legal_source",
        description=f"Good law check: {request.citation}",
        metadata=result,
    )

    return {
        "citation": request.citation,
        "is_good_law": result["is_good_law"],
        "treatment": result["treatment"],
        "overruled_by": result.get("overruled_by"),
        "note": "This is based on available data and should be verified by counsel.",
    }


@router.get("/adapters")
async def list_adapters(user: CurrentUser = None):
    """List all registered legal source adapters and their capabilities."""
    registry = get_source_registry()
    return {
        "adapters": registry.list_adapters(),
        "supported_jurisdictions": registry.list_supported_jurisdictions(),
    }


@router.get("/adapters/health")
async def check_adapter_health(user: CurrentUser = None):
    """Health check all registered legal source adapters."""
    registry = get_source_registry()
    results = await registry.health_check_all()
    return {
        "adapters": {name: {"healthy": healthy} for name, healthy in results.items()},
        "all_healthy": all(results.values()),
    }


@router.post("/import/{external_id}")
async def import_source_to_library(
    external_id: str,
    adapter_name: str = Query(...),
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Import an external legal source into the organization's internal library.

    This fetches the full document from the external source and stores it
    as a LegalSource in the database for use in analysis and research.
    """
    registry = get_source_registry()
    adapter = registry.get_adapter(adapter_name)

    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Adapter not found: {adapter_name}",
        )

    doc = await adapter.get_by_id(external_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found in {adapter_name}: {external_id}",
        )

    # Store as LegalSource in DB
    from app.models.legal_source import AuthorityLevel, LegalSource, SourceType

    source_type_map = {
        SourceContentType.CASE_LAW: SourceType.CASE_LAW,
        SourceContentType.STATUTE: SourceType.STATUTE,
        SourceContentType.REGULATION: SourceType.REGULATION,
        SourceContentType.GUIDANCE: SourceType.GUIDANCE,
        SourceContentType.TREATY: SourceType.TREATY,
        SourceContentType.SECONDARY: SourceType.SECONDARY,
    }
    authority_map = {
        "binding": AuthorityLevel.BINDING,
        "persuasive": AuthorityLevel.PERSUASIVE,
        "secondary": AuthorityLevel.SECONDARY,
    }

    legal_source = LegalSource(
        title=doc.title,
        source_type=source_type_map.get(doc.content_type, SourceType.CASE_LAW),
        authority_level=authority_map.get(doc.authority_level, AuthorityLevel.BINDING),
        citation=doc.citation,
        external_id=f"{adapter_name}:{external_id}",
        jurisdiction=doc.jurisdiction_code,
        court=doc.court_name,
        court_level=doc.court_level.value if doc.court_level else None,
        issuing_body=doc.issuing_body,
        date_decided=doc.date_decided,
        date_enacted=doc.date_enacted,
        date_effective=doc.date_effective,
        full_text=doc.full_text,
        summary=doc.summary,
        topics=doc.topics,
        keywords=doc.keywords,
        is_current=doc.is_current,
        superseded_by=doc.superseded_by,
    )
    db.add(legal_source)
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        organization_id=org.id,
        user_id=user.id,
        action="import_legal_source",
        resource_type="legal_source",
        resource_id=str(legal_source.id),
        description=f"Imported {doc.citation} from {adapter_name}",
    )

    return {
        "id": str(legal_source.id),
        "title": legal_source.title,
        "citation": legal_source.citation,
        "source": adapter_name,
        "imported": True,
    }


# ===================== STARTER PACKS =====================

@router.get("/starter-packs")
async def list_starter_packs(user: CurrentUser = None):
    """List all available jurisdiction starter packs."""
    from app.services.starter_packs.service import StarterPackService
    return StarterPackService.list_packs()


@router.post("/starter-packs/{pack_id}/import")
async def import_starter_pack(
    pack_id: str,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Import a jurisdiction starter pack into the organization's legal library.

    Searches external legal databases for each authority in the pack and
    imports the best match. Skips authorities that already exist.
    This may take 30-60 seconds depending on the pack size.
    """
    from app.services.starter_packs.service import StarterPackService

    service = StarterPackService(db)
    result = await service.import_pack(pack_id, org.id, user.id)

    audit = AuditService(db)
    await audit.log(
        organization_id=org.id,
        user_id=user.id,
        action="import_starter_pack",
        resource_type="legal_source",
        description=f"Imported starter pack: {result['pack_name']} ({result['imported_count']} sources)",
        metadata={
            "pack_id": pack_id,
            "imported": result["imported_count"],
            "skipped": result["skipped_count"],
            "failed": result["failed_count"],
        },
    )

    return result
