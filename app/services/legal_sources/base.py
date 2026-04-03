"""Base adapter interface and data models for all legal source integrations."""

import abc
import enum
from dataclasses import dataclass, field
from datetime import date, datetime


class SourceContentType(str, enum.Enum):
    CASE_LAW = "case_law"
    STATUTE = "statute"
    REGULATION = "regulation"
    GUIDANCE = "guidance"
    TREATY = "treaty"
    SECONDARY = "secondary"
    BILL = "bill"
    CONSTITUTION = "constitution"


class CourtLevel(int, enum.Enum):
    SUPREME = 1
    APPELLATE = 2
    HIGH = 3
    DISTRICT = 4
    TRIBUNAL = 5
    MAGISTRATE = 6


@dataclass
class SourceDocument:
    """A legal document retrieved from an external source."""
    external_id: str
    source_adapter: str  # e.g., "courtlistener", "legislation_gov_uk"
    title: str
    content_type: SourceContentType
    citation: str
    jurisdiction: str
    jurisdiction_code: str  # ISO 3166-1 alpha-2 or sub-jurisdiction code

    # Court metadata (for case law)
    court_name: str | None = None
    court_level: CourtLevel | None = None
    judges: list[str] | None = None

    # Issuing body (for statutes/regulations)
    issuing_body: str | None = None

    # Dates
    date_decided: date | None = None
    date_enacted: date | None = None
    date_effective: date | None = None
    date_repealed: date | None = None

    # Content
    full_text: str | None = None
    summary: str | None = None
    headnote: str | None = None
    key_passages: list[str] | None = None

    # Status
    is_current: bool = True
    superseded_by: str | None = None
    authority_level: str = "binding"  # binding, persuasive, secondary

    # Relationships
    citations_to: list[str] = field(default_factory=list)  # outgoing citations
    cited_by_count: int = 0

    # Topics
    topics: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    # Source URL for attribution
    source_url: str | None = None

    # Raw response for debugging/audit
    raw_metadata: dict = field(default_factory=dict)


@dataclass
class SourceSearchResult:
    """A search result from a legal source."""
    documents: list[SourceDocument]
    total_count: int
    page: int
    page_size: int
    query: str
    source_adapter: str
    search_time_ms: int


@dataclass
class AdapterCapabilities:
    """Declares what a source adapter can do."""
    content_types: list[SourceContentType]
    jurisdictions: list[str]  # ISO codes
    supports_full_text: bool
    supports_citation_lookup: bool
    supports_keyword_search: bool
    supports_date_filter: bool
    supports_court_filter: bool
    max_results_per_request: int
    rate_limit_per_minute: int
    requires_api_key: bool


class LegalSourceAdapter(abc.ABC):
    """Base class for all legal source integrations.

    Each adapter connects to one external legal database/API and provides
    a uniform interface for searching and retrieving legal documents.
    """

    @property
    @abc.abstractmethod
    def adapter_name(self) -> str:
        """Unique identifier for this adapter (e.g., 'courtlistener')."""

    @property
    @abc.abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g., 'CourtListener - Free Law Project')."""

    @property
    @abc.abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        """Declare what this adapter supports."""

    @abc.abstractmethod
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
        """Search for legal documents matching the query."""

    @abc.abstractmethod
    async def get_by_citation(self, citation: str) -> SourceDocument | None:
        """Retrieve a specific document by its legal citation."""

    @abc.abstractmethod
    async def get_by_id(self, external_id: str) -> SourceDocument | None:
        """Retrieve a specific document by its external ID."""

    async def get_citing_documents(self, external_id: str, limit: int = 20) -> list[SourceDocument]:
        """Get documents that cite the given document. Override if supported."""
        return []

    async def get_cited_documents(self, external_id: str, limit: int = 20) -> list[SourceDocument]:
        """Get documents cited by the given document. Override if supported."""
        return []

    async def check_good_law(self, citation: str) -> dict:
        """Check if a citation is still good law (not overruled/repealed).
        Returns: {"is_good_law": bool, "treatment": str, "overruled_by": str|None}
        Override if the source supports this.
        """
        return {"is_good_law": True, "treatment": "unknown", "overruled_by": None}

    async def health_check(self) -> bool:
        """Verify the adapter can reach its source. Used for /health/ready."""
        return True
