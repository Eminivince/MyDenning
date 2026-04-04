"""Task management — work items within matters."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, and_, func, or_

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.models.matter import Task, TaskStatus

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    matter_id: uuid.UUID | None = None
    assigned_to_id: uuid.UUID | None = None
    priority: int = 3
    due_date: datetime | None = None
    linked_document_ids: list[str] | None = None
    tags: list[str] | None = None
    requires_approval: bool = False


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    assigned_to_id: uuid.UUID | None = None
    priority: int | None = None
    due_date: datetime | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_task(request: TaskCreate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    task = Task(
        organization_id=org.id,
        created_by_id=user.id,
        matter_id=request.matter_id,
        assigned_to_id=request.assigned_to_id,
        title=request.title,
        description=request.description,
        priority=request.priority,
        due_date=request.due_date,
        linked_document_ids=request.linked_document_ids,
        tags=request.tags,
        requires_approval=request.requires_approval,
    )
    db.add(task)
    await db.flush()
    return _task_dict(task)


@router.get("")
async def list_tasks(
    org: CurrentOrg = None, user: CurrentUser = None, db: DB = None,
    status_filter: str | None = Query(None, alias="status"),
    matter_id: uuid.UUID | None = None,
    assigned_to_me: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conditions = [Task.organization_id == org.id]
    if status_filter:
        conditions.append(Task.status == TaskStatus(status_filter))
    if matter_id:
        conditions.append(Task.matter_id == matter_id)
    if assigned_to_me:
        conditions.append(Task.assigned_to_id == user.id)

    result = await db.execute(
        select(Task).where(and_(*conditions))
        .order_by(Task.priority.asc(), Task.due_date.asc().nullslast())
        .offset((page - 1) * page_size).limit(page_size)
    )
    return [_task_dict(t) for t in result.scalars().all()]


@router.patch("/{task_id}")
async def update_task(task_id: uuid.UUID, request: TaskUpdate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    task = await db.get(Task, task_id)
    if not task or task.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Task not found")

    data = request.model_dump(exclude_unset=True)
    if "status" in data:
        new_status = TaskStatus(data.pop("status"))
        task.status = new_status
        if new_status == TaskStatus.COMPLETED:
            task.completed_at = datetime.now(timezone.utc)
    for k, v in data.items():
        setattr(task, k, v)
    await db.flush()
    return _task_dict(task)


@router.post("/{task_id}/approve")
async def approve_task(task_id: uuid.UUID, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    task = await db.get(Task, task_id)
    if not task or task.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Task not found")
    task.approved_by_id = user.id
    task.approved_at = datetime.now(timezone.utc)
    await db.flush()
    return _task_dict(task)


def _task_dict(t: Task) -> dict:
    return {
        "id": str(t.id), "title": t.title, "description": t.description,
        "status": t.status.value, "priority": t.priority,
        "matter_id": str(t.matter_id) if t.matter_id else None,
        "assigned_to_id": str(t.assigned_to_id) if t.assigned_to_id else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "requires_approval": t.requires_approval,
        "approved_at": t.approved_at.isoformat() if t.approved_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "tags": t.tags, "created_at": t.created_at.isoformat(),
    }
