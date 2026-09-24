"""
engine/commercial/billing_manager.py — Subscription Lifecycle, Upgrades, Safe Downgrades, and Audit Logging.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .license_manager import OfflineLicenseManager
from .models import PaymentReceipt, PlanTier, SubscriptionStatus, UserAccount
from .payment_provider import PaymentProvider
from .plan_registry import PlanRegistry

logger = logging.getLogger("jarvis.commercial.billing")


class GracePeriodManager:
    """Manages temporary grace period for transient payment failures."""

    DEFAULT_GRACE_DAYS = 3

    def __init__(self, grace_days: int = DEFAULT_GRACE_DAYS):
        self.grace_days = grace_days

    def activate_grace_period(self, user: UserAccount) -> None:
        user.subscription_status = SubscriptionStatus.GRACE_PERIOD
        logger.warning("Activated %d-day grace period for user %s", self.grace_days, user.user_id)

    def is_grace_expired(self, user: UserAccount) -> bool:
        if user.subscription_status != SubscriptionStatus.GRACE_PERIOD:
            return False
        if not user.current_period_end:
            return True
        grace_end = user.current_period_end + timedelta(days=self.grace_days)
        return datetime.now(timezone.utc) > grace_end


class ReceiptManager:
    """Stores and retrieves transaction receipts. Never stores payment credentials/CVVs."""

    def __init__(self):
        self._receipts: Dict[str, List[PaymentReceipt]] = {}  # user_id -> receipts

    def record_receipt(self, receipt: PaymentReceipt) -> None:
        if receipt.user_id not in self._receipts:
            self._receipts[receipt.user_id] = []
        self._receipts[receipt.user_id].append(receipt)

    def get_user_receipts(self, user_id: str) -> List[PaymentReceipt]:
        return list(self._receipts.get(user_id, []))


class BillingAuditManager:
    """Records security-compliant billing audit events through SecurityCore without leaking secrets."""

    def __init__(self, audit_engine: Optional[Any] = None):
        self.audit_engine = audit_engine

    def record_billing_event(self, action: str, user_id: str, plan: str, details: str, status: str = "SUCCESS") -> None:
        safe_details = details.replace("secret", "[REDACTED]").replace("key", "[REDACTED]")
        logger.info("[BILLING_AUDIT] %s | User: %s | Plan: %s | Status: %s | %s", action, user_id, plan, status, safe_details)
        if self.audit_engine and hasattr(self.audit_engine, "record_event"):
            try:
                self.audit_engine.record_event(
                    origin="COMMERCIAL_BILLING",
                    agent_name="BillingManager",
                    tool_name="SubscriptionLifecycle",
                    action=action,
                    target=user_id,
                    risk_level="SYSTEM_CHANGE",
                    policy_decision=status,
                )
            except Exception as e:
                logger.error("AuditEngine recording failed: %s", e)


class BillingManager:
    """Master controller coordinating payment checkout, verification, upgrades, and cancellations."""

    def __init__(
        self,
        plan_registry: PlanRegistry,
        payment_provider: PaymentProvider,
        offline_license_mgr: Optional[OfflineLicenseManager] = None,
        audit_manager: Optional[BillingAuditManager] = None,
    ):
        self.registry = plan_registry
        self.payment_provider = payment_provider
        self.license_mgr = offline_license_mgr
        self.grace_mgr = GracePeriodManager()
        self.receipt_mgr = ReceiptManager()
        self.audit_mgr = audit_manager or BillingAuditManager()

    def initiate_checkout(self, user: UserAccount, target_tier: PlanTier) -> Any:
        """Creates payment checkout session for selected plan."""
        plan_def = self.registry.get_plan(target_tier)
        amount_paise = plan_def.price_inr * 100
        session = self.payment_provider.create_checkout(user.user_id, target_tier, amount_paise)
        self.audit_mgr.record_billing_event("CHECKOUT_INITIATED", user.user_id, target_tier.value, f"Session: {session.session_id}")
        return session

    def verify_and_activate_purchase(
        self,
        user: UserAccount,
        target_tier: PlanTier,
        order_id: str,
        payment_id: str,
        signature: str,
        device_id: str = "local_device",
    ) -> Tuple[bool, str]:
        """Cryptographically verifies payment with provider before activating plan entitlement."""
        verified = self.payment_provider.verify_payment(order_id, payment_id, signature)
        if not verified:
            self.audit_mgr.record_billing_event("PAYMENT_VERIFICATION_FAILED", user.user_id, target_tier.value, f"Order: {order_id}", "DENY")
            return False, "Payment verification failed. Invalid gateway signature."

        plan_def = self.registry.get_plan(target_tier)
        user.plan = target_tier
        now = datetime.now(timezone.utc)

        if target_tier == PlanTier.LIFETIME:
            user.subscription_status = SubscriptionStatus.LIFETIME_ACTIVE
            user.current_period_end = None
            user.cancel_at_period_end = False
        else:
            user.subscription_status = SubscriptionStatus.ACTIVE
            user.current_period_end = now + timedelta(days=30)
            user.cancel_at_period_end = False

        user.last_entitlement_sync = now

        # Generate receipt
        receipt = self.payment_provider.create_receipt(
            transaction_id=payment_id,
            order_id=order_id,
            user_id=user.user_id,
            plan=target_tier,
            amount_paise=plan_def.price_inr * 100,
        )
        self.receipt_mgr.record_receipt(receipt)

        # Issue signed offline license
        if self.license_mgr:
            features = [e.value for e in plan_def.entitlements]
            val_days = 3650 if target_tier == PlanTier.LIFETIME else 45
            self.license_mgr.sign_license(user.user_id, target_tier, features, device_id, validity_days=val_days)

        self.audit_mgr.record_billing_event("PLAN_ACTIVATED", user.user_id, target_tier.value, f"Txn: {payment_id}")
        return True, f"Successfully activated {target_tier.value} plan."

    def cancel_subscription(self, user: UserAccount) -> Tuple[bool, str]:
        """Schedules recurring subscription cancellation at end of current paid period."""
        if user.plan in (PlanTier.STARTER, PlanTier.LIFETIME):
            return False, f"Cannot cancel {user.plan.value} plan."

        user.cancel_at_period_end = True
        user.subscription_status = SubscriptionStatus.CANCEL_AT_PERIOD_END
        self.audit_mgr.record_billing_event("SUBSCRIPTION_CANCEL_REQUESTED", user.user_id, user.plan.value, "Will cancel at period end.")
        return True, "Subscription will cancel at the end of the current billing cycle. Data remains intact."

    def process_period_end_expiry(self, user: UserAccount) -> None:
        """Downgrades expired accounts to Starter without touching any user data or files."""
        if user.subscription_status == SubscriptionStatus.LIFETIME_ACTIVE:
            return

        now = datetime.now(timezone.utc)
        if user.current_period_end and now > user.current_period_end:
            old_plan = user.plan
            user.plan = PlanTier.STARTER
            user.subscription_status = SubscriptionStatus.EXPIRED
            user.cancel_at_period_end = False
            self.audit_mgr.record_billing_event("PLAN_EXPIRED_DOWNGRADE", user.user_id, old_plan.value, "Switched to Starter. User data preserved.")
