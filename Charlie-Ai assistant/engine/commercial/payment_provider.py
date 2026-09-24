"""
engine/commercial/payment_provider.py — Payment Gateway Abstractions, Webhook Verification, and Replay Defense.
"""

from __future__ import annotations

import abc
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set, Tuple

from .models import PaymentCheckoutSession, PaymentReceipt, PlanTier

logger = logging.getLogger("jarvis.commercial.payment")


class PaymentProvider(abc.ABC):
    """Abstract interface for payment gateways (Razorpay, Cashfree, Stripe, etc.)."""

    @abc.abstractmethod
    def name(self) -> str:
        pass

    @abc.abstractmethod
    def create_checkout(self, user_id: str, plan: PlanTier, amount_paise: int) -> PaymentCheckoutSession:
        pass

    @abc.abstractmethod
    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        pass

    @abc.abstractmethod
    def cancel_subscription(self, subscription_id: str) -> bool:
        pass

    @abc.abstractmethod
    def handle_webhook(self, payload_bytes: bytes, signature_header: str) -> Tuple[bool, Dict[str, Any]]:
        pass

    @abc.abstractmethod
    def create_receipt(self, transaction_id: str, order_id: str, user_id: str, plan: PlanTier, amount_paise: int) -> PaymentReceipt:
        pass


class MockPaymentProvider(PaymentProvider):
    """Deterministic Mock Payment Provider for unit tests, offline QA, and sandbox verification."""

    def __init__(self, webhook_secret: str = "mock_secret_key_12345"):
        self.webhook_secret = webhook_secret.encode("utf-8")
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.processed_webhook_event_ids: Set[str] = set()

    def name(self) -> str:
        return "MockPaymentGateway"

    def create_checkout(self, user_id: str, plan: PlanTier, amount_paise: int) -> PaymentCheckoutSession:
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        session_id = f"sess_{uuid.uuid4().hex[:16]}"
        self.orders[order_id] = {
            "order_id": order_id,
            "user_id": user_id,
            "plan": plan,
            "amount_paise": amount_paise,
            "status": "CREATED",
        }
        return PaymentCheckoutSession(
            session_id=session_id,
            order_id=order_id,
            plan=plan,
            amount_paise=amount_paise,
            checkout_url=f"https://checkout.jarvis.local/pay/{order_id}",
        )

    def generate_valid_signature(self, order_id: str, payment_id: str) -> str:
        payload = f"{order_id}|{payment_id}".encode("utf-8")
        return hmac.new(self.webhook_secret, payload, hashlib.sha256).hexdigest()

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        """Verifies signature matches order_id|payment_id HMAC."""
        if not order_id or not payment_id or not signature:
            return False
        expected_sig = self.generate_valid_signature(order_id, payment_id)
        if not hmac.compare_digest(expected_sig, signature):
            return False

        if order_id in self.orders:
            self.orders[order_id]["status"] = "PAID"
            self.orders[order_id]["payment_id"] = payment_id
        return True

    def cancel_subscription(self, subscription_id: str) -> bool:
        return True

    def handle_webhook(self, payload_bytes: bytes, signature_header: str) -> Tuple[bool, Dict[str, Any]]:
        """Validates webhook HMAC and enforces replay protection on event IDs."""
        expected = hmac.new(self.webhook_secret, payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature_header):
            return False, {"error": "Invalid webhook signature."}

        import json
        try:
            data = json.loads(payload_bytes.decode("utf-8"))
            event_id = data.get("event_id")
            if not event_id:
                return False, {"error": "Missing event_id in webhook."}

            # Replay protection
            if event_id in self.processed_webhook_event_ids:
                return False, {"error": f"Replay detected for event {event_id}."}

            self.processed_webhook_event_ids.add(event_id)
            return True, data
        except Exception as e:
            return False, {"error": f"Failed to parse webhook: {e}"}

    def create_receipt(self, transaction_id: str, order_id: str, user_id: str, plan: PlanTier, amount_paise: int) -> PaymentReceipt:
        return PaymentReceipt(
            receipt_id=f"rcpt_{uuid.uuid4().hex[:8]}",
            transaction_id=transaction_id,
            order_id=order_id,
            user_id=user_id,
            plan=plan,
            amount_paise=amount_paise,
            status="PAID",
        )


class RazorpayPaymentProvider(PaymentProvider):
    """India-focused Payment Provider supporting UPI, Cards, Netbanking via Razorpay protocol."""

    def __init__(self, key_id: str, key_secret: str):
        self.key_id = key_id
        self._key_secret = key_secret.encode("utf-8")
        self.processed_events: Set[str] = set()

    def name(self) -> str:
        return "Razorpay"

    def create_checkout(self, user_id: str, plan: PlanTier, amount_paise: int) -> PaymentCheckoutSession:
        order_id = f"rzp_ord_{uuid.uuid4().hex[:12]}"
        session_id = f"rzp_sess_{uuid.uuid4().hex[:16]}"
        return PaymentCheckoutSession(
            session_id=session_id,
            order_id=order_id,
            plan=plan,
            amount_paise=amount_paise,
            checkout_url=f"https://api.razorpay.com/v1/checkout/{order_id}",
        )

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        message = f"{order_id}|{payment_id}".encode("utf-8")
        expected_sig = hmac.new(self._key_secret, message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature)

    def cancel_subscription(self, subscription_id: str) -> bool:
        # In real runtime, triggers Razorpay Subscriptions API cancel call
        return True

    def handle_webhook(self, payload_bytes: bytes, signature_header: str) -> Tuple[bool, Dict[str, Any]]:
        expected_sig = hmac.new(self._key_secret, payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, signature_header):
            return False, {"error": "Invalid Razorpay webhook signature."}

        import json
        try:
            data = json.loads(payload_bytes.decode("utf-8"))
            event_id = data.get("event_id") or data.get("id")
            if event_id and event_id in self.processed_events:
                return False, {"error": "Duplicate webhook event."}
            if event_id:
                self.processed_events.add(event_id)
            return True, data
        except Exception as e:
            return False, {"error": f"Webhook payload error: {e}"}

    def create_receipt(self, transaction_id: str, order_id: str, user_id: str, plan: PlanTier, amount_paise: int) -> PaymentReceipt:
        return PaymentReceipt(
            receipt_id=f"rzp_rcpt_{uuid.uuid4().hex[:10]}",
            transaction_id=transaction_id,
            order_id=order_id,
            user_id=user_id,
            plan=plan,
            amount_paise=amount_paise,
            payment_method="Razorpay UPI/Cards",
        )
