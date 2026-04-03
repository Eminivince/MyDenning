import uuid

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MatterMemory, OrganizationPreference

logger = structlog.get_logger(__name__)


class MemoryService:
    """Manages organizational preferences and matter-level contextual memory."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Organization Preferences ---

    async def get_organization_preferences(
        self,
        organization_id: uuid.UUID,
        category: str | None = None,
    ) -> list[OrganizationPreference]:
        conditions = [
            OrganizationPreference.organization_id == organization_id,
            OrganizationPreference.is_active == True,  # noqa: E712
        ]
        if category:
            conditions.append(OrganizationPreference.category == category)

        result = await self.db.execute(
            select(OrganizationPreference).where(and_(*conditions))
        )
        return list(result.scalars().all())

    async def set_preference(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        category: str,
        key: str,
        value: dict,
        description: str | None = None,
    ) -> OrganizationPreference:
        # Upsert: deactivate existing and create new
        existing = await self.db.execute(
            select(OrganizationPreference).where(
                and_(
                    OrganizationPreference.organization_id == organization_id,
                    OrganizationPreference.category == category,
                    OrganizationPreference.key == key,
                    OrganizationPreference.is_active == True,  # noqa: E712
                )
            )
        )
        for pref in existing.scalars().all():
            pref.is_active = False

        new_pref = OrganizationPreference(
            organization_id=organization_id,
            set_by_id=user_id,
            category=category,
            key=key,
            value=value,
            description=description,
        )
        self.db.add(new_pref)
        await self.db.flush()
        return new_pref

    async def delete_preference(self, preference_id: uuid.UUID) -> None:
        pref = await self.db.get(OrganizationPreference, preference_id)
        if pref:
            pref.is_active = False
            await self.db.flush()

    # --- Matter Memory ---

    async def get_matter_memories(
        self,
        matter_id: uuid.UUID,
        memory_type: str | None = None,
        min_importance: int | None = None,
    ) -> list[MatterMemory]:
        conditions = [
            MatterMemory.matter_id == matter_id,
            MatterMemory.is_active == True,  # noqa: E712
        ]
        if memory_type:
            conditions.append(MatterMemory.memory_type == memory_type)
        if min_importance is not None:
            conditions.append(MatterMemory.importance >= min_importance)

        result = await self.db.execute(
            select(MatterMemory)
            .where(and_(*conditions))
            .order_by(MatterMemory.importance.desc(), MatterMemory.created_at.desc())
        )
        return list(result.scalars().all())

    async def add_matter_memory(
        self,
        matter_id: uuid.UUID,
        user_id: uuid.UUID,
        memory_type: str,
        content: str,
        source: str = "user_input",
        importance: int = 5,
        structured_data: dict | None = None,
    ) -> MatterMemory:
        memory = MatterMemory(
            matter_id=matter_id,
            created_by_id=user_id,
            memory_type=memory_type,
            content=content,
            structured_data=structured_data,
            source=source,
            importance=importance,
        )
        self.db.add(memory)
        await self.db.flush()
        logger.info("matter_memory_added", matter_id=str(matter_id), type=memory_type)
        return memory

    async def deactivate_memory(self, memory_id: uuid.UUID) -> None:
        memory = await self.db.get(MatterMemory, memory_id)
        if memory:
            memory.is_active = False
            await self.db.flush()

    async def get_context_for_prompt(
        self,
        organization_id: uuid.UUID,
        matter_id: uuid.UUID | None = None,
    ) -> dict:
        """Build a context dict for use in LLM prompts from org preferences and matter memory."""
        context: dict = {}

        prefs = await self.get_organization_preferences(organization_id)
        for pref in prefs:
            context.setdefault(pref.category, {})[pref.key] = pref.value

        if matter_id:
            memories = await self.get_matter_memories(matter_id, min_importance=3)
            context["matter_memories"] = [
                {"type": m.memory_type, "content": m.content, "importance": m.importance}
                for m in memories[:20]
            ]

        return context
