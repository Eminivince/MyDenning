"""Client portal service — read-only access for external clients.

Lets law firms give their clients visibility into their matters without
exposing internal work product. Clients can see:
- Matter status and basic info
- Upcoming deadlines
- Document list (without privileged docs)
- Upload documents for review

Clients CANNOT see:
- Internal notes (unless explicitly allowed)
- Analysis results
- Playbooks
- Privileged documents
- Other clients' matters
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.document import Document, ProcessingStatus
from app.models.legal_features import ClientMatterAccess, ClientUser, PrivilegeTag, PrivilegeStatus
from app.models.matter import Matter, MatterDeadline, MatterNote, DeadlineStatus

logger = structlog.get_logger(__name__)


class ClientPortalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Client User Management (called by internal users) ---

    async def invite_client(
        self,
        organization_id: uuid.UUID,
        invited_by_id: uuid.UUID,
        email: str,
        full_name: str,
        password: str,
        company_name: str | None = None,
        matter_ids: list[uuid.UUID] | None = None,
    ) -> ClientUser:
        """Create a client portal account and grant matter access."""
        # Check if already exists
        existing = await self.db.execute(
            select(ClientUser).where(ClientUser.email == email.lower().strip())
        )
        if existing.scalar_one_or_none():
            raise ValueError("A client user with this email already exists")

        client = ClientUser(
            organization_id=organization_id,
            invited_by_id=invited_by_id,
            email=email.lower().strip(),
            hashed_password=hash_password(password),
            full_name=full_name,
            company_name=company_name,
        )
        self.db.add(client)
        await self.db.flush()

        # Grant access to specified matters
        if matter_ids:
            for matter_id in matter_ids:
                access = ClientMatterAccess(
                    client_user_id=client.id,
                    matter_id=matter_id,
                )
                self.db.add(access)

        await self.db.flush()
        logger.info("client_invited", email=email, matters=len(matter_ids or []))
        return client

    async def grant_matter_access(
        self,
        client_user_id: uuid.UUID,
        matter_id: uuid.UUID,
        can_view_documents: bool = True,
        can_view_deadlines: bool = True,
        can_view_status: bool = True,
        can_view_notes: bool = False,
        can_upload_documents: bool = True,
    ) -> ClientMatterAccess:
        access = ClientMatterAccess(
            client_user_id=client_user_id,
            matter_id=matter_id,
            can_view_documents=can_view_documents,
            can_view_deadlines=can_view_deadlines,
            can_view_status=can_view_status,
            can_view_notes=can_view_notes,
            can_upload_documents=can_upload_documents,
        )
        self.db.add(access)
        await self.db.flush()
        return access

    async def revoke_matter_access(self, client_user_id: uuid.UUID, matter_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(ClientMatterAccess).where(
                and_(ClientMatterAccess.client_user_id == client_user_id, ClientMatterAccess.matter_id == matter_id)
            )
        )
        access = result.scalar_one_or_none()
        if access:
            await self.db.delete(access)
            await self.db.flush()

    async def list_clients(self, organization_id: uuid.UUID) -> list[ClientUser]:
        result = await self.db.execute(
            select(ClientUser).where(ClientUser.organization_id == organization_id).order_by(ClientUser.created_at.desc())
        )
        return list(result.scalars().all())

    # --- Client Authentication ---

    async def authenticate_client(self, email: str, password: str) -> dict | None:
        result = await self.db.execute(
            select(ClientUser).where(ClientUser.email == email.lower().strip())
        )
        client = result.scalar_one_or_none()
        if not client or not client.is_active or not verify_password(password, client.hashed_password):
            return None

        client.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()

        token = create_access_token(str(client.id), extra_claims={"type": "client", "org_id": str(client.organization_id)})
        return {
            "access_token": token,
            "token_type": "bearer",
            "client_id": str(client.id),
            "full_name": client.full_name,
            "organization_id": str(client.organization_id),
        }

    # --- Client Portal Views (called with client auth) ---

    async def get_client_matters(self, client_user_id: uuid.UUID) -> list[dict]:
        """Get all matters this client has access to."""
        access_result = await self.db.execute(
            select(ClientMatterAccess).where(ClientMatterAccess.client_user_id == client_user_id)
        )
        accesses = access_result.scalars().all()

        matters = []
        for access in accesses:
            matter = await self.db.get(Matter, access.matter_id)
            if not matter:
                continue
            matters.append({
                "matter_id": str(matter.id),
                "title": matter.title,
                "reference_number": matter.reference_number,
                "type": matter.matter_type.value,
                "status": matter.status.value if access.can_view_status else "visible",
                "jurisdiction": matter.jurisdiction,
                "permissions": {
                    "documents": access.can_view_documents,
                    "deadlines": access.can_view_deadlines,
                    "status": access.can_view_status,
                    "notes": access.can_view_notes,
                    "upload": access.can_upload_documents,
                },
            })
        return matters

    async def get_client_matter_detail(self, client_user_id: uuid.UUID, matter_id: uuid.UUID) -> dict | None:
        """Get matter detail from the client's perspective — filtered by permissions."""
        access = await self._check_access(client_user_id, matter_id)
        if not access:
            return None

        matter = await self.db.get(Matter, matter_id)
        if not matter:
            return None

        result: dict = {
            "matter_id": str(matter.id),
            "title": matter.title,
            "reference_number": matter.reference_number,
            "type": matter.matter_type.value,
            "jurisdiction": matter.jurisdiction,
            "client_name": matter.client_name,
        }

        if access.can_view_status:
            result["status"] = matter.status.value
            result["opened_at"] = matter.opened_at.isoformat() if matter.opened_at else None

        if access.can_view_deadlines:
            deadlines = await self.db.execute(
                select(MatterDeadline).where(MatterDeadline.matter_id == matter_id)
                .order_by(MatterDeadline.due_date.asc())
            )
            result["deadlines"] = [
                {
                    "title": dl.title,
                    "due_date": dl.due_date.isoformat(),
                    "status": dl.status.value,
                    "priority": dl.priority,
                    "is_court_deadline": dl.is_court_deadline,
                }
                for dl in deadlines.scalars().all()
            ]

        if access.can_view_documents:
            # Exclude privileged documents
            privileged_doc_ids = set()
            priv_result = await self.db.execute(
                select(PrivilegeTag.document_id).where(
                    and_(
                        PrivilegeTag.matter_id == matter_id,
                        PrivilegeTag.status == PrivilegeStatus.ASSERTED,
                        PrivilegeTag.document_id.isnot(None),
                    )
                )
            )
            for row in priv_result.all():
                if row[0]:
                    privileged_doc_ids.add(row[0])

            docs = await self.db.execute(
                select(Document).where(
                    and_(
                        Document.matter_id == matter_id,
                        Document.is_active == True,  # noqa: E712
                    )
                ).order_by(Document.created_at.desc())
            )
            result["documents"] = [
                {
                    "id": str(doc.id),
                    "title": doc.title,
                    "file_name": doc.file_name,
                    "type": doc.document_type.value,
                    "status": doc.processing_status.value,
                    "created_at": doc.created_at.isoformat(),
                }
                for doc in docs.scalars().all()
                if doc.id not in privileged_doc_ids
            ]

        if access.can_view_notes:
            notes = await self.db.execute(
                select(MatterNote).where(MatterNote.matter_id == matter_id)
                .order_by(MatterNote.created_at.desc()).limit(20)
            )
            result["notes"] = [
                {"content": n.content, "date": n.created_at.isoformat()}
                for n in notes.scalars().all()
            ]

        return result

    async def _check_access(self, client_user_id: uuid.UUID, matter_id: uuid.UUID) -> ClientMatterAccess | None:
        result = await self.db.execute(
            select(ClientMatterAccess).where(
                and_(ClientMatterAccess.client_user_id == client_user_id, ClientMatterAccess.matter_id == matter_id)
            )
        )
        return result.scalar_one_or_none()
