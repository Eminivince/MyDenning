"""Indian Kanoon adapter — Indian legal search engine.

Source: https://api.indiankanoon.org
Coverage: Indian case law (Supreme Court, High Courts, Tribunals), Acts, Rules
Auth: API key required (apply at indiankanoon.org/api)
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

INDIAN_COURTS = {
    "supreme court": CourtLevel.SUPREME,
    "high court": CourtLevel.HIGH,
    "delhi high court": CourtLevel.HIGH,
    "bombay high court": CourtLevel.HIGH,
    "madras high court": CourtLevel.HIGH,
    "calcutta high court": CourtLevel.HIGH,
    "district court": CourtLevel.DISTRICT,
    "tribunal": CourtLevel.TRIBUNAL,
    "nclat": CourtLevel.TRIBUNAL,
    "nclt": CourtLevel.TRIBUNAL,
    "itat": CourtLevel.TRIBUNAL,
}


class IndianKanoonAdapter(LegalSourceAdapter):
    """Indian case law and legislation from Indian Kanoon."""

    BASE_URL = "https://api.indiankanoon.org"

    def __init__(self):
        settings = get_settings()
        self._api_key = getattr(settings, "indian_kanoon_api_key", "")
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Token {self._api_key}"
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="indian_kanoon",
            rate_limit_per_minute=10,
            headers=headers,
        )

    @property
    def adapter_name(self) -> str:
        return "indian_kanoon"

    @property
    def display_name(self) -> str:
        return "Indian Kanoon — Indian Legal Search"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[SourceContentType.CASE_LAW, SourceContentType.STATUTE],
            jurisdictions=["IN"],
            supports_full_text=True,
            supports_citation_lookup=True,
            supports_keyword_search=True,
            supports_date_filter=True,
            supports_court_filter=True,
            max_results_per_request=10,
            rate_limit_per_minute=10,
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
        params = {"formInput": query, "pagenum": page - 1}

        if date_from:
            params["fromdate"] = date_from.strftime("%d-%m-%Y")
        if date_to:
            params["todate"] = date_to.strftime("%d-%m-%Y")

        try:
            data = await self._http.post("/search/", data=params)
            if isinstance(data, dict):
                documents = self._parse_results(data)
                total = data.get("found", len(documents))
            else:
                documents, total = [], 0
        except Exception as e:
            logger.error("indian_kanoon_search_failed", error=str(e))
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
        results = await self.search(f'"{citation}"', page_size=1)
        return results.documents[0] if results.documents else None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        if not self._api_key:
            return None
        try:
            data = await self._http.post("/doc/", data={"docid": external_id})
            if isinstance(data, dict):
                return self._parse_doc(data)
        except Exception as e:
            logger.error("indian_kanoon_get_failed", id=external_id, error=str(e))
        return None

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        return await self._http.ping()

    def _parse_results(self, data: dict) -> list[SourceDocument]:
        documents = []
        for item in data.get("docs", []):
            doc = self._parse_doc(item)
            if doc:
                documents.append(doc)
        return documents

    def _parse_doc(self, item: dict) -> SourceDocument | None:
        try:
            title = item.get("title", "")
            doc_id = str(item.get("tid", item.get("docid", "")))

            court_name = item.get("docsource", "")
            court_level = CourtLevel.HIGH
            if court_name:
                for keyword, level in INDIAN_COURTS.items():
                    if keyword in court_name.lower():
                        court_level = level
                        break

            content_type = SourceContentType.CASE_LAW
            if item.get("doctype") == "legislation":
                content_type = SourceContentType.STATUTE

            parsed_date = None
            date_str = item.get("publishdate", "")
            if date_str:
                try:
                    from datetime import datetime
                    parsed_date = datetime.strptime(date_str, "%d-%m-%Y").date()
                except (ValueError, TypeError):
                    pass

            return SourceDocument(
                external_id=doc_id,
                source_adapter=self.adapter_name,
                title=title,
                content_type=content_type,
                citation=item.get("citation", title),
                jurisdiction="India",
                jurisdiction_code="IN",
                court_name=court_name,
                court_level=court_level,
                date_decided=parsed_date,
                full_text=item.get("doc", ""),
                summary=item.get("headline", item.get("snippet", "")),
                source_url=f"https://indiankanoon.org/doc/{doc_id}/",
                is_current=True,
                authority_level="binding",
                raw_metadata=item,
            )
        except Exception as e:
            logger.warning("indian_kanoon_parse_failed", error=str(e))
            return None
