"""NigeriaLII adapter — Nigerian Legal Information Institute.

Source: https://nigerialii.org (part of the AfricanLII network)
Coverage: Nigerian case law (Supreme Court, Court of Appeal, Federal High Court),
          Laws of the Federation, state laws, regulations
Auth: None required (open access)
Rate limit: Reasonable use
Note: NigeriaLII uses the LII platform (same as AfricanLII, SAFLII, etc.)
      which provides Atom feeds and structured search.
"""

import time
import xml.etree.ElementTree as ET
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

# Nigerian court hierarchy
NIGERIAN_COURTS = {
    "supreme court": CourtLevel.SUPREME,
    "supreme court of nigeria": CourtLevel.SUPREME,
    "court of appeal": CourtLevel.APPELLATE,
    "federal high court": CourtLevel.HIGH,
    "national industrial court": CourtLevel.HIGH,
    "high court": CourtLevel.HIGH,
    "state high court": CourtLevel.HIGH,
    "sharia court of appeal": CourtLevel.APPELLATE,
    "customary court of appeal": CourtLevel.APPELLATE,
    "magistrate court": CourtLevel.MAGISTRATE,
    "tax appeal tribunal": CourtLevel.TRIBUNAL,
    "investment and securities tribunal": CourtLevel.TRIBUNAL,
    "code of conduct tribunal": CourtLevel.TRIBUNAL,
}


class NigeriaLIIAdapter(LegalSourceAdapter):
    """Nigerian law from NigeriaLII — case law, statutes, and regulations."""

    BASE_URL = "https://nigerialii.org"

    def __init__(self):
        self._http = AdapterHTTPClient(
            base_url=self.BASE_URL,
            adapter_name="nigeria_lii",
            rate_limit_per_minute=20,
            timeout=45.0,
            headers={"Accept": "application/json, application/atom+xml, text/html"},
        )

    @property
    def adapter_name(self) -> str:
        return "nigeria_lii"

    @property
    def display_name(self) -> str:
        return "NigeriaLII — Nigerian Legal Information Institute"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            content_types=[
                SourceContentType.CASE_LAW,
                SourceContentType.STATUTE,
                SourceContentType.REGULATION,
            ],
            jurisdictions=["NG"],
            supports_full_text=True,
            supports_citation_lookup=True,
            supports_keyword_search=True,
            supports_date_filter=True,
            supports_court_filter=True,
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

        # NigeriaLII uses a search interface with query parameters
        params = {
            "q": query,
            "page": page,
        }

        # Build collection scope based on content type
        collection = ""
        if content_type == SourceContentType.CASE_LAW:
            collection = "/ng/judgment"
        elif content_type == SourceContentType.STATUTE:
            collection = "/ng/legislation"
        elif content_type == SourceContentType.REGULATION:
            collection = "/ng/legislation"

        if date_from:
            params["date_from"] = date_from.isoformat()
        if date_to:
            params["date_to"] = date_to.isoformat()

        try:
            # Try the JSON search endpoint
            data = await self._http.get(f"/api/search{collection}", params=params)

            if isinstance(data, dict):
                documents = self._parse_search_results(data)
                total = data.get("count", data.get("total", len(documents)))
            elif isinstance(data, str) and data.strip().startswith("<?xml"):
                documents, total = self._parse_atom_results(data)
            else:
                documents, total = [], 0

        except Exception as e:
            logger.error("nigeria_lii_search_failed", error=str(e))
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
        # Search by citation text
        results = await self.search(f'"{citation}"', page_size=5)
        for doc in results.documents:
            if citation.lower() in doc.citation.lower() or citation.lower() in doc.title.lower():
                return doc
        return results.documents[0] if results.documents else None

    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        try:
            data = await self._http.get(f"/api/document/{external_id}")
            if isinstance(data, dict):
                return self._parse_document(data)
        except Exception as e:
            logger.error("nigeria_lii_get_failed", id=external_id, error=str(e))
        return None

    async def health_check(self) -> bool:
        try:
            await self._http.get("/api/search", params={"q": "law", "page": "1"})
            return True
        except Exception:
            return False

    def _parse_search_results(self, data: dict) -> list[SourceDocument]:
        documents = []
        results = data.get("results", data.get("items", []))
        if not isinstance(results, list):
            return documents

        for item in results:
            doc = self._parse_document(item)
            if doc:
                documents.append(doc)

        return documents

    def _parse_document(self, item: dict) -> SourceDocument | None:
        try:
            title = item.get("title", "")
            doc_url = item.get("url", item.get("link", ""))

            # Determine content type from URL or metadata
            content_type = SourceContentType.CASE_LAW
            if "legislation" in str(doc_url).lower() or "act" in title.lower():
                content_type = SourceContentType.STATUTE
            elif "regulation" in str(doc_url).lower():
                content_type = SourceContentType.REGULATION

            # Determine court level from court name
            court_name = item.get("court", item.get("authority", ""))
            court_level = None
            if court_name:
                court_lower = court_name.lower()
                for keyword, level in NIGERIAN_COURTS.items():
                    if keyword in court_lower:
                        court_level = level
                        break

            # Parse date
            date_str = item.get("date", item.get("date_decided", item.get("year", "")))
            date_decided = None
            if date_str:
                try:
                    if len(str(date_str)) == 4:
                        date_decided = date(int(date_str), 1, 1)
                    else:
                        date_decided = date.fromisoformat(str(date_str)[:10])
                except (ValueError, TypeError):
                    pass

            citation = item.get("citation", item.get("media_neutral_citation", title))

            return SourceDocument(
                external_id=item.get("id", doc_url),
                source_adapter=self.adapter_name,
                title=title,
                content_type=content_type,
                citation=citation,
                jurisdiction="Nigeria",
                jurisdiction_code="NG",
                court_name=court_name,
                court_level=court_level,
                date_decided=date_decided if content_type == SourceContentType.CASE_LAW else None,
                date_enacted=date_decided if content_type in (SourceContentType.STATUTE, SourceContentType.REGULATION) else None,
                full_text=item.get("body", item.get("content", "")),
                summary=item.get("snippet", item.get("summary", "")),
                source_url=doc_url if doc_url.startswith("http") else f"{self.BASE_URL}{doc_url}",
                is_current=True,
                authority_level="binding",
                topics=item.get("subjects", item.get("tags", [])),
                raw_metadata=item,
            )
        except Exception as e:
            logger.warning("nigeria_lii_doc_parse_failed", error=str(e))
            return None

    def _parse_atom_results(self, xml_text: str) -> tuple[list[SourceDocument], int]:
        documents = []
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                link_el = entry.find("atom:link", ns)
                summary_el = entry.find("atom:summary", ns)
                id_el = entry.find("atom:id", ns)

                title = title_el.text if title_el is not None else ""
                link = link_el.get("href", "") if link_el is not None else ""
                summary = summary_el.text if summary_el is not None else ""
                ext_id = id_el.text if id_el is not None else link

                doc = SourceDocument(
                    external_id=ext_id,
                    source_adapter=self.adapter_name,
                    title=title,
                    content_type=SourceContentType.CASE_LAW,
                    citation=title,
                    jurisdiction="Nigeria",
                    jurisdiction_code="NG",
                    summary=summary,
                    source_url=link if link.startswith("http") else f"{self.BASE_URL}{link}",
                    is_current=True,
                    authority_level="binding",
                    raw_metadata={},
                )
                documents.append(doc)
        except ET.ParseError as e:
            logger.warning("nigeria_lii_atom_parse_failed", error=str(e))

        return documents, len(documents)
