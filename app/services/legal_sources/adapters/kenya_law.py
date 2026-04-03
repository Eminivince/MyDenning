"""Kenya Law adapter — Kenya Law Reports.

Source: http://kenyalaw.org / Kenya Law Reports API
Coverage: Kenyan case law, Acts of Parliament, subsidiary legislation
Auth: None required
Rate limit: Reasonable use
"""

import time
from datetime import date

import structlog

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

KENYAN_COURTS = {
    "supreme court": CourtLevel.SUPREME,
    "court of appeal": CourtLevel.APPELLATE,
    "high court": CourtLevel.HIGH,
    "employment and labour relations court": CourtLevel.HIGH,
    "environment and land court": CourtLevel.HIGH,
    "magistrate": CourtLevel.MAGISTRATE,
    "tribunal": CourtLevel.TRIBUNAL,
}


class KenyaLawAdapter(LegalSourceAdapter):
    """Kenyan law from Kenya Law Reports."""

    BASE_URL = "http://kenyalaw.org"

    def __init__(self):
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="kenya_law",
            rate_limit_per_minute=15,
            timeout=45.0,
            headers={"Accept": "application/json, text/html"},
        )

    @property
    def adapter_name(self) -> str:
        return "kenya_law"

    @property
    def display_name(self) -> str:
        return "Kenya Law Reports"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[SourceContentType.CASE_LAW, SourceContentType.STATUTE],
            jurisdictions=["KE"],
            supports_full_text=True,
            supports_citation_lookup=True,
            supports_keyword_search=True,
            supports_date_filter=True,
            supports_court_filter=True,
            max_results_per_request=20,
            rate_limit_per_minute=15,
            requires_api_key=False,
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
        start = time.time()

        params = {"q": query, "page": page, "per_page": min(page_size, 20)}

        path = "/api/search"
        if content_type == SourceContentType.CASE_LAW:
            path = "/api/search/caselaw"
        elif content_type == SourceContentType.STATUTE:
            path = "/api/search/legislation"

        if date_from:
            params["year_from"] = str(date_from.year)
        if date_to:
            params["year_to"] = str(date_to.year)

        try:
            data = await self._http.get(path, params=params)
            if isinstance(data, dict):
                documents = []
                for item in data.get("results", data.get("items", [])):
                    doc = self._parse_result(item)
                    if doc:
                        documents.append(doc)
                total = data.get("count", data.get("total", len(documents)))
            else:
                documents, total = [], 0
        except Exception as e:
            logger.error("kenya_law_search_failed", error=str(e))
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
        results = await self.search(f'"{citation}"', page_size=3)
        return results.documents[0] if results.documents else None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        try:
            data = await self._http.get(f"/api/document/{external_id}")
            if isinstance(data, dict):
                return self._parse_result(data)
        except Exception:
            pass
        return None

    async def health_check(self) -> bool:
        return await self._http.ping()

    def _parse_result(self, item: dict) -> SourceDocument | None:
        try:
            title = item.get("title", item.get("case_name", ""))
            court_name = item.get("court", "")
            court_level = None
            if court_name:
                for keyword, level in KENYAN_COURTS.items():
                    if keyword in court_name.lower():
                        court_level = level
                        break

            content_type = SourceContentType.CASE_LAW
            if item.get("type") == "legislation" or "act" in title.lower():
                content_type = SourceContentType.STATUTE

            parsed_date = None
            date_str = item.get("date", item.get("year", ""))
            if date_str:
                try:
                    if len(str(date_str)) == 4:
                        parsed_date = date(int(date_str), 1, 1)
                    else:
                        parsed_date = date.fromisoformat(str(date_str)[:10])
                except (ValueError, TypeError):
                    pass

            return SourceDocument(
                external_id=str(item.get("id", "")),
                source_adapter=self.adapter_name,
                title=title,
                content_type=content_type,
                citation=item.get("citation", title),
                jurisdiction="Kenya",
                jurisdiction_code="KE",
                court_name=court_name,
                court_level=court_level,
                date_decided=parsed_date,
                full_text=item.get("body", item.get("content", "")),
                summary=item.get("snippet", item.get("summary", "")),
                source_url=item.get("url", ""),
                is_current=True,
                authority_level="binding",
                raw_metadata=item,
            )
        except Exception as e:
            logger.warning("kenya_law_parse_failed", error=str(e))
            return None
