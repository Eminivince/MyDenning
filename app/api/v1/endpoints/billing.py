"""Billing — time entries, invoicing, payment tracking."""

import uuid
from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, and_, func

from app.api.deps import CurrentOrg, CurrentUser, DB, require_role, BILLING_ROLES, WRITE_ROLES
from app.models.matter import TimeEntry, Invoice, InvoiceStatus

router = APIRouter(prefix="/billing", tags=["billing"])


# ===== Time Entries =====

class TimeEntryCreate(BaseModel):
    matter_id: uuid.UUID | None = None
    date: datetime
    hours: float
    description: str
    is_billable: bool = True
    rate: float | None = None
    task_id: uuid.UUID | None = None


class TimeEntryUpdate(BaseModel):
    hours: float | None = None
    description: str | None = None
    is_billable: bool | None = None
    rate: float | None = None


@router.post("/time-entries", status_code=status.HTTP_201_CREATED)
async def log_time(request: TimeEntryCreate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    amount = (request.hours * request.rate) if request.rate else None
    entry = TimeEntry(
        organization_id=org.id,
        matter_id=request.matter_id,
        user_id=user.id,
        task_id=request.task_id,
        date=request.date,
        hours=request.hours,
        description=request.description,
        is_billable=request.is_billable,
        rate=request.rate,
        amount=amount,
    )
    db.add(entry)
    await db.flush()
    return _entry_dict(entry)


@router.get("/time-entries")
async def list_time_entries(
    org: CurrentOrg = None, user: CurrentUser = None, db: DB = None,
    matter_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    billable_only: bool = False,
    uninvoiced_only: bool = False,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    conditions = [TimeEntry.organization_id == org.id]
    if matter_id:
        conditions.append(TimeEntry.matter_id == matter_id)
    if user_id:
        conditions.append(TimeEntry.user_id == user_id)
    if billable_only:
        conditions.append(TimeEntry.is_billable == True)  # noqa: E712
    if uninvoiced_only:
        conditions.append(TimeEntry.invoice_id.is_(None))
    if date_from:
        conditions.append(TimeEntry.date >= date_from)
    if date_to:
        conditions.append(TimeEntry.date <= date_to)

    result = await db.execute(
        select(TimeEntry).where(and_(*conditions))
        .order_by(TimeEntry.date.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )

    # Summary
    summary_result = await db.execute(
        select(
            func.sum(TimeEntry.hours).label("total_hours"),
            func.sum(TimeEntry.amount).label("total_amount"),
            func.count().label("count"),
        ).where(and_(*conditions))
    )
    summary = summary_result.one()

    return {
        "entries": [_entry_dict(e) for e in result.scalars().all()],
        "summary": {
            "total_hours": round(summary.total_hours or 0, 2),
            "total_amount": round(summary.total_amount or 0, 2),
            "count": summary.count or 0,
        },
    }


@router.patch("/time-entries/{entry_id}")
async def update_time_entry(entry_id: uuid.UUID, request: TimeEntryUpdate, org: CurrentOrg = None, db: DB = None):
    entry = await db.get(TimeEntry, entry_id)
    if not entry or entry.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Time entry not found")
    data = request.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(entry, k, v)
    if entry.hours and entry.rate:
        entry.amount = entry.hours * entry.rate
    await db.flush()
    return _entry_dict(entry)


# ===== Invoices =====

class InvoiceCreate(BaseModel):
    client_id: uuid.UUID | None = None
    matter_id: uuid.UUID | None = None
    due_date: datetime
    currency: str = "NGN"
    notes: str | None = None
    payment_terms: str | None = None
    time_entry_ids: list[uuid.UUID] | None = None  # specific entries to include


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
async def create_invoice(request: InvoiceCreate, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None, _role=Depends(require_role(BILLING_ROLES))):
    # Generate invoice number
    count_result = await db.execute(select(func.count()).where(Invoice.organization_id == org.id))
    count = count_result.scalar() or 0
    invoice_number = f"INV-{datetime.now(timezone.utc).year}-{count + 1:04d}"

    # Gather time entries
    conditions = [TimeEntry.organization_id == org.id, TimeEntry.is_billable == True, TimeEntry.invoice_id.is_(None)]  # noqa: E712
    if request.time_entry_ids:
        conditions.append(TimeEntry.id.in_(request.time_entry_ids))
    elif request.matter_id:
        conditions.append(TimeEntry.matter_id == request.matter_id)

    entries_result = await db.execute(select(TimeEntry).where(and_(*conditions)))
    entries = entries_result.scalars().all()

    line_items = []
    subtotal = 0.0
    for entry in entries:
        amount = entry.amount or (entry.hours * (entry.rate or 0))
        line_items.append({
            "entry_id": str(entry.id),
            "date": entry.date.isoformat(),
            "description": entry.description,
            "hours": entry.hours,
            "rate": entry.rate or 0,
            "amount": amount,
        })
        subtotal += amount

    invoice = Invoice(
        organization_id=org.id,
        client_id=request.client_id,
        matter_id=request.matter_id,
        created_by_id=user.id,
        invoice_number=invoice_number,
        issue_date=datetime.now(timezone.utc),
        due_date=request.due_date,
        subtotal=round(subtotal, 2),
        total=round(subtotal, 2),  # tax can be added separately
        currency=request.currency,
        line_items=line_items,
        notes=request.notes,
        payment_terms=request.payment_terms,
    )
    db.add(invoice)
    await db.flush()

    # Link time entries to this invoice
    for entry in entries:
        entry.invoice_id = invoice.id
    await db.flush()

    return _invoice_dict(invoice)


@router.get("/invoices")
async def list_invoices(
    org: CurrentOrg = None, db: DB = None,
    status_filter: str | None = Query(None, alias="status"),
    client_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conditions = [Invoice.organization_id == org.id]
    if status_filter:
        conditions.append(Invoice.status == InvoiceStatus(status_filter))
    if client_id:
        conditions.append(Invoice.client_id == client_id)

    result = await db.execute(
        select(Invoice).where(and_(*conditions)).order_by(Invoice.issue_date.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    return [_invoice_dict(i) for i in result.scalars().all()]


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: uuid.UUID, org: CurrentOrg = None, db: DB = None):
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _invoice_dict(invoice)


@router.patch("/invoices/{invoice_id}/status")
async def update_invoice_status(
    invoice_id: uuid.UUID,
    new_status: str = Query(...),
    amount_paid: float | None = None,
    org: CurrentOrg = None, db: DB = None,
):
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = InvoiceStatus(new_status)
    if amount_paid is not None:
        invoice.amount_paid = amount_paid
    if new_status == "paid":
        invoice.paid_at = datetime.now(timezone.utc)
        invoice.amount_paid = invoice.total
    await db.flush()
    return _invoice_dict(invoice)


# ===== Billing Summary =====

@router.get("/summary")
async def billing_summary(org: CurrentOrg = None, db: DB = None):
    """Firm-wide billing summary."""
    # Total billable hours this month
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    hours_result = await db.execute(
        select(func.sum(TimeEntry.hours), func.sum(TimeEntry.amount))
        .where(and_(
            TimeEntry.organization_id == org.id,
            TimeEntry.is_billable == True,  # noqa: E712
            TimeEntry.date >= month_start,
        ))
    )
    hours_row = hours_result.one()

    # Outstanding invoices
    outstanding_result = await db.execute(
        select(func.sum(Invoice.total - Invoice.amount_paid), func.count())
        .where(and_(
            Invoice.organization_id == org.id,
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE]),
        ))
    )
    outstanding_row = outstanding_result.one()

    # Paid this month
    paid_result = await db.execute(
        select(func.sum(Invoice.amount_paid))
        .where(and_(
            Invoice.organization_id == org.id,
            Invoice.paid_at >= month_start,
        ))
    )
    paid = paid_result.scalar() or 0

    return {
        "this_month": {
            "billable_hours": round(hours_row[0] or 0, 2),
            "billable_amount": round(hours_row[1] or 0, 2),
        },
        "outstanding": {
            "amount": round(outstanding_row[0] or 0, 2),
            "invoice_count": outstanding_row[1] or 0,
        },
        "collected_this_month": round(paid, 2),
    }


def _entry_dict(e: TimeEntry) -> dict:
    return {
        "id": str(e.id), "date": e.date.isoformat(), "hours": e.hours,
        "description": e.description, "is_billable": e.is_billable,
        "rate": e.rate, "amount": e.amount,
        "matter_id": str(e.matter_id) if e.matter_id else None,
        "user_id": str(e.user_id),
        "invoice_id": str(e.invoice_id) if e.invoice_id else None,
        "created_at": e.created_at.isoformat(),
    }


def _invoice_dict(i: Invoice) -> dict:
    return {
        "id": str(i.id), "invoice_number": i.invoice_number,
        "client_id": str(i.client_id) if i.client_id else None,
        "matter_id": str(i.matter_id) if i.matter_id else None,
        "issue_date": i.issue_date.isoformat(),
        "due_date": i.due_date.isoformat(),
        "status": i.status.value,
        "subtotal": i.subtotal, "total": i.total,
        "amount_paid": i.amount_paid, "currency": i.currency,
        "line_items": i.line_items, "notes": i.notes,
        "paid_at": i.paid_at.isoformat() if i.paid_at else None,
        "created_at": i.created_at.isoformat(),
    }
