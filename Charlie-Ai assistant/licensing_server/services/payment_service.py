"""
licensing_server/services/payment_service.py — Payment webhook verification and subscription activation.

Payment truth lives HERE, not on the desktop. Desktop cannot fake payment status.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from licensing_server.config import config
from licensing_server.database import (
    LicenseEventDB,
    LicenseEventType,
    PaymentDB,
    PlanTier,
    SubscriptionDB,
    SubscriptionStatus,
)

# Plan prices (paise)
PLAN_PRICES = {
    PlanTier.BASIC.value: 9900,         # ₹99/mo (base tier)
    PlanTier.PREMIUM.value: 19900,      # ₹199/mo
    PlanTier.ADVANCED.value: 29900,     # ₹299/mo
    PlanTier.LIFETIME.value: 99900,     # ₹999 one-time
    PlanTier.PRO.value: 29900,          # ₹299/mo
    PlanTier.PRO_PLUS.value: 59900,     # ₹599/mo
    PlanTier.ANNUAL_PRO.value: 299900,  # ₹2,999/yr
    # Backward compatibility aliases
    "PREMIUM": 19900,
    "ADVANCED": 29900,
    # Credit pack add-ons
    "STARTER_PACK": 9900,   # ₹99 for 500 credits
    "POWER_PACK": 19900,    # ₹199 for 1,200 credits
    "PRO_PACK": 39900,      # ₹399 for 3,000 credits
}

CREDIT_PACK_AMOUNTS = {
    "STARTER_PACK": 500,
    "POWER_PACK": 1200,
    "PRO_PACK": 3000,
}


class PaymentService:
    """Verifies payment webhooks and activates subscriptions server-side."""

    def get_plan_registry(self) -> dict:
        """Return centralized authoritative plan catalog and feature metadata."""
        from licensing_server.services.license_service import PLAN_FEATURES
        from engine.commercial.plan_registry import PlanRegistry
        savings = PlanRegistry.calculate_annual_savings(299, 2999)

        return {
            "currency": "INR",
            "plans": [
                {
                    "tier": PlanTier.STARTER.value,
                    "name": "Starter",
                    "price_inr": 0,
                    "price_paise": 0,
                    "daily_minutes": 10,
                    "billing": "free",
                    "interval": "forever",
                    "monthly_credits": 0,
                    "daily_messages_limit": 15,
                    "device_limit": 1,
                    "description": "Try CHARLIE. 15 AI messages per day.",
                    "badge": None,
                    "cta": "Start Free",
                    "features": PLAN_FEATURES.get(PlanTier.STARTER.value, []),
                },
                {
                    "tier": PlanTier.BASIC.value,
                    "name": "Basic",
                    "price_inr": 99,
                    "price_paise": 9900,
                    "billing": "monthly",
                    "interval": "month",
                    "monthly_credits": 500,
                    "device_limit": 1,
                    "description": "For everyday use. 500 AI credits per month.",
                    "badge": None,
                    "cta": "Get Basic",
                    "features": PLAN_FEATURES.get(PlanTier.BASIC.value, []),
                },
                {
                    "tier": PlanTier.PREMIUM.value,
                    "name": "Premium",
                    "price_inr": 199,
                    "price_paise": 19900,
                    "billing": "monthly",
                    "interval": "month",
                    "monthly_credits": 1500,
                    "device_limit": 2,
                    "description": "Dual voice, deep research, coding & 2 devices.",
                    "badge": "MOST POPULAR",
                    "cta": "Get Premium",
                    "features": PLAN_FEATURES.get(PlanTier.PREMIUM.value, []),
                },
                {
                    "tier": PlanTier.ADVANCED.value,
                    "name": "Advanced",
                    "price_inr": 299,
                    "price_paise": 29900,
                    "billing": "monthly",
                    "interval": "month",
                    "monthly_credits": 4000,
                    "device_limit": 5,
                    "description": "Power users & creators. Autonomous PC & 5 devices.",
                    "badge": "FULL POWER",
                    "cta": "Get Advanced",
                    "features": PLAN_FEATURES.get(PlanTier.ADVANCED.value, []),
                },
                {
                    "tier": PlanTier.LIFETIME.value,
                    "name": "Lifetime",
                    "price_inr": 999,
                    "price_paise": 99900,
                    "billing": "one_time",
                    "interval": "lifetime",
                    "monthly_credits": 2000,
                    "device_limit": 1,
                    "description": "Lifetime access to all features.",
                    "badge": "BEST LONG-TERM VALUE",
                    "cta": "Get Lifetime",
                    "features": PLAN_FEATURES.get(PlanTier.LIFETIME.value, []),
                },
            ],
            "credit_packs": [
                {"id": "STARTER_PACK", "name": "Starter Credit Pack", "credits": 500, "price_inr": 99},
                {"id": "POWER_PACK", "name": "Power Credit Pack", "credits": 1200, "price_inr": 199},
                {"id": "PRO_PACK", "name": "Pro Credit Pack", "credits": 3000, "price_inr": 399},
            ],
            "currency": "INR",
        }

    def create_order(
        self,
        db: Session,
        user_id: str,
        plan: str,
        client_amount: Optional[int] = None,
    ) -> Tuple[bool, str, Optional[dict]]:
        """Create order server-side with strict price-authority verification."""
        plan_upper = plan.upper().strip()
        if plan_upper == PlanTier.STARTER.value:
            return False, "Starter plan is free. No checkout required.", None

        if plan_upper not in PLAN_PRICES:
            return False, f"Invalid plan: {plan}.", None

        expected_amount = PLAN_PRICES[plan_upper]

        # Security check: Server-side pricing authority. Reject price tampering.
        if client_amount is not None and client_amount != expected_amount:
            event = LicenseEventDB(
                id=f"evt_{uuid.uuid4().hex[:16]}",
                user_id=user_id,
                event_type=LicenseEventType.TAMPER_DETECTED.value,
                details_json=json.dumps({
                    "action": "PRICE_TAMPERING_REJECTED",
                    "plan": plan_upper,
                    "client_amount": client_amount,
                    "expected_amount": expected_amount,
                }),
            )
            db.add(event)
            db.commit()
            return False, "Price mismatch: Server-side price authority enforced. Tampering rejected.", None

        order_id = f"order_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)

        payment = PaymentDB(
            id=f"pay_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            provider="razorpay",
            order_id=order_id,
            amount_paise=expected_amount,
            plan=plan_upper,
            status="PENDING",
            created_at=now,
        )
        db.add(payment)
        db.commit()

        return True, "Order created successfully.", {
            "order_id": order_id,
            "amount_paise": expected_amount,
            "amount_inr": expected_amount // 100,
            "currency": "INR",
            "plan": plan_upper,
            "key_id": config.RAZORPAY_KEY_ID or "rzp_test_public_key",
        }

    def verify_razorpay_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        """Verify Razorpay payment signature using server-side secret."""
        if not config.RAZORPAY_KEY_SECRET:
            return False
        message = f"{order_id}|{payment_id}".encode("utf-8")
        expected = hmac.new(

            config.RAZORPAY_KEY_SECRET.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_razorpay_webhook(self, payload_bytes: bytes, signature_header: str) -> Tuple[bool, dict]:
        """Verify Razorpay webhook HMAC."""
        if not config.RAZORPAY_WEBHOOK_SECRET:
            return False, {"error": "Webhook secret not configured."}
        expected = hmac.new(
            config.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature_header):
            return False, {"error": "Invalid webhook signature."}
        try:
            return True, json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            return False, {"error": f"Payload parse error: {e}"}

    def activate_subscription(
        self,
        db: Session,
        user_id: str,
        plan: str,
        order_id: str,
        payment_id: str,
        amount_paise: int,
    ) -> Tuple[bool, str]:
        # Idempotency check: reject replayed webhooks without duplicate charging or revenue duplication
        existing_payment = db.query(PaymentDB).filter(
            PaymentDB.payment_id == payment_id, PaymentDB.status == "VERIFIED"
        ).first()
        if existing_payment:
            return True, f"Payment {payment_id} already verified (idempotent replay)."

        now = datetime.now(timezone.utc)

        # Record payment
        payment = PaymentDB(
            id=f"pay_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            provider="razorpay",
            order_id=order_id,
            payment_id=payment_id,
            amount_paise=amount_paise,
            plan=plan,
            status="VERIFIED",
            verified_at=now,
        )
        db.add(payment)

        from licensing_server.services.credit_service import CreditService
        credit_service = CreditService()

        # Handle one-time credit pack purchase
        if plan in CREDIT_PACK_AMOUNTS:
            pack_credits = CREDIT_PACK_AMOUNTS[plan]
            credit_service.add_purchased_credits(db, user_id, pack_credits, plan, payment_id)
            db.commit()
            return True, f"Successfully purchased {pack_credits} credits."

        # Normalize plan aliases
        plan_norm = plan

        # Update subscription
        sub = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        if not sub:
            sub = SubscriptionDB(
                id=f"sub_{uuid.uuid4().hex[:16]}",
                user_id=user_id,
                plan=plan_norm,
                status=SubscriptionStatus.ACTIVE.value,
            )
            db.add(sub)

        sub.plan = plan_norm
        sub.payment_reference = payment_id

        if plan_norm == PlanTier.LIFETIME.value:
            sub.status = SubscriptionStatus.LIFETIME_ACTIVE.value
            sub.legacy_lifetime = True
            sub.expires_at = None
            sub.billing_interval = "once"
            sub.device_limit = 1
        elif plan_norm == PlanTier.ANNUAL_PRO.value:
            sub.status = SubscriptionStatus.ACTIVE.value
            sub.started_at = now
            sub.expires_at = now + timedelta(days=365)
            sub.billing_interval = "annual"
            sub.device_limit = 2
        elif plan_norm in (PlanTier.PRO_PLUS.value, PlanTier.ADVANCED.value):
            sub.status = SubscriptionStatus.ACTIVE.value
            sub.started_at = now
            sub.expires_at = now + timedelta(days=30)
            sub.billing_interval = "monthly"
            sub.device_limit = 5
        elif plan_norm in (PlanTier.PRO.value, PlanTier.PREMIUM.value):
            sub.status = SubscriptionStatus.ACTIVE.value
            sub.started_at = now
            sub.expires_at = now + timedelta(days=30)
            sub.billing_interval = "monthly"
            sub.device_limit = 2
        else:
            sub.status = SubscriptionStatus.ACTIVE.value
            sub.started_at = now
            sub.expires_at = now + timedelta(days=30)
            sub.billing_interval = "monthly"
            sub.device_limit = 1

        # Allocate monthly credit allowance in credit wallet
        credit_service.allocate_plan_credits(db, user_id, plan_norm, sub.billing_interval)

        db.commit()

        # Audit
        event = LicenseEventDB(
            id=f"evt_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            event_type=LicenseEventType.PAYMENT_VERIFIED.value,
            details_json=json.dumps({"plan": plan, "payment_id": payment_id, "amount": amount_paise}),
        )
        db.add(event)
        db.commit()

        return True, f"Subscription activated: {plan}."

    def check_subscription_expiry(self, db: Session, user_id: str) -> Tuple[str, str]:
        """Check and handle subscription expiry. Returns (plan, status)."""
        sub = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        if not sub:
            return PlanTier.STARTER.value, SubscriptionStatus.FREE.value

        if sub.status == SubscriptionStatus.LIFETIME_ACTIVE.value:
            return sub.plan, sub.status

        if sub.expires_at and datetime.now(timezone.utc) > sub.expires_at:
            old_plan = sub.plan
            sub.plan = PlanTier.STARTER.value
            sub.status = SubscriptionStatus.EXPIRED.value

            event = LicenseEventDB(
                id=f"evt_{uuid.uuid4().hex[:16]}",
                user_id=user_id,
                event_type=LicenseEventType.SUBSCRIPTION_CHANGED.value,
                details_json=json.dumps({"from": old_plan, "to": PlanTier.STARTER.value, "reason": "expired"}),
            )
            db.add(event)
            db.commit()

        return sub.plan, sub.status
