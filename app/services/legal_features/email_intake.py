"""Email intake service — auto-ingests documents from forwarded emails.

Supports inbound email webhooks from SendGrid, Mailgun, and Postmark.
These providers parse incoming emails and POST the structured data
(sender, subject, body, attachments) to our webhook endpoint.

Flow:
1. Email sent to acme-legal@ingest.mydenning.com
2. Email provider (SendGrid/Mailgun/Postmark) receives it
3. Provider parses email and POSTs to /api/v1/intake/email/inbound
4. We validate sender, extract attachments, create Documents
5. Trigger async processing via Celery
6. Optionally auto-run clause extraction and playbook comparison
"""

import base64
import hashlib
import hmac
import re
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.document import Document, DocumentType, ProcessingStatus
from app.models.legal_features import EmailIntakeConfig, EmailIntakeLog
from app.services.document_parser.parser import DocumentParserService
from app.services.storage import StorageService

logger = structlog.get_logger(__name__)

# Map file extensions to MIME types and document types
ALLOWED_EXTENSIONS = {
    ".pdf": ("application/pdf", DocumentType.CONTRACT),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", DocumentType.CONTRACT),
    ".doc": ("application/msword", DocumentType.CONTRACT),
    ".txt": ("text/plain", DocumentType.OTHER),
}


class EmailIntakeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.storage = StorageService()

    async def configure(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        default_document_type: str = "contract",
        default_jurisdiction: str | None = None,
        default_matter_id: uuid.UUID | None = None,
        auto_review: bool = False,
        auto_playbook_id: uuid.UUID | None = None,
        allowed_sender_domains: list[str] | None = None,
        allowed_sender_emails: list[str] | None = None,
    ) -> EmailIntakeConfig:
        """Configure email intake for an organization."""
        # Generate a unique intake email address
        from app.models.user import Organization
        org = await self.db.get(Organization, organization_id)
        slug = org.slug if org else str(organization_id)[:8]
        domain = self.settings.email_intake_domain or "ingest.mydenning.com"
        intake_email = f"{slug}@{domain}"

        # Upsert
        existing = await self.db.execute(
            select(EmailIntakeConfig).where(EmailIntakeConfig.organization_id == organization_id)
        )
        config = existing.scalar_one_or_none()

        if config:
            config.default_document_type = default_document_type
            config.default_jurisdiction = default_jurisdiction
            config.default_matter_id = default_matter_id
            config.auto_review = auto_review
            config.auto_playbook_id = auto_playbook_id
            config.allowed_sender_domains = allowed_sender_domains
            config.allowed_sender_emails = allowed_sender_emails
        else:
            config = EmailIntakeConfig(
                organization_id=organization_id,
                created_by_id=user_id,
                intake_email=intake_email,
                default_document_type=default_document_type,
                default_jurisdiction=default_jurisdiction,
                default_matter_id=default_matter_id,
                auto_review=auto_review,
                auto_playbook_id=auto_playbook_id,
                allowed_sender_domains=allowed_sender_domains,
                allowed_sender_emails=allowed_sender_emails,
            )
            self.db.add(config)

        await self.db.flush()
        return config

    async def get_config(self, organization_id: uuid.UUID) -> EmailIntakeConfig | None:
        result = await self.db.execute(
            select(EmailIntakeConfig).where(EmailIntakeConfig.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def process_inbound_email(
        self,
        to_email: str,
        from_email: str,
        subject: str | None,
        body_text: str | None,
        attachments: list[dict],  # [{filename, content_base64, content_type}]
    ) -> dict:
        """Process an inbound email from the email provider webhook.

        Returns: {status, documents_created, rejection_reason}
        """
        # 1. Find the intake config by to_email
        config_result = await self.db.execute(
            select(EmailIntakeConfig).where(
                EmailIntakeConfig.intake_email == to_email.lower().strip(),
                EmailIntakeConfig.is_active == True,  # noqa: E712
            )
        )
        config = config_result.scalar_one_or_none()

        if not config:
            logger.warning("email_intake_no_config", to=to_email)
            return {"status": "rejected", "reason": "No active intake configuration for this address"}

        # 2. Validate sender
        rejection = self._validate_sender(from_email, config)
        if rejection:
            log = EmailIntakeLog(
                organization_id=config.organization_id,
                config_id=config.id,
                sender_email=from_email,
                subject=subject,
                body_preview=body_text[:500] if body_text else None,
                attachment_count=len(attachments),
                status="rejected",
                rejection_reason=rejection,
            )
            self.db.add(log)
            await self.db.flush()
            return {"status": "rejected", "reason": rejection}

        # 3. Filter to valid attachments
        valid_attachments = []
        for att in attachments:
            filename = att.get("filename", "")
            ext = self._get_extension(filename)
            if ext in ALLOWED_EXTENSIONS:
                valid_attachments.append(att)

        if not valid_attachments:
            log = EmailIntakeLog(
                organization_id=config.organization_id,
                config_id=config.id,
                sender_email=from_email,
                subject=subject,
                body_preview=body_text[:500] if body_text else None,
                attachment_count=len(attachments),
                status="rejected",
                rejection_reason="No valid document attachments (PDF, DOCX, DOC, TXT)",
            )
            self.db.add(log)
            await self.db.flush()
            return {"status": "rejected", "reason": "No valid attachments"}

        # 4. Create documents from attachments
        documents_created = []
        for att in valid_attachments:
            try:
                doc = await self._create_document_from_attachment(att, config, from_email, subject)
                documents_created.append({
                    "document_id": str(doc.id),
                    "title": doc.title,
                    "file_name": doc.file_name,
                })
            except Exception as e:
                logger.error("email_intake_attachment_failed", filename=att.get("filename"), error=str(e))

        # 5. Log the intake
        log = EmailIntakeLog(
            organization_id=config.organization_id,
            config_id=config.id,
            sender_email=from_email,
            subject=subject,
            body_preview=body_text[:500] if body_text else None,
            attachment_count=len(attachments),
            documents_created=documents_created,
            status="processed",
        )
        self.db.add(log)
        await self.db.flush()

        # 6. Trigger async processing
        from app.tasks.document_tasks import process_document_task
        for doc_info in documents_created:
            process_document_task.delay(doc_info["document_id"])

            # Auto-review if configured
            if config.auto_review and config.auto_playbook_id:
                from app.tasks.document_tasks import celery_app
                # We'll fire the review after processing completes (handled by the webhook system)

        logger.info(
            "email_intake_processed",
            from_email=from_email,
            subject=subject,
            documents=len(documents_created),
        )

        return {
            "status": "processed",
            "documents_created": documents_created,
            "count": len(documents_created),
        }

    async def _create_document_from_attachment(
        self,
        attachment: dict,
        config: EmailIntakeConfig,
        sender_email: str,
        subject: str | None,
    ) -> Document:
        filename = attachment.get("filename", "unknown.pdf")
        content_b64 = attachment.get("content_base64", "")
        content = base64.b64decode(content_b64)

        ext = self._get_extension(filename)
        mime_type, default_doc_type = ALLOWED_EXTENSIONS.get(ext, ("application/octet-stream", DocumentType.OTHER))

        # Override with attachment content_type if provided
        if attachment.get("content_type"):
            mime_type = attachment["content_type"]

        content_hash = DocumentParserService.compute_hash(content)

        # Build title from subject + filename
        title = filename.rsplit(".", 1)[0]
        if subject:
            title = f"{subject} — {title}"

        # Upload to S3
        file_key = f"documents/{config.organization_id}/email-intake/{content_hash[:16]}/{filename}"
        await self.storage.upload_file(content, file_key, mime_type)

        doc_type = DocumentType(config.default_document_type) if config.default_document_type else default_doc_type

        document = Document(
            organization_id=config.organization_id,
            uploaded_by_id=config.created_by_id,  # attribute to the config creator
            title=title,
            description=f"Ingested via email from {sender_email}",
            document_type=doc_type,
            file_name=filename,
            file_path=file_key,
            file_size=len(content),
            mime_type=mime_type,
            content_hash=content_hash,
            jurisdiction=config.default_jurisdiction,
            matter_id=config.default_matter_id,
            processing_status=ProcessingStatus.PENDING,
        )
        self.db.add(document)
        await self.db.flush()

        return document

    def _validate_sender(self, from_email: str, config: EmailIntakeConfig) -> str | None:
        """Validate the sender against allowed lists. Returns rejection reason or None."""
        from_email_lower = from_email.lower().strip()
        domain = from_email_lower.split("@")[-1] if "@" in from_email_lower else ""

        # If specific emails are allowed, check against them
        if config.allowed_sender_emails:
            allowed = [e.lower().strip() for e in config.allowed_sender_emails]
            if from_email_lower in allowed:
                return None
            # If emails are specified but sender isn't in the list, check domain fallback

        # If domains are allowed, check against them
        if config.allowed_sender_domains:
            allowed_domains = [d.lower().strip() for d in config.allowed_sender_domains]
            if domain in allowed_domains:
                return None
            return f"Sender domain '{domain}' not in allowed list"

        # If neither list is set, accept all
        return None

    @staticmethod
    def _get_extension(filename: str) -> str:
        if "." in filename:
            return "." + filename.rsplit(".", 1)[-1].lower()
        return ""

    @staticmethod
    def verify_sendgrid_signature(payload: bytes, signature: str, timestamp: str, secret: str) -> bool:
        """Verify SendGrid inbound parse webhook signature."""
        data = timestamp + payload.decode("utf-8")
        expected = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def verify_mailgun_signature(token: str, timestamp: str, signature: str, secret: str) -> bool:
        """Verify Mailgun webhook signature."""
        data = timestamp + token
        expected = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
