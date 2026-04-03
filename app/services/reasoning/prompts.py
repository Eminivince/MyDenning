from app.services.retrieval.hybrid import RetrievedChunk


class PromptBuilder:
    """Builds structured prompts for legal reasoning tasks."""

    LEGAL_SYSTEM_BASE = """You are a legal intelligence assistant. You help lawyers and legal professionals
analyze legal documents, answer legal questions, and draft legal work products.

IMPORTANT RULES:
1. Always cite your sources. Never make claims without supporting authority.
2. When uncertain, explicitly state your uncertainty level.
3. Distinguish between binding authority and persuasive authority.
4. Flag any risks or potential issues.
5. Structure your analysis using IRAC format (Issue, Rule, Authority, Analysis, Conclusion).
6. Include jurisdiction-specific considerations.
7. Never provide definitive legal advice - frame as analysis and research findings.
8. If the available sources are insufficient, say so clearly.

You MUST respond with valid JSON."""

    IRAC_SCHEMA = {
        "answer": "string - comprehensive answer in plain English",
        "issues": [{
            "issue": "string - the legal issue identified",
            "rule": "string - the applicable legal rule",
            "authority": [{"citation": "string", "relevance": "string", "binding": "boolean"}],
            "analysis": "string - application of rule to facts",
            "uncertainty": "string or null - areas of uncertainty",
            "recommendation": "string - practical recommendation",
            "risk_level": "critical|high|medium|low|info",
        }],
        "confidence_score": "float 0.0-1.0",
        "risk_flags": ["string - risk flags"],
        "follow_up_questions": ["string - suggested follow-up questions"],
        "key_findings": ["string - key findings for matter memory"],
        "overall_risk": "critical|high|medium|low|info",
    }

    def build_analysis_system_prompt(self, context: dict) -> str:
        prompt = self.LEGAL_SYSTEM_BASE

        if context.get("jurisdiction"):
            prompt += f"\n\nPrimary jurisdiction: {context['jurisdiction']}"

        if context.get("matter_context"):
            prompt += "\n\nRelevant matter context:"
            for mem in context["matter_context"]:
                prompt += f"\n- [{mem['type']}] {mem['content']}"

        if context.get("contract_positions"):
            prompt += "\n\nOrganization's standard contract positions:"
            for pos in context["contract_positions"]:
                prompt += f"\n- {pos}"

        return prompt

    def build_question_prompt(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        task_type: str,
        jurisdiction: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> str:
        prompt_parts = []

        if conversation_history:
            prompt_parts.append("## Previous conversation:")
            for msg in conversation_history[-6:]:
                prompt_parts.append(f"**{msg['role']}**: {msg['content'][:500]}")

        prompt_parts.append("## Relevant sources and documents:")
        for i, chunk in enumerate(chunks, 1):
            source_info = f"[Source {i}]"
            if chunk.document_title:
                source_info += f" Document: {chunk.document_title}"
            if chunk.clause_type:
                source_info += f" | Clause type: {chunk.clause_type}"
            if chunk.jurisdiction:
                source_info += f" | Jurisdiction: {chunk.jurisdiction}"
            if chunk.page_number:
                source_info += f" | Page: {chunk.page_number}"
            if chunk.clause_number:
                source_info += f" | Clause: {chunk.clause_number}"

            prompt_parts.append(f"{source_info}")
            prompt_parts.append(f"```\n{chunk.content}\n```")

        prompt_parts.append(f"\n## Question:\n{question}")

        if jurisdiction:
            prompt_parts.append(f"\n## Jurisdiction: {jurisdiction}")

        prompt_parts.append(f"\n## Task type: {task_type}")
        prompt_parts.append(
            "\nAnalyze thoroughly using IRAC format. Cite sources by [Source N] reference. "
            "Return your response as valid JSON."
        )

        return "\n\n".join(prompt_parts)

    def build_research_system_prompt(self) -> str:
        return self.LEGAL_SYSTEM_BASE + """

You are conducting legal research. Your task is to:
1. Analyze the available legal sources
2. Identify binding vs persuasive authority
3. Note any gaps in the research
4. Provide a comprehensive summary of the legal position
5. Flag any conflicting authorities

Respond with JSON containing: summary, jurisdiction_notes, confidence_score, key_findings"""

    def build_research_prompt(
        self,
        query: str,
        legal_sources: list[dict],
        document_chunks: list[RetrievedChunk],
        jurisdiction: str | None = None,
    ) -> str:
        parts = [f"## Research Query: {query}"]

        if jurisdiction:
            parts.append(f"## Target Jurisdiction: {jurisdiction}")

        if legal_sources:
            parts.append("## Legal Sources Found:")
            for src in legal_sources:
                parts.append(
                    f"- {src['citation']} ({src['source_type']}, {src['authority_level']}) "
                    f"- {src['jurisdiction']}"
                )
                if src.get('summary'):
                    parts.append(f"  Summary: {src['summary'][:300]}")

        if document_chunks:
            parts.append("## Relevant Internal Documents:")
            for chunk in document_chunks[:10]:
                parts.append(f"- [{chunk.document_title}] {chunk.content[:300]}")

        parts.append("\nProvide a comprehensive research summary with citations. Return as valid JSON.")
        return "\n\n".join(parts)

    def build_clause_extraction_prompt(self, document_text: str, focus_areas: list[str] | None = None) -> str:
        prompt = f"""## Document Text:
```
{document_text[:15000]}
```

Extract all legal clauses from this document. For each clause, identify:
1. Clause type (e.g., indemnity, liability, termination, confidentiality, governing_law, etc.)
2. Clause number and title
3. The full clause text
4. Parties involved
5. Key obligations
6. Important dates
7. Monetary values
8. Conditions
9. Risk level (critical/high/medium/low/info)
10. Risk notes
11. Whether this is a standard or unusual clause"""

        if focus_areas:
            prompt += f"\n\nFocus especially on these areas: {', '.join(focus_areas)}"

        prompt += "\n\nReturn as JSON with a 'clauses' array."
        return prompt

    def build_deviation_prompt(
        self,
        document_clauses: list[dict],
        playbook_clauses: list[dict],
    ) -> str:
        prompt = "## Document Clauses:\n"
        for clause in document_clauses:
            prompt += f"\n### {clause.get('clause_type', 'Unknown')} - {clause.get('clause_title', 'N/A')}\n"
            prompt += f"```\n{clause.get('clause_text', '')}\n```\n"

        prompt += "\n## Playbook Standard Positions:\n"
        for clause in playbook_clauses:
            prompt += f"\n### {clause.get('clause_type', 'Unknown')} ({clause.get('position', 'N/A')})\n"
            prompt += f"Standard: ```{clause.get('standard_language', '')}```\n"
            if clause.get("fallback_language"):
                prompt += f"Fallback: ```{clause['fallback_language']}```\n"
            if clause.get("negotiation_notes"):
                prompt += f"Notes: {clause['negotiation_notes']}\n"

        prompt += """
Compare each document clause against the playbook position. For each deviation:
1. Identify the deviation type (missing, weaker, different, additional)
2. Describe the deviation clearly
3. Assess risk level
4. Provide a recommendation
5. Suggest replacement language if appropriate
6. Flag if approval is required

Return as JSON with a 'deviations' array."""
        return prompt

    def build_draft_prompt(
        self,
        draft_type: str,
        instructions: str,
        context_chunks: list[RetrievedChunk],
        jurisdiction: str | None = None,
        tone: str | None = None,
    ) -> str:
        prompt = f"## Draft Type: {draft_type}\n"
        prompt += f"## Instructions: {instructions}\n"

        if jurisdiction:
            prompt += f"## Jurisdiction: {jurisdiction}\n"
        if tone:
            prompt += f"## Tone: {tone}\n"

        if context_chunks:
            prompt += "\n## Reference Materials:\n"
            for chunk in context_chunks[:8]:
                prompt += f"\n[{chunk.document_title}]\n```\n{chunk.content[:500]}\n```\n"

        prompt += f"""
Draft a professional {draft_type}. Requirements:
1. Use proper legal formatting
2. Include all necessary citations
3. Be jurisdiction-appropriate
4. Flag any assumptions made
5. Note any areas requiring human review

Return as JSON with: content, citations, assumptions, risk_flags, confidence_score"""
        return prompt

    def build_deadline_extraction_prompt(self, document_text: str) -> str:
        return f"""## Document Text:
```
{document_text[:15000]}
```

Extract all deadlines, important dates, and time-sensitive obligations from this document.
For each deadline, identify:
1. Title/description of the deadline
2. Due date or triggering event
3. Related obligation
4. Consequence of missing the deadline
5. Priority (1=critical, 2=high, 3=medium, 4=low)
6. Whether it's a court/regulatory deadline
7. Any notice period requirements

Return as JSON with a 'deadlines' array."""

    def build_comparison_prompt(
        self,
        doc1_text: str,
        doc2_text: str,
        doc1_name: str,
        doc2_name: str,
        focus_areas: list[str] | None = None,
    ) -> str:
        prompt = f"""## Document 1: {doc1_name}
```
{doc1_text[:8000]}
```

## Document 2: {doc2_name}
```
{doc2_text[:8000]}
```

Compare these two documents and identify:
1. Key differences in legal terms
2. Clause-by-clause comparison
3. Added, removed, or modified clauses
4. Risk implications of changes
5. Recommendation on which position is stronger/weaker"""

        if focus_areas:
            prompt += f"\n\nFocus especially on: {', '.join(focus_areas)}"

        prompt += "\n\nReturn as JSON with: summary, differences (array), risk_assessment, recommendation"
        return prompt
