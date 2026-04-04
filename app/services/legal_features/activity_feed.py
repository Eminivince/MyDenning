"""Activity feed service — chronological timeline of everything that happened on a matter.

Aggregates events from: audit logs, documents, deadlines, notes, analyses, and memories.
Returns a unified, sorted feed with icons and descriptions.
"""

import uuid
from datetime import datetime

import structlog
from sqlalchemy import select, and_, or_, union_all, literal, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisResult
from app.models.audit import AuditLog
from app.models.document import Document
from app.models.matter import Matter, MatterDeadline, MatterDocument, MatterNote
from app.models.memory import MatterMemory

logger = structlog.get_logger(__name__)


class ActivityFeedService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_matter_feed(
        self,
        matter_id: uuid.UUID,
        organization_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Build a chronological activity feed for a matter from multiple sources."""
        events: list[dict] = []

        # 1. Notes
        notes_result = await self.db.execute(
            select(MatterNote).where(MatterNote.matter_id == matter_id)
            .order_by(MatterNote.created_at.desc()).limit(limit)
        )
        for note in notes_result.scalars().all():
            events.append({
                "type": "note",
                "icon": "message_square",
                "title": f"Note added ({note.note_type or 'general'})",
                "description": note.content[:200] + ("..." if len(note.content) > 200 else ""),
                "timestamp": note.created_at.isoformat(),
                "user_id": str(note.created_by_id),
                "resource_id": str(note.id),
            })

        # 2. Deadlines
        deadlines_result = await self.db.execute(
            select(MatterDeadline).where(MatterDeadline.matter_id == matter_id)
            .order_by(MatterDeadline.created_at.desc()).limit(limit)
        )
        for dl in deadlines_result.scalars().all():
            events.append({
                "type": "deadline",
                "icon": "calendar",
                "title": f"Deadline: {dl.title}",
                "description": f"Due {dl.due_date.strftime('%b %d, %Y')} — {dl.status}{'  (COURT)' if dl.is_court_deadline else ''}",
                "timestamp": dl.created_at.isoformat(),
                "user_id": str(dl.created_by_id),
                "resource_id": str(dl.id),
                "metadata": {"status": dl.status.value, "priority": dl.priority},
            })

        # 3. Documents linked to matter
        docs_result = await self.db.execute(
            select(Document).where(
                and_(Document.matter_id == matter_id, Document.is_active == True)  # noqa: E712
            ).order_by(Document.created_at.desc()).limit(limit)
        )
        for doc in docs_result.scalars().all():
            events.append({
                "type": "document",
                "icon": "file_text",
                "title": f"Document uploaded: {doc.title}",
                "description": f"{doc.document_type.value.replace('_', ' ').title()} — {doc.processing_status.value}",
                "timestamp": doc.created_at.isoformat(),
                "user_id": str(doc.uploaded_by_id),
                "resource_id": str(doc.id),
                "metadata": {"status": doc.processing_status.value},
            })

        # 4. Analyses on this matter
        analyses_result = await self.db.execute(
            select(AnalysisResult).where(AnalysisResult.matter_id == matter_id)
            .order_by(AnalysisResult.created_at.desc()).limit(limit)
        )
        for analysis in analyses_result.scalars().all():
            type_label = analysis.analysis_type.value.replace("_", " ").title()
            events.append({
                "type": "analysis",
                "icon": "zap",
                "title": f"Analysis: {type_label}",
                "description": analysis.summary[:200] if analysis.summary else analysis.query[:200] if analysis.query else type_label,
                "timestamp": analysis.created_at.isoformat(),
                "user_id": str(analysis.requested_by_id),
                "resource_id": str(analysis.id),
                "metadata": {
                    "analysis_type": analysis.analysis_type.value,
                    "confidence": analysis.confidence_score,
                    "risk_level": analysis.risk_level.value if analysis.risk_level else None,
                },
            })

        # 5. Matter memories
        memories_result = await self.db.execute(
            select(MatterMemory).where(
                and_(MatterMemory.matter_id == matter_id, MatterMemory.is_active == True)  # noqa: E712
            ).order_by(MatterMemory.created_at.desc()).limit(limit)
        )
        for mem in memories_result.scalars().all():
            events.append({
                "type": "memory",
                "icon": "brain",
                "title": f"Memory ({mem.memory_type}): {mem.content[:60]}",
                "description": mem.content[:200],
                "timestamp": mem.created_at.isoformat(),
                "user_id": str(mem.created_by_id),
                "resource_id": str(mem.id),
                "metadata": {"source": mem.source, "importance": mem.importance},
            })

        # 6. Audit log entries referencing this matter
        audit_result = await self.db.execute(
            select(AuditLog).where(
                and_(
                    AuditLog.organization_id == organization_id,
                    or_(
                        AuditLog.resource_id == str(matter_id),
                        AuditLog.metadata.op("->>")(  # type: ignore
                            "matter_id"
                        ) == str(matter_id),
                    ),
                )
            ).order_by(AuditLog.created_at.desc()).limit(limit)
        )
        for log in audit_result.scalars().all():
            # Skip if we already have this event from another source
            if str(log.resource_id) in {e["resource_id"] for e in events}:
                continue
            events.append({
                "type": "audit",
                "icon": "clipboard_list",
                "title": f"{log.action.replace('_', ' ').title()}",
                "description": log.description or f"{log.action} on {log.resource_type}",
                "timestamp": log.created_at.isoformat(),
                "user_id": str(log.user_id) if log.user_id else None,
                "resource_id": str(log.id),
            })

        # Sort all events by timestamp descending
        events.sort(key=lambda e: e["timestamp"], reverse=True)

        # Apply pagination
        return events[offset:offset + limit]

    async def get_matter_stats(self, matter_id: uuid.UUID) -> dict:
        """Quick stats for a matter — counts of documents, deadlines, analyses, notes."""
        from sqlalchemy import func

        docs_count = await self.db.execute(
            select(func.count()).where(and_(Document.matter_id == matter_id, Document.is_active == True))  # noqa: E712
        )
        deadlines_count = await self.db.execute(
            select(func.count()).where(MatterDeadline.matter_id == matter_id)
        )
        overdue_count = await self.db.execute(
            select(func.count()).where(
                and_(MatterDeadline.matter_id == matter_id, MatterDeadline.status == "overdue")
            )
        )
        notes_count = await self.db.execute(
            select(func.count()).where(MatterNote.matter_id == matter_id)
        )
        analyses_count = await self.db.execute(
            select(func.count()).where(AnalysisResult.matter_id == matter_id)
        )

        return {
            "documents": docs_count.scalar() or 0,
            "deadlines": deadlines_count.scalar() or 0,
            "overdue_deadlines": overdue_count.scalar() or 0,
            "notes": notes_count.scalar() or 0,
            "analyses": analyses_count.scalar() or 0,
        }
