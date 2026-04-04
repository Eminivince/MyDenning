"""Outbound email service — sends notifications, digests, and client communications.

Supports three providers:
1. SMTP (any provider — Gmail, Outlook, Amazon SES, custom)
2. SendGrid (API-based, recommended for production)
3. Postmark (API-based, great deliverability)

All providers share the same interface. HTML templates with plain-text fallback.
"""

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class EmailService:
    """Unified email sending interface across SMTP, SendGrid, and Postmark."""

    def __init__(self):
        self.settings = get_settings()

    async def send(
        self,
        to: str | list[str],
        subject: str,
        html_body: str,
        text_body: str | None = None,
        reply_to: str | None = None,
    ) -> bool:
        """Send an email. Returns True on success."""
        if isinstance(to, str):
            to = [to]

        if not text_body:
            # Strip HTML tags for plain text fallback
            import re
            text_body = re.sub(r'<[^>]+>', '', html_body)

        provider = self.settings.email_provider
        try:
            if provider == "sendgrid":
                return await self._send_sendgrid(to, subject, html_body, text_body, reply_to)
            elif provider == "postmark":
                return await self._send_postmark(to, subject, html_body, text_body, reply_to)
            else:
                return await self._send_smtp(to, subject, html_body, text_body, reply_to)
        except Exception as e:
            logger.error("email_send_failed", to=to, subject=subject, error=str(e))
            return False

    async def _send_smtp(self, to: list[str], subject: str, html: str, text: str, reply_to: str | None) -> bool:
        s = self.settings
        if not s.smtp_host:
            logger.warning("smtp_not_configured")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{s.email_from_name} <{s.email_from_address}>"
        msg["To"] = ", ".join(to)
        if reply_to:
            msg["Reply-To"] = reply_to

        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        def _send():
            with smtplib.SMTP(s.smtp_host, s.smtp_port) as server:
                if s.smtp_use_tls:
                    server.starttls()
                if s.smtp_username:
                    server.login(s.smtp_username, s.smtp_password)
                server.sendmail(s.email_from_address, to, msg.as_string())

        await asyncio.to_thread(_send)
        logger.info("email_sent_smtp", to=to, subject=subject)
        return True

    async def _send_sendgrid(self, to: list[str], subject: str, html: str, text: str, reply_to: str | None) -> bool:
        s = self.settings
        if not s.sendgrid_api_key:
            logger.warning("sendgrid_not_configured")
            return False

        payload = {
            "personalizations": [{"to": [{"email": addr} for addr in to]}],
            "from": {"email": s.email_from_address, "name": s.email_from_name},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text},
                {"type": "text/html", "value": html},
            ],
        }
        if reply_to:
            payload["reply_to"] = {"email": reply_to}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={"Authorization": f"Bearer {s.sendgrid_api_key}", "Content-Type": "application/json"},
                timeout=10.0,
            )
            success = resp.status_code in (200, 202)
            if success:
                logger.info("email_sent_sendgrid", to=to, subject=subject)
            else:
                logger.error("sendgrid_error", status=resp.status_code, body=resp.text[:200])
            return success

    async def _send_postmark(self, to: list[str], subject: str, html: str, text: str, reply_to: str | None) -> bool:
        s = self.settings
        if not s.postmark_server_token:
            logger.warning("postmark_not_configured")
            return False

        payload = {
            "From": f"{s.email_from_name} <{s.email_from_address}>",
            "To": ", ".join(to),
            "Subject": subject,
            "HtmlBody": html,
            "TextBody": text,
            "MessageStream": "outbound",
        }
        if reply_to:
            payload["ReplyTo"] = reply_to

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.postmarkapp.com/email",
                json=payload,
                headers={"X-Postmark-Server-Token": s.postmark_server_token, "Content-Type": "application/json"},
                timeout=10.0,
            )
            success = resp.status_code == 200
            if success:
                logger.info("email_sent_postmark", to=to, subject=subject)
            else:
                logger.error("postmark_error", status=resp.status_code, body=resp.text[:200])
            return success


class EmailTemplates:
    """HTML email templates for all notification types."""

    BASE_STYLE = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1a1a2e; line-height: 1.6; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { border-bottom: 2px solid #1a1a2e; padding-bottom: 16px; margin-bottom: 24px; }
        .header h1 { font-size: 20px; margin: 0; }
        .content { margin-bottom: 24px; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .badge-critical { background: #fee2e2; color: #991b1b; }
        .badge-high { background: #fef3c7; color: #92400e; }
        .badge-medium { background: #e0e7ff; color: #3730a3; }
        .btn { display: inline-block; padding: 10px 20px; background: #1a1a2e; color: white; text-decoration: none; border-radius: 6px; font-size: 14px; }
        .footer { border-top: 1px solid #e5e7eb; padding-top: 16px; font-size: 12px; color: #6b7280; }
    </style>
    """

    @classmethod
    def task_assigned(cls, task_title: str, assigned_by: str, priority: int, due_date: str | None, matter_title: str | None, app_url: str = "") -> str:
        pri_label = {1: "Critical", 2: "High", 3: "Medium", 4: "Low"}.get(priority, "Medium")
        pri_class = {1: "critical", 2: "high", 3: "medium"}.get(priority, "medium")
        return f"""<html><head>{cls.BASE_STYLE}</head><body><div class="container">
        <div class="header"><h1>New Task Assigned</h1></div>
        <div class="content">
            <p>You've been assigned a new task by <strong>{assigned_by}</strong>.</p>
            <h2 style="margin:16px 0 8px">{task_title}</h2>
            <p><span class="badge badge-{pri_class}">{pri_label}</span></p>
            {f'<p><strong>Due:</strong> {due_date}</p>' if due_date else ''}
            {f'<p><strong>Matter:</strong> {matter_title}</p>' if matter_title else ''}
            {f'<a href="{app_url}/tasks" class="btn">View Task</a>' if app_url else ''}
        </div>
        <div class="footer">MyDenning — Legal Intelligence Platform</div>
        </div></body></html>"""

    @classmethod
    def deadline_approaching(cls, title: str, due_date: str, hours_until: int, matter_title: str | None, is_court: bool = False, app_url: str = "") -> str:
        urgency = "URGENT: Court Deadline" if is_court else "Deadline Approaching"
        return f"""<html><head>{cls.BASE_STYLE}</head><body><div class="container">
        <div class="header"><h1>{urgency}</h1></div>
        <div class="content">
            <h2 style="margin:0 0 8px">{title}</h2>
            <p><strong>Due:</strong> {due_date} ({hours_until} hours from now)</p>
            {f'<p><strong>Matter:</strong> {matter_title}</p>' if matter_title else ''}
            {'<p><span class="badge badge-critical">Court Deadline</span></p>' if is_court else ''}
            {f'<a href="{app_url}/matters" class="btn">View Matter</a>' if app_url else ''}
        </div>
        <div class="footer">MyDenning — Legal Intelligence Platform</div>
        </div></body></html>"""

    @classmethod
    def digest(cls, digest_name: str, sections: dict, app_url: str = "") -> str:
        body_parts = []
        deadlines = sections.get("deadlines", {})
        if deadlines.get("overdue_count", 0) > 0:
            body_parts.append(f'<h3 style="color:#991b1b">Overdue Deadlines ({deadlines["overdue_count"]})</h3>')
            for d in deadlines.get("overdue", [])[:5]:
                body_parts.append(f'<p>• {d["title"]} — due {d["due_date"][:10]}</p>')
        if deadlines.get("upcoming_count", 0) > 0:
            body_parts.append(f'<h3>Upcoming Deadlines ({deadlines["upcoming_count"]})</h3>')
            for d in deadlines.get("upcoming", [])[:5]:
                body_parts.append(f'<p>• {d["title"]} — due {d["due_date"][:10]}</p>')

        alerts = sections.get("regulatory_alerts", {})
        if alerts.get("unread_count", 0) > 0:
            body_parts.append(f'<h3>Regulatory Alerts ({alerts["unread_count"]})</h3>')
            for a in alerts.get("unread_alerts", [])[:5]:
                body_parts.append(f'<p>• {a["title"]}</p>')

        pending = sections.get("pending_documents", {})
        if pending.get("pending_count", 0) > 0:
            body_parts.append(f'<p>{pending["pending_count"]} documents processing</p>')
        if pending.get("failed_count", 0) > 0:
            body_parts.append(f'<p style="color:#991b1b">{pending["failed_count"]} documents failed</p>')

        matters = sections.get("active_matters", {})
        if matters.get("active_matters"):
            body_parts.append(f'<p>{matters["active_matters"]} active matters</p>')

        content = "\n".join(body_parts) if body_parts else "<p>Nothing to report. All clear.</p>"

        return f"""<html><head>{cls.BASE_STYLE}</head><body><div class="container">
        <div class="header"><h1>{digest_name}</h1></div>
        <div class="content">{content}</div>
        {f'<a href="{app_url}" class="btn">Open MyDenning</a>' if app_url else ''}
        <div class="footer">MyDenning — Legal Intelligence Platform</div>
        </div></body></html>"""

    @classmethod
    def client_update(cls, matter_title: str, update_text: str, firm_name: str, app_url: str = "") -> str:
        return f"""<html><head>{cls.BASE_STYLE}</head><body><div class="container">
        <div class="header"><h1>Matter Update from {firm_name}</h1></div>
        <div class="content">
            <h2 style="margin:0 0 8px">{matter_title}</h2>
            <p>{update_text}</p>
            {f'<a href="{app_url}" class="btn">View in Portal</a>' if app_url else ''}
        </div>
        <div class="footer">This is a confidential communication from {firm_name}.</div>
        </div></body></html>"""

    @classmethod
    def invoice_sent(cls, invoice_number: str, total: float, currency: str, due_date: str, firm_name: str, payment_url: str = "") -> str:
        return f"""<html><head>{cls.BASE_STYLE}</head><body><div class="container">
        <div class="header"><h1>Invoice from {firm_name}</h1></div>
        <div class="content">
            <p>Invoice <strong>{invoice_number}</strong> has been issued.</p>
            <h2 style="margin:16px 0 8px">{currency} {total:,.2f}</h2>
            <p><strong>Due:</strong> {due_date}</p>
            {f'<a href="{payment_url}" class="btn">Pay Now</a>' if payment_url else ''}
        </div>
        <div class="footer">{firm_name} — powered by MyDenning</div>
        </div></body></html>"""
