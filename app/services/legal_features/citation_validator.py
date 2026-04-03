"""Citation validation service — checks if citations are still good law.

This is MyDenning's equivalent of Shepard's Citations / KeyCite.
It verifies whether:
- A case has been overruled, reversed, or distinguished
- A statute has been repealed or amended
- A regulation is still in force
- The citation is being used correctly

Uses external legal source adapters + internal knowledge graph.
"""

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.legal_features import CitationValidation
from app.models.legal_source import CitationRelationship, CitationRelationType, LegalSource
from app.services.legal_sources import get_source_registry
from app.services.reasoning.llm_client import LLMClient

logger = structlog.get_logger(__name__)

# Treatment classifications
POSITIVE_TREATMENTS = {"followed", "applied", "affirmed", "approved", "cited"}
NEGATIVE_TREATMENTS = {"overruled", "reversed", "disapproved", "doubted", "criticized"}
CAUTIONARY_TREATMENTS = {"distinguished", "limited", "questioned", "explained"}


class CitationValidatorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()
        self.settings = get_settings()

    async def validate_citation(
        self,
        citation: str,
        jurisdiction: str | None = None,
        organization_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        analysis_id: uuid.UUID | None = None,
        force_refresh: bool = False,
    ) -> dict:
        """Validate a single citation. Returns treatment and good-law status.

        Checks (in order):
        1. Cache — return if valid cached result exists
        2. Internal knowledge graph — check CitationRelationship for overruling/repealing edges
        3. External sources — query CourtListener, Laws.Africa etc. for treatment data
        4. LLM analysis — if source data is ambiguous, use LLM to assess
        """

        # Step 1: Check cache
        if not force_refresh:
            cached = await self._get_cached(citation, jurisdiction)
            if cached:
                return self._format_validation(cached)

        # Step 2: Check internal knowledge graph
        internal_result = await self._check_internal_graph(citation)

        # Step 3: Check external sources
        external_result = await self._check_external_sources(citation, jurisdiction)

        # Step 4: Merge results and determine treatment
        merged = self._merge_results(internal_result, external_result)

        # Step 5: If ambiguous, use LLM
        if merged["treatment"] == "unknown" and (internal_result or external_result):
            merged = await self._llm_assess_treatment(citation, jurisdiction, internal_result, external_result)

        # Step 6: Store validation result
        validation = CitationValidation(
            organization_id=organization_id,
            checked_by_id=user_id,
            citation=citation,
            jurisdiction=jurisdiction,
            is_good_law=merged["is_good_law"],
            treatment=merged["treatment"],
            negative_treatment=merged.get("negative_treatment"),
            overruled_by=merged.get("overruled_by"),
            distinguished_by=merged.get("distinguished_by"),
            followed_by_count=merged.get("followed_by_count", 0),
            cited_by_count=merged.get("cited_by_count", 0),
            source_adapter=merged.get("source_adapter"),
            confidence=merged.get("confidence", 0.5),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),  # cache for 30 days
            analysis_id=analysis_id,
            raw_result=merged,
        )
        self.db.add(validation)
        await self.db.flush()

        logger.info(
            "citation_validated",
            citation=citation,
            treatment=merged["treatment"],
            is_good_law=merged["is_good_law"],
        )

        return self._format_validation(validation)

    async def validate_multiple(
        self,
        citations: list[str],
        jurisdiction: str | None = None,
        organization_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """Validate multiple citations. Returns results for each."""
        results = []
        for citation in citations:
            try:
                result = await self.validate_citation(
                    citation, jurisdiction, organization_id, user_id,
                )
                results.append(result)
            except Exception as e:
                results.append({
                    "citation": citation,
                    "is_good_law": True,
                    "treatment": "unknown",
                    "confidence": 0.0,
                    "error": str(e),
                })
        return results

    async def validate_analysis_citations(
        self,
        analysis_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        """Validate all citations used in an analysis result."""
        from app.models.analysis import AnalysisResult
        analysis = await self.db.get(AnalysisResult, analysis_id)
        if not analysis:
            raise ValueError("Analysis not found")

        citations_data = analysis.citations_used or []
        citation_texts = []
        for c in citations_data:
            if isinstance(c, dict):
                text = c.get("citation_text") or c.get("text") or c.get("citation", "")
                if text:
                    citation_texts.append(text)
            elif isinstance(c, str):
                citation_texts.append(c)

        if not citation_texts:
            return {"analysis_id": str(analysis_id), "citations_checked": 0, "results": []}

        results = await self.validate_multiple(citation_texts, None, organization_id, user_id)

        bad_law = [r for r in results if not r.get("is_good_law", True)]
        cautionary = [r for r in results if r.get("treatment") in CAUTIONARY_TREATMENTS]

        return {
            "analysis_id": str(analysis_id),
            "citations_checked": len(results),
            "all_good_law": len(bad_law) == 0,
            "bad_law_count": len(bad_law),
            "cautionary_count": len(cautionary),
            "results": results,
            "bad_law_citations": bad_law,
            "cautionary_citations": cautionary,
        }

    async def _get_cached(self, citation: str, jurisdiction: str | None) -> CitationValidation | None:
        conditions = [
            CitationValidation.citation == citation,
            CitationValidation.expires_at > datetime.now(timezone.utc),
        ]
        if jurisdiction:
            conditions.append(CitationValidation.jurisdiction == jurisdiction)

        result = await self.db.execute(
            select(CitationValidation)
            .where(and_(*conditions))
            .order_by(CitationValidation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _check_internal_graph(self, citation: str) -> dict | None:
        """Check our internal citation graph for overruling/repealing edges."""
        # Find the source in our database
        result = await self.db.execute(
            select(LegalSource).where(LegalSource.citation == citation).limit(1)
        )
        source = result.scalar_one_or_none()
        if not source:
            return None

        # Check for negative treatments
        neg_result = await self.db.execute(
            select(CitationRelationship).where(
                and_(
                    CitationRelationship.target_id == source.id,
                    CitationRelationship.relationship_type.in_([
                        CitationRelationType.OVERRULED_BY,
                        CitationRelationType.OVERRULES,
                    ]),
                )
            )
        )
        negative_edges = neg_result.scalars().all()

        if negative_edges:
            # Load the overruling source
            overruling_ids = [e.source_id for e in negative_edges]
            overruling_result = await self.db.execute(
                select(LegalSource).where(LegalSource.id.in_(overruling_ids))
            )
            overruling_sources = overruling_result.scalars().all()

            return {
                "is_good_law": False,
                "treatment": "overruled",
                "overruled_by": overruling_sources[0].citation if overruling_sources else None,
                "source": "internal_graph",
                "confidence": 0.9,
            }

        # Count positive citations
        pos_result = await self.db.execute(
            select(CitationRelationship).where(
                and_(
                    CitationRelationship.target_id == source.id,
                    CitationRelationship.relationship_type.in_([
                        CitationRelationType.FOLLOWS,
                        CitationRelationType.CITES,
                        CitationRelationType.APPLIES,
                    ]),
                )
            )
        )
        positive_count = len(pos_result.scalars().all())

        return {
            "is_good_law": source.is_current,
            "treatment": "positive" if positive_count > 0 else "unknown",
            "followed_by_count": positive_count,
            "source": "internal_graph",
            "confidence": 0.7,
        }

    async def _check_external_sources(self, citation: str, jurisdiction: str | None) -> dict | None:
        """Check external legal source adapters for treatment data."""
        registry = get_source_registry()
        result = await registry.check_good_law(citation, jurisdiction)

        if result.get("treatment") == "unknown":
            return None

        return {
            "is_good_law": result["is_good_law"],
            "treatment": result["treatment"],
            "overruled_by": result.get("overruled_by"),
            "source_adapter": "external",
            "confidence": 0.6,
        }

    def _merge_results(self, internal: dict | None, external: dict | None) -> dict:
        """Merge internal and external validation results."""
        if not internal and not external:
            return {"is_good_law": True, "treatment": "unknown", "confidence": 0.3}

        if internal and not external:
            return internal

        if external and not internal:
            return external

        # Both exist — prefer the one that found negative treatment
        if not internal["is_good_law"]:
            internal["confidence"] = min(internal["confidence"] + 0.1, 1.0)
            return internal
        if not external["is_good_law"]:
            external["confidence"] = min(external["confidence"] + 0.1, 1.0)
            return external

        # Both positive — merge counts
        merged = internal.copy()
        merged["confidence"] = min(internal["confidence"] + external.get("confidence", 0), 1.0)
        merged["cited_by_count"] = max(
            internal.get("cited_by_count", 0), external.get("cited_by_count", 0)
        )
        return merged

    async def _llm_assess_treatment(
        self,
        citation: str,
        jurisdiction: str | None,
        internal: dict | None,
        external: dict | None,
    ) -> dict:
        """Use LLM to assess citation treatment when data is ambiguous."""
        prompt = f"""Assess whether this legal citation is still good law:

Citation: {citation}
Jurisdiction: {jurisdiction or 'Unknown'}

Internal graph data: {internal or 'No data'}
External source data: {external or 'No data'}

Determine:
1. is_good_law: true/false
2. treatment: one of [positive, negative, cautionary, overruled, reversed, distinguished, followed, unknown]
3. confidence: 0.0-1.0
4. reasoning: brief explanation

Return as JSON."""

        response = await self.llm.structured_analysis(
            "You are a legal citation analyst.", prompt,
            {"is_good_law": "bool", "treatment": "string", "confidence": "float", "reasoning": "string"},
        )

        return {
            "is_good_law": response.get("is_good_law", True),
            "treatment": response.get("treatment", "unknown"),
            "confidence": response.get("confidence", 0.5),
            "negative_treatment": response.get("reasoning") if not response.get("is_good_law", True) else None,
            "source_adapter": "llm_assessment",
        }

    def _format_validation(self, v: CitationValidation | dict) -> dict:
        if isinstance(v, CitationValidation):
            return {
                "citation": v.citation,
                "is_good_law": v.is_good_law,
                "treatment": v.treatment,
                "negative_treatment": v.negative_treatment,
                "overruled_by": v.overruled_by,
                "distinguished_by": v.distinguished_by,
                "followed_by_count": v.followed_by_count,
                "cited_by_count": v.cited_by_count,
                "confidence": v.confidence,
                "source": v.source_adapter,
                "checked_at": v.created_at.isoformat() if v.created_at else None,
                "expires_at": v.expires_at.isoformat() if v.expires_at else None,
            }
        return v
