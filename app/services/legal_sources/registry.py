"""Source Registry — discovers, manages, and routes queries to the right legal source adapters."""

import structlog

from app.services.legal_sources.base import (
    AdapterCapabilities,
    LegalSourceAdapter,
    SourceContentType,
    SourceDocument,
    SourceSearchResult,
)

logger = structlog.get_logger(__name__)

# Jurisdiction code to human-readable name mapping
JURISDICTION_MAP = {
    # Africa
    "NG": "Nigeria",
    "ZA": "South Africa",
    "KE": "Kenya",
    "GH": "Ghana",
    "TZ": "Tanzania",
    "UG": "Uganda",
    "RW": "Rwanda",
    "ET": "Ethiopia",
    "EG": "Egypt",
    # Americas
    "US": "United States",
    "CA": "Canada",
    "BR": "Brazil",
    "MX": "Mexico",
    # Europe
    "GB": "United Kingdom",
    "EU": "European Union",
    "DE": "Germany",
    "FR": "France",
    "NL": "Netherlands",
    "IE": "Ireland",
    "CH": "Switzerland",
    # Asia-Pacific
    "IN": "India",
    "AU": "Australia",
    "NZ": "New Zealand",
    "SG": "Singapore",
    "HK": "Hong Kong",
    "MY": "Malaysia",
    "PK": "Pakistan",
    # Middle East
    "AE": "United Arab Emirates",
    "SA": "Saudi Arabia",
    # International
    "INTL": "International",
    "ECHR": "European Court of Human Rights",
    "ICJ": "International Court of Justice",
}

# Jurisdiction aliases — maps common names and variations to ISO codes
JURISDICTION_ALIASES = {
    "nigeria": "NG",
    "nigerian": "NG",
    "nigerian law": "NG",
    "south africa": "ZA",
    "kenya": "KE",
    "ghana": "GH",
    "united states": "US",
    "usa": "US",
    "us": "US",
    "american": "US",
    "federal": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "england": "GB",
    "england and wales": "GB",
    "english law": "GB",
    "european union": "EU",
    "eu": "EU",
    "eu law": "EU",
    "india": "IN",
    "indian": "IN",
    "australia": "AU",
    "australian": "AU",
    "canada": "CA",
    "canadian": "CA",
    "singapore": "SG",
    "hong kong": "HK",
    "malaysia": "MY",
    "uae": "AE",
    "dubai": "AE",
    "international": "INTL",
    "echr": "ECHR",
}


def normalize_jurisdiction(jurisdiction: str) -> str:
    """Convert a jurisdiction string (free text or code) to a standard ISO code."""
    if not jurisdiction:
        return ""
    clean = jurisdiction.strip().upper()
    if clean in JURISDICTION_MAP:
        return clean
    lower = jurisdiction.strip().lower()
    if lower in JURISDICTION_ALIASES:
        return JURISDICTION_ALIASES[lower]
    return jurisdiction.strip()


class SourceRegistry:
    """Central registry for all legal source adapters.

    Manages adapter lifecycle and routes queries to the right adapters
    based on jurisdiction and content type.
    """

    def __init__(self):
        self._adapters: dict[str, LegalSourceAdapter] = {}
        self._jurisdiction_index: dict[str, list[str]] = {}  # jurisdiction -> [adapter_names]
        self._content_type_index: dict[SourceContentType, list[str]] = {}

    def register(self, adapter: LegalSourceAdapter) -> None:
        name = adapter.adapter_name
        if name in self._adapters:
            logger.warning("adapter_already_registered", adapter=name)
            return

        self._adapters[name] = adapter

        for jurisdiction in adapter.capabilities.jurisdictions:
            self._jurisdiction_index.setdefault(jurisdiction, []).append(name)

        for content_type in adapter.capabilities.content_types:
            self._content_type_index.setdefault(content_type, []).append(name)

        logger.info(
            "adapter_registered",
            adapter=name,
            jurisdictions=adapter.capabilities.jurisdictions,
            content_types=[ct.value for ct in adapter.capabilities.content_types],
        )

    def get_adapter(self, name: str) -> LegalSourceAdapter | None:
        return self._adapters.get(name)

    def get_adapters_for_jurisdiction(self, jurisdiction: str) -> list[LegalSourceAdapter]:
        code = normalize_jurisdiction(jurisdiction)
        adapter_names = self._jurisdiction_index.get(code, [])
        return [self._adapters[n] for n in adapter_names if n in self._adapters]

    def get_adapters_for_content_type(self, content_type: SourceContentType) -> list[LegalSourceAdapter]:
        adapter_names = self._content_type_index.get(content_type, [])
        return [self._adapters[n] for n in adapter_names if n in self._adapters]

    def get_best_adapters(
        self,
        jurisdiction: str | None = None,
        content_type: SourceContentType | None = None,
    ) -> list[LegalSourceAdapter]:
        """Find the best adapters for a given jurisdiction and content type."""
        candidates = set(self._adapters.keys())

        if jurisdiction:
            code = normalize_jurisdiction(jurisdiction)
            jurisdiction_adapters = set(self._jurisdiction_index.get(code, []))
            if jurisdiction_adapters:
                candidates &= jurisdiction_adapters

        if content_type:
            ct_adapters = set(self._content_type_index.get(content_type, []))
            if ct_adapters:
                candidates &= ct_adapters

        return [self._adapters[n] for n in candidates]

    def list_adapters(self) -> list[dict]:
        return [
            {
                "name": a.adapter_name,
                "display_name": a.display_name,
                "jurisdictions": a.capabilities.jurisdictions,
                "content_types": [ct.value for ct in a.capabilities.content_types],
                "requires_api_key": a.capabilities.requires_api_key,
            }
            for a in self._adapters.values()
        ]

    def list_supported_jurisdictions(self) -> dict[str, str]:
        """Return all jurisdictions that have at least one adapter."""
        return {
            code: JURISDICTION_MAP.get(code, code)
            for code in self._jurisdiction_index.keys()
        }

    async def search_all(
        self,
        query: str,
        jurisdiction: str | None = None,
        content_type: SourceContentType | None = None,
        date_from=None,
        date_to=None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[SourceSearchResult]:
        """Search across all relevant adapters for a jurisdiction/content type."""
        adapters = self.get_best_adapters(jurisdiction, content_type)

        if not adapters:
            logger.warning("no_adapters_found", jurisdiction=jurisdiction, content_type=content_type)
            return []

        import asyncio
        tasks = [
            adapter.search(
                query=query,
                content_type=content_type,
                jurisdiction=jurisdiction,
                date_from=date_from,
                date_to=date_to,
                page=page,
                page_size=page_size,
            )
            for adapter in adapters
        ]

        results = []
        for coro in asyncio.as_completed(tasks):
            try:
                result = await coro
                results.append(result)
            except Exception as e:
                logger.error("adapter_search_failed", error=str(e))

        return results

    async def find_by_citation(self, citation: str, jurisdiction: str | None = None) -> SourceDocument | None:
        """Look up a specific citation across all relevant adapters."""
        adapters = self.get_best_adapters(jurisdiction) if jurisdiction else list(self._adapters.values())

        for adapter in adapters:
            if not adapter.capabilities.supports_citation_lookup:
                continue
            try:
                doc = await adapter.get_by_citation(citation)
                if doc:
                    return doc
            except Exception as e:
                logger.error("citation_lookup_failed", adapter=adapter.adapter_name, error=str(e))

        return None

    async def check_good_law(self, citation: str, jurisdiction: str | None = None) -> dict:
        """Check if a citation is still good law across relevant sources."""
        adapters = self.get_best_adapters(jurisdiction) if jurisdiction else list(self._adapters.values())

        for adapter in adapters:
            try:
                result = await adapter.check_good_law(citation)
                if result.get("treatment") != "unknown":
                    return result
            except Exception as e:
                logger.error("good_law_check_failed", adapter=adapter.adapter_name, error=str(e))

        return {"is_good_law": True, "treatment": "unknown", "overruled_by": None}

    async def health_check_all(self) -> dict[str, bool]:
        """Health check all registered adapters."""
        results = {}
        for name, adapter in self._adapters.items():
            try:
                results[name] = await adapter.health_check()
            except Exception:
                results[name] = False
        return results


# Singleton registry
_registry: SourceRegistry | None = None


def get_source_registry() -> SourceRegistry:
    global _registry
    if _registry is None:
        _registry = SourceRegistry()
        _register_all_adapters(_registry)
    return _registry


def _register_all_adapters(registry: SourceRegistry) -> None:
    """Register all available adapters.

    Priority order based on verified API availability:
    1. Government APIs with documented, stable endpoints
    2. LII APIs backed by academic institutions
    3. API-key-gated free sources
    """
    from app.core.config import get_settings
    settings = get_settings()

    # --- P0: Primary sources (verified stable APIs) ---

    # US case law — CourtListener is the primary US source. It now includes all
    # Harvard Caselaw Access Project data (Harvard CAP API was deprecated in 2024).
    from app.services.legal_sources.adapters.courtlistener import CourtListenerAdapter
    registry.register(CourtListenerAdapter())

    # US federal regulations — fully open, no auth needed
    from app.services.legal_sources.adapters.ecfr import ECFRAdapter
    registry.register(ECFRAdapter())

    # African legislation (20+ countries including Nigeria) — this is THE source.
    # NigeriaLII, SAFLII, KenyaLII, GhaLII all feed from Laws.Africa data.
    from app.services.legal_sources.adapters.laws_africa import LawsAfricaAdapter
    registry.register(LawsAfricaAdapter())

    # UK legislation — official government API, open access
    from app.services.legal_sources.adapters.legislation_gov_uk import LegislationGovUKAdapter
    registry.register(LegislationGovUKAdapter())

    # UK case law — National Archives, Open Justice Licence (commercial reuse OK)
    from app.services.legal_sources.adapters.uk_caselaw import UKCaseLawAdapter
    registry.register(UKCaseLawAdapter())

    # EU legislation + CJEU case law
    from app.services.legal_sources.adapters.eur_lex import EURLexAdapter
    registry.register(EURLexAdapter())

    # --- P1: Secondary sources (API-key-gated but free) ---

    # Canada — requires free API key from developer.canlii.org
    from app.services.legal_sources.adapters.canlii import CanLIIAdapter
    registry.register(CanLIIAdapter())

    # India — requires API key (apply at indiankanoon.org/api)
    from app.services.legal_sources.adapters.indian_kanoon import IndianKanoonAdapter
    registry.register(IndianKanoonAdapter())

    # --- P2: Best-effort sources (work but less stable/documented) ---

    # Nigeria case law via NigeriaLII (web-based, no official API — best effort)
    from app.services.legal_sources.adapters.nigeria_lii import NigeriaLIIAdapter
    registry.register(NigeriaLIIAdapter())

    # Pan-African case law via AfricanLII (web-based, best effort)
    from app.services.legal_sources.adapters.african_lii import AfricanLIIAdapter
    registry.register(AfricanLIIAdapter())

    # Kenya case law (web-based, best effort)
    from app.services.legal_sources.adapters.kenya_law import KenyaLawAdapter
    registry.register(KenyaLawAdapter())

    # Australia legislation via Federal Register of Legislation
    # Note: AustLII explicitly blocks programmatic access — we only use the
    # Federal Register of Legislation API which is open
    from app.services.legal_sources.adapters.austlii import AustLIIAdapter
    registry.register(AustLIIAdapter())

    logger.info("all_adapters_registered", count=len(registry._adapters))
