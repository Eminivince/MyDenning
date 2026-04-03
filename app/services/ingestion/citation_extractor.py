import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ExtractedCitation:
    raw_text: str
    normalized: str | None
    citation_type: str  # case_law, statute, regulation, section_ref
    jurisdiction: str | None
    start_pos: int
    end_pos: int


class CitationExtractor:
    """Extracts legal citations from text using pattern matching."""

    # Nigerian case law: Party v Party [Year] court_report page
    NIGERIAN_CASE = re.compile(
        r'([A-Z][a-zA-Z\s&.,]+)\s+v\.?\s+([A-Z][a-zA-Z\s&.,]+?)\s*'
        r'\[(\d{4})\]\s*(\d+\s+[A-Z]+(?:\s+[A-Z]+)*\s+\d+)',
        re.MULTILINE
    )

    # General case citation: Party v Party (Year) report
    GENERAL_CASE = re.compile(
        r'([A-Z][a-zA-Z\s&.,]+)\s+v\.?\s+([A-Z][a-zA-Z\s&.,]+?)\s*'
        r'[\[\(](\d{4})[\]\)]\s*([A-Z0-9\s]+\d+)',
        re.MULTILINE
    )

    # UK/Nigeria statutes: Act Name Year / Cap X, LFN Year
    STATUTE_CAP = re.compile(
        r'Cap\.?\s+([A-Z]\d+),?\s*(?:Laws?\s+of\s+the\s+Federation\s+of\s+Nigeria|LFN)\s*(?:,?\s*(\d{4}))?',
        re.IGNORECASE
    )

    STATUTE_ACT = re.compile(
        r'(?:the\s+)?([A-Z][a-zA-Z\s]+?)\s+Act,?\s+(\d{4})',
    )

    # Section references: Section 5(1)(a), s.5(1)
    SECTION_REF = re.compile(
        r'(?:Section|s\.?)\s*(\d+(?:\(\d+\))*(?:\([a-z]\))*)',
        re.IGNORECASE
    )

    # Regulation references
    REGULATION_REF = re.compile(
        r'(?:Regulation|Reg\.?)\s*(\d+(?:\.\d+)*)',
        re.IGNORECASE
    )

    # US case citations: Volume Reporter Page (Court Year)
    US_CASE = re.compile(
        r'(\d+)\s+(U\.S\.|S\.\s*Ct\.|F\.\s*(?:2d|3d|4th)?|F\.\s*Supp\.\s*(?:2d|3d)?)\s+(\d+)',
    )

    # EU legislation
    EU_DIRECTIVE = re.compile(
        r'(?:Directive|Regulation)\s+(?:\((?:EU|EC)\)\s+)?(?:No\.?\s+)?(\d+/\d+)',
        re.IGNORECASE
    )

    def extract_citations(self, text: str, jurisdiction: str | None = None) -> list[ExtractedCitation]:
        citations: list[ExtractedCitation] = []
        seen_positions: set[tuple[int, int]] = set()

        extractors = [
            (self.NIGERIAN_CASE, "case_law", self._normalize_nigerian_case, "Nigeria"),
            (self.US_CASE, "case_law", self._normalize_us_case, "United States"),
            (self.GENERAL_CASE, "case_law", self._normalize_general_case, None),
            (self.STATUTE_CAP, "statute", self._normalize_cap, "Nigeria"),
            (self.STATUTE_ACT, "statute", self._normalize_act, None),
            (self.SECTION_REF, "section_ref", self._normalize_section, None),
            (self.REGULATION_REF, "regulation", self._normalize_regulation, None),
            (self.EU_DIRECTIVE, "regulation", self._normalize_eu, "EU"),
        ]

        for pattern, cite_type, normalizer, default_jurisdiction in extractors:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                if any(s <= span[0] < e or s < span[1] <= e for s, e in seen_positions):
                    continue

                seen_positions.add(span)
                raw = match.group(0).strip()
                normalized = normalizer(match)

                citations.append(ExtractedCitation(
                    raw_text=raw,
                    normalized=normalized,
                    citation_type=cite_type,
                    jurisdiction=jurisdiction or default_jurisdiction,
                    start_pos=span[0],
                    end_pos=span[1],
                ))

        citations.sort(key=lambda c: c.start_pos)
        return citations

    def _normalize_nigerian_case(self, match: re.Match) -> str:
        p1, p2, year, report = match.groups()
        return f"{p1.strip()} v {p2.strip()} [{year}] {report.strip()}"

    def _normalize_general_case(self, match: re.Match) -> str:
        p1, p2, year, report = match.groups()
        return f"{p1.strip()} v {p2.strip()} [{year}] {report.strip()}"

    def _normalize_us_case(self, match: re.Match) -> str:
        vol, reporter, page = match.groups()
        return f"{vol} {reporter} {page}"

    def _normalize_cap(self, match: re.Match) -> str:
        cap, year = match.groups()
        year_str = f", LFN {year}" if year else ", LFN"
        return f"Cap {cap}{year_str}"

    def _normalize_act(self, match: re.Match) -> str:
        name, year = match.groups()
        return f"{name.strip()} Act, {year}"

    def _normalize_section(self, match: re.Match) -> str:
        return f"Section {match.group(1)}"

    def _normalize_regulation(self, match: re.Match) -> str:
        return f"Regulation {match.group(1)}"

    def _normalize_eu(self, match: re.Match) -> str:
        return match.group(0).strip()

    def extract_dates(self, text: str) -> list[dict]:
        date_patterns = [
            re.compile(r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})', re.IGNORECASE),
            re.compile(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})', re.IGNORECASE),
            re.compile(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})'),
        ]
        dates = []
        for pattern in date_patterns:
            for match in pattern.finditer(text):
                dates.append({
                    "raw_text": match.group(0),
                    "position": match.start(),
                })
        return dates

    def extract_parties(self, text: str) -> list[str]:
        patterns = [
            re.compile(r'(?:between|BETWEEN)\s+(.+?)\s+(?:and|AND)\s+(.+?)(?:\s*[\(\.])', re.DOTALL),
            re.compile(r'(?:"Party"|"the Company"|"the Employer"|"the Contractor"|"the Client"|"the Vendor"|"the Supplier"|"the Licensor"|"the Licensee")\s*(?:means|refers to)?\s*([A-Z][A-Za-z\s&.,]+?)(?:\s*[,\.])', re.MULTILINE),
        ]
        parties = set()
        for pattern in patterns:
            for match in pattern.finditer(text[:5000]):
                for group in match.groups():
                    party = group.strip().rstrip(",.")
                    if party and len(party) < 200:
                        parties.add(party)
        return list(parties)

    def extract_monetary_values(self, text: str) -> list[dict]:
        pattern = re.compile(
            r'(?:NGN|USD|GBP|EUR|₦|\$|£|€)\s*[\d,]+(?:\.\d{2})?|'
            r'[\d,]+(?:\.\d{2})?\s*(?:Naira|Dollars|Pounds|Euro)',
            re.IGNORECASE
        )
        values = []
        for match in pattern.finditer(text):
            values.append({
                "raw_text": match.group(0),
                "position": match.start(),
            })
        return values
