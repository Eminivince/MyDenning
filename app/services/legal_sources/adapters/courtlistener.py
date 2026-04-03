"""CourtListener adapter — Free Law Project.

Source: https://www.courtlistener.com/api/rest/v4/
Coverage: US case law (4M+ opinions), PACER dockets
Auth: Free API token (register at courtlistener.com)
Rate limit: ~5000 requests/day for authenticated users
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

# CourtListener court hierarchy mapping
COURT_LEVEL_MAP = {
    "scotus": CourtLevel.SUPREME,
    "ca1": CourtLevel.APPELLATE, "ca2": CourtLevel.APPELLATE, "ca3": CourtLevel.APPELLATE,
    "ca4": CourtLevel.APPELLATE, "ca5": CourtLevel.APPELLATE, "ca6": CourtLevel.APPELLATE,
    "ca7": CourtLevel.APPELLATE, "ca8": CourtLevel.APPELLATE, "ca9": CourtLevel.APPELLATE,
    "ca10": CourtLevel.APPELLATE, "ca11": CourtLevel.APPELLATE, "cadc": CourtLevel.APPELLATE,
    "cafc": CourtLevel.APPELLATE,
}


class CourtListenerAdapter(LegalSourceAdapter):
    """US case law via the CourtListener REST API (Free Law Project)."""

    BASE_URL = "https://www.courtlistener.com/api/rest/v4"

    def __init__(self):
        settings = get_settings()
        api_token = getattr(settings, "courtlistener_api_token", "")
        headers = {}
        if api_token:
            headers["Authorization"] = f"Token {api_token}"
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="courtlistener",
            rate_limit_per_minute=50,
            headers=headers,
        )

    @property
    def adapter_name(self) -> str:
        return "courtlistener"

    @property
    def display_name(self) -> str:
        return "CourtListener — Free Law Project (US)"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[SourceContentType.CASE_LAW],
            jurisdictions=["US"],
            supports_full_text=True,
            supports_citation_lookup=True,
            supports_keyword_search=True,
            supports_date_filter=True,
            supports_court_filter=True,
            max_results_per_request=20,
            rate_limit_per_minute=50,
            requires_api_key=False,  # works without, better with
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
        params = {
            "q": query,
            "order_by": "score desc",
            "page_size": min(page_size, 20),
            "page": page,
        }

        if date_from:
            params["filed_after"] = date_from.isoformat()
        if date_to:
            params["filed_before"] = date_to.isoformat()

        data = await self._http.get("/search/", params=params)

        documents = []
        results = data.get("results", []) if isinstance(data, dict) else []

        for item in results:
            doc = self._parse_opinion(item)
            if doc:
                documents.append(doc)

        return SourceSearchResult(
            documents=documents,
            total_count=data.get("count", 0) if isinstance(data, dict) else 0,
            page=page,
            page_size=page_size,
            query=query,
            source_adapter=self.adapter_name,
            search_time_ms=int((time.time() - start) * 1000),
        )

    async def get_by_citation(self, citation: str) -> SourceDocument | None:
        params = {"citation": citation}
        try:
            data = await self._http.get("/search/", params=params)
            results = data.get("results", []) if isinstance(data, dict) else []
            if results:
                return self._parse_opinion(results[0])
        except Exception as e:
            logger.error("courtlistener_citation_lookup_failed", citation=citation, error=str(e))
        return None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        try:
            data = await self._http.get(f"/opinions/{external_id}/")
            return self._parse_opinion(data) if isinstance(data, dict) else None
        except Exception as e:
            logger.error("courtlistener_get_by_id_failed", id=external_id, error=str(e))
        return None

    async def get_citing_documents(self, external_id: str, limit: int = 20) -> list[SourceDocument]:
        try:
            data = await self._http.get(f"/opinions/{external_id}/cited-by/", params={"page_size": limit})
            results = data.get("results", []) if isinstance(data, dict) else []
            return [self._parse_opinion(r) for r in results if self._parse_opinion(r)]
        except Exception:
            return []

    async def check_good_law(self, citation: str) -> dict:
        doc = await self.get_by_citation(citation)
        if not doc:
            return {"is_good_law": True, "treatment": "unknown", "overruled_by": None}

        # CourtListener tracks citation treatments in the citedBy network
        # A negative cited_by_count with specific treatment markers indicates bad law
        return {
            "is_good_law": doc.is_current,
            "treatment": "cited" if doc.cited_by_count > 0 else "unknown",
            "overruled_by": doc.superseded_by,
        }

    async def health_check(self) -> bool:
        return await self._http.ping()

    def _parse_opinion(self, data: dict) -> SourceDocument | None:
        if not data:
            return None

        try:
            court_id = data.get("court_id", "") or data.get("court", "")
            court_level = COURT_LEVEL_MAP.get(court_id, CourtLevel.DISTRICT)

            citation = data.get("citation", [])
            if isinstance(citation, list) and citation:
                cite_str = citation[0] if isinstance(citation[0], str) else str(citation[0])
            else:
                cite_str = data.get("caseName", data.get("case_name", "Unknown"))

            date_filed = data.get("dateFiled") or data.get("date_filed")
            date_decided = None
            if date_filed:
                try:
                    date_decided = date.fromisoformat(date_filed[:10])
                except (ValueError, TypeError):
                    pass

            return SourceDocument(
                external_id=str(data.get("id", "")),
                source_adapter=self.adapter_name,
                title=data.get("caseName") or data.get("case_name", "Unknown"),
                content_type=SourceContentType.CASE_LAW,
                citation=cite_str,
                jurisdiction="US",
                jurisdiction_code="US",
                court_name=data.get("court_citation_string") or data.get("court", ""),
                court_level=court_level,
                date_decided=date_decided,
                full_text=data.get("plain_text") or data.get("text", ""),
                summary=data.get("snippet", ""),
                source_url=f"https://www.courtlistener.com/opinion/{data.get('id', '')}/",
                cited_by_count=data.get("citeCount", 0) or data.get("citation_count", 0),
                topics=data.get("suitNature", []) if isinstance(data.get("suitNature"), list) else [],
                raw_metadata=data,
            )
        except Exception as e:
            logger.warning("courtlistener_parse_failed", error=str(e))
            return None
