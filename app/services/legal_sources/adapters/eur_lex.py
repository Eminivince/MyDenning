"""EUR-Lex adapter — European Union law.

Source: https://eur-lex.europa.eu/eurlex-ws (REST + SPARQL)
Coverage: EU treaties, regulations, directives, decisions, case law (CJEU)
Auth: None for search; registered access for bulk
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


class EURLexAdapter(LegalSourceAdapter):
    """EU legislation and CJEU case law from EUR-Lex."""

    BASE_URL = "https://eur-lex.europa.eu"
    SEARCH_URL = "https://eur-lex.europa.eu/search.html"

    def __init__(self):
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="eur_lex",
            rate_limit_per_minute=20,
            headers={"Accept": "application/json"},
        )

    @property
    def adapter_name(self) -> str:
        return "eur_lex"

    @property
    def display_name(self) -> str:
        return "EUR-Lex — European Union Law"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[
                SourceContentType.STATUTE, SourceContentType.REGULATION,
                SourceContentType.CASE_LAW, SourceContentType.TREATY,
            ],
            jurisdictions=["EU"],
            supports_full_text=True,
            supports_citation_lookup=True,
            supports_keyword_search=True,
            supports_date_filter=True,
            supports_court_filter=False,
            max_results_per_request=20,
            rate_limit_per_minute=20,
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

        # EUR-Lex REST API uses the CELLAR identifier system
        # Use the search API endpoint
        params = {
            "text": query,
            "qid": "",
            "page": page,
            "type": "quick",
        }

        # Map content type to EUR-Lex document type codes
        if content_type == SourceContentType.REGULATION:
            params["DD_YEAR"] = ""
            params["SUBDOM_INIT"] = "LEGISLATION"
        elif content_type == SourceContentType.CASE_LAW:
            params["SUBDOM_INIT"] = "CASE_LAW"

        if date_from:
            params["DD_YEAR_FROM"] = str(date_from.year)
        if date_to:
            params["DD_YEAR_TO"] = str(date_to.year)

        try:
            # Use the REST endpoint that returns structured data
            api_params = {
                "text": query,
                "page": str(page),
                "pageSize": str(min(page_size, 20)),
            }
            data = await self._http.get("/eurlex-ws/rest/search", params=api_params)

            if isinstance(data, dict):
                documents = self._parse_results(data)
                total = data.get("totalResults", 0)
            else:
                documents, total = [], 0

        except Exception as e:
            logger.error("eur_lex_search_failed", error=str(e))
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
        results = await self.search(citation, page_size=1)
        return results.documents[0] if results.documents else None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        try:
            # CELEX number lookup
            data = await self._http.get(f"/eurlex-ws/rest/cellar/{external_id}")
            if isinstance(data, dict):
                docs = self._parse_results({"results": [data]})
                return docs[0] if docs else None
        except Exception as e:
            logger.error("eur_lex_get_failed", id=external_id, error=str(e))
        return None

    async def health_check(self) -> bool:
        try:
            await self._http.get("/eurlex-ws/rest/search", params={"text": "regulation", "pageSize": "1"})
            return True
        except Exception:
            return False

    def _parse_results(self, data: dict) -> list[SourceDocument]:
        documents = []
        results = data.get("results", [])
        if not isinstance(results, list):
            return documents

        for item in results:
            try:
                celex = item.get("celex", "") or item.get("id", "")
                title = item.get("title", {})
                if isinstance(title, dict):
                    title_text = title.get("en", title.get("EN", str(title)))
                else:
                    title_text = str(title)

                # Determine content type from CELEX number
                content_type = SourceContentType.REGULATION
                if celex.startswith("6"):
                    content_type = SourceContentType.CASE_LAW
                elif celex.startswith("1"):
                    content_type = SourceContentType.TREATY
                elif celex.startswith("3"):
                    content_type = SourceContentType.REGULATION

                doc = SourceDocument(
                    external_id=celex,
                    source_adapter=self.adapter_name,
                    title=title_text,
                    content_type=content_type,
                    citation=celex,
                    jurisdiction="European Union",
                    jurisdiction_code="EU",
                    issuing_body=item.get("author", ""),
                    date_enacted=self._parse_date(item.get("date")),
                    summary=item.get("summary", {}).get("en", "") if isinstance(item.get("summary"), dict) else "",
                    source_url=f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}",
                    is_current=True,
                    authority_level="binding",
                    raw_metadata=item,
                )
                documents.append(doc)
            except Exception as e:
                logger.warning("eur_lex_parse_failed", error=str(e))

        return documents

    def _parse_date(self, date_str) -> date | None:
        if not date_str:
            return None
        try:
            if isinstance(date_str, str):
                return date.fromisoformat(date_str[:10])
        except (ValueError, TypeError):
            pass
        return None
