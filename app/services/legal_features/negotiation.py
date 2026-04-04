"""Smart negotiation assistant — not just review, but strategy.

Given a counterparty's contract, this service:
1. Extracts the counterparty's positions clause by clause
2. Looks up prior dealings with this counterparty from matter history
3. Compares against the org's playbook to identify gaps
4. Predicts which clauses will face pushback (based on counterparty history)
5. Generates a negotiation strategy memo with prioritized counter-positions

This is what makes a GC say "I need this."
"""

import time
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.analysis import AnalysisResult, AnalysisType, RiskLevel
from app.models.document import Document
from app.models.legal_features import ConflictMatterParty, ConflictParty
from app.models.matter import Matter
from app.models.playbook import Playbook, PlaybookClause
from app.services.reasoning.llm_client import LLMClient

logger = structlog.get_logger(__name__)


class NegotiationAssistant:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()
        self.settings = get_settings()

    async def generate_strategy(
        self,
        document_id: uuid.UUID,
        playbook_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        counterparty_name: str | None = None,
        matter_id: uuid.UUID | None = None,
        priorities: list[str] | None = None,
        deal_context: str | None = None,
    ) -> dict:
        """Generate a full negotiation strategy for a contract.

        Args:
            document_id: The counterparty's contract/draft to negotiate
            playbook_id: Our standard positions to compare against
            counterparty_name: Name for looking up prior dealings
            matter_id: Current matter for context
            priorities: User's priorities (e.g. ["limit liability", "keep IP rights"])
            deal_context: Freeform context (e.g. "They're a key vendor, we need this deal")
        """
        start_time = time.time()

        # 1. Load the contract
        document = await self.db.get(Document, document_id)
        if not document or not document.raw_text:
            raise ValueError("Document not found or not processed")

        # 2. Load the playbook with clauses
        pb_result = await self.db.execute(
            select(Playbook).where(Playbook.id == playbook_id).options(selectinload(Playbook.clauses))
        )
        playbook = pb_result.scalar_one_or_none()
        if not playbook:
            raise ValueError("Playbook not found")

        # 3. Look up prior dealings with counterparty
        counterparty_history = []
        if counterparty_name:
            counterparty_history = await self._get_counterparty_history(organization_id, counterparty_name)

        # 4. Load matter context if available
        matter_context = None
        if matter_id:
            matter = await self.db.get(Matter, matter_id)
            if matter:
                matter_context = {
                    "title": matter.title,
                    "type": matter.matter_type.value,
                    "jurisdiction": matter.jurisdiction,
                    "client": matter.client_name,
                    "counterparty": matter.counterparty,
                }

        # 5. Build the strategy prompt
        system_prompt = """You are a senior contract negotiation strategist. You help legal teams
prepare negotiation strategies by analyzing counterparty positions against the organization's
standard playbook and prior dealings.

Your output must be practical, specific, and actionable. For each clause:
- State the counterparty's current position
- State our preferred position
- Assess likelihood of pushback (based on how aggressive their position is)
- Recommend a specific negotiation approach
- Provide exact counter-language ready to use
- Identify fallback positions in priority order

Think like a partner at a top law firm advising on strategy before a negotiation call."""

        user_prompt = self._build_strategy_prompt(
            document_text=document.raw_text,
            playbook_clauses=playbook.clauses,
            counterparty_name=counterparty_name,
            counterparty_history=counterparty_history,
            matter_context=matter_context,
            priorities=priorities,
            deal_context=deal_context,
        )

        llm_response = await self.llm.structured_analysis(
            system_prompt, user_prompt,
            {
                "executive_summary": "string",
                "overall_risk_level": "string",
                "counterparty_stance": "string — hawkish/neutral/flexible",
                "negotiation_clauses": [{
                    "clause_type": "string",
                    "their_position": "string",
                    "our_preferred_position": "string",
                    "gap_severity": "string — critical/major/minor/aligned",
                    "pushback_likelihood": "string — high/medium/low",
                    "pushback_reason": "string",
                    "strategy": "string — specific negotiation approach",
                    "counter_language": "string — exact clause language to propose",
                    "fallback_positions": ["string — ordered fallback options"],
                    "walk_away_trigger": "string — what makes this unacceptable",
                    "priority": "integer — 1=must-win, 2=important, 3=nice-to-have",
                }],
                "key_leverage_points": ["string"],
                "concession_candidates": ["string — clauses we can concede on"],
                "red_lines": ["string — absolute non-negotiables"],
                "opening_talking_points": ["string — how to open the negotiation"],
                "confidence_score": "float",
            },
        )

        # 6. Store as analysis result
        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            document_id=document_id,
            matter_id=matter_id,
            analysis_type=AnalysisType.RISK_ASSESSMENT,  # closest type
            query=f"Negotiation strategy: {document.title} vs {playbook.name}",
            result=llm_response,
            summary=llm_response.get("executive_summary", ""),
            risk_level=self._map_risk(llm_response.get("overall_risk_level", "medium")),
            confidence_score=llm_response.get("confidence_score", 0.7),
            model_used=self.settings.anthropic_model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        return {
            "id": analysis.id,
            "document_id": str(document_id),
            "playbook_id": str(playbook_id),
            "counterparty": counterparty_name,
            "executive_summary": llm_response.get("executive_summary", ""),
            "overall_risk_level": llm_response.get("overall_risk_level", "medium"),
            "counterparty_stance": llm_response.get("counterparty_stance", "unknown"),
            "clauses": llm_response.get("negotiation_clauses", []),
            "key_leverage_points": llm_response.get("key_leverage_points", []),
            "concession_candidates": llm_response.get("concession_candidates", []),
            "red_lines": llm_response.get("red_lines", []),
            "opening_talking_points": llm_response.get("opening_talking_points", []),
            "counterparty_history": counterparty_history,
            "confidence_score": llm_response.get("confidence_score", 0.7),
            "created_at": analysis.created_at,
        }

    async def _get_counterparty_history(self, organization_id: uuid.UUID, counterparty_name: str) -> list[dict]:
        """Look up all prior matters and outcomes with this counterparty."""
        # Normalize name for fuzzy matching
        import re
        normalized = re.sub(r'\b(limited|ltd|llc|plc|inc|corp|corporation)\b\.?', '', counterparty_name.lower(), flags=re.IGNORECASE)
        normalized = re.sub(r'[^\w\s]', '', normalized).strip()

        # Search conflict parties table
        parties_result = await self.db.execute(
            select(ConflictParty).where(
                and_(
                    ConflictParty.organization_id == organization_id,
                    or_(
                        ConflictParty.normalized_name.ilike(f"%{normalized}%"),
                        ConflictParty.name.ilike(f"%{counterparty_name}%"),
                    ),
                )
            )
        )
        parties = parties_result.scalars().all()

        history = []
        for party in parties:
            links_result = await self.db.execute(
                select(ConflictMatterParty).where(ConflictMatterParty.party_id == party.id)
            )
            for link in links_result.scalars().all():
                matter = await self.db.get(Matter, link.matter_id)
                if not matter:
                    continue

                # Look for prior analyses on this matter
                analyses_result = await self.db.execute(
                    select(AnalysisResult).where(
                        and_(
                            AnalysisResult.matter_id == matter.id,
                            AnalysisResult.analysis_type.in_([
                                AnalysisType.DEVIATION_CHECK,
                                AnalysisType.CLAUSE_EXTRACTION,
                            ]),
                        )
                    ).order_by(AnalysisResult.created_at.desc()).limit(1)
                )
                prior_analysis = analyses_result.scalar_one_or_none()

                entry = {
                    "matter_title": matter.title,
                    "matter_type": matter.matter_type.value,
                    "matter_status": matter.status.value,
                    "role": link.role,
                    "jurisdiction": matter.jurisdiction,
                    "opened": matter.opened_at.isoformat() if matter.opened_at else None,
                }
                if prior_analysis and prior_analysis.result:
                    deviations = prior_analysis.result.get("deviations", [])
                    entry["prior_deviations"] = len(deviations)
                    entry["prior_risk_level"] = prior_analysis.risk_level.value if prior_analysis.risk_level else None
                    # Extract what they accepted/rejected
                    accepted = [d for d in deviations if d.get("deviation_type") == "accepted"]
                    entry["accepted_deviations"] = len(accepted)

                history.append(entry)

        return history

    def _build_strategy_prompt(
        self,
        document_text: str,
        playbook_clauses: list[PlaybookClause],
        counterparty_name: str | None,
        counterparty_history: list[dict],
        matter_context: dict | None,
        priorities: list[str] | None,
        deal_context: str | None,
    ) -> str:
        parts = []

        # Deal context
        if deal_context:
            parts.append(f"## Deal Context\n{deal_context}")

        if matter_context:
            parts.append(f"## Matter\n{matter_context['title']} ({matter_context['type']})")
            if matter_context.get("jurisdiction"):
                parts.append(f"Jurisdiction: {matter_context['jurisdiction']}")
            if matter_context.get("client"):
                parts.append(f"Client: {matter_context['client']}")

        if priorities:
            parts.append(f"## Our Priorities (in order)\n" + "\n".join(f"{i+1}. {p}" for i, p in enumerate(priorities)))

        # Counterparty history
        if counterparty_name:
            parts.append(f"\n## Counterparty: {counterparty_name}")
        if counterparty_history:
            parts.append("### Prior Dealings with This Counterparty:")
            for h in counterparty_history:
                parts.append(
                    f"- Matter: {h['matter_title']} ({h['matter_status']}) — "
                    f"role: {h['role']}, jurisdiction: {h.get('jurisdiction', 'N/A')}"
                )
                if h.get("prior_deviations") is not None:
                    parts.append(f"  Prior deviations: {h['prior_deviations']}, risk: {h.get('prior_risk_level', 'N/A')}")
        else:
            parts.append("### No prior dealings found with this counterparty.")

        # Their contract
        parts.append(f"\n## Counterparty's Contract\n```\n{document_text[:15000]}\n```")

        # Our playbook positions
        parts.append("\n## Our Standard Playbook Positions:")
        for clause in sorted(playbook_clauses, key=lambda c: c.order_index):
            parts.append(f"\n### {clause.clause_name} ({clause.clause_type})")
            parts.append(f"Position: {clause.position.value}")
            parts.append(f"Standard: {clause.standard_language[:500]}")
            if clause.fallback_language:
                parts.append(f"Fallback: {clause.fallback_language[:300]}")
            if clause.negotiation_notes:
                parts.append(f"Notes: {clause.negotiation_notes}")
            if clause.risk_if_deviated:
                parts.append(f"Risk if deviated: {clause.risk_if_deviated}")

        parts.append("""
## Instructions

Analyze the counterparty's contract against our playbook and generate a
complete negotiation strategy. For each material clause:

1. State their position vs our position
2. Rate the gap severity (critical/major/minor/aligned)
3. Predict pushback likelihood based on their drafting stance
4. Recommend a specific negotiation approach
5. Draft exact counter-language we can propose
6. List fallback positions in order of preference
7. Define our walk-away trigger

Also provide:
- Executive summary of the overall negotiation landscape
- Key leverage points we can use
- Clauses we can strategically concede on (trade chips)
- Absolute red lines (non-negotiable)
- Opening talking points for the negotiation call

Return as JSON.""")

        return "\n".join(parts)

    @staticmethod
    def _map_risk(risk_str: str) -> RiskLevel:
        return {"critical": RiskLevel.CRITICAL, "high": RiskLevel.HIGH, "medium": RiskLevel.MEDIUM,
                "low": RiskLevel.LOW, "info": RiskLevel.INFO}.get(risk_str.lower(), RiskLevel.MEDIUM)
