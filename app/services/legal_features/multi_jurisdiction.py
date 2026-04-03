"""Multi-jurisdiction comparison analysis.

Answers questions like:
- "How does this indemnity clause work under Nigerian law vs English law?"
- "Compare the termination rights regime in these 3 jurisdictions"
- "What are the data protection requirements across US, EU, and Nigeria?"
"""

import time
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.analysis import AnalysisResult, AnalysisType, RiskLevel
from app.services.legal_sources import get_source_registry
from app.services.legal_sources.base import SourceContentType
from app.services.reasoning.llm_client import LLMClient
from app.services.retrieval.hybrid import HybridRetrievalService, RetrievalFilters

logger = structlog.get_logger(__name__)


class MultiJurisdictionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()
        self.retrieval = HybridRetrievalService(db)
        self.settings = get_settings()

    async def compare_jurisdictions(
        self,
        topic: str,
        jurisdictions: list[str],
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID] | None = None,
        content_type: str | None = None,
    ) -> dict:
        start_time = time.time()

        if len(jurisdictions) < 2:
            raise ValueError("At least 2 jurisdictions required for comparison")
        if len(jurisdictions) > 6:
            raise ValueError("Maximum 6 jurisdictions per comparison")

        # Step 1: Gather sources from each jurisdiction
        jurisdiction_data = {}
        registry = get_source_registry()

        for jurisdiction in jurisdictions:
            # Search external legal sources
            external_results = await registry.search_all(
                query=topic,
                jurisdiction=jurisdiction,
                content_type=SourceContentType(content_type) if content_type else None,
                page_size=5,
            )

            external_docs = []
            for result in external_results:
                for doc in result.documents[:3]:
                    external_docs.append({
                        "title": doc.title,
                        "citation": doc.citation,
                        "type": doc.content_type.value,
                        "summary": doc.summary[:300] if doc.summary else "",
                        "full_text": doc.full_text[:2000] if doc.full_text else "",
                        "source": doc.source_adapter,
                    })

            # Also search internal documents scoped to this jurisdiction
            filters = RetrievalFilters(
                organization_id=organization_id,
                document_ids=document_ids,
                jurisdiction=jurisdiction,
            )
            internal_chunks = await self.retrieval.search(topic, filters, top_k=5)
            internal_docs = [
                {
                    "title": c.document_title,
                    "content": c.content[:500],
                    "clause_type": c.clause_type,
                }
                for c in internal_chunks
            ]

            jurisdiction_data[jurisdiction] = {
                "external_sources": external_docs,
                "internal_documents": internal_docs,
            }

        # Step 2: LLM comparison analysis
        system_prompt = """You are a comparative legal analyst. Compare legal positions across multiple jurisdictions.

Structure your response as:
1. Overview of the legal topic
2. Per-jurisdiction analysis (the rule, key authorities, practical implications)
3. Comparison matrix (which jurisdiction is more protective/restrictive/favorable)
4. Key differences and their practical impact
5. Risk flags for cross-border operations
6. Recommendations

Be precise about which jurisdiction's law you are discussing. Cite specific authorities."""

        user_prompt = f"## Topic: {topic}\n\n"
        for jurisdiction, data in jurisdiction_data.items():
            user_prompt += f"## {jurisdiction}\n"
            if data["external_sources"]:
                user_prompt += "### Legal Sources:\n"
                for src in data["external_sources"]:
                    user_prompt += f"- [{src['citation']}] ({src['type']}, {src['source']})\n"
                    if src["summary"]:
                        user_prompt += f"  {src['summary'][:200]}\n"
                    if src["full_text"]:
                        user_prompt += f"  ```{src['full_text'][:500]}```\n"
            if data["internal_documents"]:
                user_prompt += "### Internal Documents:\n"
                for doc in data["internal_documents"]:
                    user_prompt += f"- [{doc['title']}] {doc['content'][:200]}\n"
            user_prompt += "\n"

        user_prompt += """
Return as JSON with:
- summary: overall comparison summary
- jurisdictions: array of {jurisdiction, legal_position, key_authorities, risk_level, practical_implications}
- comparison_matrix: array of {aspect, ...one field per jurisdiction with the position}
- key_differences: array of {difference, impact, recommendation}
- risk_flags: array of strings
- recommendations: array of strings
- confidence_score: 0.0-1.0"""

        llm_response = await self.llm.structured_analysis(
            system_prompt, user_prompt,
            {"summary": "string", "jurisdictions": [], "comparison_matrix": [], "key_differences": []},
        )

        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            analysis_type=AnalysisType.RESEARCH,
            query=f"Multi-jurisdiction comparison: {topic} across {', '.join(jurisdictions)}",
            result=llm_response,
            summary=llm_response.get("summary", ""),
            confidence_score=llm_response.get("confidence_score", 0.7),
            model_used=self.settings.anthropic_model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        return {
            "id": analysis.id,
            "topic": topic,
            "jurisdictions_compared": jurisdictions,
            "summary": llm_response.get("summary", ""),
            "jurisdictions": llm_response.get("jurisdictions", []),
            "comparison_matrix": llm_response.get("comparison_matrix", []),
            "key_differences": llm_response.get("key_differences", []),
            "risk_flags": llm_response.get("risk_flags", []),
            "recommendations": llm_response.get("recommendations", []),
            "confidence_score": llm_response.get("confidence_score", 0.7),
            "sources_by_jurisdiction": {
                j: len(d["external_sources"]) + len(d["internal_documents"])
                for j, d in jurisdiction_data.items()
            },
            "created_at": analysis.created_at,
        }
