"""Regulatory change monitoring service.

Handles:
1. Subscribing to monitor specific laws/regulations/topics per jurisdiction
2. Periodic checking for changes via legal source adapters
3. Impact assessment of changes against active matters
4. Alert generation and management
"""

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.legal_features import MonitoredRegulation, RegulatoryAlert
from app.services.legal_sources import get_source_registry
from app.services.legal_sources.base import SourceContentType
from app.services.reasoning.llm_client import LLMClient

logger = structlog.get_logger(__name__)


class RegulatoryMonitorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()
        self.settings = get_settings()

    async def create_monitor(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str,
        jurisdiction: str,
        source_type: str,
        description: str | None = None,
        source_identifier: str | None = None,
        keywords: list[str] | None = None,
        topics: list[str] | None = None,
        check_frequency_hours: int = 24,
        affected_matter_ids: list[uuid.UUID] | None = None,
    ) -> MonitoredRegulation:
        # Find the best adapter for this jurisdiction
        registry = get_source_registry()
        adapters = registry.get_best_adapters(jurisdiction)
        source_adapter = adapters[0].adapter_name if adapters else None

        regulation = MonitoredRegulation(
            organization_id=organization_id,
            created_by_id=user_id,
            title=title,
            description=description,
            jurisdiction=jurisdiction,
            source_type=source_type,
            source_identifier=source_identifier,
            source_adapter=source_adapter,
            keywords=keywords,
            topics=topics,
            check_frequency_hours=check_frequency_hours,
            affected_matter_ids=[str(m) for m in affected_matter_ids] if affected_matter_ids else None,
        )
        self.db.add(regulation)
        await self.db.flush()
        logger.info("regulatory_monitor_created", title=title, jurisdiction=jurisdiction)
        return regulation

    async def list_monitors(
        self,
        organization_id: uuid.UUID,
        jurisdiction: str | None = None,
        active_only: bool = True,
    ) -> list[MonitoredRegulation]:
        conditions = [MonitoredRegulation.organization_id == organization_id]
        if jurisdiction:
            conditions.append(MonitoredRegulation.jurisdiction == jurisdiction)
        if active_only:
            conditions.append(MonitoredRegulation.is_active == True)  # noqa: E712

        result = await self.db.execute(
            select(MonitoredRegulation).where(and_(*conditions)).order_by(MonitoredRegulation.created_at.desc())
        )
        return list(result.scalars().all())

    async def check_for_changes(self, regulation_id: uuid.UUID) -> list[RegulatoryAlert]:
        """Check a single monitored regulation for changes. Called by Celery beat."""
        regulation = await self.db.get(MonitoredRegulation, regulation_id)
        if not regulation or not regulation.is_active:
            return []

        registry = get_source_registry()
        query_parts = [regulation.title]
        if regulation.keywords:
            query_parts.extend(regulation.keywords[:5])
        if regulation.source_identifier:
            query_parts.append(regulation.source_identifier)
        query = " ".join(query_parts)

        # Search for recent changes
        content_type_map = {
            "statute": SourceContentType.STATUTE,
            "regulation": SourceContentType.REGULATION,
            "case_law": SourceContentType.CASE_LAW,
            "guidance": SourceContentType.GUIDANCE,
        }
        content_type = content_type_map.get(regulation.source_type)

        # Only look at changes since last check
        date_from = None
        if regulation.last_checked_at:
            date_from = regulation.last_checked_at.date()

        results = await registry.search_all(
            query=query,
            jurisdiction=regulation.jurisdiction,
            content_type=content_type,
            date_from=date_from,
            page_size=10,
        )

        new_documents = []
        for result in results:
            for doc in result.documents:
                new_documents.append({
                    "title": doc.title,
                    "citation": doc.citation,
                    "type": doc.content_type.value,
                    "date": doc.date_enacted.isoformat() if doc.date_enacted else (
                        doc.date_decided.isoformat() if doc.date_decided else None
                    ),
                    "summary": doc.summary[:500] if doc.summary else "",
                    "url": doc.source_url,
                    "source": doc.source_adapter,
                })

        regulation.last_checked_at = datetime.now(timezone.utc)

        alerts = []
        if new_documents:
            regulation.last_change_detected_at = datetime.now(timezone.utc)

            # LLM impact assessment
            impact = await self._assess_impact(regulation, new_documents)

            for i, new_doc in enumerate(new_documents[:5]):
                alert_impact = impact.get("assessments", [{}])[i] if i < len(impact.get("assessments", [])) else {}

                alert = RegulatoryAlert(
                    regulation_id=regulation.id,
                    organization_id=regulation.organization_id,
                    alert_type=self._classify_alert_type(new_doc),
                    title=f"Update: {new_doc['title'][:200]}",
                    summary=new_doc.get("summary", ""),
                    impact_assessment=alert_impact.get("impact", ""),
                    risk_level=alert_impact.get("risk_level", "medium"),
                    source_url=new_doc.get("url"),
                    source_citation=new_doc.get("citation"),
                    affected_matter_ids=regulation.affected_matter_ids,
                )
                self.db.add(alert)
                alerts.append(alert)

        await self.db.flush()
        logger.info(
            "regulatory_check_completed",
            regulation_id=str(regulation_id),
            new_documents=len(new_documents),
            alerts=len(alerts),
        )
        return alerts

    async def check_all_due(self) -> int:
        """Check all regulations that are due for checking. Called by Celery beat."""
        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(MonitoredRegulation).where(
                and_(
                    MonitoredRegulation.is_active == True,  # noqa: E712
                    MonitoredRegulation.last_checked_at.is_(None) |
                    (MonitoredRegulation.last_checked_at < now - timedelta(hours=1)),
                )
            )
        )
        regulations = result.scalars().all()

        # Filter to those actually due based on their frequency
        total_checked = 0
        for reg in regulations:
            if reg.last_checked_at:
                next_check = reg.last_checked_at + timedelta(hours=reg.check_frequency_hours)
                if now < next_check:
                    continue

            try:
                await self.check_for_changes(reg.id)
                total_checked += 1
            except Exception as e:
                logger.error("regulatory_check_failed", regulation_id=str(reg.id), error=str(e))

        return total_checked

    async def get_alerts(
        self,
        organization_id: uuid.UUID,
        unread_only: bool = False,
        jurisdiction: str | None = None,
        limit: int = 50,
    ) -> list[RegulatoryAlert]:
        conditions = [RegulatoryAlert.organization_id == organization_id]
        if unread_only:
            conditions.append(RegulatoryAlert.is_read == False)  # noqa: E712
        if jurisdiction:
            conditions.append(
                RegulatoryAlert.regulation_id.in_(
                    select(MonitoredRegulation.id).where(MonitoredRegulation.jurisdiction == jurisdiction)
                )
            )

        result = await self.db.execute(
            select(RegulatoryAlert).where(and_(*conditions))
            .order_by(RegulatoryAlert.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_alert_actioned(
        self,
        alert_id: uuid.UUID,
        user_id: uuid.UUID,
        notes: str | None = None,
    ) -> RegulatoryAlert:
        alert = await self.db.get(RegulatoryAlert, alert_id)
        if not alert:
            raise ValueError("Alert not found")

        alert.is_read = True
        alert.actioned_by_id = user_id
        alert.actioned_at = datetime.now(timezone.utc)
        alert.action_notes = notes
        await self.db.flush()
        return alert

    async def _assess_impact(self, regulation: MonitoredRegulation, new_documents: list[dict]) -> dict:
        docs_text = ""
        for doc in new_documents[:5]:
            docs_text += f"\n- {doc['title']} ({doc.get('citation', '')})\n"
            if doc.get("summary"):
                docs_text += f"  {doc['summary'][:300]}\n"

        prompt = f"""A monitored regulation has new developments.

Monitored: {regulation.title}
Jurisdiction: {regulation.jurisdiction}
Type: {regulation.source_type}
Description: {regulation.description or 'N/A'}

New documents found:
{docs_text}

For each new document, assess:
1. impact: how this affects the monitored regulation/area
2. risk_level: critical/high/medium/low/info
3. action_required: what should be done

Return as JSON with: assessments (array), overall_summary"""

        return await self.llm.structured_analysis(
            "You are a regulatory change analyst.", prompt, {"assessments": [], "overall_summary": "string"},
        )

    def _classify_alert_type(self, doc: dict) -> str:
        doc_type = doc.get("type", "")
        title_lower = doc.get("title", "").lower()

        if "repeal" in title_lower or "revok" in title_lower:
            return "repeal"
        if "amend" in title_lower or "modif" in title_lower:
            return "amendment"
        if doc_type == "case_law":
            return "new_case"
        if doc_type == "guidance":
            return "guidance_update"
        return "new_law"
