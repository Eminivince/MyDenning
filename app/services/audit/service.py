import uuid
from typing import Any

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = structlog.get_logger(__name__)


class AuditService:
    """Comprehensive audit trail for all operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        description: str | None = None,
        request_path: str | None = None,
        request_method: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        old_values: dict | None = None,
        new_values: dict | None = None,
        metadata: dict | None = None,
        model_used: str | None = None,
        model_version: str | None = None,
        sources_used: list | None = None,
        source_versions: list | None = None,
        confidence_score: float | None = None,
        token_count: int | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            request_path=request_path,
            request_method=request_method,
            ip_address=ip_address,
            user_agent=user_agent,
            old_values=old_values,
            new_values=new_values,
            metadata=metadata,
            model_used=model_used,
            model_version=model_version,
            sources_used=sources_used,
            source_versions=source_versions,
            confidence_score=confidence_score,
            token_count=token_count,
        )
        self.db.add(entry)
        await self.db.flush()
        logger.info(
            "audit_log_created",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return entry

    async def get_logs(
        self,
        organization_id: uuid.UUID,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        user_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        conditions = [AuditLog.organization_id == organization_id]

        if action:
            conditions.append(AuditLog.action == action)
        if resource_type:
            conditions.append(AuditLog.resource_type == resource_type)
        if resource_id:
            conditions.append(AuditLog.resource_id == resource_id)
        if user_id:
            conditions.append(AuditLog.user_id == user_id)

        # Count
        count_stmt = select(func.count()).select_from(AuditLog).where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch
        stmt = (
            select(AuditLog)
            .where(and_(*conditions))
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        logs = list(result.scalars().all())

        return logs, total

    async def log_ai_operation(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: str,
        model_used: str,
        sources_used: list[dict],
        confidence_score: float,
        token_count: int | None = None,
        description: str | None = None,
    ) -> AuditLog:
        """Specialized logging for AI operations with source tracking."""
        source_ids = [s.get("id") or s.get("chunk_id") for s in sources_used if s]
        source_versions_list = [s.get("version") for s in sources_used if s.get("version")]

        return await self.log(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            model_used=model_used,
            sources_used=source_ids,
            source_versions=source_versions_list if source_versions_list else None,
            confidence_score=confidence_score,
            token_count=token_count,
        )
