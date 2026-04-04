"""Integration endpoints — email, payments, Google Calendar, cloud storage."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.db.session import get_db

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ===== Email =====

class SendEmailRequest(BaseModel):
    to: list[str]
    subject: str
    html_body: str
    text_body: str | None = None


@router.post("/email/send")
async def send_email(request: SendEmailRequest, user: CurrentUser = None, org: CurrentOrg = None):
    """Send an email via the configured provider (SMTP, SendGrid, or Postmark)."""
    from app.services.integrations.email import EmailService
    service = EmailService()
    success = await service.send(to=request.to, subject=request.subject, html_body=request.html_body, text_body=request.text_body)
    if not success:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Email sending failed")
    return {"sent": True, "to": request.to}


@router.post("/email/test")
async def test_email(user: CurrentUser = None, org: CurrentOrg = None):
    """Send a test email to the current user."""
    from app.services.integrations.email import EmailService, EmailTemplates
    service = EmailService()
    html = EmailTemplates.task_assigned(
        task_title="Test Task",
        assigned_by="MyDenning System",
        priority=3,
        due_date="2026-04-15",
        matter_title="Test Matter",
    )
    success = await service.send(to=[user.email], subject="MyDenning Test Email", html_body=html)
    return {"sent": success, "to": user.email}


# ===== Payments =====

class CreatePaymentRequest(BaseModel):
    invoice_id: uuid.UUID
    callback_url: str | None = None


@router.post("/payments/create-link")
async def create_payment_link(
    request: CreatePaymentRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Create a payment link for an invoice (Stripe or Paystack)."""
    from app.models.matter import Invoice
    from app.services.integrations.payments import PaymentService

    invoice = await db.get(Invoice, request.invoice_id)
    if not invoice or invoice.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Get client email
    customer_email = ""
    if invoice.client_id:
        from app.models.user import Client
        client = await db.get(Client, invoice.client_id)
        if client:
            customer_email = client.email or client.primary_contact_email or ""

    if not customer_email:
        raise HTTPException(status_code=400, detail="Invoice has no client email for payment")

    service = PaymentService()
    result = await service.create_payment_link(
        invoice_id=str(invoice.id),
        amount=invoice.total - invoice.amount_paid,
        currency=invoice.currency,
        customer_email=customer_email,
        description=f"Invoice {invoice.invoice_number}",
        callback_url=request.callback_url,
    )
    return result


@router.post("/payments/verify/{reference}")
async def verify_payment(
    reference: str,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Verify a payment and update the linked invoice if paid."""
    from app.models.matter import Invoice, InvoiceStatus
    from app.services.integrations.payments import PaymentService

    service = PaymentService()
    result = await service.verify_payment(reference)

    if result["verified"] and result.get("invoice_id"):
        invoice = await db.get(Invoice, uuid.UUID(result["invoice_id"]))
        if invoice and invoice.organization_id == org.id:
            invoice.amount_paid = result["amount"]
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = datetime.now(datetime.timezone.utc) if hasattr(datetime, 'timezone') else None
            await db.flush()

    return result


@router.post("/payments/webhook")
async def payment_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Webhook endpoint for Stripe/Paystack payment notifications."""
    from app.core.config import get_settings
    from app.models.matter import Invoice, InvoiceStatus
    from app.services.integrations.payments import PaymentService

    settings = get_settings()
    body = await request.body()
    service = PaymentService()

    if settings.payment_provider == "stripe":
        sig = request.headers.get("stripe-signature", "")
        if not service.verify_stripe_webhook(body, sig):
            raise HTTPException(status_code=400, detail="Invalid signature")
        data = await request.json()
        if data.get("type") == "checkout.session.completed":
            session = data["data"]["object"]
            invoice_id = session.get("metadata", {}).get("invoice_id")
            if invoice_id:
                invoice = await db.get(Invoice, uuid.UUID(invoice_id))
                if invoice:
                    invoice.status = InvoiceStatus.PAID
                    invoice.amount_paid = invoice.total
                    invoice.paid_at = datetime.now(datetime.timezone.utc) if hasattr(datetime, 'timezone') else None
                    await db.commit()

    elif settings.payment_provider == "paystack":
        sig = request.headers.get("x-paystack-signature", "")
        if not service.verify_paystack_webhook(body, sig):
            raise HTTPException(status_code=400, detail="Invalid signature")
        data = await request.json()
        if data.get("event") == "charge.success":
            tx = data.get("data", {})
            invoice_id = tx.get("metadata", {}).get("invoice_id")
            if invoice_id:
                invoice = await db.get(Invoice, uuid.UUID(invoice_id))
                if invoice:
                    invoice.status = InvoiceStatus.PAID
                    invoice.amount_paid = tx.get("amount", 0) / 100
                    invoice.paid_at = datetime.now(datetime.timezone.utc) if hasattr(datetime, 'timezone') else None
                    await db.commit()

    return {"received": True}


# ===== Google Calendar =====

@router.get("/google/calendar/auth-url")
async def google_calendar_auth_url(
    redirect_uri: str = Query(...),
    user: CurrentUser = None,
):
    """Get the Google OAuth2 consent URL for calendar access."""
    from app.services.integrations.google_calendar import GoogleCalendarService
    service = GoogleCalendarService()
    url = service.get_auth_url(redirect_uri, state=str(user.id))
    return {"auth_url": url}


@router.post("/google/calendar/callback")
async def google_calendar_callback(
    code: str,
    redirect_uri: str,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Exchange OAuth2 code for tokens and store for the user."""
    from app.services.integrations.google_calendar import GoogleCalendarService
    from app.services.memory.service import MemoryService

    service = GoogleCalendarService()
    tokens = await service.exchange_code(code, redirect_uri)

    # Store tokens in org preferences (encrypted in production)
    mem = MemoryService(db)
    await mem.set_preference(
        organization_id=org.id,
        user_id=user.id,
        category="integrations",
        key=f"google_calendar_tokens_{user.id}",
        value=tokens,
        description="Google Calendar OAuth tokens",
    )
    return {"connected": True}


@router.post("/google/calendar/push-event")
async def push_event_to_google(
    event_id: uuid.UUID,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Push a MyDenning calendar event to Google Calendar."""
    from app.models.matter import CalendarEvent
    from app.services.integrations.google_calendar import GoogleCalendarService
    from app.services.memory.service import MemoryService

    event = await db.get(CalendarEvent, event_id)
    if not event or event.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Event not found")

    # Get stored tokens
    mem = MemoryService(db)
    prefs = await mem.get_organization_preferences(org.id, "integrations")
    token_pref = next((p for p in prefs if p.key == f"google_calendar_tokens_{user.id}"), None)
    if not token_pref:
        raise HTTPException(status_code=400, detail="Google Calendar not connected. Authorize first.")

    tokens = token_pref.value
    service = GoogleCalendarService()

    # Refresh token if needed
    access_token = tokens.get("access_token")
    if tokens.get("refresh_token"):
        try:
            access_token = await service.refresh_access_token(tokens["refresh_token"])
        except Exception:
            pass  # use existing token

    result = await service.push_event(access_token, {
        "title": event.title,
        "description": event.description or "",
        "location": event.location or "",
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat() if event.end_time else event.start_time.isoformat(),
    })
    return result


# ===== Google Drive =====

@router.get("/google/drive/auth-url")
async def google_drive_auth_url(redirect_uri: str = Query(...), user: CurrentUser = None):
    from app.services.integrations.cloud_storage import GoogleDriveService
    service = GoogleDriveService()
    return {"auth_url": service.get_auth_url(redirect_uri, state=str(user.id))}


@router.post("/google/drive/callback")
async def google_drive_callback(
    code: str, redirect_uri: str,
    user: CurrentUser = None, org: CurrentOrg = None, db: DB = None,
):
    from app.services.integrations.cloud_storage import GoogleDriveService
    from app.services.memory.service import MemoryService

    service = GoogleDriveService()
    tokens = await service.exchange_code(code, redirect_uri)
    mem = MemoryService(db)
    await mem.set_preference(org.id, user.id, "integrations", f"gdrive_tokens_{user.id}", tokens, "Google Drive OAuth tokens")
    return {"connected": True}


@router.get("/google/drive/folders")
async def list_drive_folders(user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    """List Google Drive folders for the folder picker."""
    from app.services.integrations.cloud_storage import GoogleDriveService
    from app.services.memory.service import MemoryService

    mem = MemoryService(db)
    prefs = await mem.get_organization_preferences(org.id, "integrations")
    token_pref = next((p for p in prefs if p.key == f"gdrive_tokens_{user.id}"), None)
    if not token_pref:
        raise HTTPException(status_code=400, detail="Google Drive not connected")

    service = GoogleDriveService()
    access_token = token_pref.value.get("access_token")
    if token_pref.value.get("refresh_token"):
        try:
            access_token = await service.refresh_access_token(token_pref.value["refresh_token"])
        except Exception:
            pass

    return await service.list_folders(access_token)


@router.get("/google/drive/files/{folder_id}")
async def list_drive_files(folder_id: str, user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    """List files in a Google Drive folder."""
    from app.services.integrations.cloud_storage import GoogleDriveService
    from app.services.memory.service import MemoryService

    mem = MemoryService(db)
    prefs = await mem.get_organization_preferences(org.id, "integrations")
    token_pref = next((p for p in prefs if p.key == f"gdrive_tokens_{user.id}"), None)
    if not token_pref:
        raise HTTPException(status_code=400, detail="Google Drive not connected")

    service = GoogleDriveService()
    access_token = token_pref.value.get("access_token")
    if token_pref.value.get("refresh_token"):
        try:
            access_token = await service.refresh_access_token(token_pref.value["refresh_token"])
        except Exception:
            pass

    return await service.list_folder(access_token, folder_id)


@router.post("/google/drive/import/{file_id}")
async def import_drive_file(
    file_id: str,
    title: str = Query(""),
    document_type: str = Query("other"),
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Import a file from Google Drive into MyDenning as a document."""
    from app.models.document import Document, DocumentType, ProcessingStatus
    from app.services.document_parser.parser import DocumentParserService
    from app.services.integrations.cloud_storage import GoogleDriveService
    from app.services.memory.service import MemoryService
    from app.services.storage import StorageService

    mem = MemoryService(db)
    prefs = await mem.get_organization_preferences(org.id, "integrations")
    token_pref = next((p for p in prefs if p.key == f"gdrive_tokens_{user.id}"), None)
    if not token_pref:
        raise HTTPException(status_code=400, detail="Google Drive not connected")

    gdrive = GoogleDriveService()
    access_token = token_pref.value.get("access_token")
    if token_pref.value.get("refresh_token"):
        try:
            access_token = await gdrive.refresh_access_token(token_pref.value["refresh_token"])
        except Exception:
            pass

    # Download file
    content = await gdrive.download_file(access_token, file_id)
    content_hash = DocumentParserService.compute_hash(content)

    # Upload to S3
    storage = StorageService()
    file_key = f"documents/{org.id}/gdrive-import/{content_hash[:16]}/{title or file_id}"
    await storage.upload_file(content, file_key)

    doc = Document(
        organization_id=org.id,
        uploaded_by_id=user.id,
        title=title or file_id,
        description=f"Imported from Google Drive",
        document_type=DocumentType(document_type),
        file_name=title or file_id,
        file_path=file_key,
        file_size=len(content),
        mime_type="application/octet-stream",
        content_hash=content_hash,
        processing_status=ProcessingStatus.PENDING,
    )
    db.add(doc)
    await db.flush()

    from app.tasks.document_tasks import process_document_task
    process_document_task.delay(str(doc.id))

    return {"document_id": str(doc.id), "title": doc.title, "status": "processing"}


# ===== Status =====

@router.get("/status")
async def integration_status(user: CurrentUser = None, org: CurrentOrg = None, db: DB = None):
    """Check which integrations are configured and connected."""
    from app.core.config import get_settings
    from app.services.memory.service import MemoryService

    s = get_settings()
    mem = MemoryService(db)
    prefs = await mem.get_organization_preferences(org.id, "integrations")
    pref_keys = {p.key for p in prefs}

    return {
        "email": {
            "provider": s.email_provider,
            "configured": bool(s.smtp_host or s.sendgrid_api_key or s.postmark_server_token),
        },
        "payments": {
            "provider": s.payment_provider or None,
            "configured": bool(s.stripe_secret_key or s.paystack_secret_key),
        },
        "google_calendar": {
            "configured": bool(s.google_client_id),
            "connected": f"google_calendar_tokens_{user.id}" in pref_keys,
        },
        "google_drive": {
            "configured": bool(s.gdrive_client_id),
            "connected": f"gdrive_tokens_{user.id}" in pref_keys,
        },
    }
