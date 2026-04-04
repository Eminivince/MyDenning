"""Payment gateway integration — Stripe and Paystack.

Supports:
1. Stripe — global, card payments, bank transfers
2. Paystack — Nigeria/Africa focus, card + bank + USSD + mobile money

Both expose the same interface: create payment link, verify payment, handle webhook.
"""

import hashlib
import hmac
import uuid
from datetime import datetime, timezone

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class PaymentService:
    """Unified payment interface for Stripe and Paystack."""

    def __init__(self):
        self.settings = get_settings()

    async def create_payment_link(
        self,
        invoice_id: str,
        amount: float,  # in major currency unit (e.g. 5000.00 for NGN 5000)
        currency: str,
        customer_email: str,
        description: str,
        callback_url: str | None = None,
    ) -> dict:
        """Create a payment link/session. Returns {url, reference, provider}."""
        provider = self.settings.payment_provider
        if provider == "stripe":
            return await self._create_stripe_session(invoice_id, amount, currency, customer_email, description, callback_url)
        elif provider == "paystack":
            return await self._create_paystack_link(invoice_id, amount, currency, customer_email, description, callback_url)
        else:
            raise ValueError("No payment provider configured. Set PAYMENT_PROVIDER to 'stripe' or 'paystack'.")

    async def verify_payment(self, reference: str) -> dict:
        """Verify a payment by reference. Returns {verified, amount, currency, status}."""
        provider = self.settings.payment_provider
        if provider == "stripe":
            return await self._verify_stripe(reference)
        elif provider == "paystack":
            return await self._verify_paystack(reference)
        return {"verified": False, "status": "no_provider"}

    # ===== Stripe =====

    async def _create_stripe_session(self, invoice_id, amount, currency, email, description, callback_url) -> dict:
        s = self.settings
        if not s.stripe_secret_key:
            raise ValueError("Stripe secret key not configured")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data={
                    "mode": "payment",
                    "payment_method_types[]": "card",
                    "line_items[0][price_data][currency]": currency.lower(),
                    "line_items[0][price_data][unit_amount]": int(amount * 100),  # Stripe uses cents
                    "line_items[0][price_data][product_data][name]": description,
                    "line_items[0][quantity]": "1",
                    "customer_email": email,
                    "metadata[invoice_id]": invoice_id,
                    "success_url": callback_url or "https://mydenning.com/billing?payment=success",
                    "cancel_url": callback_url or "https://mydenning.com/billing?payment=cancelled",
                },
                headers={"Authorization": f"Bearer {s.stripe_secret_key}"},
                timeout=15.0,
            )
            data = resp.json()
            if resp.status_code != 200:
                logger.error("stripe_session_failed", error=data)
                raise ValueError(f"Stripe error: {data.get('error', {}).get('message', 'Unknown')}")

            return {
                "url": data["url"],
                "reference": data["id"],
                "provider": "stripe",
            }

    async def _verify_stripe(self, session_id: str) -> dict:
        s = self.settings
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
                headers={"Authorization": f"Bearer {s.stripe_secret_key}"},
            )
            data = resp.json()
            return {
                "verified": data.get("payment_status") == "paid",
                "amount": data.get("amount_total", 0) / 100,
                "currency": data.get("currency", "").upper(),
                "status": data.get("payment_status", "unknown"),
                "invoice_id": data.get("metadata", {}).get("invoice_id"),
            }

    def verify_stripe_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify Stripe webhook signature."""
        s = self.settings
        if not s.stripe_webhook_secret:
            return False
        # Stripe uses their own signing scheme — simplified check
        expected = hmac.new(s.stripe_webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ===== Paystack =====

    async def _create_paystack_link(self, invoice_id, amount, currency, email, description, callback_url) -> dict:
        s = self.settings
        if not s.paystack_secret_key:
            raise ValueError("Paystack secret key not configured")

        # Paystack amount is in kobo (smallest unit)
        amount_minor = int(amount * 100)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.paystack.co/transaction/initialize",
                json={
                    "email": email,
                    "amount": amount_minor,
                    "currency": currency.upper(),
                    "reference": f"inv-{invoice_id}-{uuid.uuid4().hex[:8]}",
                    "callback_url": callback_url or "https://mydenning.com/billing?payment=success",
                    "metadata": {"invoice_id": invoice_id, "description": description},
                },
                headers={"Authorization": f"Bearer {s.paystack_secret_key}", "Content-Type": "application/json"},
                timeout=15.0,
            )
            data = resp.json()
            if not data.get("status"):
                logger.error("paystack_init_failed", error=data)
                raise ValueError(f"Paystack error: {data.get('message', 'Unknown')}")

            return {
                "url": data["data"]["authorization_url"],
                "reference": data["data"]["reference"],
                "provider": "paystack",
            }

    async def _verify_paystack(self, reference: str) -> dict:
        s = self.settings
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.paystack.co/transaction/verify/{reference}",
                headers={"Authorization": f"Bearer {s.paystack_secret_key}"},
            )
            data = resp.json()
            tx = data.get("data", {})
            return {
                "verified": tx.get("status") == "success",
                "amount": tx.get("amount", 0) / 100,
                "currency": tx.get("currency", "").upper(),
                "status": tx.get("status", "unknown"),
                "invoice_id": tx.get("metadata", {}).get("invoice_id"),
            }

    def verify_paystack_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify Paystack webhook signature (HMAC SHA512)."""
        s = self.settings
        if not s.paystack_webhook_secret:
            return False
        expected = hmac.new(s.paystack_webhook_secret.encode(), payload, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, signature)
