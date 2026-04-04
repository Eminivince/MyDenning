"""Feedback service — collects and queries user ratings on AI outputs."""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_features import Feedback, FeedbackRating

logger = structlog.get_logger(__name__)


class FeedbackService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        resource_type: str,
        resource_id: str,
        rating: FeedbackRating,
        comment: str | None = None,
        correction: str | None = None,
        correction_type: str | None = None,
        query: str | None = None,
        jurisdiction: str | None = None,
        clause_type: str | None = None,
        analysis_id: uuid.UUID | None = None,
        conversation_message_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> Feedback:
        # Upsert: if user already rated this resource, update it
        existing = await self.db.execute(
            select(Feedback).where(
                and_(
                    Feedback.user_id == user_id,
                    Feedback.resource_type == resource_type,
                    Feedback.resource_id == resource_id,
                )
            )
        )
        fb = existing.scalar_one_or_none()

        if fb:
            fb.rating = rating
            fb.comment = comment
            fb.correction = correction
            fb.correction_type = correction_type
        else:
            fb = Feedback(
                organization_id=organization_id,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                rating=rating,
                comment=comment,
                correction=correction,
                correction_type=correction_type,
                query=query,
                jurisdiction=jurisdiction,
                clause_type=clause_type,
                analysis_id=analysis_id,
                conversation_message_id=conversation_message_id,
                metadata=metadata,
            )
            self.db.add(fb)

        await self.db.flush()
        logger.info("feedback_submitted", resource_type=resource_type, resource_id=resource_id, rating=rating.value)
        return fb

    async def get_for_resource(self, resource_type: str, resource_id: str) -> list[Feedback]:
        result = await self.db.execute(
            select(Feedback).where(
                and_(Feedback.resource_type == resource_type, Feedback.resource_id == resource_id)
            )
        )
        return list(result.scalars().all())

    async def get_stats(self, organization_id: uuid.UUID, resource_type: str | None = None) -> dict:
        """Get aggregate feedback stats for the organization."""
        conditions = [Feedback.organization_id == organization_id]
        if resource_type:
            conditions.append(Feedback.resource_type == resource_type)

        total_result = await self.db.execute(
            select(func.count()).where(and_(*conditions))
        )
        total = total_result.scalar() or 0

        positive_result = await self.db.execute(
            select(func.count()).where(
                and_(*conditions, Feedback.rating == FeedbackRating.POSITIVE)
            )
        )
        positive = positive_result.scalar() or 0

        negative = total - positive

        # Most corrected areas
        corrections_result = await self.db.execute(
            select(Feedback.correction_type, func.count().label("count"))
            .where(and_(*conditions, Feedback.correction_type.isnot(None)))
            .group_by(Feedback.correction_type)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_corrections = [
            {"type": row.correction_type, "count": row.count}
            for row in corrections_result.all()
        ]

        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "satisfaction_rate": round(positive / total * 100, 1) if total > 0 else 0,
            "top_correction_types": top_corrections,
        }
