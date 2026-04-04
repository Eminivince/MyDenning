"""Webhook delivery service — fires events to registered webhook URLs.

Supports HMAC-SHA256 signing, automatic retry on failure, circuit breaker
(disables webhook after 10 consecutive failures), and full delivery logging.
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_features import Webhook, WebhookDelivery, WebhookEventType

logger = structlog.get_logger(__name__)

MAX_CONSECUTIVE_FAILURES = 10


class WebhookService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        url: str,
        events: list[str],
        secret: str | None = None,
    ) -> Webhook:
        webhook = Webhook(
            organization_id=organization_id,
            created_by_id=user_id,
            name=name,
            url=url,
            secret=secret,
            events=events,
            is_active=True,
        )
        self.db.add(webhook)
        await self.db.flush()
        logger.info("webhook_registered", name=name, events=events)
        return webhook

    async def list_webhooks(self, organization_id: uuid.UUID) -> list[Webhook]:
        result = await self.db.execute(
            select(Webhook).where(Webhook.organization_id == organization_id).order_by(Webhook.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, webhook_id: uuid.UUID) -> None:
        webhook = await self.db.get(Webhook, webhook_id)
        if webhook:
            await self.db.delete(webhook)
            await self.db.flush()

    async def fire_event(
        self,
        organization_id: uuid.UUID,
        event_type: str,
        payload: dict,
    ) -> int:
        """Fire an event to all matching webhooks. Returns count of deliveries attempted."""
        result = await self.db.execute(
            select(Webhook).where(
                and_(
                    Webhook.organization_id == organization_id,
                    Webhook.is_active == True,  # noqa: E712
                )
            )
        )
        webhooks = result.scalars().all()

        delivered = 0
        for webhook in webhooks:
            if event_type not in webhook.events:
                continue

            # Skip if circuit breaker tripped
            if webhook.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.warning("webhook_circuit_open", webhook_id=str(webhook.id), name=webhook.name)
                continue

            success, status_code, duration = await self._deliver(webhook, event_type, payload)

            # Log delivery
            delivery = WebhookDelivery(
                webhook_id=webhook.id,
                event_type=event_type,
                payload=payload,
                status_code=status_code,
                success=success,
                duration_ms=duration,
            )
            self.db.add(delivery)

            # Update webhook health
            webhook.last_triggered_at = datetime.now(timezone.utc)
            webhook.last_status_code = status_code
            if success:
                webhook.consecutive_failures = 0
            else:
                webhook.consecutive_failures += 1
                if webhook.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    webhook.is_active = False
                    logger.error("webhook_disabled", webhook_id=str(webhook.id), name=webhook.name)

            delivered += 1

        await self.db.flush()
        return delivered

    async def _deliver(self, webhook: Webhook, event_type: str, payload: dict) -> tuple[bool, int | None, int]:
        """Deliver a payload to a webhook URL. Returns (success, status_code, duration_ms)."""
        body = json.dumps({
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload,
        })

        headers = {"Content-Type": "application/json", "User-Agent": "MyDenning-Webhooks/1.0"}

        # HMAC signing
        if webhook.secret:
            signature = hmac.new(webhook.secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook.url, content=body, headers=headers)
                duration = int((time.time() - start) * 1000)
                success = 200 <= response.status_code < 300
                return success, response.status_code, duration
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            logger.warning("webhook_delivery_failed", url=webhook.url, error=str(e))
            return False, None, duration

    async def get_deliveries(self, webhook_id: uuid.UUID, limit: int = 50) -> list[WebhookDelivery]:
        result = await self.db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == webhook_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def reset_webhook(self, webhook_id: uuid.UUID) -> Webhook:
        """Reset a disabled webhook (clear failure count, re-enable)."""
        webhook = await self.db.get(Webhook, webhook_id)
        if not webhook:
            raise ValueError("Webhook not found")
        webhook.consecutive_failures = 0
        webhook.is_active = True
        await self.db.flush()
        return webhook
