"""
engine/commercial/cloud_policy.py — Cloud AI Cost Protection, Token Quotas, and BYOK Decoupling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .models import CloudComputeMode, PlanTier, UserAccount
from .plan_registry import PlanRegistry

logger = logging.getLogger("jarvis.commercial.cloud_policy")


@dataclass
class CloudQuotaState:
    tokens_consumed: int = 0
    tokens_total_allowance: int = 50_000
    byok_active: bool = False
    byok_provider: Optional[str] = None


class QuotaManager:
    """Monitors and meters token/API cost consumption per user account."""

    def __init__(self, plan_registry: PlanRegistry):
        self.registry = plan_registry
        self._quotas: Dict[str, CloudQuotaState] = {}  # user_id -> quota

    def get_quota_state(self, user: UserAccount) -> CloudQuotaState:
        if user.user_id not in self._quotas:
            plan_def = self.registry.get_plan(user.plan)
            self._quotas[user.user_id] = CloudQuotaState(
                tokens_consumed=0,
                tokens_total_allowance=plan_def.cloud_fair_use_tokens,
                byok_active=False,
            )
        return self._quotas[user.user_id]

    def record_token_consumption(self, user: UserAccount, token_count: int) -> None:
        state = self.get_quota_state(user)
        if not state.byok_active:
            state.tokens_consumed += max(0, token_count)

    def is_cloud_quota_available(self, user: UserAccount, required_tokens: int = 100) -> bool:
        state = self.get_quota_state(user)
        if state.byok_active:
            return True  # User pays their own API provider directly
        return (state.tokens_consumed + required_tokens) <= state.tokens_total_allowance

    def set_byok(self, user: UserAccount, provider: str, active: bool = True) -> None:
        state = self.get_quota_state(user)
        state.byok_active = active
        state.byok_provider = provider if active else None


class CloudUsagePolicy:
    """Enforces cloud AI cost protection rules.

    Decouples permanent app feature entitlement (like Lifetime ₹999 or Advanced)
    from owner-funded cloud API token consumption.
    """

    def __init__(self, quota_manager: QuotaManager, credential_vault: Optional[Any] = None):
        self.quota_mgr = quota_manager
        self.vault = credential_vault

    def evaluate_model_execution_mode(
        self,
        user: UserAccount,
        requires_cloud_model: bool = False,
    ) -> Tuple[CloudComputeMode, str]:
        """Determines whether task should execute via Included Quota, BYOK, or Local AI."""
        state = self.quota_mgr.get_quota_state(user)

        # 1. User provided their own API key (BYOK)
        if state.byok_active:
            return CloudComputeMode.BYOK, f"Executing via user's private {state.byok_provider or 'cloud'} API key."

        # 2. Included quota is available
        if self.quota_mgr.is_cloud_quota_available(user):
            return CloudComputeMode.INCLUDED_QUOTA, "Executing via included monthly fair-use cloud quota."

        # 3. Quota exhausted: Fallback to Local AI or request BYOK
        if requires_cloud_model:
            return (
                CloudComputeMode.BYOK,
                "Included cloud AI quota exhausted. Please configure your own API key in Settings (BYOK) or upgrade plan.",
            )

        return CloudComputeMode.LOCAL_AI, "Cloud allowance exhausted. Seamlessly routed to offline local neural model."
