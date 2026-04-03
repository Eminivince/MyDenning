import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select, text, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.document import Document, DocumentChunk
from app.models.legal_source import LegalSource, AuthorityLevel
from app.services.ingestion.embedder import EmbeddingService
from app.services.retrieval.elasticsearch_client import ElasticsearchClient

logger = structlog.get_logger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    score: float
    page_number: int | None
    section_title: str | None
    clause_number: str | None
    clause_type: str | None
    document_title: str | None = None
    document_type: str | None = None
    jurisdiction: str | None = None
    citations: list | None = None
    source: str = "vector"  # vector, bm25, hybrid


@dataclass
class RetrievalFilters:
    organization_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] | None = None
    matter_id: uuid.UUID | None = None
    jurisdiction: str | None = None
    document_types: list[str] | None = None
    clause_types: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None


class HybridRetrievalService:
    """Hybrid retrieval combining BM25 keyword search, semantic vector search,
    metadata filtering, and citation-aware reranking."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedder = EmbeddingService()
        self.es_client = ElasticsearchClient()
        self.settings = get_settings()

    async def search(
        self,
        query: str,
        filters: RetrievalFilters | None = None,
        top_k: int | None = None,
        alpha: float = 0.5,  # weight for vector vs BM25 (1.0 = all vector, 0.0 = all BM25)
    ) -> list[RetrievedChunk]:
        top_k = top_k or self.settings.retrieval_top_k
        filters = filters or RetrievalFilters()

        vector_results = await self._vector_search(query, filters, top_k * 2)
        bm25_results = await self._bm25_search(query, filters, top_k * 2)

        merged = self._reciprocal_rank_fusion(vector_results, bm25_results, alpha=alpha)

        reranked = await self._citation_aware_rerank(merged, query, filters)

        return reranked[:top_k]

    async def _vector_search(
        self,
        query: str,
        filters: RetrievalFilters,
        limit: int,
    ) -> list[RetrievedChunk]:
        query_embedding = await self.embedder.embed_single(query)

        filter_conditions = []
        join_conditions = [DocumentChunk.document_id == Document.id]

        if filters.organization_id:
            filter_conditions.append(Document.organization_id == filters.organization_id)
        if filters.document_ids:
            filter_conditions.append(Document.id.in_(filters.document_ids))
        if filters.matter_id:
            filter_conditions.append(Document.matter_id == filters.matter_id)
        if filters.jurisdiction:
            filter_conditions.append(Document.jurisdiction == filters.jurisdiction)
        if filters.document_types:
            filter_conditions.append(Document.document_type.in_(filters.document_types))
        if filters.clause_types:
            filter_conditions.append(DocumentChunk.clause_type.in_(filters.clause_types))

        filter_conditions.append(Document.is_active == True)  # noqa: E712
        filter_conditions.append(Document.processing_status == "completed")

        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        distance_expr = DocumentChunk.embedding.cosine_distance(query_embedding)

        stmt = (
            select(
                DocumentChunk,
                Document.title.label("doc_title"),
                Document.document_type.label("doc_type"),
                Document.jurisdiction.label("doc_jurisdiction"),
                distance_expr.label("distance"),
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(and_(*filter_conditions))
            .where(DocumentChunk.embedding.isnot(None))
            .order_by(distance_expr)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        chunks = []
        for row in rows:
            chunk = row[0]
            similarity = 1.0 - row.distance
            chunks.append(RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                score=similarity,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
                clause_number=chunk.clause_number,
                clause_type=chunk.clause_type,
                document_title=row.doc_title,
                document_type=row.doc_type,
                jurisdiction=row.doc_jurisdiction,
                citations=chunk.citations,
                source="vector",
            ))

        return chunks

    async def _bm25_search(
        self,
        query: str,
        filters: RetrievalFilters,
        limit: int,
    ) -> list[RetrievedChunk]:
        es_filters = {}
        if filters.organization_id:
            es_filters["organization_id"] = str(filters.organization_id)
        if filters.document_ids:
            es_filters["document_id"] = [str(d) for d in filters.document_ids]
        if filters.jurisdiction:
            es_filters["jurisdiction"] = filters.jurisdiction
        if filters.document_types:
            es_filters["document_type"] = filters.document_types
        if filters.clause_types:
            es_filters["clause_type"] = filters.clause_types

        es_results = await self.es_client.search(query, es_filters, limit)

        chunks = []
        for hit in es_results:
            chunks.append(RetrievedChunk(
                chunk_id=uuid.UUID(hit["chunk_id"]),
                document_id=uuid.UUID(hit["document_id"]),
                content=hit["content"],
                score=hit["score"],
                page_number=hit.get("page_number"),
                section_title=hit.get("section_title"),
                clause_number=hit.get("clause_number"),
                clause_type=hit.get("clause_type"),
                document_title=hit.get("document_title"),
                document_type=hit.get("document_type"),
                jurisdiction=hit.get("jurisdiction"),
                citations=hit.get("citations"),
                source="bm25",
            ))

        return chunks

    def _reciprocal_rank_fusion(
        self,
        vector_results: list[RetrievedChunk],
        bm25_results: list[RetrievedChunk],
        alpha: float = 0.5,
        k: int = 60,
    ) -> list[RetrievedChunk]:
        """Combine results using Reciprocal Rank Fusion."""
        scores: dict[uuid.UUID, float] = {}
        chunk_map: dict[uuid.UUID, RetrievedChunk] = {}

        for rank, chunk in enumerate(vector_results):
            rrf_score = alpha * (1.0 / (k + rank + 1))
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + rrf_score
            chunk_map[chunk.chunk_id] = chunk

        for rank, chunk in enumerate(bm25_results):
            rrf_score = (1 - alpha) * (1.0 / (k + rank + 1))
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + rrf_score
            if chunk.chunk_id not in chunk_map:
                chunk_map[chunk.chunk_id] = chunk

        sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

        results = []
        for cid in sorted_ids:
            chunk = chunk_map[cid]
            chunk.score = scores[cid]
            chunk.source = "hybrid"
            results.append(chunk)

        return results

    async def _citation_aware_rerank(
        self,
        chunks: list[RetrievedChunk],
        query: str,
        filters: RetrievalFilters,
    ) -> list[RetrievedChunk]:
        """Boost chunks that cite binding authority or highly-cited sources."""
        for chunk in chunks:
            boost = 0.0

            if chunk.citations:
                for cite in chunk.citations:
                    cite_type = cite.get("type", "")
                    if cite_type in ("case_law", "statute"):
                        boost += 0.02

                    normalized = cite.get("normalized", "")
                    if normalized:
                        source_result = await self.db.execute(
                            select(LegalSource).where(
                                LegalSource.citation == normalized
                            ).limit(1)
                        )
                        source = source_result.scalar_one_or_none()
                        if source:
                            if source.authority_level == AuthorityLevel.BINDING:
                                boost += 0.05
                            if source.court_level and source.court_level <= 2:
                                boost += 0.03
                            if source.is_current:
                                boost += 0.02

            if chunk.clause_type and filters.clause_types:
                if chunk.clause_type in filters.clause_types:
                    boost += 0.03

            chunk.score += boost

        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks

    async def search_legal_sources(
        self,
        query: str,
        jurisdiction: str | None = None,
        source_types: list[str] | None = None,
        court_level: int | None = None,
        binding_only: bool = False,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search the legal sources / knowledge graph directly."""
        conditions = [LegalSource.is_current == True]  # noqa: E712

        if jurisdiction:
            conditions.append(LegalSource.jurisdiction == jurisdiction)
        if source_types:
            conditions.append(LegalSource.source_type.in_(source_types))
        if court_level:
            conditions.append(LegalSource.court_level <= court_level)
        if binding_only:
            conditions.append(LegalSource.authority_level == AuthorityLevel.BINDING)

        stmt = (
            select(LegalSource)
            .where(and_(*conditions))
            .order_by(LegalSource.date_decided.desc().nullslast())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        sources = result.scalars().all()

        return [
            {
                "id": str(s.id),
                "title": s.title,
                "citation": s.citation,
                "source_type": s.source_type.value,
                "authority_level": s.authority_level.value,
                "jurisdiction": s.jurisdiction,
                "court": s.court,
                "court_level": s.court_level,
                "date_decided": s.date_decided.isoformat() if s.date_decided else None,
                "summary": s.summary,
                "is_current": s.is_current,
            }
            for s in sources
        ]
