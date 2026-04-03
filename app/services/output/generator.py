import time
import uuid
from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.analysis import AnalysisResult, AnalysisType
from app.services.reasoning.llm_client import LLMClient
from app.services.reasoning.prompts import PromptBuilder
from app.services.retrieval.hybrid import HybridRetrievalService, RetrievalFilters

logger = structlog.get_logger(__name__)


class OutputGenerator:
    """Generates structured legal work products: memos, checklists, risk matrices, drafts."""

    TEMPLATES = {
        "memo": """LEGAL MEMORANDUM

TO: {to}
FROM: {from_}
DATE: {date}
RE: {subject}

I. QUESTION PRESENTED
{question}

II. SHORT ANSWER
{short_answer}

III. STATEMENT OF FACTS
{facts}

IV. DISCUSSION
{discussion}

V. CONCLUSION
{conclusion}

VI. RECOMMENDATIONS
{recommendations}
""",
        "issue_checklist": """ISSUE CHECKLIST

Matter: {matter}
Date: {date}
Prepared by: AI Legal Assistant

{issues}
""",
        "risk_matrix": """RISK ASSESSMENT MATRIX

Document: {document}
Date: {date}

| # | Risk Area | Likelihood | Impact | Risk Level | Mitigation |
|---|-----------|-----------|--------|-----------|------------|
{rows}

SUMMARY: {summary}
""",
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()
        self.prompts = PromptBuilder()
        self.retrieval = HybridRetrievalService(db)
        self.settings = get_settings()

    async def generate_draft(
        self,
        draft_type: str,
        instructions: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID] | None = None,
        matter_id: uuid.UUID | None = None,
        jurisdiction: str | None = None,
        tone: str | None = None,
    ) -> dict:
        start_time = time.time()

        # Retrieve relevant context
        filters = RetrievalFilters(
            organization_id=organization_id,
            document_ids=document_ids,
            matter_id=matter_id,
            jurisdiction=jurisdiction,
        )
        context_chunks = await self.retrieval.search(instructions, filters, top_k=8)

        system_prompt = self.prompts.LEGAL_SYSTEM_BASE + f"\n\nYou are drafting a {draft_type}."
        user_prompt = self.prompts.build_draft_prompt(
            draft_type=draft_type,
            instructions=instructions,
            context_chunks=context_chunks,
            jurisdiction=jurisdiction,
            tone=tone,
        )

        llm_response = await self.llm.structured_analysis(
            system_prompt,
            user_prompt,
            output_schema={
                "content": "string",
                "citations": [{"text": "string", "source": "string"}],
                "assumptions": ["string"],
                "risk_flags": ["string"],
                "confidence_score": "float",
            },
        )

        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            document_id=document_ids[0] if document_ids and len(document_ids) == 1 else None,
            matter_id=matter_id,
            analysis_type=AnalysisType.MEMO_DRAFT,
            query=instructions,
            result=llm_response,
            summary=f"Generated {draft_type} draft",
            model_used=self.settings.anthropic_model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        return {
            "id": analysis.id,
            "draft_type": draft_type,
            "content": llm_response.get("content", ""),
            "citations": [
                {
                    "citation_text": c.get("text", ""),
                    "source_title": c.get("source"),
                }
                for c in llm_response.get("citations", [])
            ],
            "assumptions": llm_response.get("assumptions", []),
            "risk_flags": llm_response.get("risk_flags", []),
            "confidence_score": llm_response.get("confidence_score", 0.7),
            "created_at": analysis.created_at,
        }

    async def generate_risk_matrix(
        self,
        document_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        start_time = time.time()

        from app.models.document import Document
        document = await self.db.get(Document, document_id)
        if not document or not document.raw_text:
            raise ValueError("Document not found or not processed")

        system_prompt = self.prompts.LEGAL_SYSTEM_BASE + "\n\nGenerate a comprehensive risk assessment matrix."
        user_prompt = f"""Analyze this document and create a risk matrix:

```
{document.raw_text[:12000]}
```

For each risk, provide:
1. Risk area (the clause or topic)
2. Likelihood (1-5)
3. Impact (1-5)
4. Risk level (critical/high/medium/low)
5. Mitigation recommendation

Return as JSON with: risks (array), summary, overall_risk_score"""

        llm_response = await self.llm.structured_analysis(
            system_prompt,
            user_prompt,
            output_schema={"risks": [], "summary": "string", "overall_risk_score": "float"},
        )

        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            document_id=document_id,
            analysis_type=AnalysisType.RISK_ASSESSMENT,
            result=llm_response,
            summary=llm_response.get("summary", ""),
            model_used=self.settings.anthropic_model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        return {
            "id": analysis.id,
            "document_id": document_id,
            "risks": llm_response.get("risks", []),
            "summary": llm_response.get("summary", ""),
            "overall_risk_score": llm_response.get("overall_risk_score", 0.0),
            "created_at": analysis.created_at,
        }

    async def generate_issue_checklist(
        self,
        matter_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID] | None = None,
    ) -> dict:
        start_time = time.time()

        from app.models.matter import Matter
        matter = await self.db.get(Matter, matter_id)
        if not matter:
            raise ValueError("Matter not found")

        filters = RetrievalFilters(
            organization_id=organization_id,
            matter_id=matter_id,
            document_ids=document_ids,
        )
        context_chunks = await self.retrieval.search(
            f"{matter.title} {matter.description or ''}", filters, top_k=15
        )

        system_prompt = self.prompts.LEGAL_SYSTEM_BASE + "\n\nGenerate a comprehensive issue checklist."
        user_prompt = f"""Matter: {matter.title}
Type: {matter.matter_type.value}
Description: {matter.description or 'N/A'}
Jurisdiction: {matter.jurisdiction or 'N/A'}
Counterparty: {matter.counterparty or 'N/A'}

Relevant documents:
"""
        for chunk in context_chunks[:10]:
            user_prompt += f"\n[{chunk.document_title}]\n{chunk.content[:400]}\n"

        user_prompt += """
Generate a comprehensive issue checklist with:
1. Key legal issues
2. Due diligence items
3. Risk areas
4. Action items
5. Open questions
6. Priority for each item

Return as JSON with: issues (array of {issue, category, priority, status, notes, assigned_to}), summary"""

        llm_response = await self.llm.structured_analysis(
            system_prompt,
            user_prompt,
            output_schema={"issues": [], "summary": "string"},
        )

        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            matter_id=matter_id,
            analysis_type=AnalysisType.RISK_ASSESSMENT,
            result=llm_response,
            summary=llm_response.get("summary", ""),
            model_used=self.settings.anthropic_model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        return {
            "id": analysis.id,
            "matter_id": matter_id,
            "issues": llm_response.get("issues", []),
            "summary": llm_response.get("summary", ""),
            "created_at": analysis.created_at,
        }
