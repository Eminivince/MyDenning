import asyncio
import uuid

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(self, document_id: str):
    """Process a document through the full ingestion pipeline."""
    logger.info("task_process_document_started", document_id=document_id)

    async def _process():
        from app.db.session import async_session_factory
        from app.services.ingestion.pipeline import IngestionPipeline
        from app.services.retrieval.elasticsearch_client import ElasticsearchClient

        async with async_session_factory() as db:
            try:
                pipeline = IngestionPipeline(db)
                document = await pipeline.process_document(uuid.UUID(document_id))

                # Index chunks in Elasticsearch
                es_client = ElasticsearchClient()
                await es_client.ensure_index()

                from sqlalchemy import select
                from app.models.document import DocumentChunk, Document

                doc = await db.get(Document, uuid.UUID(document_id))
                chunks_result = await db.execute(
                    select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document_id))
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
                        "parties_mentioned": chunk.parties_mentioned or [],
                    })

                if es_docs:
                    await es_client.index_chunks_bulk(es_docs)

                await es_client.close()

                # Fire webhook event
                try:
                    from app.services.legal_features.webhooks import WebhookService
                    wh_service = WebhookService(db)
                    await wh_service.fire_event(
                        organization_id=doc.organization_id,
                        event_type="document.processed",
                        payload={"document_id": document_id, "title": doc.title, "status": "completed", "chunks": len(chunks)},
                    )
                except Exception:
                    pass  # webhook failure should not break document processing

                await db.commit()

                logger.info("task_process_document_completed", document_id=document_id)
            except Exception as e:
                # Fire failure webhook
                try:
                    from app.services.legal_features.webhooks import WebhookService
                    wh_service = WebhookService(db)
                    await wh_service.fire_event(
                        organization_id=doc.organization_id if doc else uuid.UUID(int=0),
                        event_type="document.failed",
                        payload={"document_id": document_id, "error": str(e)},
                    )
                except Exception:
                    pass
                await db.rollback()
                logger.error("task_process_document_failed", document_id=document_id, error=str(e))
                raise

    try:
        _run_async(_process())
    except Exception as exc:
        logger.error("task_process_document_retry", document_id=document_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2)
def reindex_document_task(self, document_id: str):
    """Re-index a document's chunks in Elasticsearch."""
    logger.info("task_reindex_started", document_id=document_id)

    async def _reindex():
        from app.db.session import async_session_factory
        from app.services.retrieval.elasticsearch_client import ElasticsearchClient
        from sqlalchemy import select
        from app.models.document import Document, DocumentChunk

        async with async_session_factory() as db:
            es_client = ElasticsearchClient()
            await es_client.ensure_index()
            await es_client.delete_by_document_id(document_id)

            doc = await db.get(Document, uuid.UUID(document_id))
            if not doc:
                return

            chunks_result = await db.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(document_id))
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
            logger.info("task_reindex_completed", document_id=document_id, chunks=len(es_docs))

    try:
        _run_async(_reindex())
    except Exception as exc:
        raise self.retry(exc=exc)
