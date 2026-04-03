"""Laws.Africa Content API — THE primary African legislation source.

Source: https://api.laws.africa/v3/
Coverage: Legislation from 20+ African countries in Akoma Ntoso XML format.
          Nigeria, South Africa, Kenya, Ghana, Uganda, Zimbabwe, Namibia,
          Zambia, Tanzania, Malawi, Mozambique, Rwanda, Lesotho, eSwatini, Botswana
Auth: Free API token (register at edit.laws.africa)
Format: JSON metadata, Akoma Ntoso XML, HTML, ePUB, PDF for content
Rate limit: Reasonable use on free tier

This replaces NigeriaLII, AfricanLII, KenyaLII, SAFLII, GhaLII for legislation
because none of those have public APIs — they serve content through Laws.Africa.
"""

import time
from datetime import date

import structlog

from app.core.config import get_settings
from app.services.legal_sources.adapters.http_client import AdapterHTTPClient
from app.services.legal_sources.base import (
    AdapterCapabilities,
    LegalSourceAdapter,
    SourceContentType,
    SourceDocument,
    SourceSearchResult,
)

logger = structlog.get_logger(__name__)

# Laws.Africa country codes (Akoma Ntoso 2-letter codes)
LAWS_AFRICA_COUNTRIES = {
    "ng": ("Nigeria", "NG"),
    "za": ("South Africa", "ZA"),
    "ke": ("Kenya", "KE"),
    "gh": ("Ghana", "GH"),
    "ug": ("Uganda", "UG"),
    "tz": ("Tanzania", "TZ"),
    "zw": ("Zimbabwe", "ZW"),
    "na": ("Namibia", "NA"),
    "zm": ("Zambia", "ZM"),
    "mw": ("Malawi", "MW"),
    "mz": ("Mozambique", "MZ"),
    "rw": ("Rwanda", "RW"),
    "ls": ("Lesotho", "LS"),
    "sz": ("Eswatini", "SZ"),
    "bw": ("Botswana", "BW"),
    "mu": ("Mauritius", "MU"),
    "sc": ("Seychelles", "SC"),
    "sl": ("Sierra Leone", "SL"),
    "lr": ("Liberia", "LR"),
}


class LawsAfricaAdapter(LegalSourceAdapter):
    """African legislation from the Laws.Africa Content API.

    This is the authoritative source for legislation across 20+ African jurisdictions.
    NigeriaLII, SAFLII, KenyaLII, GhaLII etc. all feed from this same data.
    """

    BASE_URL = "https://api.laws.africa/v3"

    def __init__(self):
        settings = get_settings()
        api_token = getattr(settings, "laws_africa_api_token", "")
        headers = {"Accept": "application/json"}
        if api_token:
            headers["Authorization"] = f"Token {api_token}"
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="laws_africa",
            rate_limit_per_minute=30,
            timeout=30.0,
            headers=headers,
        )

    @property
    def adapter_name(self) -> str:
        return "laws_africa"

    @property
    def display_name(self) -> str:
        return "Laws.Africa — African Legislation (20+ countries)"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[SourceContentType.STATUTE, SourceContentType.REGULATION, SourceContentType.CONSTITUTION],
            jurisdictions=[iso for _, (_, iso) in LAWS_AFRICA_COUNTRIES.items()],
            supports_full_text=True,
            supports_citation_lookup=True,
            supports_keyword_search=True,
            supports_date_filter=True,
            supports_court_filter=False,
            max_results_per_request=20,
            rate_limit_per_minute=30,
            requires_api_key=False,  # works without but better with
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

        # Build the country path
        country_code = ""
        if jurisdiction:
            jur_lower = jurisdiction.lower()
            if jur_lower in LAWS_AFRICA_COUNTRIES:
                country_code = jur_lower
            else:
                # Try matching ISO code
                for code, (_, iso) in LAWS_AFRICA_COUNTRIES.items():
                    if iso == jurisdiction.upper():
                        country_code = code
                        break

        # Laws.Africa uses Akoma Ntoso FRBR URIs
        path = f"/akn/{country_code}" if country_code else "/akn"
        params = {
            "search": query,
            "page": page,
            "page_size": min(page_size, 20),
        }

        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()

        try:
            data = await self._http.get(f"{path}/", params=params)
            if isinstance(data, dict):
                documents = self._parse_results(data)
                total = data.get("count", len(documents))
            else:
                documents, total = [], 0
        except Exception as e:
            logger.error("laws_africa_search_failed", error=str(e))
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
        results = await self.search(f'"{citation}"', page_size=5)
        for doc in results.documents:
            if citation.lower() in doc.title.lower() or citation.lower() in doc.citation.lower():
                return doc
        return results.documents[0] if results.documents else None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        """external_id is a FRBR URI like /akn/ng/act/2020/3"""
        try:
            data = await self._http.get(f"{external_id}.json")
            if isinstance(data, dict):
                return self._parse_work(data)
        except Exception as e:
            logger.error("laws_africa_get_failed", id=external_id, error=str(e))
        return None

    async def get_full_text(self, external_id: str) -> str | None:
        """Fetch the full HTML content of a legislation work."""
        try:
            html = await self._http.get(f"{external_id}/eng/")
            return html if isinstance(html, str) else None
        except Exception:
            return None

    async def get_toc(self, external_id: str) -> list[dict]:
        """Get the table of contents for a legislation work."""
        try:
            data = await self._http.get(f"{external_id}/eng/toc.json")
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def health_check(self) -> bool:
        try:
            data = await self._http.get("/akn/ng/", params={"page_size": "1"})
            return isinstance(data, dict)
        except Exception:
            return False

    def _parse_results(self, data: dict) -> list[SourceDocument]:
        documents = []
        results = data.get("results", [])
        if not isinstance(results, list):
            return documents

        for item in results:
            doc = self._parse_work(item)
            if doc:
                documents.append(doc)
        return documents

    def _parse_work(self, item: dict) -> SourceDocument | None:
        try:
            frbr_uri = item.get("frbr_uri", "")
            title = item.get("title", "")

            # Extract country from FRBR URI: /akn/ng/act/2020/3 -> ng
            parts = frbr_uri.strip("/").split("/") if frbr_uri else []
            country_code = parts[1] if len(parts) > 1 else ""
            country_info = LAWS_AFRICA_COUNTRIES.get(country_code, ("Unknown", country_code.upper()))

            # Determine content type
            doc_subtype = item.get("subtype", "") or (parts[2] if len(parts) > 2 else "")
            content_type = SourceContentType.STATUTE
            if doc_subtype in ("regulation", "si", "ln", "gn"):
                content_type = SourceContentType.REGULATION
            elif doc_subtype == "constitution":
                content_type = SourceContentType.CONSTITUTION

            # Parse dates
            date_str = item.get("date", item.get("publication_date", ""))
            enacted_date = None
            if date_str:
                try:
                    enacted_date = date.fromisoformat(str(date_str)[:10])
                except (ValueError, TypeError):
                    pass

            commencement_date = None
            commencements = item.get("commencements", [])
            if commencements and isinstance(commencements, list):
                first = commencements[0]
                if isinstance(first, dict) and first.get("date"):
                    try:
                        commencement_date = date.fromisoformat(str(first["date"])[:10])
                    except (ValueError, TypeError):
                        pass

            # Repeal status
            is_current = not bool(item.get("repeal"))
            repealed_by = None
            if item.get("repeal") and isinstance(item["repeal"], dict):
                repealed_by = item["repeal"].get("repealing_title")

            return SourceDocument(
                external_id=frbr_uri,
                source_adapter=self.adapter_name,
                title=title,
                content_type=content_type,
                citation=title,  # Laws.Africa uses title as primary citation
                jurisdiction=country_info[0],
                jurisdiction_code=country_info[1],
                issuing_body=item.get("authority", ""),
                date_enacted=enacted_date,
                date_effective=commencement_date,
                date_repealed=None,  # could parse from repeal object
                summary=item.get("description", ""),
                source_url=item.get("url", f"https://laws.africa{frbr_uri}"),
                is_current=is_current,
                superseded_by=repealed_by,
                authority_level="binding",
                topics=item.get("taxonomies", []),
                keywords=item.get("numbered_title", "").split() if item.get("numbered_title") else [],
                raw_metadata=item,
            )
        except Exception as e:
            logger.warning("laws_africa_parse_failed", error=str(e))
            return None
