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
from typing import Any, Optional, Tuple

from sqlalchemy.exc import IntegrityError
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
    PlanTier.BASIC.value: 14900,        # ₹149/mo (Launch)
    PlanTier.PRO.value: 29900,          # ₹299/mo (Growth)
    PlanTier.PRO_PLUS.value: 59900,     # ₹599/mo (Scale)
    PlanTier.ANNUAL_PRO.value: 299900,  # ₹2,999/yr (Annual Plan)
    # Plan aliases
    "FREE": 0,
    "BASIC": 14900,
    "LAUNCH": 14900,
    "PRO": 29900,
    "GROWTH": 29900,
    "PRO_PLUS": 59900,
    "SCALE": 59900,
    "ANNUAL_PRO": 299900,
    "ANNUAL_PLAN": 299900,
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
                    "daily_minutes": 30,
                    "billing": "free",
                    "interval": "forever",
                    "allowance": "30 Min Talking / Day",
                    "monthly_credits": 0,
                    "daily_messages_limit": 15,
                    "device_limit": 1,
                    "tagline": "Try the product",
                    "description": "30 min daily talking free, refreshes after 12 AM local time, 15 daily AI messages.",
                    "badge": None,
                    "cta": "Download Starter",
                    "features": [
                        "30 min daily talking free (Male neural voice)",
                        "Resets daily after 12:00 AM (Country GMT / Local time)",
                        "15 daily AI assistant messages",
                        "1 active Windows device",
                        "Basic app launcher & file search",
                        "Community forum support",
                        "Zero credit card required",
                    ],
                },
                {
                    "tier": PlanTier.BASIC.value,
                    "name": "Launch",
                    "price_inr": 149,
                    "price_paise": 14900,
                    "billing": "monthly",
                    "interval": "month",
                    "allowance": "500 Credits / Month",
                    "monthly_credits": 500,
                    "device_limit": 1,
                    "tagline": "Getting started",
                    "description": "500 AI credits every month, Male voice, PC control & research.",
                    "badge": None,
                    "cta": "Get Launch",
                    "features": [
                        "500 AI credits every month",
                        "Male neural voice synthesis",
                        "1 active Windows device",
                        "PC control & file organizer",
                        "Autonomous web research agent",
                        "Standard email support",
                    ],
                },
                {
                    "tier": PlanTier.PRO.value,
                    "name": "Growth",
                    "price_inr": 299,
                    "price_paise": 29900,
                    "billing": "monthly",
                    "interval": "month",
                    "allowance": "1,500 Credits / Month",
                    "monthly_credits": 1500,
                    "device_limit": 2,
                    "tagline": "Growing business",
                    "description": "1,500 monthly AI credits, Dual voice, 2 devices, Office automation.",
                    "badge": "MOST POPULAR",
                    "cta": "Get Growth",
                    "features": [
                        "1,500 monthly AI credits",
                        "Dual voice switching (Male + Female)",
                        "2 active Windows devices",
                        "Advanced Knowledge Graph memory",
                        "Office Excel / Word automation",
                        "Priority email & Discord support",
                    ],
                },
                {
                    "tier": PlanTier.PRO_PLUS.value,
                    "name": "Scale",
                    "price_inr": 599,
                    "price_paise": 59900,
                    "billing": "monthly",
                    "interval": "month",
                    "allowance": "4,000 Credits / Month",
                    "monthly_credits": 4000,
                    "device_limit": 5,
                    "tagline": "Serious/professional users",
                    "description": "4,000 monthly credits, Full PC autonomy, Filmora & Shorts, 5 devices.",
                    "badge": "BEST VALUE",
                    "cta": "Get Scale",
                    "features": [
                        "4,000 monthly AI credits",
                        "Autonomous PC & mouse navigation",
                        "Filmora 14 Studio & FFmpeg pipeline",
                        "YouTube Shorts auto-publish",
                        "5 active devices + Team sharing",
                        "Developer MCP plugins & priority queue",
                    ],
                },
                {
                    "tier": PlanTier.ANNUAL_PRO.value,
                    "name": "Annual Plan",
                    "price_inr": 2999,
                    "price_paise": 299900,
                    "billing": "annual",
                    "interval": "year",
                    "allowance": "1,800 Credits / Month",
                    "monthly_credits": 1800,
                    "device_limit": 3,
                    "regular_annual_cost": 3588,
                    "annual_saving_inr": 589,
                    "annual_saving_pct": 16.4,
                    "effective_monthly_inr": 250,
                    "tagline": "Annual plan for users",
                    "description": "1,800 credits/mo, +500 welcome credits, Rollover, 3 PCs, Save ₹589/yr.",
                    "badge": "SAVE ₹589/YEAR + VIP BONUSES",
                    "cta": "Get Annual Plan (Save ₹589)",
                    "features": [
                        "1,800 Credits/mo (+300 bonus vs monthly Pro)",
                        "+500 Welcome Credits (Instant onboarding bonus)",
                        "Credit Rollover (Keep unused up to 2,000 cr)",
                        "3 Active PCs (+1 extra PC vs monthly Pro)",
                        "Deep Research Agent (Multi-source web synthesis)",
                        "Autonomous PC Hooks (Shell sandbox & mouse)",
                        "Dual Voice Switch (Male & Female neural voices)",
                        "1-on-1 VIP Support (Priority Discord & email)",
                    ],
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
        idempotency_key = f"pay_{payment_id}"

        # Record payment with unique idempotency key
        payment = PaymentDB(
            id=f"pay_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            provider="razorpay",
            order_id=order_id,
            payment_id=payment_id,
            idempotency_key=idempotency_key,
            amount_paise=amount_paise,
            plan=plan,
            status="VERIFIED",
            verified_at=now,
        )
        db.add(payment)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return True, f"Payment {payment_id} already verified (idempotent replay)."

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
        sub: Any = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
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

        if plan_norm == PlanTier.ANNUAL_PRO.value:
            sub.status = SubscriptionStatus.ACTIVE.value
            sub.started_at = now
            sub.expires_at = now + timedelta(days=365)
            sub.billing_interval = "annual"
            sub.device_limit = 3
        elif plan_norm == PlanTier.PRO_PLUS.value:
            sub.status = SubscriptionStatus.ACTIVE.value
            sub.started_at = now
            sub.expires_at = now + timedelta(days=30)
            sub.billing_interval = "monthly"
            sub.device_limit = 5
        elif plan_norm == PlanTier.PRO.value:
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
        credit_service.allocate_plan_credits(db, user_id, plan_norm, str(sub.billing_interval))

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
        sub: Any = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        if not sub:
            return PlanTier.STARTER.value, SubscriptionStatus.FREE.value

        if sub.status == SubscriptionStatus.LIFETIME_ACTIVE.value:
            return str(sub.plan), str(sub.status)

        if sub.expires_at and datetime.now(timezone.utc) > sub.expires_at:
            old_plan = str(sub.plan)
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

        return str(sub.plan), str(sub.status)
