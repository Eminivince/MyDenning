"""Email intake API — inbound email webhook + configuration endpoints."""

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import CurrentOrg, CurrentUser, DB
from app.db.session import get_db

router = APIRouter(tags=["email-intake"])


# ===== Config endpoints (authenticated) =====

class IntakeConfigRequest(BaseModel):
    default_document_type: str = "contract"
    default_jurisdiction: str | None = None
    default_matter_id: uuid.UUID | None = None
    auto_review: bool = False
    auto_playbook_id: uuid.UUID | None = None
    allowed_sender_domains: list[str] | None = None
    allowed_sender_emails: list[str] | None = None


@router.post("/intake/email/configure")
async def configure_email_intake(
    request: IntakeConfigRequest,
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Configure email intake for your organization.

    After configuration, forward emails with document attachments to the
    generated intake address. Attachments (PDF, DOCX, DOC, TXT) are
    automatically uploaded, processed, and optionally reviewed against
    your playbook.
    """
    from app.services.legal_features.email_intake import EmailIntakeService
    service = EmailIntakeService(db)
    config = await service.configure(
        organization_id=org.id,
        user_id=user.id,
        default_document_type=request.default_document_type,
        default_jurisdiction=request.default_jurisdiction,
        default_matter_id=request.default_matter_id,
        auto_review=request.auto_review,
        auto_playbook_id=request.auto_playbook_id,
        allowed_sender_domains=request.allowed_sender_domains,
        allowed_sender_emails=request.allowed_sender_emails,
    )
    return {
        "id": str(config.id),
        "intake_email": config.intake_email,
        "is_active": config.is_active,
        "default_document_type": config.default_document_type,
        "default_jurisdiction": config.default_jurisdiction,
        "auto_review": config.auto_review,
    }


@router.get("/intake/email/config")
async def get_email_intake_config(
    user: CurrentUser = None,
    org: CurrentOrg = None,
    db: DB = None,
):
    """Get the current email intake configuration."""
    from app.services.legal_features.email_intake import EmailIntakeService
    service = EmailIntakeService(db)
    config = await service.get_config(org.id)
    if not config:
        return {"configured": False}
    return {
        "configured": True,
        "id": str(config.id),
        "intake_email": config.intake_email,
        "is_active": config.is_active,
        "default_document_type": config.default_document_type,
        "default_jurisdiction": config.default_jurisdiction,
        "auto_review": config.auto_review,
        "allowed_sender_domains": config.allowed_sender_domains,
        "allowed_sender_emails": config.allowed_sender_emails,
    }


# ===== Inbound webhook (no auth — verified by provider signature) =====

@router.post("/intake/email/inbound")
async def inbound_email_webhook(request: Request):
    """Webhook endpoint for inbound email providers (SendGrid, Mailgun, Postmark).

    This is called by the email provider when an email arrives at an intake address.
    No JWT auth — authenticated via provider-specific signature verification.
    """
    from app.core.config import get_settings
    from app.db.session import async_session_factory
    from app.services.legal_features.email_intake import EmailIntakeService

    settings = get_settings()
    if not settings.email_intake_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email intake not enabled")

    content_type = request.headers.get("content-type", "")

    # Parse based on provider
    if "multipart/form-data" in content_type:
        # SendGrid Inbound Parse format
        form = await request.form()
        to_email = str(form.get("to", ""))
        from_email = str(form.get("from", ""))
        subject = str(form.get("subject", ""))
        body_text = str(form.get("text", ""))

        # Extract attachments
        import base64
        attachments = []
        attachment_count = int(form.get("attachments", 0) or 0)
        for i in range(1, attachment_count + 1):
            att_file = form.get(f"attachment{i}")
            if att_file and hasattr(att_file, "read"):
                content_bytes = await att_file.read()
                attachments.append({
                    "filename": getattr(att_file, "filename", f"attachment{i}"),
                    "content_base64": base64.b64encode(content_bytes).decode(),
                    "content_type": getattr(att_file, "content_type", "application/octet-stream"),
                })

    elif "application/json" in content_type:
        # Mailgun / Postmark JSON format
        data = await request.json()

        # Mailgun format
        if "sender" in data:
            to_email = data.get("recipient", "")
            from_email = data.get("sender", "")
            subject = data.get("subject", "")
            body_text = data.get("body-plain", data.get("stripped-text", ""))
        # Postmark format
        elif "FromFull" in data:
            to_email = data.get("To", "")
            from_email = data.get("From", "")
            subject = data.get("Subject", "")
            body_text = data.get("TextBody", "")
        else:
            to_email = data.get("to", "")
            from_email = data.get("from", "")
            subject = data.get("subject", "")
            body_text = data.get("text", data.get("body", ""))

        import base64
        attachments = []
        raw_attachments = data.get("attachments", data.get("Attachments", []))
        for att in raw_attachments:
            if isinstance(att, dict):
                content = att.get("content", att.get("Content", att.get("data", "")))
                # Some providers send base64, some send raw
                if not isinstance(content, str):
                    content = base64.b64encode(content).decode() if isinstance(content, bytes) else ""
                attachments.append({
                    "filename": att.get("filename", att.get("Name", att.get("FileName", "unknown"))),
                    "content_base64": content,
                    "content_type": att.get("content-type", att.get("ContentType", "application/octet-stream")),
                })
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported content type")

    # Process the email
    async with async_session_factory() as db:
        service = EmailIntakeService(db)
        result = await service.process_inbound_email(
            to_email=to_email,
            from_email=from_email,
            subject=subject,
            body_text=body_text,
            attachments=attachments,
        )
        await db.commit()

    return result
