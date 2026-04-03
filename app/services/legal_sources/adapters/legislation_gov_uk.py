"""legislation.gov.uk adapter — UK National Archives.

Source: https://www.legislation.gov.uk (REST + Atom feeds)
Coverage: All UK primary and secondary legislation
Auth: None required (open API)
Rate limit: Reasonable use
"""

import time
import xml.etree.ElementTree as ET
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

# legislation.gov.uk document type mapping
TYPE_MAP = {
    "ukpga": ("UK Public General Act", SourceContentType.STATUTE),
    "uksi": ("UK Statutory Instrument", SourceContentType.REGULATION),
    "ukppa": ("UK Private and Personal Act", SourceContentType.STATUTE),
    "ukla": ("UK Local Act", SourceContentType.STATUTE),
    "asp": ("Act of the Scottish Parliament", SourceContentType.STATUTE),
    "ssi": ("Scottish Statutory Instrument", SourceContentType.REGULATION),
    "anaw": ("Act of the National Assembly for Wales", SourceContentType.STATUTE),
    "wsi": ("Wales Statutory Instrument", SourceContentType.REGULATION),
    "nia": ("Act of the Northern Ireland Assembly", SourceContentType.STATUTE),
    "nisr": ("Northern Ireland Statutory Rule", SourceContentType.REGULATION),
    "eur": ("EU Retained Legislation", SourceContentType.REGULATION),
}

ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "leg": "http://www.legislation.gov.uk/namespaces/legislation",
    "ukm": "http://www.legislation.gov.uk/namespaces/metadata",
}


class LegislationGovUKAdapter(LegalSourceAdapter):
    """UK primary and secondary legislation from legislation.gov.uk."""

    BASE_URL = "https://www.legislation.gov.uk"

    def __init__(self):
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="legislation_gov_uk",
            rate_limit_per_minute=30,
            headers={"Accept": "application/atom+xml"},
        )

    @property
    def adapter_name(self) -> str:
        return "legislation_gov_uk"

    @property
    def display_name(self) -> str:
        return "legislation.gov.uk — UK National Archives"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[SourceContentType.STATUTE, SourceContentType.REGULATION],
            jurisdictions=["GB"],
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
        params = {"text": query, "page": page, "results-count": min(page_size, 20)}

        if date_from:
            params["start-year"] = date_from.year
        if date_to:
            params["end-year"] = date_to.year

        # Build type filter
        if content_type == SourceContentType.STATUTE:
            type_path = "/ukpga+asp+anaw+nia"
        elif content_type == SourceContentType.REGULATION:
            type_path = "/uksi+ssi+wsi+nisr"
        else:
            type_path = ""

        try:
            response_text = await self._http.get(f"{type_path}/data.feed", params=params)
            documents, total = self._parse_atom_feed(response_text)
        except Exception as e:
            logger.error("legislation_gov_uk_search_failed", error=str(e))
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
        # Try common patterns: "Theft Act 1968" -> /ukpga/1968/60
        results = await self.search(citation, page_size=1)
        if results.documents:
            return results.documents[0]
        return None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        try:
            # external_id is a URI like /ukpga/2006/46
            response_text = await self._http.get(f"{external_id}/data.feed")
            documents, _ = self._parse_atom_feed(response_text)
            if documents:
                # Fetch full text
                try:
                    text_response = await self._http.get(f"{external_id}/data.xml")
                    if isinstance(text_response, str):
                        documents[0].full_text = self._extract_text_from_xml(text_response)
                except Exception:
                    pass
                return documents[0]
        except Exception as e:
            logger.error("legislation_gov_uk_get_failed", id=external_id, error=str(e))
        return None

    async def health_check(self) -> bool:
        try:
            await self._http.get("/ukpga/data.feed", params={"results-count": 1})
            return True
        except Exception:
            return False

    def _parse_atom_feed(self, xml_text: str) -> tuple[list[SourceDocument], int]:
        if not xml_text or not isinstance(xml_text, str):
            return [], 0

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return [], 0

        documents = []

        # Get total results
        total_el = root.find(".//opensearch:totalResults", {"opensearch": "http://a9.com/-/spec/opensearch/1.1/"})
        total = int(total_el.text) if total_el is not None and total_el.text else 0

        for entry in root.findall("atom:entry", ATOM_NS):
            doc = self._parse_entry(entry)
            if doc:
                documents.append(doc)

        return documents, total

    def _parse_entry(self, entry) -> SourceDocument | None:
        try:
            title_el = entry.find("atom:title", ATOM_NS)
            title = title_el.text if title_el is not None else "Unknown"

            id_el = entry.find("atom:id", ATOM_NS)
            external_id = id_el.text if id_el is not None else ""

            # Extract doc type from URI
            uri_parts = external_id.split("/") if external_id else []
            doc_type_code = uri_parts[3] if len(uri_parts) > 3 else ""
            type_info = TYPE_MAP.get(doc_type_code, ("Unknown", SourceContentType.STATUTE))

            # Extract year
            year = None
            if len(uri_parts) > 4:
                try:
                    year = int(uri_parts[4])
                except ValueError:
                    pass

            summary_el = entry.find("atom:summary", ATOM_NS)
            summary = summary_el.text if summary_el is not None else ""

            updated_el = entry.find("atom:updated", ATOM_NS)

            return SourceDocument(
                external_id=external_id.replace("http://www.legislation.gov.uk", ""),
                source_adapter=self.adapter_name,
                title=title,
                content_type=type_info[1],
                citation=title,
                jurisdiction="United Kingdom",
                jurisdiction_code="GB",
                issuing_body="UK Parliament" if type_info[1] == SourceContentType.STATUTE else "UK Government",
                date_enacted=date(year, 1, 1) if year else None,
                summary=summary,
                source_url=f"https://www.legislation.gov.uk{external_id}" if external_id.startswith("/") else external_id,
                is_current=True,
                authority_level="binding",
                raw_metadata={"type_code": doc_type_code, "type_name": type_info[0]},
            )
        except Exception as e:
            logger.warning("legislation_entry_parse_failed", error=str(e))
            return None

    def _extract_text_from_xml(self, xml_text: str) -> str:
        try:
            root = ET.fromstring(xml_text)
            texts = []
            for elem in root.iter():
                if elem.text and elem.text.strip():
                    texts.append(elem.text.strip())
            return "\n".join(texts)
        except Exception:
            return ""
