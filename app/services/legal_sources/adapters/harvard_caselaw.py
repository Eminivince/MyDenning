"""Harvard Caselaw Access Project adapter.

Source: https://api.case.law/v1/
Coverage: All US case law (6.5M+ cases, 40M+ pages) — released by Harvard Law Library
Auth: Free API key for bulk access (register at case.law)
Rate limit: 500 requests/hour unauthenticated, higher with key
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

COURT_LEVEL_KEYWORDS = {
    "supreme": CourtLevel.SUPREME,
    "appellate": CourtLevel.APPELLATE,
    "appeals": CourtLevel.APPELLATE,
    "circuit": CourtLevel.APPELLATE,
    "superior": CourtLevel.HIGH,
    "district": CourtLevel.DISTRICT,
    "trial": CourtLevel.DISTRICT,
    "bankruptcy": CourtLevel.TRIBUNAL,
    "tax": CourtLevel.TRIBUNAL,
}


class HarvardCaselawAdapter(LegalSourceAdapter):
    """US case law from the Harvard Caselaw Access Project (case.law)."""

    BASE_URL = "https://api.case.law/v1"

    def __init__(self):
        settings = get_settings()
        api_key = getattr(settings, "caselaw_api_key", "")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Token {api_key}"
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="harvard_caselaw",
            rate_limit_per_minute=8,  # conservative
            headers=headers,
        )

    @property
    def adapter_name(self) -> str:
        return "harvard_caselaw"

    @property
    def display_name(self) -> str:
        return "Harvard Caselaw Access Project (US)"

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
            max_results_per_request=100,
            rate_limit_per_minute=8,
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
            "search": query,
            "page_size": min(page_size, 100),
            "page": page,
            "ordering": "-decision_date",
        }

        if date_from:
            params["decision_date_min"] = date_from.isoformat()
        if date_to:
            params["decision_date_max"] = date_to.isoformat()

        try:
            data = await self._http.get("/cases/", params=params)
            if isinstance(data, dict):
                documents = self._parse_cases(data.get("results", []))
                total = data.get("count", 0)
            else:
                documents, total = [], 0
        except Exception as e:
            logger.error("harvard_caselaw_search_failed", error=str(e))
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
        params = {"cite": citation}
        try:
            data = await self._http.get("/cases/", params=params)
            if isinstance(data, dict):
                results = data.get("results", [])
                if results:
                    docs = self._parse_cases([results[0]])
                    return docs[0] if docs else None
        except Exception as e:
            logger.error("harvard_citation_lookup_failed", citation=citation, error=str(e))
        return None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        try:
            data = await self._http.get(f"/cases/{external_id}/", params={"full_case": "true"})
            if isinstance(data, dict):
                docs = self._parse_cases([data])
                return docs[0] if docs else None
        except Exception as e:
            logger.error("harvard_get_by_id_failed", id=external_id, error=str(e))
        return None

    async def health_check(self) -> bool:
        try:
            await self._http.get("/cases/", params={"page_size": "1"})
            return True
        except Exception:
            return False

    def _parse_cases(self, cases: list) -> list[SourceDocument]:
        documents = []
        for case in cases:
            try:
                court = case.get("court", {})
                court_name = court.get("name", "") if isinstance(court, dict) else str(court)

                court_level = CourtLevel.DISTRICT
                court_name_lower = court_name.lower()
                for keyword, level in COURT_LEVEL_KEYWORDS.items():
                    if keyword in court_name_lower:
                        court_level = level
                        break

                citations = case.get("citations", [])
                cite_str = ""
                if citations:
                    cite_obj = citations[0]
                    cite_str = cite_obj.get("cite", "") if isinstance(cite_obj, dict) else str(cite_obj)

                decision_date = None
                date_str = case.get("decision_date")
                if date_str:
                    try:
                        decision_date = date.fromisoformat(date_str[:10])
                    except (ValueError, TypeError):
                        pass

                # Full text may be in casebody
                full_text = ""
                casebody = case.get("casebody", {})
                if isinstance(casebody, dict):
                    data_section = casebody.get("data", "")
                    if isinstance(data_section, str):
                        full_text = data_section
                    elif isinstance(data_section, dict):
                        opinions = data_section.get("opinions", [])
                        full_text = "\n\n".join(
                            op.get("text", "") for op in opinions if isinstance(op, dict)
                        )

                doc = SourceDocument(
                    external_id=str(case.get("id", "")),
                    source_adapter=self.adapter_name,
                    title=case.get("name", case.get("name_abbreviation", "Unknown")),
                    content_type=SourceContentType.CASE_LAW,
                    citation=cite_str or case.get("name_abbreviation", ""),
                    jurisdiction="United States",
                    jurisdiction_code="US",
                    court_name=court_name,
                    court_level=court_level,
                    date_decided=decision_date,
                    full_text=full_text if full_text else None,
                    summary=case.get("preview", [""])[0] if case.get("preview") else "",
                    source_url=case.get("frontend_url", ""),
                    is_current=True,
                    authority_level="binding",
                    raw_metadata={"jurisdiction_name": case.get("jurisdiction", {}).get("name", "")},
                )
                documents.append(doc)
            except Exception as e:
                logger.warning("harvard_case_parse_failed", error=str(e))

        return documents
