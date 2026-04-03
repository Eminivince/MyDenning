import time
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.analysis import AnalysisResult, AnalysisType, ClauseExtraction, DeviationReport, RiskLevel
from app.models.document import Document, DocumentChunk
from app.models.matter import MatterDeadline
from app.models.playbook import Playbook, PlaybookClause
from app.services.reasoning.llm_client import LLMClient
from app.services.reasoning.prompts import PromptBuilder

logger = structlog.get_logger(__name__)


class DocumentIntelligenceService:
    """Document intelligence: clause extraction, deviation detection, comparison, deadline extraction."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()
        self.prompts = PromptBuilder()
        self.settings = get_settings()

    async def extract_clauses(
        self,
        document_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        focus_areas: list[str] | None = None,
    ) -> dict:
        start_time = time.time()

        document = await self.db.get(Document, document_id)
        if not document or not document.raw_text:
            raise ValueError(f"Document {document_id} not found or not processed")

        system_prompt = self.prompts.LEGAL_SYSTEM_BASE + "\n\nYou are extracting legal clauses from a document."
        user_prompt = self.prompts.build_clause_extraction_prompt(document.raw_text, focus_areas)

        llm_response = await self.llm.structured_analysis(
            system_prompt,
            user_prompt,
            output_schema={"clauses": [{"clause_type": "string", "clause_text": "string", "risk_level": "string"}]},
        )

        clauses_data = llm_response.get("clauses", [])

        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            document_id=document_id,
            analysis_type=AnalysisType.CLAUSE_EXTRACTION,
            result=llm_response,
            summary=f"Extracted {len(clauses_data)} clauses",
            model_used=self.settings.anthropic_model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        # Store individual clause extractions
        risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        missing_clauses = []
        unusual_terms = []

        for clause_data in clauses_data:
            risk_level_str = clause_data.get("risk_level", "low").lower()
            risk_level = self._map_risk(risk_level_str)
            risk_counts[risk_level_str] = risk_counts.get(risk_level_str, 0) + 1

            extraction = ClauseExtraction(
                analysis_id=analysis.id,
                document_id=document_id,
                clause_type=clause_data.get("clause_type", "unknown"),
                clause_number=clause_data.get("clause_number"),
                clause_title=clause_data.get("clause_title"),
                clause_text=clause_data.get("clause_text", ""),
                page_number=clause_data.get("page_number"),
                parties_involved=clause_data.get("parties_involved"),
                obligations=clause_data.get("obligations"),
                dates=clause_data.get("dates"),
                monetary_values=clause_data.get("monetary_values"),
                conditions=clause_data.get("conditions"),
                risk_level=risk_level,
                risk_notes=clause_data.get("risk_notes"),
                is_standard=clause_data.get("is_standard"),
                confidence=clause_data.get("confidence", 0.8),
            )
            self.db.add(extraction)

            if clause_data.get("is_standard") is False:
                unusual_terms.append(clause_data.get("clause_type", "unknown"))

        missing = llm_response.get("missing_clauses", [])
        if isinstance(missing, list):
            missing_clauses = missing

        overall_risk = RiskLevel.LOW
        if risk_counts.get("critical", 0) > 0:
            overall_risk = RiskLevel.CRITICAL
        elif risk_counts.get("high", 0) > 0:
            overall_risk = RiskLevel.HIGH
        elif risk_counts.get("medium", 0) > 0:
            overall_risk = RiskLevel.MEDIUM

        key_dates = []
        key_obligations = []
        for clause_data in clauses_data:
            if clause_data.get("dates"):
                for d in clause_data["dates"]:
                    key_dates.append({"clause": clause_data.get("clause_type"), "date": d})
            if clause_data.get("obligations"):
                for o in clause_data["obligations"]:
                    key_obligations.append({"clause": clause_data.get("clause_type"), "obligation": o})

        await self.db.flush()

        return {
            "id": analysis.id,
            "document_id": document_id,
            "summary": f"Extracted {len(clauses_data)} clauses from document",
            "clauses": clauses_data,
            "risk_flags": [
                {"level": level, "count": count}
                for level, count in risk_counts.items()
                if count > 0
            ],
            "missing_clauses": missing_clauses,
            "unusual_terms": unusual_terms,
            "key_dates": key_dates[:20],
            "key_obligations": key_obligations[:20],
            "overall_risk_level": overall_risk.value,
            "confidence_score": llm_response.get("confidence_score", 0.8),
            "created_at": analysis.created_at,
        }

    async def detect_deviations(
        self,
        document_id: uuid.UUID,
        playbook_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        start_time = time.time()

        document = await self.db.get(Document, document_id)
        if not document or not document.raw_text:
            raise ValueError("Document not found or not processed")

        playbook_result = await self.db.execute(
            select(Playbook)
            .where(Playbook.id == playbook_id)
            .options(selectinload(Playbook.clauses))
        )
        playbook = playbook_result.scalar_one_or_none()
        if not playbook:
            raise ValueError("Playbook not found")

        # First extract clauses from document
        clause_result = await self.extract_clauses(document_id, organization_id, user_id)
        document_clauses = clause_result.get("clauses", [])

        playbook_clauses = [
            {
                "clause_type": c.clause_type,
                "clause_name": c.clause_name,
                "position": c.position.value,
                "standard_language": c.standard_language,
                "fallback_language": c.fallback_language,
                "negotiation_notes": c.negotiation_notes,
                "risk_if_deviated": c.risk_if_deviated,
                "importance_weight": c.importance_weight,
            }
            for c in playbook.clauses
        ]

        system_prompt = self.prompts.LEGAL_SYSTEM_BASE + "\n\nYou are comparing a document against a contract playbook."
        user_prompt = self.prompts.build_deviation_prompt(document_clauses, playbook_clauses)

        llm_response = await self.llm.structured_analysis(
            system_prompt,
            user_prompt,
            output_schema={"deviations": [{"clause_type": "string", "deviation_type": "string", "risk_level": "string"}]},
        )

        deviations_data = llm_response.get("deviations", [])

        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            document_id=document_id,
            analysis_type=AnalysisType.DEVIATION_CHECK,
            result=llm_response,
            summary=f"Found {len(deviations_data)} deviations from playbook '{playbook.name}'",
            model_used=self.settings.anthropic_model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        approval_required = False
        risk_score = 0.0

        for dev_data in deviations_data:
            risk_level = self._map_risk(dev_data.get("risk_level", "low"))

            playbook_clause = next(
                (c for c in playbook.clauses if c.clause_type == dev_data.get("clause_type")),
                None,
            )

            deviation = DeviationReport(
                analysis_id=analysis.id,
                document_id=document_id,
                playbook_id=playbook_id,
                playbook_clause_id=playbook_clause.id if playbook_clause else None,
                clause_type=dev_data.get("clause_type", "unknown"),
                document_clause_text=dev_data.get("document_clause_text", ""),
                playbook_clause_text=dev_data.get("playbook_clause_text", ""),
                deviation_type=dev_data.get("deviation_type", "different"),
                deviation_description=dev_data.get("deviation_description", ""),
                risk_level=risk_level,
                recommendation=dev_data.get("recommendation", ""),
                suggested_language=dev_data.get("suggested_language"),
                requires_approval=dev_data.get("requires_approval", False),
                confidence=dev_data.get("confidence", 0.8),
            )
            self.db.add(deviation)

            if dev_data.get("requires_approval"):
                approval_required = True

            risk_weights = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.1}
            risk_score += risk_weights.get(dev_data.get("risk_level", "low"), 0.1)

        max_possible = len(deviations_data) * 1.0
        normalized_risk = risk_score / max_possible if max_possible > 0 else 0.0

        overall_risk = RiskLevel.LOW
        if normalized_risk > 0.7:
            overall_risk = RiskLevel.CRITICAL
        elif normalized_risk > 0.5:
            overall_risk = RiskLevel.HIGH
        elif normalized_risk > 0.3:
            overall_risk = RiskLevel.MEDIUM

        await self.db.flush()

        return {
            "id": analysis.id,
            "document_id": document_id,
            "compared_to": playbook.name,
            "summary": f"Found {len(deviations_data)} deviations from playbook '{playbook.name}'",
            "deviations": deviations_data,
            "risk_score": round(normalized_risk, 2),
            "overall_risk_level": overall_risk.value,
            "approval_required": approval_required,
            "created_at": analysis.created_at,
        }

    async def compare_documents(
        self,
        document_id: uuid.UUID,
        compare_to_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        focus_areas: list[str] | None = None,
    ) -> dict:
        start_time = time.time()

        doc1 = await self.db.get(Document, document_id)
        doc2 = await self.db.get(Document, compare_to_id)

        if not doc1 or not doc1.raw_text:
            raise ValueError(f"Document {document_id} not found or not processed")
        if not doc2 or not doc2.raw_text:
            raise ValueError(f"Document {compare_to_id} not found or not processed")

        system_prompt = self.prompts.LEGAL_SYSTEM_BASE + "\n\nYou are comparing two legal documents."
        user_prompt = self.prompts.build_comparison_prompt(
            doc1.raw_text, doc2.raw_text, doc1.title, doc2.title, focus_areas
        )

        llm_response = await self.llm.structured_analysis(
            system_prompt,
            user_prompt,
            output_schema={"summary": "string", "differences": [], "risk_assessment": "string"},
        )

        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            document_id=document_id,
            analysis_type=AnalysisType.DOCUMENT_COMPARISON,
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
            "compared_to": doc2.title,
            "summary": llm_response.get("summary", ""),
            "differences": llm_response.get("differences", []),
            "risk_assessment": llm_response.get("risk_assessment", ""),
            "recommendation": llm_response.get("recommendation", ""),
            "created_at": analysis.created_at,
        }

    async def extract_deadlines(
        self,
        document_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        matter_id: uuid.UUID | None = None,
    ) -> dict:
        start_time = time.time()

        document = await self.db.get(Document, document_id)
        if not document or not document.raw_text:
            raise ValueError("Document not found or not processed")

        system_prompt = self.prompts.LEGAL_SYSTEM_BASE + "\n\nYou are extracting deadlines from a legal document."
        user_prompt = self.prompts.build_deadline_extraction_prompt(document.raw_text)

        llm_response = await self.llm.structured_analysis(
            system_prompt,
            user_prompt,
            output_schema={"deadlines": [{"title": "string", "due_date": "string", "priority": "integer"}]},
        )

        deadlines_data = llm_response.get("deadlines", [])

        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            document_id=document_id,
            analysis_type=AnalysisType.DEADLINE_EXTRACTION,
            result=llm_response,
            summary=f"Extracted {len(deadlines_data)} deadlines",
            model_used=self.settings.anthropic_model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        created_deadlines = []
        if matter_id:
            from dateutil.parser import parse as parse_date

            for dl in deadlines_data:
                try:
                    due_date = parse_date(dl.get("due_date", ""))
                    if due_date.tzinfo is None:
                        due_date = due_date.replace(tzinfo=timezone.utc)

                    deadline = MatterDeadline(
                        matter_id=matter_id,
                        created_by_id=user_id,
                        title=dl.get("title", "Extracted deadline"),
                        description=dl.get("description"),
                        due_date=due_date,
                        priority=dl.get("priority", 3),
                        is_court_deadline=dl.get("is_court_deadline", False),
                        source_document_id=document_id,
                    )
                    self.db.add(deadline)
                    created_deadlines.append({
                        "title": deadline.title,
                        "due_date": due_date.isoformat(),
                        "priority": deadline.priority,
                    })
                except (ValueError, TypeError):
                    logger.warning("deadline_date_parse_failed", raw=dl.get("due_date"))

            await self.db.flush()

        return {
            "id": analysis.id,
            "document_id": document_id,
            "deadlines": deadlines_data,
            "created_deadlines": created_deadlines,
            "total": len(deadlines_data),
            "created_at": analysis.created_at,
        }

    @staticmethod
    def _map_risk(risk_str: str) -> RiskLevel:
        mapping = {
            "critical": RiskLevel.CRITICAL,
            "high": RiskLevel.HIGH,
            "medium": RiskLevel.MEDIUM,
            "low": RiskLevel.LOW,
            "info": RiskLevel.INFO,
        }
        return mapping.get(risk_str.lower(), RiskLevel.LOW)
