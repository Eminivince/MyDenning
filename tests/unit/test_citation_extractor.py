import pytest

from app.services.ingestion.citation_extractor import CitationExtractor


@pytest.fixture
def extractor():
    return CitationExtractor()


class TestCitationExtractor:
    def test_extract_nigerian_case(self, extractor):
        text = "As held in Ariori v Elemo [1983] 1 SCNLR 1, the court stated..."
        citations = extractor.extract_citations(text, "Nigeria")
        assert len(citations) >= 1
        case_cites = [c for c in citations if c.citation_type == "case_law"]
        assert len(case_cites) >= 1

    def test_extract_statute_cap(self, extractor):
        text = "Under Cap C20, Laws of the Federation of Nigeria, 2004"
        citations = extractor.extract_citations(text, "Nigeria")
        statute_cites = [c for c in citations if c.citation_type == "statute"]
        assert len(statute_cites) >= 1

    def test_extract_act(self, extractor):
        text = "The Companies and Allied Matters Act, 2020 provides that..."
        citations = extractor.extract_citations(text, "Nigeria")
        statute_cites = [c for c in citations if c.citation_type == "statute"]
        assert len(statute_cites) >= 1

    def test_extract_section_reference(self, extractor):
        text = "Pursuant to Section 5(1)(a) of the Act..."
        citations = extractor.extract_citations(text)
        section_cites = [c for c in citations if c.citation_type == "section_ref"]
        assert len(section_cites) >= 1

    def test_extract_dates(self, extractor):
        text = "The agreement dated 15 January, 2024 shall expire on 31 December, 2025."
        dates = extractor.extract_dates(text)
        assert len(dates) >= 2

    def test_extract_monetary_values(self, extractor):
        text = "The total consideration is NGN 5,000,000.00 (Five Million Naira)."
        values = extractor.extract_monetary_values(text)
        assert len(values) >= 1

    def test_extract_parties(self, extractor):
        text = 'THIS AGREEMENT is made between ABC Limited and XYZ Corporation (the "Parties").'
        parties = extractor.extract_parties(text)
        assert len(parties) >= 1

    def test_no_citations_in_plain_text(self, extractor):
        text = "This is a simple paragraph with no legal citations."
        citations = extractor.extract_citations(text)
        assert len(citations) == 0


class TestChunker:
    def test_chunk_basic(self):
        from app.services.ingestion.chunker import LegalDocumentChunker
        from app.services.document_parser.parser import ParsedSection

        chunker = LegalDocumentChunker(chunk_size=50, chunk_overlap=10)
        sections = [
            ParsedSection(
                title="Test Section",
                content="This is a test section with some content. " * 20,
                page_number=1,
                clause_number="1.1",
                section_type="clause",
            )
        ]
        chunks = chunker.chunk_sections(sections)
        assert len(chunks) > 1
        assert all(c.clause_number == "1.1" for c in chunks)

    def test_chunk_preserves_small_sections(self):
        from app.services.ingestion.chunker import LegalDocumentChunker
        from app.services.document_parser.parser import ParsedSection

        chunker = LegalDocumentChunker(chunk_size=1000, chunk_overlap=200)
        sections = [
            ParsedSection(
                title="Short",
                content="Short content.",
                page_number=1,
                clause_number=None,
                section_type="paragraph",
            )
        ]
        chunks = chunker.chunk_sections(sections)
        assert len(chunks) == 1
        assert chunks[0].content == "Short content."
