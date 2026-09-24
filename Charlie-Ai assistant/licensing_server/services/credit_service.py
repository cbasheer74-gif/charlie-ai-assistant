"""
licensing_server/services/credit_service.py — Server-side Credit Ledger, Consumption, & Cost Tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from licensing_server.database import (
    CreditTransactionDB,
    CreditWalletDB,
    PlanTier,
    SubscriptionDB,
    UsageEventDB,
)

# Standard action credit costs
ACTION_CREDIT_COSTS: Dict[str, int] = {
    "basic_text": 1,
    "voice_request": 2,
    "web_search": 2,
    "document_summary": 3,
    "pdf_analysis": 5,
    "file_analysis": 5,
    "research_mode": 5,
    "premium_model": 8,
    "deep_research": 15,
    "automation_execution": 10,
    "multi_agent": 12,
}

# Monthly allowances (Annual Pro resets monthly: 1500/mo, not 18k upfront)
MONTHLY_ALLOWANCES: Dict[str, int] = {
    PlanTier.STARTER.value: 0,
    PlanTier.BASIC.value: 500,
    PlanTier.PRO.value: 1500,
    PlanTier.PRO_PLUS.value: 4000,
    PlanTier.ANNUAL_PRO.value: 1500,
    PlanTier.LIFETIME.value: 2000,
}

# Provider cost estimation per 1k tokens in INR (~₹86/USD)
PROVIDER_COST_PER_1K_INR: Dict[str, float] = {
    "low_cost": 0.02,    # e.g. Gemini Flash / Haiku
    "standard": 0.15,    # e.g. GPT-4o-mini
    "premium": 1.20,     # e.g. Claude 3.5 Sonnet / GPT-4o
    "deep_research": 4.50,
}


class CreditService:
    """Authoritative server-side credit balance, transaction logging, and usage accounting."""

    def get_or_create_wallet(self, db: Session, user_id: str, plan_tier: str = PlanTier.STARTER.value) -> CreditWalletDB:
        wallet = db.query(CreditWalletDB).filter(CreditWalletDB.user_id == user_id).first()
        now = datetime.now(timezone.utc)
        if not wallet:
            initial_allowance = MONTHLY_ALLOWANCES.get(plan_tier, 0)
            wallet = CreditWalletDB(
                id=f"wal_{uuid.uuid4().hex[:16]}",
                user_id=user_id,
                plan_tier=plan_tier,
                subscription_credits=initial_allowance,
                purchased_credits=0,
                credits_used=0,
                daily_messages_used=0,
                billing_cycle_start=now,
                billing_cycle_end=now + timedelta(days=30),
                last_reset_at=now,
            )
            db.add(wallet)
            db.commit()
            db.refresh(wallet)
        else:
            self._check_and_apply_reset(db, wallet)
        return wallet

    def _check_and_apply_reset(self, db: Session, wallet: CreditWalletDB) -> None:
        """Reset monthly subscription credits if period expired."""
        now = datetime.now(timezone.utc)
        if wallet.billing_cycle_end and now >= wallet.billing_cycle_end:
            allowance = MONTHLY_ALLOWANCES.get(wallet.plan_tier, 0)
            wallet.subscription_credits = allowance
            wallet.daily_messages_used = 0
            wallet.billing_cycle_start = now
            wallet.billing_cycle_end = now + timedelta(days=30)
            wallet.last_reset_at = now

            tx = CreditTransactionDB(
                id=f"tx_{uuid.uuid4().hex[:16]}",
                user_id=wallet.user_id,
                type="RESET",
                amount=allowance,
                source="monthly_cycle_reset",
                created_at=now,
            )
            db.add(tx)
            db.commit()

    def deduct_credits(
        self,
        db: Session,
        user_id: str,
        feature: str,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        custom_cost: Optional[int] = None,
    ) -> Tuple[bool, str, int]:
        """Atomically deduct credits with consumption order: 1) subscription, 2) purchased."""
        wallet = self.get_or_create_wallet(db, user_id)
        cost = custom_cost if custom_cost is not None else ACTION_CREDIT_COSTS.get(feature, 1)

        # Starter tier checks daily message limit (15)
        if wallet.plan_tier == PlanTier.STARTER.value:
            if wallet.daily_messages_used >= 15:
                return False, "You've reached your daily free allowance (15 messages/day). Upgrade for AI credits.", cost
            wallet.daily_messages_used += 1
            db.commit()
            return True, "Starter message recorded", cost

        total_credits = (wallet.subscription_credits or 0) + (wallet.purchased_credits or 0)
        if total_credits < cost:
            return False, f"Insufficient AI credits. Needed: {cost}, Available: {total_credits}", cost

        # Deduct in strict order: subscription credits first, then purchased credits
        rem_cost = cost
        if wallet.subscription_credits >= rem_cost:
            wallet.subscription_credits -= rem_cost
            rem_cost = 0
        else:
            rem_cost -= wallet.subscription_credits
            wallet.subscription_credits = 0
            wallet.purchased_credits = max(0, wallet.purchased_credits - rem_cost)

        wallet.credits_used = (wallet.credits_used or 0) + cost

        now = datetime.now(timezone.utc)

        # Record transaction
        tx = CreditTransactionDB(
            id=f"tx_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            type="USAGE",
            amount=-cost,
            source=f"operation:{feature}",
            created_at=now,
        )
        db.add(tx)

        # Record usage & cost tracking
        token_count = input_tokens + output_tokens
        rate_key = "premium" if "deep" in feature or "gpt-4" in (model or "") else ("low_cost" if "flash" in (model or "") else "standard")
        estimated_cost = (token_count / 1000.0) * PROVIDER_COST_PER_1K_INR.get(rate_key, 0.15)

        usage = UsageEventDB(
            id=f"use_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            feature=feature,
            model=model,
            provider=provider or "cloud",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            credits_used=cost,
            estimated_provider_cost=round(estimated_cost, 4),
            created_at=now,
        )
        db.add(usage)
        db.commit()

        return True, "Credits deducted successfully", cost

    def allocate_plan_credits(
        self,
        db: Session,
        user_id: str,
        plan_tier: str,
        billing_interval: str = "monthly",
    ) -> None:
        """Assign monthly credit allowance to user wallet."""
        wallet = self.get_or_create_wallet(db, user_id, plan_tier)
        allowance = MONTHLY_ALLOWANCES.get(plan_tier, 0)
        now = datetime.now(timezone.utc)

        wallet.plan_tier = plan_tier
        wallet.subscription_credits = allowance
        wallet.daily_messages_used = 0
        wallet.billing_cycle_start = now
        wallet.billing_cycle_end = now + timedelta(days=30)
        wallet.last_reset_at = now

        tx = CreditTransactionDB(
            id=f"tx_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            type="RESET",
            amount=allowance,
            source=f"plan_activation:{plan_tier}",
            created_at=now,
        )
        db.add(tx)
        db.commit()

    def add_purchased_credits(
        self,
        db: Session,
        user_id: str,
        amount: int,
        pack_id: str,
        payment_id: str,
    ) -> None:
        """Add purchased credits (never expire) upon payment confirmation."""
        wallet = self.get_or_create_wallet(db, user_id)
        wallet.purchased_credits = (wallet.purchased_credits or 0) + amount
        now = datetime.now(timezone.utc)

        tx = CreditTransactionDB(
            id=f"tx_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            type="PURCHASE",
            amount=amount,
            source=pack_id,
            reference_id=payment_id,
            created_at=now,
        )
        db.add(tx)
        db.commit()
