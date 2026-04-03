"""CanLII adapter — Canadian Legal Information Institute.

Source: https://api.canlii.org/v1/ (REST API)
Coverage: Canadian case law and legislation (federal + provincial)
Auth: API key required (free, register at developer.canlii.org)
Rate limit: Varies by plan
"""

import time
from datetime import date

import structlog

from app.core.config import get_settings
from app.services.legal_sources.adapters.http_client import AdapterHTTPClient
from app.services.legal_sources.base import (
    AdapterCapabilities,
    CourtLevel,
    LegalSourceAdapter,
    SourceContentType,
    SourceDocument,
    SourceSearchResult,
)

logger = structlog.get_logger(__name__)

CANADIAN_COURT_LEVELS = {
    "scc": CourtLevel.SUPREME, "csc": CourtLevel.SUPREME,
    "fca": CourtLevel.APPELLATE, "caf": CourtLevel.APPELLATE,
    "onca": CourtLevel.APPELLATE, "bcca": CourtLevel.APPELLATE, "abca": CourtLevel.APPELLATE,
    "fc": CourtLevel.HIGH, "cf": CourtLevel.HIGH,
    "onsc": CourtLevel.HIGH, "bcsc": CourtLevel.HIGH,
    "tcc": CourtLevel.TRIBUNAL,
}


class CanLIIAdapter(LegalSourceAdapter):
    """Canadian case law and legislation from CanLII."""

    BASE_URL = "https://api.canlii.org/v1"

    def __init__(self):
        settings = get_settings()
        self._api_key = getattr(settings, "canlii_api_key", "")
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="canlii",
            rate_limit_per_minute=30,
        )

    @property
    def adapter_name(self) -> str:
        return "canlii"

    @property
    def display_name(self) -> str:
        return "CanLII — Canadian Legal Information Institute"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[SourceContentType.CASE_LAW, SourceContentType.STATUTE],
            jurisdictions=["CA"],
            supports_full_text=True,
            supports_citation_lookup=True,
            supports_keyword_search=True,
            supports_date_filter=True,
            supports_court_filter=True,
            max_results_per_request=100,
            rate_limit_per_minute=30,
            requires_api_key=True,
        )

    async def search(
        self,
        query: str,
        content_type: SourceContentType | None = None,
        jurisdiction: str | None = None,
        court_level: CourtLevel | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SourceSearchResult:
        if not self._api_key:
            return SourceSearchResult([], 0, page, page_size, query, self.adapter_name, 0)

        start = time.time()
        params = {
            "api_key": self._api_key,
            "fullText": query,
            "resultCount": min(page_size, 100),
            "offset": (page - 1) * page_size,
        }

        path = "/search"
        if content_type == SourceContentType.CASE_LAW:
            path = "/caseBrowse/en"
        elif content_type == SourceContentType.STATUTE:
            path = "/legislationBrowse/en"

        try:
            data = await self._http.get(path, params=params)
            if isinstance(data, dict):
                results = data.get("results", data.get("caseBrowse", data.get("legislationBrowse", [])))
                documents = [self._parse_result(r) for r in results if r]
                documents = [d for d in documents if d]
                total = data.get("resultCount", len(documents))
            else:
                documents, total = [], 0
        except Exception as e:
            logger.error("canlii_search_failed", error=str(e))
            documents, total = [], 0

        return SourceSearchResult(
            documents=documents,
            total_count=total,
            page=page,
            page_size=page_size,
            query=query,
            source_adapter=self.adapter_name,
            search_time_ms=int((time.time() - start) * 1000),
        )

    async def get_by_citation(self, citation: str) -> SourceDocument | None:
        if not self._api_key:
            return None
        results = await self.search(citation, page_size=1)
        return results.documents[0] if results.documents else None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        return None  # CanLII uses database/case ID combos

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        return await self._http.ping()

    def _parse_result(self, item: dict) -> SourceDocument | None:
        try:
            title = item.get("title", item.get("shortTitle", ""))
            citation = item.get("citation", "")

            db_id = item.get("databaseId", "")
            court_level = CANADIAN_COURT_LEVELS.get(db_id.lower(), CourtLevel.HIGH)

            content_type = SourceContentType.CASE_LAW
            if item.get("type") == "legislation":
                content_type = SourceContentType.STATUTE

            parsed_date = None
            date_str = item.get("dateDecided", item.get("date", ""))
            if date_str:
                try:
                    parsed_date = date.fromisoformat(str(date_str)[:10])
                except (ValueError, TypeError):
                    pass

            return SourceDocument(
                external_id=f"{db_id}/{item.get('caseId', item.get('legislationId', ''))}",
                source_adapter=self.adapter_name,
                title=title,
                content_type=content_type,
                citation=citation or title,
                jurisdiction="Canada",
                jurisdiction_code="CA",
                court_name=item.get("databaseName", ""),
                court_level=court_level,
                date_decided=parsed_date,
                source_url=item.get("url", ""),
                is_current=True,
                authority_level="binding",
                raw_metadata=item,
            )
        except Exception as e:
            logger.warning("canlii_parse_failed", error=str(e))
            return None
