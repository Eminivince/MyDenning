import time
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.analysis import AnalysisResult, AnalysisType, RiskLevel
from app.models.conversation import Conversation, ConversationMessage, MessageRole
from app.services.reasoning.llm_client import LLMClient
from app.services.reasoning.prompts import PromptBuilder
from app.services.retrieval.hybrid import HybridRetrievalService, RetrievalFilters, RetrievedChunk
from app.services.memory.service import MemoryService

logger = structlog.get_logger(__name__)


class LegalReasoningOrchestrator:
    """Orchestrates the full legal reasoning pipeline:
    1. Classify user task
    2. Identify jurisdiction and document type
    3. Retrieve authority
    4. Extract relevant passages
    5. Run structured legal analysis (IRAC)
    6. Produce answer with citations and confidence band
    7. Flag escalation when risk is high
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.retrieval = HybridRetrievalService(db)
        self.llm = LLMClient()
        self.prompts = PromptBuilder()
        self.memory = MemoryService(db)
        self.settings = get_settings()

    async def answer_question(
        self,
        question: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        document_ids: list[uuid.UUID] | None = None,
        matter_id: uuid.UUID | None = None,
        jurisdiction: str | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> dict:
        start_time = time.time()

        # Step 1: Classify the task
        task_classification = await self._classify_task(question)

        # Step 2: Gather context (org preferences, matter memory)
        context = await self._gather_context(organization_id, matter_id, jurisdiction)

        # Step 3: Retrieve relevant chunks
        filters = RetrievalFilters(
            organization_id=organization_id,
            document_ids=document_ids,
            matter_id=matter_id,
            jurisdiction=jurisdiction or context.get("jurisdiction"),
        )
        retrieved_chunks = await self.retrieval.search(question, filters, top_k=self.settings.rerank_top_k)

        # Step 4: Build prompt with retrieved context
        system_prompt = self.prompts.build_analysis_system_prompt(context)
        user_prompt = self.prompts.build_question_prompt(
            question=question,
            chunks=retrieved_chunks,
            task_type=task_classification,
            jurisdiction=jurisdiction or context.get("jurisdiction"),
            conversation_history=await self._get_conversation_history(conversation_id) if conversation_id else None,
        )

        # Step 5: Run LLM analysis
        llm_response = await self.llm.analyze(system_prompt, user_prompt)

        # Step 6: Parse structured response
        parsed = self._parse_analysis_response(llm_response)

        # Step 7: Store analysis result
        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            document_id=document_ids[0] if document_ids and len(document_ids) == 1 else None,
            matter_id=matter_id,
            analysis_type=AnalysisType.QUESTION_ANSWER,
            query=question,
            result=parsed,
            summary=parsed.get("answer", ""),
            risk_level=self._map_risk_level(parsed.get("overall_risk", "low")),
            confidence_score=parsed.get("confidence_score", 0.0),
            citations_used=[
                {"text": c.content[:200], "source": c.document_title, "chunk_id": str(c.chunk_id)}
                for c in retrieved_chunks[:5]
            ],
            sources_consulted=[str(c.document_id) for c in retrieved_chunks],
            model_used=self.settings.anthropic_model,
            token_count_input=llm_response.get("input_tokens"),
            token_count_output=llm_response.get("output_tokens"),
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        # Step 8: Update conversation if applicable
        if conversation_id:
            await self._update_conversation(
                conversation_id, question, parsed.get("answer", ""), analysis.id, llm_response
            )

        # Auto-extract memories from analysis
        if matter_id and parsed.get("key_findings"):
            for finding in parsed["key_findings"][:3]:
                await self.memory.add_matter_memory(
                    matter_id=matter_id,
                    user_id=user_id,
                    memory_type="fact",
                    content=finding,
                    source="extracted",
                    importance=6,
                )

        return {
            "id": analysis.id,
            "question": question,
            "answer": parsed.get("answer", ""),
            "issues": parsed.get("issues", []),
            "citations": self._format_citations(retrieved_chunks),
            "confidence_score": parsed.get("confidence_score", 0.0),
            "risk_flags": parsed.get("risk_flags", []),
            "follow_up_questions": parsed.get("follow_up_questions", []),
            "model_used": self.settings.anthropic_model,
            "created_at": analysis.created_at,
        }

    async def research(
        self,
        query: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        jurisdiction: str | None = None,
        source_types: list[str] | None = None,
        court_level: int | None = None,
        binding_only: bool = False,
        max_results: int = 20,
    ) -> dict:
        start_time = time.time()

        # Search legal sources directly
        source_results = await self.retrieval.search_legal_sources(
            query=query,
            jurisdiction=jurisdiction,
            source_types=source_types,
            court_level=court_level,
            binding_only=binding_only,
            limit=max_results,
        )

        # Also search document chunks for internal documents
        filters = RetrievalFilters(
            organization_id=organization_id,
            jurisdiction=jurisdiction,
        )
        chunk_results = await self.retrieval.search(query, filters, top_k=max_results)

        # Build research summary using LLM
        system_prompt = self.prompts.build_research_system_prompt()
        user_prompt = self.prompts.build_research_prompt(
            query=query,
            legal_sources=source_results,
            document_chunks=chunk_results,
            jurisdiction=jurisdiction,
        )
        llm_response = await self.llm.analyze(system_prompt, user_prompt)
        parsed = self._parse_analysis_response(llm_response)

        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            analysis_type=AnalysisType.RESEARCH,
            query=query,
            result=parsed,
            summary=parsed.get("summary", ""),
            confidence_score=parsed.get("confidence_score", 0.0),
            model_used=self.settings.anthropic_model,
            token_count_input=llm_response.get("input_tokens"),
            token_count_output=llm_response.get("output_tokens"),
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        return {
            "id": analysis.id,
            "query": query,
            "results": source_results + [
                {
                    "title": c.document_title,
                    "content": c.content[:500],
                    "source_type": "internal_document",
                    "jurisdiction": c.jurisdiction,
                    "relevance_score": c.score,
                }
                for c in chunk_results[:10]
            ],
            "summary": parsed.get("summary", ""),
            "jurisdiction_notes": parsed.get("jurisdiction_notes"),
            "total_results": len(source_results) + len(chunk_results),
            "created_at": analysis.created_at,
        }

    async def _classify_task(self, question: str) -> str:
        classification_prompt = f"""Classify this legal question into one category.
Categories: question, research, review, comparison, drafting, deadline, compliance
Question: {question}
Reply with just the category name."""

        response = await self.llm.quick_completion(classification_prompt)
        category = response.strip().lower()
        valid_categories = {"question", "research", "review", "comparison", "drafting", "deadline", "compliance"}
        return category if category in valid_categories else "question"

    async def _gather_context(
        self,
        organization_id: uuid.UUID,
        matter_id: uuid.UUID | None,
        jurisdiction: str | None,
    ) -> dict:
        context: dict = {}

        # Get organization preferences
        prefs = await self.memory.get_organization_preferences(organization_id)
        if prefs:
            for pref in prefs:
                if pref.category == "legal":
                    context[pref.key] = pref.value
            jurisdiction_pref = next((p for p in prefs if p.key == "default_jurisdiction"), None)
            if jurisdiction_pref and not jurisdiction:
                context["jurisdiction"] = jurisdiction_pref.value.get("value")

        # Get matter memories
        if matter_id:
            memories = await self.memory.get_matter_memories(matter_id)
            if memories:
                context["matter_context"] = [
                    {"type": m.memory_type, "content": m.content, "importance": m.importance}
                    for m in memories
                ]

        return context

    async def _get_conversation_history(self, conversation_id: uuid.UUID) -> list[dict]:
        from sqlalchemy import select
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.sequence_number.desc())
            .limit(10)
        )
        result = await self.db.execute(stmt)
        messages = result.scalars().all()
        return [
            {"role": m.role.value, "content": m.content}
            for m in reversed(messages)
        ]

    async def _update_conversation(
        self,
        conversation_id: uuid.UUID,
        question: str,
        answer: str,
        analysis_id: uuid.UUID,
        llm_response: dict,
    ):
        from sqlalchemy import select, func
        count_stmt = select(func.count()).where(ConversationMessage.conversation_id == conversation_id)
        result = await self.db.execute(count_stmt)
        count = result.scalar() or 0

        user_msg = ConversationMessage(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=question,
            sequence_number=count + 1,
        )
        self.db.add(user_msg)

        assistant_msg = ConversationMessage(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            sequence_number=count + 2,
            model_used=self.settings.anthropic_model,
            token_count_input=llm_response.get("input_tokens"),
            token_count_output=llm_response.get("output_tokens"),
            analysis_id=analysis_id,
        )
        self.db.add(assistant_msg)
        await self.db.flush()

    def _parse_analysis_response(self, llm_response: dict) -> dict:
        content = llm_response.get("content", "")

        # Try to parse structured JSON from response
        import json
        import re

        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try parsing the whole response as JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Fallback: return as plain answer
        return {
            "answer": content,
            "issues": [],
            "confidence_score": 0.7,
            "risk_flags": [],
            "follow_up_questions": [],
        }

    def _format_citations(self, chunks: list[RetrievedChunk]) -> list[dict]:
        citations = []
        seen = set()
        for chunk in chunks:
            if chunk.citations:
                for cite in chunk.citations:
                    normalized = cite.get("normalized", cite.get("raw", ""))
                    if normalized not in seen:
                        seen.add(normalized)
                        citations.append({
                            "citation_text": cite.get("raw", ""),
                            "source_title": chunk.document_title,
                            "source_type": cite.get("type"),
                            "jurisdiction": chunk.jurisdiction,
                            "relevant_passage": chunk.content[:300],
                            "confidence": chunk.score,
                        })
        return citations

    @staticmethod
    def _map_risk_level(risk_str: str) -> RiskLevel:
        mapping = {
            "critical": RiskLevel.CRITICAL,
            "high": RiskLevel.HIGH,
            "medium": RiskLevel.MEDIUM,
            "low": RiskLevel.LOW,
            "info": RiskLevel.INFO,
        }
        return mapping.get(risk_str.lower(), RiskLevel.LOW)
