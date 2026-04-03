import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk, DocumentVersion, ProcessingStatus
from app.models.legal_source import LegalCitation
from app.services.document_parser.parser import DocumentParserService, ParsedDocument
from app.services.ingestion.chunker import LegalDocumentChunker
from app.services.ingestion.citation_extractor import CitationExtractor
from app.services.ingestion.embedder import EmbeddingService
from app.services.storage import StorageService

logger = structlog.get_logger(__name__)


class IngestionPipeline:
    """End-to-end pipeline: parse -> chunk -> extract metadata -> embed -> index -> store."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.parser = DocumentParserService()
        self.chunker = LegalDocumentChunker()
        self.citation_extractor = CitationExtractor()
        self.embedder = EmbeddingService()
        self.storage = StorageService()

    async def process_document(self, document_id: uuid.UUID) -> Document:
        document = await self.db.get(Document, document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")

        try:
            await self._update_status(document, ProcessingStatus.PARSING)
            file_content = await self.storage.download_file(document.file_path)
            parsed = await self.parser.parse(file_content, document.file_name, document.mime_type)
            document.raw_text = parsed.raw_text
            document.page_count = parsed.page_count
            document.extracted_metadata = parsed.metadata

            await self._update_status(document, ProcessingStatus.CHUNKING)
            chunks = self.chunker.chunk_sections(parsed.sections)

            self._enrich_chunks_with_metadata(chunks, parsed, document.jurisdiction)

            await self._update_status(document, ProcessingStatus.EMBEDDING)
            chunk_texts = [c.content for c in chunks]
            embeddings = await self.embedder.embed_texts(chunk_texts)

            await self._update_status(document, ProcessingStatus.INDEXING)
            await self._store_chunks(document, chunks, embeddings)

            parties = self.citation_extractor.extract_parties(parsed.raw_text[:10000])
            dates = self.citation_extractor.extract_dates(parsed.raw_text[:10000])
            monetary = self.citation_extractor.extract_monetary_values(parsed.raw_text)

            if parties:
                document.parties = {"extracted": parties}
            if dates or monetary:
                meta = document.extracted_metadata or {}
                if dates:
                    meta["key_dates"] = dates[:50]
                if monetary:
                    meta["monetary_values"] = monetary[:50]
                document.extracted_metadata = meta

            await self._update_status(document, ProcessingStatus.COMPLETED)
            logger.info("document_processing_completed", document_id=str(document_id), chunks=len(chunks))
            return document

        except Exception as e:
            logger.error("document_processing_failed", document_id=str(document_id), error=str(e))
            document.processing_status = ProcessingStatus.FAILED
            document.processing_error = str(e)
            await self.db.flush()
            raise

    def _enrich_chunks_with_metadata(self, chunks, parsed: ParsedDocument, jurisdiction: str | None):
        for chunk in chunks:
            citations = self.citation_extractor.extract_citations(chunk.content, jurisdiction)
            dates = self.citation_extractor.extract_dates(chunk.content)
            parties = self.citation_extractor.extract_parties(chunk.content)
            monetary = self.citation_extractor.extract_monetary_values(chunk.content)

            chunk.metadata = {
                "citations": [{"raw": c.raw_text, "normalized": c.normalized, "type": c.citation_type} for c in citations],
                "dates": dates,
                "parties": parties,
                "monetary_values": monetary,
            }

    async def _store_chunks(
        self,
        document: Document,
        chunks: list,
        embeddings: list[list[float]],
    ):
        # Delete existing chunks for reprocessing
        existing = await self.db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
        for chunk_record in existing.scalars().all():
            await self.db.delete(chunk_record)

        for chunk, embedding in zip(chunks, embeddings):
            citations_data = chunk.metadata.get("citations", [])
            dates_data = chunk.metadata.get("dates", [])
            parties_data = chunk.metadata.get("parties", [])

            db_chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                embedding=embedding,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
                clause_number=chunk.clause_number,
                chunk_type=chunk.chunk_type,
                clause_type=self._infer_clause_type(chunk.content, chunk.section_title),
                parties_mentioned=parties_data if parties_data else None,
                dates_mentioned=dates_data if dates_data else None,
                citations=citations_data if citations_data else None,
                token_count=chunk.token_count,
            )
            self.db.add(db_chunk)

            for cite in citations_data:
                legal_citation = LegalCitation(
                    document_chunk_id=db_chunk.id,
                    citation_text=cite["raw"],
                    normalized_citation=cite.get("normalized"),
                    context=chunk.content[:500],
                )
                self.db.add(legal_citation)

        await self.db.flush()

    def _infer_clause_type(self, content: str, title: str | None) -> str | None:
        text = f"{title or ''} {content}".lower()
        clause_keywords = {
            "indemnity": ["indemnif", "indemnity", "hold harmless"],
            "liability": ["limitation of liability", "liability cap", "aggregate liability", "consequential damages"],
            "termination": ["terminat", "right to terminate", "notice of termination"],
            "confidentiality": ["confidential", "non-disclosure", "proprietary information"],
            "governing_law": ["governing law", "governed by", "laws of"],
            "dispute_resolution": ["arbitrat", "mediat", "dispute resolution", "jurisdiction"],
            "force_majeure": ["force majeure", "act of god", "beyond reasonable control"],
            "intellectual_property": ["intellectual property", "ip rights", "patent", "copyright", "trademark"],
            "payment": ["payment terms", "invoice", "fees", "compensation"],
            "warranty": ["warrant", "representation", "guarantee"],
            "assignment": ["assign", "transfer of rights", "novation"],
            "notice": ["notice", "notification", "written notice"],
            "entire_agreement": ["entire agreement", "whole agreement", "supersedes"],
            "amendment": ["amend", "modif", "variation"],
            "severability": ["severab", "invalid provision", "unenforceable"],
            "renewal": ["renewal", "auto-renew", "extension"],
            "insurance": ["insurance", "coverage", "policy"],
            "data_protection": ["data protection", "personal data", "gdpr", "ndpr", "privacy"],
            "non_compete": ["non-compete", "restrictive covenant", "non-solicitation"],
            "compliance": ["compliance", "anti-bribery", "anti-corruption", "sanctions"],
        }

        for clause_type, keywords in clause_keywords.items():
            if any(kw in text for kw in keywords):
                return clause_type
        return None

    async def _update_status(self, document: Document, status: ProcessingStatus):
        document.processing_status = status
        await self.db.flush()

    async def create_version(
        self,
        document: Document,
        file_content: bytes,
        user_id: uuid.UUID,
        change_summary: str | None = None,
    ) -> DocumentVersion:
        latest_version = 0
        if document.versions:
            latest_version = max(v.version_number for v in document.versions)

        content_hash = DocumentParserService.compute_hash(file_content)
        file_path = await self.storage.upload_file(
            file_content,
            f"documents/{document.organization_id}/{document.id}/v{latest_version + 1}/{document.file_name}",
        )

        version = DocumentVersion(
            document_id=document.id,
            version_number=latest_version + 1,
            file_path=file_path,
            file_size=len(file_content),
            content_hash=content_hash,
            change_summary=change_summary,
            created_by_id=user_id,
        )
        self.db.add(version)

        document.file_path = file_path
        document.file_size = len(file_content)
        document.content_hash = content_hash
        document.processing_status = ProcessingStatus.PENDING
        await self.db.flush()

        return version
