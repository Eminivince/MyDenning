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
