"""Privilege tagging service — attorney-client privilege, work product, litigation hold.

Handles:
1. Tagging documents/analyses with privilege assertions
2. Tracking privilege waivers with full audit trail
3. Generating privilege logs for litigation discovery
4. Auto-detecting potentially privileged content
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_features import (
    PrivilegeLog, PrivilegeStatus, PrivilegeTag, PrivilegeType,
)
from app.services.reasoning.llm_client import LLMClient

logger = structlog.get_logger(__name__)


class PrivilegeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()

    async def tag_privilege(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        privilege_type: PrivilegeType,
        basis: str,
        document_id: uuid.UUID | None = None,
        matter_id: uuid.UUID | None = None,
        analysis_id: uuid.UUID | None = None,
        scope_description: str | None = None,
        attorney_name: str | None = None,
        client_name: str | None = None,
    ) -> PrivilegeTag:
        tag = PrivilegeTag(
            organization_id=organization_id,
            document_id=document_id,
            matter_id=matter_id,
            analysis_id=analysis_id,
            privilege_type=privilege_type,
            status=PrivilegeStatus.ASSERTED,
            asserted_by_id=user_id,
            basis=basis,
            scope_description=scope_description,
            attorney_name=attorney_name,
            client_name=client_name,
        )
        self.db.add(tag)
        await self.db.flush()
        logger.info("privilege_tagged", type=privilege_type.value, document_id=str(document_id))
        return tag

    async def waive_privilege(
        self,
        tag_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str,
        scope: str = "full",
    ) -> PrivilegeTag:
        tag = await self.db.get(PrivilegeTag, tag_id)
        if not tag:
            raise ValueError("Privilege tag not found")

        tag.status = PrivilegeStatus.WAIVED
        tag.waived_by_id = user_id
        tag.waived_at = datetime.now(timezone.utc)
        tag.waiver_reason = reason
        tag.waiver_scope = scope
        await self.db.flush()
        logger.warning("privilege_waived", tag_id=str(tag_id), reason=reason)
        return tag

    async def review_privilege(
        self,
        tag_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        new_status: PrivilegeStatus,
        notes: str | None = None,
    ) -> PrivilegeTag:
        tag = await self.db.get(PrivilegeTag, tag_id)
        if not tag:
            raise ValueError("Privilege tag not found")

        tag.status = new_status
        tag.reviewed_by_id = reviewer_id
        tag.reviewed_at = datetime.now(timezone.utc)
        tag.review_notes = notes
        await self.db.flush()
        return tag

    async def get_document_privileges(self, document_id: uuid.UUID) -> list[PrivilegeTag]:
        result = await self.db.execute(
            select(PrivilegeTag).where(
                PrivilegeTag.document_id == document_id,
                PrivilegeTag.status != PrivilegeStatus.WAIVED,
            )
        )
        return list(result.scalars().all())

    async def get_matter_privileges(self, matter_id: uuid.UUID) -> list[PrivilegeTag]:
        result = await self.db.execute(
            select(PrivilegeTag).where(PrivilegeTag.matter_id == matter_id)
        )
        return list(result.scalars().all())

    async def generate_privilege_log(
        self,
        matter_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> list[dict]:
        """Generate a standard privilege log for discovery responses."""
        result = await self.db.execute(
            select(PrivilegeTag).where(
                and_(
                    PrivilegeTag.matter_id == matter_id,
                    PrivilegeTag.organization_id == organization_id,
                    PrivilegeTag.status == PrivilegeStatus.ASSERTED,
                )
            )
        )
        tags = result.scalars().all()

        log_entries = []
        for tag in tags:
            # Load document title if linked
            doc_title = ""
            if tag.document_id:
                from app.models.document import Document
                doc = await self.db.get(Document, tag.document_id)
                doc_title = doc.title if doc else ""

            entry = {
                "tag_id": str(tag.id),
                "document_id": str(tag.document_id) if tag.document_id else None,
                "document_title": doc_title,
                "privilege_type": tag.privilege_type.value,
                "basis": tag.basis,
                "scope": tag.scope_description,
                "attorney": tag.attorney_name,
                "client": tag.client_name,
                "date_asserted": tag.created_at.isoformat(),
                "status": tag.status.value,
            }
            log_entries.append(entry)

            # Also create a PrivilegeLog DB entry for the record
            log_record = PrivilegeLog(
                organization_id=organization_id,
                matter_id=matter_id,
                privilege_tag_id=tag.id,
                document_id=tag.document_id,
                document_date=tag.created_at,
                document_type_description=doc_title or "Legal document",
                author=tag.attorney_name,
                subject_matter=tag.scope_description or tag.basis,
                privilege_claimed=tag.privilege_type.value,
                basis_for_privilege=tag.basis,
            )
            self.db.add(log_record)

        await self.db.flush()
        return log_entries

    async def auto_detect_privilege(
        self,
        document_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> list[dict]:
        """Use LLM to detect potentially privileged content in a document."""
        from app.models.document import Document
        doc = await self.db.get(Document, document_id)
        if not doc or not doc.raw_text:
            raise ValueError("Document not found or not processed")

        prompt = f"""Analyze this document for attorney-client privilege and work product indicators.

Document: {doc.title}
```
{doc.raw_text[:12000]}
```

Identify any content that may be:
1. Attorney-client privileged (legal advice from attorney to client)
2. Work product (prepared in anticipation of litigation)
3. Common interest (shared under a common interest agreement)

For each finding:
- description: what the privileged content is
- privilege_type: attorney_client, work_product, common_interest
- location: where in the document (clause/section)
- confidence: how certain (0.0-1.0)
- basis: why this is likely privileged

Return as JSON with a 'findings' array."""

        response = await self.llm.structured_analysis(
            "You are a privilege review specialist.",
            prompt,
            {"findings": []},
        )

        return response.get("findings", [])
