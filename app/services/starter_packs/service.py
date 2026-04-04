"""Starter pack import service — bulk imports key authorities for a jurisdiction."""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_source import AuthorityLevel, LegalSource, SourceType
from app.services.legal_sources import get_source_registry
from app.services.legal_sources.base import SourceContentType, SourceDocument
from app.services.starter_packs.definitions import STARTER_PACKS

logger = structlog.get_logger(__name__)

SOURCE_TYPE_MAP = {
    "statute": (SourceContentType.STATUTE, SourceType.STATUTE),
    "regulation": (SourceContentType.REGULATION, SourceType.REGULATION),
    "case_law": (SourceContentType.CASE_LAW, SourceType.CASE_LAW),
    "guidance": (SourceContentType.GUIDANCE, SourceType.GUIDANCE),
}


class StarterPackService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def list_packs() -> list[dict]:
        return [
            {
                "id": pack_id,
                "name": pack["name"],
                "jurisdiction": pack["jurisdiction"],
                "jurisdiction_name": pack["jurisdiction_name"],
                "description": pack["description"],
                "source_count": len(pack["sources"]),
            }
            for pack_id, pack in STARTER_PACKS.items()
        ]

    async def import_pack(
        self,
        pack_id: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        """Import all sources from a starter pack into the org's legal source library.

        Searches for each authority via the legal source adapters, then stores
        the best result as a LegalSource in the database.
        """
        pack = STARTER_PACKS.get(pack_id)
        if not pack:
            raise ValueError(f"Starter pack '{pack_id}' not found")

        registry = get_source_registry()
        jurisdiction = pack["jurisdiction"]

        imported = []
        skipped = []
        failed = []

        for source_def in pack["sources"]:
            query = source_def["query"]
            source_type = source_def["type"]
            description = source_def.get("description", "")

            content_type_enum, db_source_type = SOURCE_TYPE_MAP.get(
                source_type, (SourceContentType.STATUTE, SourceType.STATUTE)
            )

            try:
                # Check if already imported (by query match in title)
                existing = await self.db.execute(
                    select(LegalSource).where(
                        LegalSource.jurisdiction == jurisdiction,
                        LegalSource.title.ilike(f"%{query[:50]}%"),
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    skipped.append({"query": query, "reason": "already exists"})
                    continue

                # Search external sources
                results = await registry.search_all(
                    query=query,
                    jurisdiction=jurisdiction,
                    content_type=content_type_enum,
                    page_size=3,
                )

                # Find the best result
                best_doc: SourceDocument | None = None
                for result in results:
                    for doc in result.documents:
                        if doc.title and (query.lower() in doc.title.lower() or doc.title.lower() in query.lower()):
                            best_doc = doc
                            break
                    if best_doc:
                        break

                # If no exact match, take the first result
                if not best_doc:
                    for result in results:
                        if result.documents:
                            best_doc = result.documents[0]
                            break

                if not best_doc:
                    failed.append({"query": query, "reason": "no results found"})
                    continue

                # Store as LegalSource
                legal_source = LegalSource(
                    title=best_doc.title,
                    source_type=db_source_type,
                    authority_level=AuthorityLevel.BINDING if best_doc.authority_level == "binding" else AuthorityLevel.PERSUASIVE,
                    citation=best_doc.citation or best_doc.title,
                    external_id=f"{best_doc.source_adapter}:{best_doc.external_id}",
                    jurisdiction=jurisdiction,
                    court=best_doc.court_name,
                    court_level=best_doc.court_level.value if best_doc.court_level else None,
                    issuing_body=best_doc.issuing_body,
                    date_decided=best_doc.date_decided,
                    date_enacted=best_doc.date_enacted,
                    date_effective=best_doc.date_effective,
                    full_text=best_doc.full_text[:50000] if best_doc.full_text else None,
                    summary=best_doc.summary or description,
                    topics=best_doc.topics if best_doc.topics else [description],
                    is_current=best_doc.is_current,
                )
                self.db.add(legal_source)

                imported.append({
                    "title": best_doc.title,
                    "citation": best_doc.citation,
                    "type": source_type,
                    "source_adapter": best_doc.source_adapter,
                    "description": description,
                })

                logger.info("starter_pack_source_imported", query=query, title=best_doc.title)

            except Exception as e:
                logger.warning("starter_pack_import_failed", query=query, error=str(e))
                failed.append({"query": query, "reason": str(e)})

        await self.db.flush()

        logger.info(
            "starter_pack_import_completed",
            pack=pack_id,
            imported=len(imported),
            skipped=len(skipped),
            failed=len(failed),
        )

        return {
            "pack_id": pack_id,
            "pack_name": pack["name"],
            "jurisdiction": jurisdiction,
            "imported": imported,
            "imported_count": len(imported),
            "skipped": skipped,
            "skipped_count": len(skipped),
            "failed": failed,
            "failed_count": len(failed),
            "total_sources": len(pack["sources"]),
        }
