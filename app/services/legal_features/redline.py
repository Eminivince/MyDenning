"""Document redline service — generates tracked-changes output between two document versions.

Produces:
1. Structured diff with clause-level change tracking
2. Markdown redline (insertions/deletions marked)
3. JSON redline data for rendering in any frontend
4. Legal commentary explaining the significance of each change
"""

import difflib
import re
import time
import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.analysis import AnalysisResult, AnalysisType, RiskLevel
from app.models.document import Document
from app.services.reasoning.llm_client import LLMClient

logger = structlog.get_logger(__name__)


@dataclass
class RedlineChange:
    change_type: str  # addition, deletion, modification, moved
    location: str  # clause number or section reference
    original_text: str
    new_text: str
    legal_significance: str
    risk_level: str  # critical, high, medium, low, info
    commentary: str
    page_in_doc1: int | None = None
    page_in_doc2: int | None = None


@dataclass
class RedlineResult:
    summary: str
    total_changes: int
    additions: int
    deletions: int
    modifications: int
    changes: list[RedlineChange]
    risk_level: str
    markdown_redline: str
    html_redline: str


class RedlineService:
    """Generates legal redlines between two documents or document versions."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()
        self.settings = get_settings()

    async def generate_redline(
        self,
        document_id_1: uuid.UUID,
        document_id_2: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        focus_areas: list[str] | None = None,
    ) -> dict:
        start_time = time.time()

        doc1 = await self.db.get(Document, document_id_1)
        doc2 = await self.db.get(Document, document_id_2)
        if not doc1 or not doc1.raw_text:
            raise ValueError(f"Document {document_id_1} not found or not processed")
        if not doc2 or not doc2.raw_text:
            raise ValueError(f"Document {document_id_2} not found or not processed")

        # Step 1: Structural diff at paragraph/clause level
        structural_diff = self._compute_structural_diff(doc1.raw_text, doc2.raw_text)

        # Step 2: Generate character-level redline markup
        markdown_redline = self._generate_markdown_redline(doc1.raw_text, doc2.raw_text)
        html_redline = self._generate_html_redline(doc1.raw_text, doc2.raw_text)

        # Step 3: LLM analysis of legal significance of changes
        llm_analysis = await self._analyze_changes_legally(
            structural_diff, doc1.title, doc2.title, focus_areas
        )

        changes = llm_analysis.get("changes", [])

        # Count change types
        additions = sum(1 for c in changes if c.get("change_type") == "addition")
        deletions = sum(1 for c in changes if c.get("change_type") == "deletion")
        modifications = sum(1 for c in changes if c.get("change_type") == "modification")

        # Store analysis
        analysis = AnalysisResult(
            organization_id=organization_id,
            requested_by_id=user_id,
            document_id=document_id_1,
            analysis_type=AnalysisType.DOCUMENT_COMPARISON,
            query=f"Redline: {doc1.title} vs {doc2.title}",
            result={
                "changes": changes,
                "summary": llm_analysis.get("summary", ""),
                "doc1_id": str(document_id_1),
                "doc2_id": str(document_id_2),
            },
            summary=llm_analysis.get("summary", ""),
            risk_level=self._map_risk(llm_analysis.get("overall_risk", "low")),
            confidence_score=llm_analysis.get("confidence", 0.8),
            model_used=self.settings.anthropic_model,
            processing_time_ms=int((time.time() - start_time) * 1000),
        )
        self.db.add(analysis)
        await self.db.flush()

        return {
            "id": analysis.id,
            "doc1": {"id": str(document_id_1), "title": doc1.title},
            "doc2": {"id": str(document_id_2), "title": doc2.title},
            "summary": llm_analysis.get("summary", ""),
            "total_changes": additions + deletions + modifications,
            "additions": additions,
            "deletions": deletions,
            "modifications": modifications,
            "changes": changes,
            "overall_risk_level": llm_analysis.get("overall_risk", "low"),
            "markdown_redline": markdown_redline,
            "html_redline": html_redline,
            "created_at": analysis.created_at,
        }

    async def redline_version(
        self,
        document_id: uuid.UUID,
        version_from: int,
        version_to: int,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        """Redline between two versions of the same document."""
        from sqlalchemy import select
        from app.models.document import DocumentVersion
        from app.services.storage import StorageService
        from app.services.document_parser.parser import DocumentParserService

        doc = await self.db.get(Document, document_id)
        if not doc:
            raise ValueError("Document not found")

        v_from = await self.db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version_number == version_from,
            )
        )
        v_to = await self.db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version_number == version_to,
            )
        )
        ver_from = v_from.scalar_one_or_none()
        ver_to = v_to.scalar_one_or_none()
        if not ver_from or not ver_to:
            raise ValueError("Version not found")

        # Parse both versions
        storage = StorageService()
        parser = DocumentParserService()

        content_from = await storage.download_file(ver_from.file_path)
        content_to = await storage.download_file(ver_to.file_path)
        parsed_from = await parser.parse(content_from, doc.file_name, doc.mime_type)
        parsed_to = await parser.parse(content_to, doc.file_name, doc.mime_type)

        structural_diff = self._compute_structural_diff(parsed_from.raw_text, parsed_to.raw_text)
        markdown_redline = self._generate_markdown_redline(parsed_from.raw_text, parsed_to.raw_text)
        html_redline = self._generate_html_redline(parsed_from.raw_text, parsed_to.raw_text)

        llm_analysis = await self._analyze_changes_legally(
            structural_diff, f"{doc.title} v{version_from}", f"{doc.title} v{version_to}"
        )

        return {
            "document_id": str(document_id),
            "version_from": version_from,
            "version_to": version_to,
            "summary": llm_analysis.get("summary", ""),
            "changes": llm_analysis.get("changes", []),
            "overall_risk_level": llm_analysis.get("overall_risk", "low"),
            "markdown_redline": markdown_redline,
            "html_redline": html_redline,
        }

    def _compute_structural_diff(self, text1: str, text2: str) -> list[dict]:
        """Compute paragraph-level structural diff."""
        paras1 = [p.strip() for p in text1.split("\n\n") if p.strip()]
        paras2 = [p.strip() for p in text2.split("\n\n") if p.strip()]

        matcher = difflib.SequenceMatcher(None, paras1, paras2)
        changes = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            elif tag == "replace":
                for idx in range(max(i2 - i1, j2 - j1)):
                    old = paras1[i1 + idx] if i1 + idx < i2 else ""
                    new = paras2[j1 + idx] if j1 + idx < j2 else ""
                    changes.append({
                        "type": "modification",
                        "original": old,
                        "new": new,
                        "position": i1 + idx,
                    })
            elif tag == "delete":
                for idx in range(i1, i2):
                    changes.append({
                        "type": "deletion",
                        "original": paras1[idx],
                        "new": "",
                        "position": idx,
                    })
            elif tag == "insert":
                for idx in range(j1, j2):
                    changes.append({
                        "type": "addition",
                        "original": "",
                        "new": paras2[idx],
                        "position": idx,
                    })

        return changes

    def _generate_markdown_redline(self, text1: str, text2: str) -> str:
        """Generate a markdown redline with ~~strikethrough~~ and **bold** markers."""
        lines1 = text1.splitlines()
        lines2 = text2.splitlines()
        diff = difflib.unified_diff(lines1, lines2, n=1)

        output_lines = []
        for line in diff:
            if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                continue
            elif line.startswith("-"):
                output_lines.append(f"~~{line[1:].strip()}~~")
            elif line.startswith("+"):
                output_lines.append(f"**{line[1:].strip()}**")
            else:
                output_lines.append(line.strip())

        return "\n".join(output_lines)

    def _generate_html_redline(self, text1: str, text2: str) -> str:
        """Generate HTML redline with <del> and <ins> tags."""
        lines1 = text1.splitlines()
        lines2 = text2.splitlines()
        diff = difflib.unified_diff(lines1, lines2, n=1)

        output_lines = []
        for line in diff:
            if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                continue
            elif line.startswith("-"):
                escaped = line[1:].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                output_lines.append(f'<del style="background:#fdd;text-decoration:line-through">{escaped}</del>')
            elif line.startswith("+"):
                escaped = line[1:].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                output_lines.append(f'<ins style="background:#dfd;text-decoration:underline">{escaped}</ins>')
            else:
                escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                output_lines.append(f"<p>{escaped}</p>")

        return "\n".join(output_lines)

    async def _analyze_changes_legally(
        self,
        structural_diff: list[dict],
        doc1_name: str,
        doc2_name: str,
        focus_areas: list[str] | None = None,
    ) -> dict:
        if not structural_diff:
            return {"summary": "No material changes detected.", "changes": [], "overall_risk": "info", "confidence": 1.0}

        # Truncate diff for LLM context
        diff_text = ""
        for i, change in enumerate(structural_diff[:50]):
            diff_text += f"\n[Change {i+1}] Type: {change['type']}\n"
            if change["original"]:
                diff_text += f"  ORIGINAL: {change['original'][:400]}\n"
            if change["new"]:
                diff_text += f"  NEW: {change['new'][:400]}\n"

        prompt = f"""Analyze these legal document changes between "{doc1_name}" and "{doc2_name}".

{diff_text}

For each change, provide:
1. change_type: addition, deletion, or modification
2. location: clause/section reference if identifiable
3. original_text: the original text (brief)
4. new_text: the new text (brief)
5. legal_significance: what this change means legally
6. risk_level: critical/high/medium/low/info
7. commentary: practical advice about this change

Also provide:
- summary: overall summary of changes
- overall_risk: the highest risk level across all changes
- confidence: 0.0-1.0"""

        if focus_areas:
            prompt += f"\n\nFocus especially on: {', '.join(focus_areas)}"

        prompt += "\n\nReturn as JSON with: summary, changes (array), overall_risk, confidence"

        response = await self.llm.structured_analysis(
            "You are a legal document comparison expert. Analyze tracked changes between document versions.",
            prompt,
            {"summary": "string", "changes": [], "overall_risk": "string", "confidence": "float"},
        )
        return response

    @staticmethod
    def _map_risk(risk_str: str) -> RiskLevel:
        return {"critical": RiskLevel.CRITICAL, "high": RiskLevel.HIGH, "medium": RiskLevel.MEDIUM,
                "low": RiskLevel.LOW, "info": RiskLevel.INFO}.get(risk_str.lower(), RiskLevel.LOW)
