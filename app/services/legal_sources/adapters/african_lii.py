"""AfricanLII adapter — African Legal Information Institute.

Source: https://africanlii.org
Coverage: Pan-African case law and legislation from 15+ African countries
          including South Africa (SAFLII), Ghana, Tanzania, Uganda, Rwanda, etc.
Auth: None required (open access)
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

# AfricanLII country code to jurisdiction mapping
COUNTRY_CODES = {
    "za": ("South Africa", "ZA"),
    "gh": ("Ghana", "GH"),
    "tz": ("Tanzania", "TZ"),
    "ug": ("Uganda", "UG"),
    "rw": ("Rwanda", "RW"),
    "mw": ("Malawi", "MW"),
    "zm": ("Zambia", "ZM"),
    "zw": ("Zimbabwe", "ZW"),
    "sz": ("Eswatini", "SZ"),
    "ls": ("Lesotho", "LS"),
    "bw": ("Botswana", "BW"),
    "na": ("Namibia", "NA"),
    "mu": ("Mauritius", "MU"),
    "sc": ("Seychelles", "SC"),
}


class AfricanLIIAdapter(LegalSourceAdapter):
    """Pan-African legal sources from AfricanLII (covers SAFLII and country LIIs)."""

    BASE_URL = "https://africanlii.org"

    def __init__(self):
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="african_lii",
            rate_limit_per_minute=15,
            timeout=45.0,
            headers={"Accept": "application/json, text/html"},
        )

    @property
    def adapter_name(self) -> str:
        return "african_lii"

    @property
    def display_name(self) -> str:
        return "AfricanLII — African Legal Information Institute"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[SourceContentType.CASE_LAW, SourceContentType.STATUTE, SourceContentType.REGULATION],
            jurisdictions=["ZA", "GH", "TZ", "UG", "RW", "MW", "ZM", "ZW", "BW", "NA"],
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

        params = {"q": query, "page": page}

        # Scope to specific country collection
        collection = ""
        if jurisdiction:
            code = jurisdiction.lower()
            if code in COUNTRY_CODES:
                collection = f"/{code}"
            elif len(code) == 2:
                collection = f"/{code}"

        if content_type == SourceContentType.CASE_LAW:
            collection += "/judgment"
        elif content_type in (SourceContentType.STATUTE, SourceContentType.REGULATION):
            collection += "/legislation"

        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()

        try:
            data = await self._http.get(f"/api/search{collection}", params=params)

            if isinstance(data, dict):
                documents = []
                results = data.get("results", data.get("items", []))
                for item in results:
                    doc = self._parse_result(item, jurisdiction)
                    if doc:
                        documents.append(doc)
                total = data.get("count", data.get("total", len(documents)))
            else:
                documents, total = [], 0

        except Exception as e:
            logger.error("african_lii_search_failed", error=str(e))
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
        for doc in results.documents:
            if citation.lower() in doc.citation.lower():
                return doc
        return results.documents[0] if results.documents else None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        try:
            data = await self._http.get(f"/api/document/{external_id}")
            if isinstance(data, dict):
                return self._parse_result(data)
        except Exception as e:
            logger.error("african_lii_get_failed", id=external_id, error=str(e))
        return None

    async def health_check(self) -> bool:
        try:
            await self._http.get("/api/search", params={"q": "law", "page": "1"})
            return True
        except Exception:
            return False

    def _parse_result(self, item: dict, jurisdiction: str | None = None) -> SourceDocument | None:
        try:
            title = item.get("title", "")
            doc_url = item.get("url", item.get("link", ""))

            # Infer jurisdiction from URL or metadata
            country_code = ""
            country_name = ""
            if jurisdiction:
                country_code = jurisdiction.upper()
                country_name = COUNTRY_CODES.get(jurisdiction.lower(), (jurisdiction, jurisdiction))[0]
            else:
                for code, (name, iso) in COUNTRY_CODES.items():
                    if f"/{code}/" in str(doc_url).lower():
                        country_code = iso
                        country_name = name
                        break

            content_type = SourceContentType.CASE_LAW
            if "legislation" in str(doc_url).lower() or "act" in title.lower():
                content_type = SourceContentType.STATUTE

            date_str = item.get("date", item.get("date_decided", ""))
            parsed_date = None
            if date_str:
                try:
                    if len(str(date_str)) == 4:
                        parsed_date = date(int(date_str), 1, 1)
                    else:
                        parsed_date = date.fromisoformat(str(date_str)[:10])
                except (ValueError, TypeError):
                    pass

            return SourceDocument(
                external_id=item.get("id", doc_url),
                source_adapter=self.adapter_name,
                title=title,
                content_type=content_type,
                citation=item.get("citation", item.get("media_neutral_citation", title)),
                jurisdiction=country_name or "Africa",
                jurisdiction_code=country_code or "INTL",
                court_name=item.get("court", item.get("authority", "")),
                date_decided=parsed_date if content_type == SourceContentType.CASE_LAW else None,
                date_enacted=parsed_date if content_type == SourceContentType.STATUTE else None,
                full_text=item.get("body", item.get("content", "")),
                summary=item.get("snippet", item.get("summary", "")),
                source_url=doc_url if doc_url.startswith("http") else f"{self.BASE_URL}{doc_url}",
                is_current=True,
                authority_level="binding",
                raw_metadata=item,
            )
        except Exception as e:
            logger.warning("african_lii_parse_failed", error=str(e))
            return None
