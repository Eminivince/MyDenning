"""
Legal Source Adapters - Pluggable architecture for integrating with authoritative legal databases worldwide.

Strategy (in priority order):
1. Official government APIs (free, authoritative, stable)
2. Legal Information Institute APIs (free, well-maintained, academically backed)
3. Commercial APIs (paid, comprehensive, contractually guaranteed)
4. NEVER scrape — use structured APIs only

Supported jurisdictions and sources:
- Nigeria: NigeriaLII, Laws of the Federation
- United States: CourtListener (Free Law Project), Congress.gov, eCFR, Harvard Caselaw Access Project
- United Kingdom: legislation.gov.uk, National Archives
- European Union: EUR-Lex, HUDOC (ECHR)
- Kenya: Kenya Law Reports
- South Africa: SAFLII
- Ghana: GhanaLII
- India: Indian Kanoon API
- Canada: CanLII
- Australia: AustLII, Federal Register of Legislation
- International: WorldLII, AfricanLII
"""

from app.services.legal_sources.registry import SourceRegistry, get_source_registry
from app.services.legal_sources.base import LegalSourceAdapter, SourceSearchResult, SourceDocument

__all__ = [
    "SourceRegistry",
    "get_source_registry",
    "LegalSourceAdapter",
    "SourceSearchResult",
    "SourceDocument",
]
