"""Calendar — events, hearings, meetings, deadlines."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, and_

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.models.matter import CalendarEvent, EventType

router = APIRouter(prefix="/calendar", tags=["calendar"])


class EventCreate(BaseModel):
    title: str
    description: str | None = None
    event_type: str = "meeting"
    matter_id: uuid.UUID | None = None
    start_time: datetime
    end_time: datetime | None = None
    all_day: bool = False
    location: str | None = None
    attendee_ids: list[uuid.UUID] | None = None
    reminders: list[dict] | None = None  # [{minutes_before: 30, type: "notification"}]
    is_recurring: bool = False
    recurrence: str | None = None  # daily, weekly, biweekly, monthly
    recurrence_count: int = 12  # how many instances to generate


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = None
    attendee_ids: list[uuid.UUID] | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event(request: EventCreate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    from datetime import timedelta

    RECURRENCE_DELTAS = {
        "daily": timedelta(days=1),
        "weekly": timedelta(weeks=1),
        "biweekly": timedelta(weeks=2),
        "monthly": timedelta(days=30),  # approximate
    }

    base_args = dict(
        organization_id=org.id, created_by_id=user.id, matter_id=request.matter_id,
        title=request.title, description=request.description,
        event_type=EventType(request.event_type),
        all_day=request.all_day, location=request.location,
        attendee_ids=[str(a) for a in request.attendee_ids] if request.attendee_ids else None,
        reminders=request.reminders,
    )

    # Create the first event
    event = CalendarEvent(
        **base_args,
        start_time=request.start_time, end_time=request.end_time,
        is_recurring=request.is_recurring,
        recurrence_rule=request.recurrence,
    )
    db.add(event)

    created_count = 1

    # Expand recurring events
    if request.is_recurring and request.recurrence and request.recurrence in RECURRENCE_DELTAS:
        delta = RECURRENCE_DELTAS[request.recurrence]
        duration = (request.end_time - request.start_time) if request.end_time else None
        count = min(request.recurrence_count, 52)  # cap at 52 instances

        for i in range(1, count):
            offset = delta * i
            instance_start = request.start_time + offset
            instance_end = (request.end_time + offset) if request.end_time else None

            instance = CalendarEvent(
                **base_args,
                start_time=instance_start, end_time=instance_end,
                is_recurring=True, recurrence_rule=request.recurrence,
            )
            db.add(instance)
            created_count += 1

    await db.flush()

    result = _event_dict(event)
    if created_count > 1:
        result["recurring_instances_created"] = created_count
    return result


@router.get("")
async def list_events(
    org: CurrentOrg = None, db: DB = None,
    matter_id: uuid.UUID | None = None,
    event_type: str | None = None,
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    conditions = [CalendarEvent.organization_id == org.id]
    if matter_id:
        conditions.append(CalendarEvent.matter_id == matter_id)
    if event_type:
        conditions.append(CalendarEvent.event_type == EventType(event_type))
    if start_after:
        conditions.append(CalendarEvent.start_time >= start_after)
    if start_before:
        conditions.append(CalendarEvent.start_time <= start_before)

    result = await db.execute(
        select(CalendarEvent).where(and_(*conditions))
        .order_by(CalendarEvent.start_time.asc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    return [_event_dict(e) for e in result.scalars().all()]


@router.get("/{event_id}")
async def get_event(event_id: uuid.UUID, org: CurrentOrg = None, db: DB = None):
    event = await db.get(CalendarEvent, event_id)
    if not event or event.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_dict(event)


@router.patch("/{event_id}")
async def update_event(event_id: uuid.UUID, request: EventUpdate, org: CurrentOrg = None, db: DB = None):
    event = await db.get(CalendarEvent, event_id)
    if not event or event.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Event not found")
    data = request.model_dump(exclude_unset=True)
    if "attendee_ids" in data and data["attendee_ids"]:
        data["attendee_ids"] = [str(a) for a in data["attendee_ids"]]
    for k, v in data.items():
        setattr(event, k, v)
    await db.flush()
    return _event_dict(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: uuid.UUID, org: CurrentOrg = None, db: DB = None):
    event = await db.get(CalendarEvent, event_id)
    if not event or event.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(event)
    await db.flush()


def _event_dict(e: CalendarEvent) -> dict:
    return {
        "id": str(e.id), "title": e.title, "description": e.description,
        "event_type": e.event_type.value,
        "matter_id": str(e.matter_id) if e.matter_id else None,
        "start_time": e.start_time.isoformat(), "end_time": e.end_time.isoformat() if e.end_time else None,
        "all_day": e.all_day, "location": e.location,
        "attendee_ids": e.attendee_ids, "reminders": e.reminders,
        "created_at": e.created_at.isoformat(),
    }
