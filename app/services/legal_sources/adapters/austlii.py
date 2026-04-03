"""AustLII adapter — Australasian Legal Information Institute.

Source: http://www.austlii.edu.au
Coverage: Australian case law, legislation (federal + state), plus NZ law
Auth: None required (open access)
Rate limit: Reasonable use
Also covers: Federal Register of Legislation (legislation.gov.au)
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

AUS_COURTS = {
    "high court": CourtLevel.SUPREME,
    "hca": CourtLevel.SUPREME,
    "federal court": CourtLevel.APPELLATE,
    "fca": CourtLevel.APPELLATE,
    "fcafc": CourtLevel.APPELLATE,
    "supreme court": CourtLevel.HIGH,
    "district court": CourtLevel.DISTRICT,
    "magistrates": CourtLevel.MAGISTRATE,
    "tribunal": CourtLevel.TRIBUNAL,
    "aat": CourtLevel.TRIBUNAL,
}


class AustLIIAdapter(LegalSourceAdapter):
    """Australian law from AustLII + Federal Register of Legislation."""

    AUSTLII_URL = "http://www.austlii.edu.au"
    FRL_URL = "https://www.legislation.gov.au"

    def __init__(self):
        self._austlii_http = AdapterHTTPClient(
            base_url=self.AUSTLII_URL,
            adapter_name="austlii",
            rate_limit_per_minute=15,
            timeout=45.0,
        )
        self._frl_http = AdapterHTTPClient(
            base_url=self.FRL_URL,
            adapter_name="austlii_frl",
            rate_limit_per_minute=20,
            headers={"Accept": "application/json"},
        )

    @property
    def adapter_name(self) -> str:
        return "austlii"

    @property
    def display_name(self) -> str:
        return "AustLII + Federal Register of Legislation (Australia)"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[SourceContentType.CASE_LAW, SourceContentType.STATUTE, SourceContentType.REGULATION],
            jurisdictions=["AU", "NZ"],
            supports_full_text=True,
            supports_citation_lookup=True,
            supports_keyword_search=True,
            supports_date_filter=True,
            supports_court_filter=False,
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

        # Try Federal Register of Legislation API for statutes
        if content_type in (SourceContentType.STATUTE, SourceContentType.REGULATION, None):
            try:
                frl_results = await self._search_frl(query, page, page_size)
            except Exception as e:
                logger.warning("frl_search_failed", error=str(e))
                frl_results = []
        else:
            frl_results = []

        # AustLII search for case law
        case_results = []
        if content_type in (SourceContentType.CASE_LAW, None):
            try:
                case_results = await self._search_austlii(query, page, page_size)
            except Exception as e:
                logger.warning("austlii_search_failed", error=str(e))

        all_docs = frl_results + case_results

        return SourceSearchResult(
            documents=all_docs,
            total_count=len(all_docs),
            page=page,
            page_size=page_size,
            query=query,
            source_adapter=self.adapter_name,
            search_time_ms=int((time.time() - start) * 1000),
        )

    async def _search_frl(self, query: str, page: int, page_size: int) -> list[SourceDocument]:
        params = {"query": query, "page": page, "pageSize": min(page_size, 20)}
        data = await self._frl_http.get("/api/v1/search", params=params)

        documents = []
        if isinstance(data, dict):
            for item in data.get("results", []):
                try:
                    doc = SourceDocument(
                        external_id=item.get("id", ""),
                        source_adapter=self.adapter_name,
                        title=item.get("title", ""),
                        content_type=SourceContentType.STATUTE if item.get("type") == "Act" else SourceContentType.REGULATION,
                        citation=item.get("title", ""),
                        jurisdiction="Australia",
                        jurisdiction_code="AU",
                        issuing_body=item.get("authority", "Australian Parliament"),
                        date_enacted=self._parse_date(item.get("date")),
                        summary=item.get("description", ""),
                        source_url=item.get("url", ""),
                        is_current=item.get("inForce", True),
                        authority_level="binding",
                        raw_metadata=item,
                    )
                    documents.append(doc)
                except Exception as e:
                    logger.warning("frl_parse_failed", error=str(e))

        return documents

    async def _search_austlii(self, query: str, page: int, page_size: int) -> list[SourceDocument]:
        # AustLII uses a web search interface; attempt JSON endpoint
        params = {"q": query, "page": page}
        try:
            data = await self._austlii_http.get("/cgi-bin/sinosrch.cgi", params=params)
            if isinstance(data, dict):
                return [self._parse_austlii_result(r) for r in data.get("results", []) if r]
        except Exception:
            pass
        return []

    def _parse_austlii_result(self, item: dict) -> SourceDocument | None:
        try:
            return SourceDocument(
                external_id=item.get("id", ""),
                source_adapter=self.adapter_name,
                title=item.get("title", ""),
                content_type=SourceContentType.CASE_LAW,
                citation=item.get("citation", item.get("title", "")),
                jurisdiction="Australia",
                jurisdiction_code="AU",
                court_name=item.get("court", ""),
                date_decided=self._parse_date(item.get("date")),
                summary=item.get("snippet", ""),
                source_url=item.get("url", ""),
                is_current=True,
                authority_level="binding",
                raw_metadata=item,
            )
        except Exception:
            return None

    async def get_by_citation(self, citation: str) -> SourceDocument | None:
        results = await self.search(citation, page_size=1)
        return results.documents[0] if results.documents else None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        return None

    async def health_check(self) -> bool:
        try:
            await self._frl_http.get("/api/v1/search", params={"query": "test", "pageSize": "1"})
            return True
        except Exception:
            return False

    def _parse_date(self, date_str) -> date | None:
        if not date_str:
            return None
        try:
            return date.fromisoformat(str(date_str)[:10])
        except (ValueError, TypeError):
            return None
