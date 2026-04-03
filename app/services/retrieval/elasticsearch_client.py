from typing import Any

import structlog
from elasticsearch import AsyncElasticsearch

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class ElasticsearchClient:
    """Elasticsearch client for BM25 keyword search over document chunks."""

    INDEX_SETTINGS = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "legal_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "stop", "snowball"],
                    }
                }
            },
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "organization_id": {"type": "keyword"},
                "content": {"type": "text", "analyzer": "legal_analyzer"},
                "section_title": {"type": "text", "analyzer": "legal_analyzer"},
                "clause_number": {"type": "keyword"},
                "clause_type": {"type": "keyword"},
                "chunk_type": {"type": "keyword"},
                "document_title": {"type": "text", "analyzer": "legal_analyzer"},
                "document_type": {"type": "keyword"},
                "jurisdiction": {"type": "keyword"},
                "page_number": {"type": "integer"},
                "citations": {"type": "nested", "properties": {
                    "raw": {"type": "text"},
                    "normalized": {"type": "keyword"},
                    "type": {"type": "keyword"},
                }},
                "parties_mentioned": {"type": "text"},
                "dates_mentioned": {"type": "text"},
            }
        },
    }

    def __init__(self):
        settings = get_settings()
        self._client = AsyncElasticsearch(
            hosts=[settings.elasticsearch_url],
            retry_on_timeout=True,
            max_retries=3,
        )
        self._index = f"{settings.elasticsearch_index_prefix}_chunks"

    async def ensure_index(self):
        exists = await self._client.indices.exists(index=self._index)
        if not exists:
            await self._client.indices.create(index=self._index, body=self.INDEX_SETTINGS)
            logger.info("elasticsearch_index_created", index=self._index)

    async def index_chunk(self, chunk_data: dict) -> None:
        await self._client.index(
            index=self._index,
            id=chunk_data["chunk_id"],
            document=chunk_data,
        )

    async def index_chunks_bulk(self, chunks: list[dict]) -> None:
        if not chunks:
            return

        actions = []
        for chunk in chunks:
            actions.append({"index": {"_index": self._index, "_id": chunk["chunk_id"]}})
            actions.append(chunk)

        await self._client.bulk(operations=actions, refresh=True)
        logger.info("chunks_indexed", count=len(chunks))

    async def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        must_clauses: list[dict] = [
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "content^3",
                        "section_title^2",
                        "document_title",
                        "citations.raw",
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        ]

        filter_clauses: list[dict] = []
        if filters:
            if "organization_id" in filters:
                filter_clauses.append({"term": {"organization_id": filters["organization_id"]}})
            if "document_id" in filters:
                if isinstance(filters["document_id"], list):
                    filter_clauses.append({"terms": {"document_id": filters["document_id"]}})
                else:
                    filter_clauses.append({"term": {"document_id": filters["document_id"]}})
            if "jurisdiction" in filters:
                filter_clauses.append({"term": {"jurisdiction": filters["jurisdiction"]}})
            if "document_type" in filters:
                if isinstance(filters["document_type"], list):
                    filter_clauses.append({"terms": {"document_type": filters["document_type"]}})
                else:
                    filter_clauses.append({"term": {"document_type": filters["document_type"]}})
            if "clause_type" in filters:
                if isinstance(filters["clause_type"], list):
                    filter_clauses.append({"terms": {"clause_type": filters["clause_type"]}})
                else:
                    filter_clauses.append({"term": {"clause_type": filters["clause_type"]}})

        body = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses,
                }
            },
            "size": limit,
            "_source": True,
        }

        try:
            response = await self._client.search(index=self._index, body=body)
            hits = response.get("hits", {}).get("hits", [])

            results = []
            for hit in hits:
                source = hit["_source"]
                source["score"] = hit["_score"]
                results.append(source)

            return results
        except Exception as e:
            logger.warning("elasticsearch_search_failed", error=str(e))
            return []

    async def delete_by_document_id(self, document_id: str) -> None:
        await self._client.delete_by_query(
            index=self._index,
            body={"query": {"term": {"document_id": document_id}}},
        )

    async def close(self):
        await self._client.close()
