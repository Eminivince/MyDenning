import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.schemas.memory import (
    MatterMemoryCreate, MatterMemoryOut,
    PreferenceCreate, PreferenceOut, PreferenceUpdate,
)
from app.services.memory.service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


# --- Organization Preferences ---

@router.post("/preferences", response_model=PreferenceOut, status_code=status.HTTP_201_CREATED)
async def set_preference(
    request: PreferenceCreate,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    service = MemoryService(db)
    pref = await service.set_preference(
        organization_id=org.id,
        user_id=user.id,
        category=request.category,
        key=request.key,
        value=request.value,
        description=request.description,
    )
    return pref


@router.get("/preferences", response_model=list[PreferenceOut])
async def list_preferences(
    org: CurrentOrg = None,
    db: DB = None,
    category: str | None = None,
):
    service = MemoryService(db)
    prefs = await service.get_organization_preferences(org.id, category)
    return prefs


@router.patch("/preferences/{preference_id}", response_model=PreferenceOut)
async def update_preference(
    preference_id: uuid.UUID,
    request: PreferenceUpdate,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    from app.models.memory import OrganizationPreference

    pref = await db.get(OrganizationPreference, preference_id)
    if not pref or pref.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preference not found")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(pref, key, value)
    await db.flush()
    return pref


@router.delete("/preferences/{preference_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preference(
    preference_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
):
    service = MemoryService(db)
    await service.delete_preference(preference_id)


# --- Matter Memory ---

@router.post("/matters/{matter_id}", response_model=MatterMemoryOut, status_code=status.HTTP_201_CREATED)
async def add_matter_memory(
    matter_id: uuid.UUID,
    request: MatterMemoryCreate,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    from app.models.matter import Matter

    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")

    service = MemoryService(db)
    memory = await service.add_matter_memory(
        matter_id=matter_id,
        user_id=user.id,
        memory_type=request.memory_type,
        content=request.content,
        source=request.source or "user_input",
        importance=request.importance,
        structured_data=request.structured_data,
    )
    return memory


@router.get("/matters/{matter_id}", response_model=list[MatterMemoryOut])
async def list_matter_memories(
    matter_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
    memory_type: str | None = None,
    min_importance: int | None = None,
):
    from app.models.matter import Matter

    matter = await db.get(Matter, matter_id)
    if not matter or matter.organization_id != org.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Matter not found")

    service = MemoryService(db)
    return await service.get_matter_memories(matter_id, memory_type, min_importance)


@router.delete("/matters/{matter_id}/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_matter_memory(
    matter_id: uuid.UUID,
    memory_id: uuid.UUID,
    org: CurrentOrg = None,
    db: DB = None,
):
    service = MemoryService(db)
    await service.deactivate_memory(memory_id)
