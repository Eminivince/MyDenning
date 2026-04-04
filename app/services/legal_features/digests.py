"""Scheduled digest service — generates periodic summaries of org activity.

Collects: upcoming deadlines, overdue deadlines, new regulatory alerts,
pending document reviews, matter updates, and feedback stats.
Delivers via the webhook system.
"""

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, ProcessingStatus
from app.models.legal_features import RegulatoryAlert, ScheduledDigest, WebhookEventType
from app.models.matter import Matter, MatterDeadline, MatterStatus, DeadlineStatus

logger = structlog.get_logger(__name__)

SCHEDULE_MAP = {
    "daily_9am": {"hours": 24},
    "weekly_monday": {"hours": 168},
    "weekly_friday": {"hours": 168},
}


class DigestService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_digest(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        schedule: str,
        webhook_id: uuid.UUID | None = None,
        include_deadlines: bool = True,
        include_regulatory_alerts: bool = True,
        include_pending_reviews: bool = True,
        include_matter_updates: bool = True,
        include_feedback_stats: bool = False,
    ) -> ScheduledDigest:
        digest = ScheduledDigest(
            organization_id=organization_id,
            created_by_id=user_id,
            name=name,
            schedule=schedule,
            webhook_id=webhook_id,
            include_deadlines=include_deadlines,
            include_regulatory_alerts=include_regulatory_alerts,
            include_pending_reviews=include_pending_reviews,
            include_matter_updates=include_matter_updates,
            include_feedback_stats=include_feedback_stats,
        )
        self.db.add(digest)
        await self.db.flush()
        return digest

    async def list_digests(self, organization_id: uuid.UUID) -> list[ScheduledDigest]:
        result = await self.db.execute(
            select(ScheduledDigest).where(ScheduledDigest.organization_id == organization_id)
        )
        return list(result.scalars().all())

    async def generate_digest(self, digest_id: uuid.UUID) -> dict:
        """Generate the digest payload for a specific scheduled digest."""
        digest = await self.db.get(ScheduledDigest, digest_id)
        if not digest:
            raise ValueError("Digest not found")

        org_id = digest.organization_id
        now = datetime.now(timezone.utc)
        payload: dict = {
            "digest_name": digest.name,
            "organization_id": str(org_id),
            "generated_at": now.isoformat(),
            "schedule": digest.schedule,
            "sections": {},
        }

        if digest.include_deadlines:
            payload["sections"]["deadlines"] = await self._collect_deadlines(org_id, now)

        if digest.include_regulatory_alerts:
            payload["sections"]["regulatory_alerts"] = await self._collect_regulatory_alerts(org_id, now)

        if digest.include_pending_reviews:
            payload["sections"]["pending_documents"] = await self._collect_pending_documents(org_id)

        if digest.include_matter_updates:
            payload["sections"]["active_matters"] = await self._collect_matter_summary(org_id)

        if digest.include_feedback_stats:
            from app.services.legal_features.feedback import FeedbackService
            fb_service = FeedbackService(self.db)
            payload["sections"]["feedback"] = await fb_service.get_stats(org_id)

        # Update last_sent
        digest.last_sent_at = now
        await self.db.flush()

        return payload

    async def process_all_due(self) -> int:
        """Check all digests and generate + deliver those that are due. Called by Celery beat."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(ScheduledDigest).where(ScheduledDigest.is_active == True)  # noqa: E712
        )
        digests = result.scalars().all()

        count = 0
        for digest in digests:
            if not self._is_due(digest, now):
                continue

            try:
                payload = await self.generate_digest(digest.id)

                # Deliver via webhook if configured
                if digest.webhook_id:
                    from app.services.legal_features.webhooks import WebhookService
                    wh_service = WebhookService(self.db)
                    await wh_service.fire_event(
                        organization_id=digest.organization_id,
                        event_type=WebhookEventType.DIGEST.value,
                        payload=payload,
                    )

                count += 1
                logger.info("digest_sent", digest_id=str(digest.id), name=digest.name)
            except Exception as e:
                logger.error("digest_failed", digest_id=str(digest.id), error=str(e))

        return count

    def _is_due(self, digest: ScheduledDigest, now: datetime) -> bool:
        if not digest.last_sent_at:
            return True
        interval = SCHEDULE_MAP.get(digest.schedule, {"hours": 24})
        return now >= digest.last_sent_at + timedelta(**interval)

    async def _collect_deadlines(self, org_id: uuid.UUID, now: datetime) -> dict:
        # Upcoming (next 7 days)
        upcoming_result = await self.db.execute(
            select(MatterDeadline)
            .join(Matter, MatterDeadline.matter_id == Matter.id)
            .where(
                and_(
                    Matter.organization_id == org_id,
                    MatterDeadline.status == DeadlineStatus.PENDING,
                    MatterDeadline.due_date <= now + timedelta(days=7),
                    MatterDeadline.due_date > now,
                )
            )
            .order_by(MatterDeadline.due_date.asc())
            .limit(20)
        )
        upcoming = upcoming_result.scalars().all()

        # Overdue
        overdue_result = await self.db.execute(
            select(MatterDeadline)
            .join(Matter, MatterDeadline.matter_id == Matter.id)
            .where(
                and_(
                    Matter.organization_id == org_id,
                    MatterDeadline.status == DeadlineStatus.OVERDUE,
                )
            )
            .order_by(MatterDeadline.due_date.asc())
            .limit(20)
        )
        overdue = overdue_result.scalars().all()

        return {
            "upcoming": [
                {"title": d.title, "due_date": d.due_date.isoformat(), "priority": d.priority, "is_court": d.is_court_deadline}
                for d in upcoming
            ],
            "upcoming_count": len(upcoming),
            "overdue": [
                {"title": d.title, "due_date": d.due_date.isoformat(), "priority": d.priority, "is_court": d.is_court_deadline}
                for d in overdue
            ],
            "overdue_count": len(overdue),
        }

    async def _collect_regulatory_alerts(self, org_id: uuid.UUID, now: datetime) -> dict:
        # Unread alerts from last 7 days
        result = await self.db.execute(
            select(RegulatoryAlert).where(
                and_(
                    RegulatoryAlert.organization_id == org_id,
                    RegulatoryAlert.is_read == False,  # noqa: E712
                    RegulatoryAlert.created_at >= now - timedelta(days=7),
                )
            )
            .order_by(RegulatoryAlert.created_at.desc())
            .limit(20)
        )
        alerts = result.scalars().all()

        return {
            "unread_alerts": [
                {"title": a.title, "risk_level": a.risk_level, "alert_type": a.alert_type, "created_at": a.created_at.isoformat()}
                for a in alerts
            ],
            "unread_count": len(alerts),
        }

    async def _collect_pending_documents(self, org_id: uuid.UUID) -> dict:
        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    Document.organization_id == org_id,
                    Document.processing_status.in_([ProcessingStatus.PENDING, ProcessingStatus.PARSING, ProcessingStatus.CHUNKING]),
                    Document.is_active == True,  # noqa: E712
                )
            )
        )
        pending = result.scalar() or 0

        failed_result = await self.db.execute(
            select(func.count()).where(
                and_(
                    Document.organization_id == org_id,
                    Document.processing_status == ProcessingStatus.FAILED,
                    Document.is_active == True,  # noqa: E712
                )
            )
        )
        failed = failed_result.scalar() or 0

        return {"pending_count": pending, "failed_count": failed}

    async def _collect_matter_summary(self, org_id: uuid.UUID) -> dict:
        active_result = await self.db.execute(
            select(func.count()).where(
                and_(Matter.organization_id == org_id, Matter.status == MatterStatus.ACTIVE)
            )
        )
        active = active_result.scalar() or 0

        return {"active_matters": active}
