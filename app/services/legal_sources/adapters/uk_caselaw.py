"""UK Find Case Law API — National Archives.

Source: https://caselaw.nationalarchives.gov.uk/
Coverage: England and Wales judgments from 2001+
          Supreme Court, Court of Appeal, High Court, Upper Tribunals
Auth: None required (Open Justice Licence — allows commercial reuse)
Format: LegalDocML (Akoma Ntoso) XML, HTML
Rate limit: Not documented; reasonable use expected
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

UK_COURT_MAP = {
    "uksc": ("Supreme Court", CourtLevel.SUPREME),
    "ukpc": ("Privy Council", CourtLevel.SUPREME),
    "ewca/civ": ("Court of Appeal (Civil)", CourtLevel.APPELLATE),
    "ewca/crim": ("Court of Appeal (Criminal)", CourtLevel.APPELLATE),
    "ewhc/admin": ("High Court (Administrative)", CourtLevel.HIGH),
    "ewhc/ch": ("High Court (Chancery)", CourtLevel.HIGH),
    "ewhc/comm": ("High Court (Commercial)", CourtLevel.HIGH),
    "ewhc/fam": ("High Court (Family)", CourtLevel.HIGH),
    "ewhc/kb": ("High Court (King's Bench)", CourtLevel.HIGH),
    "ewhc/qb": ("High Court (Queen's Bench)", CourtLevel.HIGH),
    "ewhc/pat": ("High Court (Patents)", CourtLevel.HIGH),
    "ewhc/tcc": ("High Court (TCC)", CourtLevel.HIGH),
    "ukut": ("Upper Tribunal", CourtLevel.TRIBUNAL),
    "ukftt": ("First-tier Tribunal", CourtLevel.TRIBUNAL),
    "ewcop": ("Court of Protection", CourtLevel.HIGH),
    "ewfc": ("Family Court", CourtLevel.HIGH),
}


class UKCaseLawAdapter(LegalSourceAdapter):
    """England & Wales case law from the UK National Archives Find Case Law API."""

    BASE_URL = "https://caselaw.nationalarchives.gov.uk"

    def __init__(self):
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="uk_caselaw",
            rate_limit_per_minute=30,
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    @property
    def adapter_name(self) -> str:
        return "uk_caselaw"

    @property
    def display_name(self) -> str:
        return "UK Find Case Law — National Archives"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[SourceContentType.CASE_LAW],
            jurisdictions=["GB"],
            supports_full_text=True,
            supports_citation_lookup=True,
            supports_keyword_search=True,
            supports_date_filter=True,
            supports_court_filter=True,
            max_results_per_request=50,
            rate_limit_per_minute=30,
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

        params = {
            "query": query,
            "page": page,
            "per_page": min(page_size, 50),
            "order": "-date",
        }

        if date_from:
            params["from_date"] = date_from.isoformat()
        if date_to:
            params["to_date"] = date_to.isoformat()

        # Court level filter
        if court_level:
            court_codes = [
                code for code, (_, level) in UK_COURT_MAP.items()
                if level == court_level
            ]
            if court_codes:
                params["court"] = court_codes[0]

        try:
            data = await self._http.get("/judgments/search", params=params)
            if isinstance(data, dict):
                documents = self._parse_results(data)
                total = data.get("total", len(documents))
            else:
                documents, total = [], 0
        except Exception as e:
            logger.error("uk_caselaw_search_failed", error=str(e))
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
        # Try neutral citation format: [2024] UKSC 1
        results = await self.search(citation, page_size=3)
        for doc in results.documents:
            if citation.lower() in doc.citation.lower():
                return doc
        return results.documents[0] if results.documents else None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        """external_id is a court/year/number path like uksc/2024/1"""
        try:
            data = await self._http.get(f"/{external_id}/data.json")
            if isinstance(data, dict):
                return self._parse_judgment(data, external_id)
        except Exception as e:
            logger.error("uk_caselaw_get_failed", id=external_id, error=str(e))
        return None

    async def health_check(self) -> bool:
        try:
            data = await self._http.get("/judgments/search", params={"query": "test", "per_page": "1"})
            return isinstance(data, (dict, str))
        except Exception:
            return False

    def _parse_results(self, data: dict) -> list[SourceDocument]:
        documents = []
        results = data.get("results", [])
        if not isinstance(results, list):
            return documents

        for item in results:
            doc = self._parse_judgment(item)
            if doc:
                documents.append(doc)
        return documents

    def _parse_judgment(self, item: dict, path: str | None = None) -> SourceDocument | None:
        try:
            uri = item.get("uri", path or "")
            title = item.get("name", item.get("title", ""))
            neutral_citation = item.get("neutral_citation", item.get("citation", ""))

            # Determine court from URI
            court_name = "Unknown Court"
            court_level = CourtLevel.HIGH
            for code, (name, level) in UK_COURT_MAP.items():
                if code in uri.lower():
                    court_name = name
                    court_level = level
                    break

            # Parse date
            date_str = item.get("date", item.get("updated", ""))
            date_decided = None
            if date_str:
                try:
                    date_decided = date.fromisoformat(str(date_str)[:10])
                except (ValueError, TypeError):
                    pass

            return SourceDocument(
                external_id=uri.strip("/"),
                source_adapter=self.adapter_name,
                title=title,
                content_type=SourceContentType.CASE_LAW,
                citation=neutral_citation or title,
                jurisdiction="United Kingdom",
                jurisdiction_code="GB",
                court_name=court_name,
                court_level=court_level,
                date_decided=date_decided,
                full_text=item.get("content", ""),
                summary=item.get("summary", ""),
                source_url=f"{self.BASE_URL}/{uri}" if uri else "",
                is_current=True,
                authority_level="binding",
                raw_metadata=item,
            )
        except Exception as e:
            logger.warning("uk_caselaw_parse_failed", error=str(e))
            return None
