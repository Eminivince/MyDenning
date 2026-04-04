import asyncio
from datetime import datetime, timedelta, timezone

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task
def check_overdue_deadlines():
    """Check for overdue deadlines and update their status."""
    logger.info("task_check_deadlines_started")

    async def _check():
        from sqlalchemy import select, and_, update
        from app.db.session import async_session_factory
        from app.models.matter import MatterDeadline, DeadlineStatus

        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)

            # Mark overdue deadlines
            stmt = (
                update(MatterDeadline)
                .where(
                    and_(
                        MatterDeadline.due_date < now,
                        MatterDeadline.status == DeadlineStatus.PENDING,
                    )
                )
                .values(status=DeadlineStatus.OVERDUE)
                .returning(MatterDeadline.id)
            )
            result = await db.execute(stmt)
            overdue_ids = result.scalars().all()
            await db.commit()

            if overdue_ids:
                logger.warning("deadlines_marked_overdue", count=len(overdue_ids))

    _run_async(_check())


@celery_app.task
def sync_elasticsearch():
    """Sync any unindexed document chunks to Elasticsearch."""
    logger.info("task_elasticsearch_sync_started")

    async def _sync():
        from sqlalchemy import select, and_
        from app.db.session import async_session_factory
        from app.models.document import Document, DocumentChunk, ProcessingStatus
        from app.services.retrieval.elasticsearch_client import ElasticsearchClient

        async with async_session_factory() as db:
            es_client = ElasticsearchClient()
            await es_client.ensure_index()

            # Find completed documents with chunks
            stmt = (
                select(Document)
                .where(
                    and_(
                        Document.processing_status == ProcessingStatus.COMPLETED,
                        Document.is_active == True,  # noqa: E712
                    )
                )
                .limit(50)
            )
            result = await db.execute(stmt)
            documents = result.scalars().all()

            for doc in documents:
                chunks_result = await db.execute(
                    select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
                )
                chunks = chunks_result.scalars().all()

                es_docs = []
                for chunk in chunks:
                    es_docs.append({
                        "chunk_id": str(chunk.id),
                        "document_id": str(chunk.document_id),
                        "organization_id": str(doc.organization_id),
                        "content": chunk.content,
                        "section_title": chunk.section_title,
                        "clause_number": chunk.clause_number,
                        "clause_type": chunk.clause_type,
                        "chunk_type": chunk.chunk_type,
                        "document_title": doc.title,
                        "document_type": doc.document_type.value,
                        "jurisdiction": doc.jurisdiction,
                        "page_number": chunk.page_number,
                        "citations": chunk.citations or [],
                    })

                if es_docs:
                    await es_client.index_chunks_bulk(es_docs)

            await es_client.close()
            logger.info("task_elasticsearch_sync_completed", documents=len(documents))

    _run_async(_sync())


@celery_app.task
def check_regulatory_changes():
    """Check all monitored regulations for changes. Runs every 6 hours via beat."""
    logger.info("task_regulatory_check_started")

    async def _check():
        from app.db.session import async_session_factory
        from app.services.legal_features.regulatory_monitor import RegulatoryMonitorService

        async with async_session_factory() as db:
            service = RegulatoryMonitorService(db)
            total = await service.check_all_due()
            await db.commit()
            logger.info("task_regulatory_check_completed", regulations_checked=total)

    _run_async(_check())


@celery_app.task
def process_scheduled_digests():
    """Process all due scheduled digests. Runs hourly via beat."""
    logger.info("task_digests_started")

    async def _process():
        from app.db.session import async_session_factory
        from app.services.legal_features.digests import DigestService

        async with async_session_factory() as db:
            service = DigestService(db)
            count = await service.process_all_due()
            await db.commit()
            logger.info("task_digests_completed", digests_sent=count)

    _run_async(_process())


@celery_app.task
def send_calendar_reminders():
    """Check for upcoming calendar events and fire reminder webhooks. Runs every 15 min."""
    logger.info("task_calendar_reminders_started")

    async def _send():
        from sqlalchemy import select, and_
        from app.db.session import async_session_factory
        from app.models.matter import CalendarEvent

        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)

            # Find events starting in the next 60 minutes that have reminders
            upcoming = await db.execute(
                select(CalendarEvent).where(
                    and_(
                        CalendarEvent.start_time > now,
                        CalendarEvent.start_time <= now + timedelta(hours=1),
                        CalendarEvent.reminders.isnot(None),
                    )
                )
            )
            events = upcoming.scalars().all()

            fired = 0
            for event in events:
                if not event.reminders:
                    continue

                for reminder in event.reminders:
                    minutes_before = reminder.get("minutes_before", 30)
                    reminder_time = event.start_time - timedelta(minutes=minutes_before)

                    # Fire if reminder time is within the last 15 minutes (our check interval)
                    if now - timedelta(minutes=15) <= reminder_time <= now:
                        try:
                            from app.services.legal_features.webhooks import WebhookService
                            wh_service = WebhookService(db)
                            await wh_service.fire_event(
                                organization_id=event.organization_id,
                                event_type="deadline.approaching",
                                payload={
                                    "event_id": str(event.id),
                                    "title": event.title,
                                    "event_type": event.event_type.value,
                                    "start_time": event.start_time.isoformat(),
                                    "location": event.location,
                                    "matter_id": str(event.matter_id) if event.matter_id else None,
                                    "minutes_until": int((event.start_time - now).total_seconds() / 60),
                                },
                            )
                            fired += 1
                        except Exception as e:
                            logger.warning("calendar_reminder_failed", event_id=str(event.id), error=str(e))

            await db.commit()
            logger.info("task_calendar_reminders_completed", events_checked=len(events), reminders_fired=fired)

    _run_async(_send())


@celery_app.task
def check_task_deadlines():
    """Fire webhooks for tasks due in the next 24 hours. Runs hourly."""
    logger.info("task_deadline_reminders_started")

    async def _check():
        from sqlalchemy import select, and_
        from app.db.session import async_session_factory
        from app.models.matter import Task, TaskStatus

        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)
            upcoming = await db.execute(
                select(Task).where(and_(
                    Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
                    Task.due_date.isnot(None),
                    Task.due_date > now,
                    Task.due_date <= now + timedelta(hours=24),
                ))
            )
            tasks = upcoming.scalars().all()
            fired = 0
            for task in tasks:
                try:
                    from app.services.legal_features.webhooks import WebhookService
                    wh_service = WebhookService(db)
                    await wh_service.fire_event(
                        organization_id=task.organization_id,
                        event_type="deadline.approaching",
                        payload={
                            "type": "task_due_soon",
                            "task_id": str(task.id),
                            "title": task.title,
                            "due_date": task.due_date.isoformat(),
                            "assigned_to_id": str(task.assigned_to_id) if task.assigned_to_id else None,
                            "priority": task.priority,
                            "hours_until": int((task.due_date - now).total_seconds() / 3600),
                        },
                    )
                    fired += 1
                except Exception:
                    pass
            await db.commit()
            logger.info("task_deadline_reminders_completed", tasks_checked=len(tasks), fired=fired)

    _run_async(_check())
