"""Conflict-of-interest checking service.

Handles:
1. Party registration and normalization across matters
2. Conflict detection when adding parties or creating matters
3. Full conflict check with cross-matter analysis
4. Conflict resolution workflow
"""

import re
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_features import (
    ConflictCheck, ConflictMatterParty, ConflictParty, ConflictStatus,
)
from app.models.matter import Matter

logger = structlog.get_logger(__name__)


class ConflictCheckingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _normalize_party_name(self, name: str) -> str:
        """Normalize party name for fuzzy matching: lowercase, strip suffixes, remove punctuation."""
        normalized = name.strip().lower()
        # Remove common corporate suffixes
        suffixes = [
            r'\b(limited|ltd|llc|plc|inc|incorporated|corp|corporation|sa|gmbh|bv|nv|ag|pty|pvt)\b\.?',
            r'\b(company|co|group|holdings|international|intl|nigeria|nig)\b\.?',
        ]
        for suffix in suffixes:
            normalized = re.sub(suffix, '', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    async def register_party(
        self,
        organization_id: uuid.UUID,
        name: str,
        party_type: str | None = None,
        jurisdiction: str | None = None,
        aliases: list[str] | None = None,
        registration_number: str | None = None,
    ) -> ConflictParty:
        """Register or get a party for conflict tracking."""
        normalized = self._normalize_party_name(name)

        # Check if party already exists
        existing = await self.db.execute(
            select(ConflictParty).where(
                and_(
                    ConflictParty.organization_id == organization_id,
                    ConflictParty.normalized_name == normalized,
                )
            )
        )
        party = existing.scalar_one_or_none()
        if party:
            # Update aliases if new ones provided
            if aliases:
                existing_aliases = party.aliases or []
                party.aliases = list(set(existing_aliases + aliases))
                await self.db.flush()
            return party

        party = ConflictParty(
            organization_id=organization_id,
            name=name,
            normalized_name=normalized,
            aliases=aliases,
            party_type=party_type,
            jurisdiction=jurisdiction,
            registration_number=registration_number,
        )
        self.db.add(party)
        await self.db.flush()
        return party

    async def link_party_to_matter(
        self,
        matter_id: uuid.UUID,
        party_id: uuid.UUID,
        role: str,
        is_adverse: bool = False,
    ) -> ConflictMatterParty:
        link = ConflictMatterParty(
            matter_id=matter_id,
            party_id=party_id,
            role=role,
            is_adverse=is_adverse,
        )
        self.db.add(link)
        await self.db.flush()
        return link

    async def check_conflicts(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        party_names: list[str],
        matter_id: uuid.UUID | None = None,
    ) -> ConflictCheck:
        """Run a full conflict check for a list of party names.

        Logic:
        1. Normalize each party name
        2. Search for matches in conflict_parties (exact + fuzzy)
        3. For each match, find all matters they appear in
        4. Flag conflicts where:
           - A party is client in one matter and adverse in another
           - A party is adverse to our client in the current matter but was our client before
           - Same party appears on both sides of any matter
        """
        conflicts_found = []
        normalized_names = [self._normalize_party_name(n) for n in party_names]

        for i, name in enumerate(party_names):
            normalized = normalized_names[i]

            # Find matching parties (exact normalized name or in aliases)
            matches = await self.db.execute(
                select(ConflictParty).where(
                    and_(
                        ConflictParty.organization_id == organization_id,
                        or_(
                            ConflictParty.normalized_name == normalized,
                            ConflictParty.normalized_name.ilike(f"%{normalized}%"),
                        ),
                    )
                )
            )
            matching_parties = matches.scalars().all()

            # Also search aliases
            alias_matches = await self.db.execute(
                select(ConflictParty).where(
                    and_(
                        ConflictParty.organization_id == organization_id,
                        ConflictParty.aliases.op("@>")(f'["{name}"]'),
                    )
                )
            )
            for alias_party in alias_matches.scalars().all():
                if alias_party not in matching_parties:
                    matching_parties.append(alias_party)

            for party in matching_parties:
                # Find all matters this party is involved in
                matter_links = await self.db.execute(
                    select(ConflictMatterParty).where(ConflictMatterParty.party_id == party.id)
                )
                links = matter_links.scalars().all()

                for link in links:
                    if link.matter_id == matter_id:
                        continue  # skip the current matter

                    linked_matter = await self.db.get(Matter, link.matter_id)
                    if not linked_matter:
                        continue

                    # Check for conflict patterns
                    conflict_desc = None

                    if link.is_adverse:
                        conflict_desc = (
                            f"Party '{party.name}' is adverse in matter '{linked_matter.title}' "
                            f"(role: {link.role}). Potential conflict if representing this party."
                        )

                    if link.role == "client":
                        # Check if any of the OTHER names in our check are adverse to this client
                        for j, other_name in enumerate(party_names):
                            if i == j:
                                continue
                            other_norm = normalized_names[j]
                            adverse_check = await self.db.execute(
                                select(ConflictMatterParty).join(ConflictParty).where(
                                    and_(
                                        ConflictMatterParty.matter_id == link.matter_id,
                                        ConflictMatterParty.is_adverse == True,
                                        ConflictParty.normalized_name.ilike(f"%{other_norm}%"),
                                    )
                                )
                            )
                            if adverse_check.scalar_one_or_none():
                                conflict_desc = (
                                    f"Party '{party.name}' was our client in '{linked_matter.title}', "
                                    f"but '{other_name}' was their adversary in that matter."
                                )

                    if conflict_desc:
                        conflicts_found.append({
                            "party_name": party.name,
                            "matter_id": str(link.matter_id),
                            "matter_title": linked_matter.title,
                            "matter_status": linked_matter.status.value,
                            "role": link.role,
                            "is_adverse": link.is_adverse,
                            "description": conflict_desc,
                        })

        # Determine overall status
        status = ConflictStatus.NO_CONFLICT
        if conflicts_found:
            has_actual = any("was our client" in c["description"] for c in conflicts_found)
            status = ConflictStatus.ACTUAL_CONFLICT if has_actual else ConflictStatus.POTENTIAL_CONFLICT

        check = ConflictCheck(
            organization_id=organization_id,
            matter_id=matter_id,
            checked_by_id=user_id,
            party_names_checked=party_names,
            status=status,
            conflicts_found=conflicts_found if conflicts_found else None,
        )
        self.db.add(check)
        await self.db.flush()

        logger.info(
            "conflict_check_completed",
            parties=len(party_names),
            conflicts=len(conflicts_found),
            status=status.value,
        )
        return check

    async def resolve_conflict(
        self,
        check_id: uuid.UUID,
        user_id: uuid.UUID,
        resolution: str,
        new_status: ConflictStatus = ConflictStatus.CLEARED,
    ) -> ConflictCheck:
        check = await self.db.get(ConflictCheck, check_id)
        if not check:
            raise ValueError("Conflict check not found")

        check.resolution = resolution
        check.resolved_by_id = user_id
        check.resolved_at = datetime.now(timezone.utc)
        check.status = new_status
        await self.db.flush()
        return check

    async def approve_conflict_clearance(
        self,
        check_id: uuid.UUID,
        approver_id: uuid.UUID,
    ) -> ConflictCheck:
        check = await self.db.get(ConflictCheck, check_id)
        if not check:
            raise ValueError("Conflict check not found")

        check.approved_by_id = approver_id
        check.approved_at = datetime.now(timezone.utc)
        await self.db.flush()
        return check

    async def get_party_history(
        self,
        organization_id: uuid.UUID,
        party_name: str,
    ) -> list[dict]:
        """Get all matters a party has been involved in."""
        normalized = self._normalize_party_name(party_name)

        result = await self.db.execute(
            select(ConflictParty).where(
                and_(
                    ConflictParty.organization_id == organization_id,
                    ConflictParty.normalized_name == normalized,
                )
            )
        )
        party = result.scalar_one_or_none()
        if not party:
            return []

        links = await self.db.execute(
            select(ConflictMatterParty).where(ConflictMatterParty.party_id == party.id)
        )

        history = []
        for link in links.scalars().all():
            matter = await self.db.get(Matter, link.matter_id)
            if matter:
                history.append({
                    "matter_id": str(matter.id),
                    "matter_title": matter.title,
                    "matter_type": matter.matter_type.value,
                    "matter_status": matter.status.value,
                    "role": link.role,
                    "is_adverse": link.is_adverse,
                    "opened": matter.opened_at.isoformat() if matter.opened_at else None,
                })

        return history
