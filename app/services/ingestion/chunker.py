import re
from dataclasses import dataclass

import structlog

from app.services.document_parser.parser import ParsedSection

logger = structlog.get_logger(__name__)


@dataclass
class TextChunk:
    content: str
    chunk_index: int
    page_number: int | None
    section_title: str | None
    clause_number: str | None
    chunk_type: str
    token_count: int
    metadata: dict


class LegalDocumentChunker:
    """Chunks legal documents preserving clause boundaries and legal structure."""

    SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_sections(self, sections: list[ParsedSection]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        chunk_index = 0

        for section in sections:
            if not section.content.strip():
                continue

            section_token_count = self._estimate_tokens(section.content)

            if section_token_count <= self.chunk_size:
                chunks.append(TextChunk(
                    content=section.content,
                    chunk_index=chunk_index,
                    page_number=section.page_number,
                    section_title=section.title,
                    clause_number=section.clause_number,
                    chunk_type=section.section_type,
                    token_count=section_token_count,
                    metadata={},
                ))
                chunk_index += 1
            else:
                sub_chunks = self._split_section(section, chunk_index)
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)

        return chunks

    def _split_section(self, section: ParsedSection, start_index: int) -> list[TextChunk]:
        sentences = self.SENTENCE_BOUNDARY.split(section.content)
        if len(sentences) <= 1:
            sentences = self._split_by_newlines(section.content)

        chunks: list[TextChunk] = []
        current_chunk: list[str] = []
        current_tokens = 0
        idx = start_index

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_tokens = self._estimate_tokens(sentence)

            if current_tokens + sentence_tokens > self.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunks.append(TextChunk(
                    content=chunk_text,
                    chunk_index=idx,
                    page_number=section.page_number,
                    section_title=section.title,
                    clause_number=section.clause_number,
                    chunk_type=section.section_type,
                    token_count=self._estimate_tokens(chunk_text),
                    metadata={},
                ))
                idx += 1

                overlap_text = self._get_overlap_text(current_chunk)
                current_chunk = [overlap_text] if overlap_text else []
                current_tokens = self._estimate_tokens(overlap_text) if overlap_text else 0

            current_chunk.append(sentence)
            current_tokens += sentence_tokens

        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(TextChunk(
                content=chunk_text,
                chunk_index=idx,
                page_number=section.page_number,
                section_title=section.title,
                clause_number=section.clause_number,
                chunk_type=section.section_type,
                token_count=self._estimate_tokens(chunk_text),
                metadata={},
            ))

        return chunks

    def _split_by_newlines(self, text: str) -> list[str]:
        parts = text.split("\n")
        return [p.strip() for p in parts if p.strip()]

    def _get_overlap_text(self, chunks: list[str]) -> str:
        overlap_parts: list[str] = []
        overlap_tokens = 0

        for part in reversed(chunks):
            part_tokens = self._estimate_tokens(part)
            if overlap_tokens + part_tokens > self.chunk_overlap:
                break
            overlap_parts.insert(0, part)
            overlap_tokens += part_tokens

        return " ".join(overlap_parts)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text.split()) * 4 // 3  # rough approximation
