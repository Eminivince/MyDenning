import uuid
from math import ceil

from fastapi import APIRouter, Query

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.services.audit.service import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
async def get_audit_logs(
    org: CurrentOrg = None,
    user: CurrentUser = None,
    db: DB = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    user_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    service = AuditService(db)
    logs, total = await service.get_logs(
        organization_id=org.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        page=page,
        page_size=page_size,
    )

    return {
        "items": [
            {
                "id": str(log.id),
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "description": log.description,
                "user_id": str(log.user_id) if log.user_id else None,
                "model_used": log.model_used,
                "confidence_score": log.confidence_score,
                "sources_used": log.sources_used,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total > 0 else 0,
    }
