"""
engine/commercial/entitlement_manager.py — Resolves Effective Entitlements for User Accounts.
"""

from __future__ import annotations

from typing import Set

from .models import Entitlement, PlanTier, SubscriptionStatus, UserAccount
from .plan_registry import PlanRegistry


class EntitlementManager:
    """Computes active entitlements based on user subscription state, grace periods, and tier."""

    def __init__(self, plan_registry: PlanRegistry):
        self.registry = plan_registry

    def get_effective_plan(self, account: UserAccount) -> PlanTier:
        """Determines effective plan tier based on subscription status."""
        status = account.subscription_status

        # Active or Lifetime
        if status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.LIFETIME_ACTIVE):
            return account.plan

        # In grace period or pending cancel at period end -> still retain paid features
        if status in (SubscriptionStatus.GRACE_PERIOD, SubscriptionStatus.CANCEL_AT_PERIOD_END):
            return account.plan

        # If account has paid plan tier specified and status is not explicitly expired/cancelled/past_due/suspended:
        if account.plan != PlanTier.STARTER and status not in (
            SubscriptionStatus.EXPIRED,
            SubscriptionStatus.CANCELLED,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.FREE,
        ):
            return account.plan

        # Expired, Suspended, Past Due without grace, or Free -> Fall back to Starter
        return PlanTier.STARTER

    def get_user_entitlements(self, account: UserAccount) -> Set[Entitlement]:
        """Returns the complete set of active entitlements currently available to the user."""
        eff_plan = self.get_effective_plan(account)
        plan_def = self.registry.get_plan(eff_plan)
        return set(plan_def.entitlements)

    def has_entitlement(self, account: UserAccount, entitlement: Entitlement) -> bool:
        """Fast check whether user is entitled to a specific capability."""
        return entitlement in self.get_user_entitlements(account)
