import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import Organization, OrganizationMember, OrgRole, User

security = HTTPBearer()


# ===== Role groups for permission checking =====

ADMIN_ROLES = {OrgRole.SUPER_ADMIN, OrgRole.MANAGING_PARTNER, OrgRole.OWNER, OrgRole.ADMIN}
WRITE_ROLES = ADMIN_ROLES | {OrgRole.PARTNER, OrgRole.ASSOCIATE, OrgRole.PARALEGAL}
ALL_ROLES = WRITE_ROLES | {OrgRole.TRAINEE, OrgRole.FINANCE_ADMIN, OrgRole.BILLING_ADMIN, OrgRole.KNOWLEDGE_ADMIN, OrgRole.READ_ONLY_GUEST, OrgRole.MEMBER}
BILLING_ROLES = ADMIN_ROLES | {OrgRole.FINANCE_ADMIN, OrgRole.BILLING_ADMIN}


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = await db.get(User, uuid.UUID(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


async def get_current_organization(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Organization:
    org_id = request.headers.get("X-Organization-ID")
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Organization-ID header required")

    try:
        org_uuid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organization ID")

    # Verify membership
    membership = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_uuid,
            OrganizationMember.user_id == user.id,
        )
    )
    if not membership.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization")

    org = await db.get(Organization, org_uuid)
    if not org or not org.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    return org


async def get_current_membership(
    user: Annotated[User, Depends(get_current_user)],
    org: Annotated[Organization, Depends(get_current_organization)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationMember:
    """Get the user's membership record (includes role) for the current org."""
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org.id,
            OrganizationMember.user_id == user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member")
    return membership


def require_role(*allowed_roles: set[OrgRole]):
    """Dependency factory that checks the user's org role against allowed roles."""
    allowed = set()
    for role_set in allowed_roles:
        if isinstance(role_set, set):
            allowed |= role_set
        else:
            allowed.add(role_set)

    async def checker(
        membership: Annotated[OrganizationMember, Depends(get_current_membership)],
    ) -> OrganizationMember:
        if membership.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{membership.role.value}' does not have permission for this action",
            )
        return membership
    return checker


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentOrg = Annotated[Organization, Depends(get_current_organization)]
CurrentMembership = Annotated[OrganizationMember, Depends(get_current_membership)]
DB = Annotated[AsyncSession, Depends(get_db)]
