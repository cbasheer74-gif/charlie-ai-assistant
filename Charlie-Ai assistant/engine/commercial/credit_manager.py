"""
engine/commercial/credit_manager.py — Client-side Credit System & Operation Accounting.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .models import CreditTransaction, CreditWallet, PlanTier

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
CREDIT_CACHE_FILE = CONFIG_DIR / "credit_wallet.json"


# Configurable credit costs for operations
CREDIT_COSTS: Dict[str, int] = {
    "basic_text": 1,
    "chat_message": 1,
    "voice_request": 2,
    "web_search": 2,
    "document_summary": 3,
    "pdf_analysis": 5,
    "file_analysis": 5,
    "research_mode": 5,
    "premium_model": 8,
    "deep_research": 15,
    "automation_execution": 10,
    "filmora_render": 25,
    "multi_agent": 12,
}

# Add-on credit packs
CREDIT_PACKS: Dict[str, Dict[str, Any]] = {
    "STARTER_PACK": {
        "id": "credit_pack_500",
        "name": "Starter Credit Pack",
        "credits": 500,
        "price_inr": 99,
        "price_paise": 9900,
    },
    "POWER_PACK": {
        "id": "credit_pack_1200",
        "name": "Power Credit Pack",
        "credits": 1200,
        "price_inr": 199,
        "price_paise": 19900,
    },
    "PRO_PACK": {
        "id": "credit_pack_3000",
        "name": "Pro Credit Pack",
        "credits": 3000,
        "price_inr": 399,
        "price_paise": 39900,
    },
}


class CreditManager:
    """Manages local credit balances, checks allowances, and raises usage warnings."""

    def __init__(self, wallet_file: Path = CREDIT_CACHE_FILE):
        self.wallet_file = wallet_file
        self._wallet: CreditWallet = self._load_wallet()

    def _load_wallet(self) -> CreditWallet:
        if self.wallet_file.exists():
            try:
                data = json.loads(self.wallet_file.read_text(encoding="utf-8"))
                return CreditWallet(
                    user_id=data.get("user_id", "local_user"),
                    plan_tier=PlanTier(data.get("plan_tier", "STARTER")),
                    subscription_credits=data.get("subscription_credits", 0),
                    purchased_credits=data.get("purchased_credits", 0),
                    daily_messages_used=data.get("daily_messages_used", 0),
                    billing_cycle_start=datetime.fromisoformat(data["billing_cycle_start"]) if data.get("billing_cycle_start") else None,
                    billing_cycle_end=datetime.fromisoformat(data["billing_cycle_end"]) if data.get("billing_cycle_end") else None,
                    last_reset_at=datetime.fromisoformat(data["last_reset_at"]) if data.get("last_reset_at") else None,
                )
            except Exception:
                pass
        return CreditWallet(user_id="local_user", plan_tier=PlanTier.STARTER)

    def save_wallet(self) -> None:
        self.wallet_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "user_id": self._wallet.user_id,
            "plan_tier": self._wallet.plan_tier.value,
            "subscription_credits": self._wallet.subscription_credits,
            "purchased_credits": self._wallet.purchased_credits,
            "daily_messages_used": self._wallet.daily_messages_used,
            "billing_cycle_start": self._wallet.billing_cycle_start.isoformat() if self._wallet.billing_cycle_start else None,
            "billing_cycle_end": self._wallet.billing_cycle_end.isoformat() if self._wallet.billing_cycle_end else None,
            "last_reset_at": self._wallet.last_reset_at.isoformat() if self._wallet.last_reset_at else None,
        }
        self.wallet_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def create_wallet(self, user_id: str, plan_tier: PlanTier = PlanTier.STARTER) -> CreditWallet:
        wallet = CreditWallet(user_id=user_id, plan_tier=plan_tier)
        self._wallet = wallet
        return wallet

    def allocate_monthly_credits(self, wallet: CreditWallet, amount: int) -> None:
        wallet.subscription_credits = amount
        self.save_wallet()

    def deduct_credits(self, wallet: CreditWallet, amount: int, action: str = "general") -> Tuple[bool, Optional[str]]:
        if wallet.subscription_credits >= amount:
            wallet.subscription_credits -= amount
        else:
            rem = amount - wallet.subscription_credits
            wallet.subscription_credits = 0
            wallet.purchased_credits = max(0, wallet.purchased_credits - rem)
        self.save_wallet()
        return True, None

    @property
    def wallet(self) -> CreditWallet:
        return self._wallet

    def get_balance(self) -> Dict[str, Any]:
        return {
            "plan_tier": self._wallet.plan_tier.value,
            "subscription_credits": self._wallet.subscription_credits,
            "purchased_credits": self._wallet.purchased_credits,
            "total_credits": self._wallet.total_credits,
            "daily_messages_used": self._wallet.daily_messages_used,
        }

    def check_can_perform(self, action: str, default_cost: int = 1) -> Tuple[bool, str, int]:
        """Check if user has sufficient credits for an action."""
        cost = CREDIT_COSTS.get(action, default_cost)
        if self._wallet.plan_tier == PlanTier.STARTER:
            # Starter uses daily message count limit (15)
            if self._wallet.daily_messages_used >= 15:
                return False, "You've reached your daily free limit (15 messages/day). Upgrade to Basic or Pro for uninterrupted AI credits.", cost
            return True, "Allowed", cost

        # Paid tiers
        if self._wallet.total_credits < cost:
            return False, f"You've reached your monthly AI allowance. Action requires {cost} credits, balance is {self._wallet.total_credits}.", cost
        return True, "Allowed", cost

    def deduct(self, action: str, default_cost: int = 1) -> Tuple[bool, Optional[str]]:
        """Deduct credits in order: 1) subscription credits, 2) purchased credits."""
        cost = CREDIT_COSTS.get(action, default_cost)

        if self._wallet.plan_tier == PlanTier.STARTER:
            self._wallet.daily_messages_used += 1
            self.save_wallet()
            if self._wallet.daily_messages_used == 11:
                return True, "You've used 70% of your daily Starter messages."
            elif self._wallet.daily_messages_used == 14:
                return True, "You're almost out of daily Starter messages."
            elif self._wallet.daily_messages_used >= 15:
                return True, "You've reached your daily free allowance. Upgrade for unlimited credits."
            return True, None

        if self._wallet.total_credits < cost:
            return False, "Insufficient credits."

        # Order: 1. Subscription credits, 2. Purchased credits
        rem_cost = cost
        if self._wallet.subscription_credits >= rem_cost:
            self._wallet.subscription_credits -= rem_cost
            rem_cost = 0
        else:
            rem_cost -= self._wallet.subscription_credits
            self._wallet.subscription_credits = 0
            self._wallet.purchased_credits = max(0, self._wallet.purchased_credits - rem_cost)

        self.save_wallet()

        # Warning threshold check
        warning = self._check_warning()
        return True, warning

    def add_purchased_credits(self, amount: int) -> None:
        self._wallet.purchased_credits += amount
        self.save_wallet()

    def set_monthly_allowance(self, tier: PlanTier, allowance: int) -> None:
        self._wallet.plan_tier = tier
        self._wallet.subscription_credits = allowance
        self._wallet.daily_messages_used = 0
        self._wallet.last_reset_at = datetime.now(timezone.utc)
        self.save_wallet()

    def _check_warning(self) -> Optional[str]:
        tier = self._wallet.plan_tier
        allocations = {
            PlanTier.BASIC: 500,
            PlanTier.PRO: 1500,
            PlanTier.PRO_PLUS: 4000,
            PlanTier.ANNUAL_PRO: 1500,
        }
        total_alloc = allocations.get(tier, 0)
        if total_alloc == 0:
            return None

        used = max(0, total_alloc - self._wallet.subscription_credits)
        pct = (used / total_alloc) * 100.0

        if pct >= 100:
            return "You've reached your monthly AI allowance."
        elif pct >= 90:
            return "You're almost out of AI credits."
        elif pct >= 70:
            return "You've used 70% of your monthly AI credits."
        return None
