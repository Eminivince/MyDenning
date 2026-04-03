"""eCFR adapter — US Code of Federal Regulations.

Source: https://www.ecfr.gov/api/versioner/v1/
Coverage: All titles of the US Code of Federal Regulations (current + historical)
Auth: None required (open API)
Rate limit: Reasonable use
"""

import time
from datetime import date

import structlog

from app.services.legal_sources.adapters.http_client import AdapterHTTPClient
from app.services.legal_sources.base import (
    AdapterCapabilities,
    LegalSourceAdapter,
    SourceContentType,
    SourceDocument,
    SourceSearchResult,
)

logger = structlog.get_logger(__name__)


class ECFRAdapter(LegalSourceAdapter):
    """US federal regulations from eCFR.gov."""

    BASE_URL = "https://www.ecfr.gov/api"

    def __init__(self):
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="ecfr",
            rate_limit_per_minute=30,
            headers={"Accept": "application/json"},
        )

    @property
    def adapter_name(self) -> str:
        return "ecfr"

    @property
    def display_name(self) -> str:
        return "eCFR — US Code of Federal Regulations"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[SourceContentType.REGULATION],
            jurisdictions=["US"],
            supports_full_text=True,
            supports_citation_lookup=True,
            supports_keyword_search=True,
            supports_date_filter=True,
            supports_court_filter=False,
            max_results_per_request=20,
            rate_limit_per_minute=30,
            requires_api_key=False,
        )

    async def search(
        self,
        query: str,
        content_type: SourceContentType | None = None,
        jurisdiction: str | None = None,
        court_level=None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SourceSearchResult:
        start = time.time()
        params = {
            "query": query,
            "per_page": min(page_size, 20),
            "page": page,
        }

        try:
            data = await self._http.get("/search/v1/results", params=params)
            if isinstance(data, dict):
                documents = self._parse_results(data)
                total = data.get("meta", {}).get("total_count", 0)
            else:
                documents, total = [], 0
        except Exception as e:
            logger.error("ecfr_search_failed", error=str(e))
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
            data = await self._http.get(f"/versioner/v1/full/{external_id}.json")
            if isinstance(data, dict):
                return self._parse_section(data, external_id)
        except Exception as e:
            logger.error("ecfr_get_failed", id=external_id, error=str(e))
        return None

    async def health_check(self) -> bool:
        try:
            await self._http.get("/search/v1/results", params={"query": "test", "per_page": "1"})
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
                hierarchy = item.get("hierarchy", {})
                title_num = hierarchy.get("title", "")
                part = hierarchy.get("part", "")
                section = hierarchy.get("section", "")

                citation = f"{title_num} CFR"
                if part:
                    citation += f" Part {part}"
                if section:
                    citation += f" § {section}"

                headline = item.get("headline", "") or item.get("full_text_excerpt", "")

                doc = SourceDocument(
                    external_id=item.get("id", f"title-{title_num}/part-{part}/section-{section}"),
                    source_adapter=self.adapter_name,
                    title=item.get("headings", {}).get("section", citation),
                    content_type=SourceContentType.REGULATION,
                    citation=citation,
                    jurisdiction="United States",
                    jurisdiction_code="US",
                    issuing_body=item.get("agency_names", [""])[0] if item.get("agency_names") else "",
                    summary=headline[:500] if headline else "",
                    source_url=f"https://www.ecfr.gov/current/title-{title_num}/part-{part}/section-{section}",
                    is_current=True,
                    authority_level="binding",
                    topics=item.get("subjects", []),
                    raw_metadata=item,
                )
                documents.append(doc)
            except Exception as e:
                logger.warning("ecfr_parse_failed", error=str(e))

        return documents

    def _parse_section(self, data: dict, external_id: str) -> SourceDocument | None:
        try:
            return SourceDocument(
                external_id=external_id,
                source_adapter=self.adapter_name,
                title=data.get("title", ""),
                content_type=SourceContentType.REGULATION,
                citation=external_id,
                jurisdiction="United States",
                jurisdiction_code="US",
                full_text=data.get("text", ""),
                is_current=True,
                authority_level="binding",
                raw_metadata=data,
            )
        except Exception:
            return None
