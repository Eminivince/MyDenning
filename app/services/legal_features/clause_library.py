"""Clause library with market intelligence.

Every contract reviewed adds to the clause library. Over time this builds:
1. A searchable database of every clause seen, by type and counterparty
2. Market benchmarks: "average liability cap is 12 months of fees"
3. Counterparty patterns: "Acme Corp always insists on unilateral termination"
4. Trend detection: "indemnity caps are getting stricter in 2026 vs 2025"
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, and_, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import ClauseExtraction, RiskLevel
from app.models.document import Document

logger = structlog.get_logger(__name__)


class ClauseLibraryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_clauses(
        self,
        organization_id: uuid.UUID,
        clause_type: str | None = None,
        risk_level: str | None = None,
        query: str | None = None,
        counterparty: str | None = None,
        jurisdiction: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Search the clause library across all reviewed documents."""
        conditions = [Document.organization_id == organization_id, Document.is_active == True]  # noqa: E712

        if clause_type:
            conditions.append(ClauseExtraction.clause_type == clause_type)
        if risk_level:
            conditions.append(ClauseExtraction.risk_level == RiskLevel(risk_level))

        # Base query
        stmt = (
            select(
                ClauseExtraction,
                Document.title.label("document_title"),
                Document.jurisdiction.label("document_jurisdiction"),
                Document.parties.label("document_parties"),
                Document.created_at.label("document_date"),
            )
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(*conditions))
        )

        if jurisdiction:
            stmt = stmt.where(Document.jurisdiction == jurisdiction)

        if query:
            stmt = stmt.where(ClauseExtraction.clause_text.ilike(f"%{query}%"))

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch
        stmt = stmt.order_by(ClauseExtraction.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        rows = result.all()

        clauses = []
        for row in rows:
            clause = row[0]
            clauses.append({
                "id": str(clause.id),
                "clause_type": clause.clause_type,
                "clause_number": clause.clause_number,
                "clause_title": clause.clause_title,
                "clause_text": clause.clause_text[:500],
                "risk_level": clause.risk_level.value if clause.risk_level else None,
                "risk_notes": clause.risk_notes,
                "is_standard": clause.is_standard,
                "confidence": clause.confidence,
                "obligations": clause.obligations,
                "monetary_values": clause.monetary_values,
                "dates": clause.dates,
                "document_title": row.document_title,
                "document_jurisdiction": row.document_jurisdiction,
                "document_date": row.document_date.isoformat() if row.document_date else None,
            })

        return {
            "clauses": clauses,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_market_benchmarks(self, organization_id: uuid.UUID) -> dict:
        """Compute market intelligence from all clauses in the library.

        Returns: clause type distribution, risk distribution, common patterns.
        """
        # Clause type distribution
        type_result = await self.db.execute(
            select(ClauseExtraction.clause_type, func.count().label("count"))
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(Document.organization_id == organization_id, Document.is_active == True))  # noqa: E712
            .group_by(ClauseExtraction.clause_type)
            .order_by(func.count().desc())
        )
        type_distribution = [{"clause_type": row.clause_type, "count": row.count} for row in type_result.all()]

        # Risk distribution
        risk_result = await self.db.execute(
            select(ClauseExtraction.risk_level, func.count().label("count"))
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(
                Document.organization_id == organization_id,
                Document.is_active == True,  # noqa: E712
                ClauseExtraction.risk_level.isnot(None),
            ))
            .group_by(ClauseExtraction.risk_level)
        )
        risk_distribution = [{"risk_level": row.risk_level.value, "count": row.count} for row in risk_result.all()]

        # Standard vs non-standard
        standard_result = await self.db.execute(
            select(ClauseExtraction.is_standard, func.count().label("count"))
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(
                Document.organization_id == organization_id,
                Document.is_active == True,  # noqa: E712
                ClauseExtraction.is_standard.isnot(None),
            ))
            .group_by(ClauseExtraction.is_standard)
        )
        standard_counts = {str(row.is_standard): row.count for row in standard_result.all()}

        # Total clauses
        total_result = await self.db.execute(
            select(func.count())
            .select_from(ClauseExtraction)
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(Document.organization_id == organization_id, Document.is_active == True))  # noqa: E712
        )
        total_clauses = total_result.scalar() or 0

        # Total documents reviewed
        docs_result = await self.db.execute(
            select(func.count(func.distinct(ClauseExtraction.document_id)))
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(Document.organization_id == organization_id, Document.is_active == True))  # noqa: E712
        )
        total_docs = docs_result.scalar() or 0

        # Most common risky clause types
        risky_result = await self.db.execute(
            select(ClauseExtraction.clause_type, func.count().label("count"))
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(
                Document.organization_id == organization_id,
                Document.is_active == True,  # noqa: E712
                ClauseExtraction.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
            ))
            .group_by(ClauseExtraction.clause_type)
            .order_by(func.count().desc())
            .limit(10)
        )
        most_risky_types = [{"clause_type": row.clause_type, "high_risk_count": row.count} for row in risky_result.all()]

        # By jurisdiction
        jurisdiction_result = await self.db.execute(
            select(Document.jurisdiction, func.count(ClauseExtraction.id).label("count"))
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(
                Document.organization_id == organization_id,
                Document.is_active == True,  # noqa: E712
                Document.jurisdiction.isnot(None),
            ))
            .group_by(Document.jurisdiction)
            .order_by(func.count().desc())
        )
        by_jurisdiction = [{"jurisdiction": row.jurisdiction, "clause_count": row.count} for row in jurisdiction_result.all()]

        return {
            "total_clauses": total_clauses,
            "total_documents_reviewed": total_docs,
            "clause_type_distribution": type_distribution,
            "risk_distribution": risk_distribution,
            "standard_clauses": standard_counts.get("True", 0),
            "non_standard_clauses": standard_counts.get("False", 0),
            "most_risky_clause_types": most_risky_types,
            "by_jurisdiction": by_jurisdiction,
        }

    async def get_clause_type_insights(
        self,
        organization_id: uuid.UUID,
        clause_type: str,
    ) -> dict:
        """Deep dive into a specific clause type across all documents.

        Returns: count, risk breakdown, example language, common patterns.
        """
        conditions = [
            Document.organization_id == organization_id,
            Document.is_active == True,  # noqa: E712
            ClauseExtraction.clause_type == clause_type,
        ]

        # Count
        count_result = await self.db.execute(
            select(func.count()).select_from(ClauseExtraction)
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(*conditions))
        )
        total = count_result.scalar() or 0

        # Risk breakdown for this type
        risk_result = await self.db.execute(
            select(ClauseExtraction.risk_level, func.count().label("count"))
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(*conditions, ClauseExtraction.risk_level.isnot(None)))
            .group_by(ClauseExtraction.risk_level)
        )
        risk_breakdown = {row.risk_level.value: row.count for row in risk_result.all()}

        # Recent examples (last 10)
        examples_result = await self.db.execute(
            select(ClauseExtraction.clause_text, ClauseExtraction.risk_level, Document.title)
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(*conditions))
            .order_by(ClauseExtraction.created_at.desc())
            .limit(10)
        )
        examples = [
            {
                "text": row.clause_text[:300],
                "risk": row.risk_level.value if row.risk_level else None,
                "document": row.title,
            }
            for row in examples_result.all()
        ]

        # Standard vs unusual
        standard_result = await self.db.execute(
            select(
                func.count().filter(ClauseExtraction.is_standard == True).label("standard"),
                func.count().filter(ClauseExtraction.is_standard == False).label("unusual"),
            )
            .join(Document, ClauseExtraction.document_id == Document.id)
            .where(and_(*conditions))
        )
        std_row = standard_result.one()

        return {
            "clause_type": clause_type,
            "total_instances": total,
            "risk_breakdown": risk_breakdown,
            "standard_count": std_row.standard or 0,
            "unusual_count": std_row.unusual or 0,
            "unusual_percentage": round((std_row.unusual or 0) / total * 100, 1) if total > 0 else 0,
            "recent_examples": examples,
        }
