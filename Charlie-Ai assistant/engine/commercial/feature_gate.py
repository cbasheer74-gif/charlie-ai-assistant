"""
engine/commercial/feature_gate.py — Authoritative Feature Gatekeeper and Backend Enforcer.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Optional

from .entitlement_manager import EntitlementManager
from .models import Entitlement, GateResult, GateStatus, PlanTier, SubscriptionStatus, UserAccount
from .plan_registry import PlanRegistry

logger = logging.getLogger("jarvis.commercial.feature_gate")


class FeatureGate:
    """Authoritative gatekeeper. All gated operations MUST pass through FeatureGate.

    UI buttons may reflect state, but backend gate guarantees security against tampering.
    """

    def __init__(
        self,
        entitlement_manager: EntitlementManager,
        plan_registry: PlanRegistry,
        daily_usage_checker: Optional[Callable[[UserAccount], bool]] = None,
        device_id: Optional[str] = None,
        entitlement_verifier: Optional[Any] = None,
        cached_entitlement_token: Optional[str] = None,
    ):
        self.entitlement_mgr = entitlement_manager
        self.registry = plan_registry
        self.daily_usage_checker = daily_usage_checker  # Returns True if Starter quota exhausted
        self.device_id = device_id
        self.entitlement_verifier = entitlement_verifier
        self.cached_entitlement_token = cached_entitlement_token

    def set_cached_token(self, token: str) -> None:
        """Update cached signed entitlement token."""
        self.cached_entitlement_token = token

    def can_use(
        self,
        account: Optional[UserAccount],
        entitlement: Entitlement,
        offline_mode: bool = False,
        offline_license_valid: bool = True,
    ) -> GateResult:
        """Evaluate if the user account is allowed to execute the given entitlement."""
        if account is None:
            return GateResult(
                status=GateStatus.ACCOUNT_REQUIRED,
                allowed=False,
                entitlement=entitlement,
                reason="User account is required for this operation.",
            )

        # Offline mode license validation
        if offline_mode and not offline_license_valid and account.plan != PlanTier.STARTER:
            return GateResult(
                status=GateStatus.OFFLINE_LICENSE_REQUIRED,
                allowed=False,
                entitlement=entitlement,
                reason="Valid signed offline license required when operating disconnected.",
            )

        # ── Server-Signed Entitlement Verification ───────────────────────
        # For paid plans, verify the signed entitlement token is valid and
        # bound to this device. This prevents:
        #   - Editing local plan field to fake an upgrade
        #   - Copying entitlement files to another PC
        #   - Tampering with local JSON to unlock features
        if account.plan != PlanTier.STARTER and self.entitlement_verifier and self.device_id and getattr(self, "strict_server_check", True):
            if not self.cached_entitlement_token:
                if account.subscription_status not in (
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.LIFETIME_ACTIVE,
                    SubscriptionStatus.GRACE_PERIOD,
                ):
                    return GateResult(
                        status=GateStatus.DEVICE_NOT_ACTIVATED,
                        allowed=False,
                        entitlement=entitlement,
                        reason="Device not activated. Login and activate to use paid features.",
                    )
            else:
                ok, reason, payload = self.entitlement_verifier.full_verify(
                    self.cached_entitlement_token, self.device_id
                )
            if not ok:
                if "mismatch" in reason.lower():
                    gate_status = GateStatus.DEVICE_MISMATCH
                elif "expired" in reason.lower():
                    gate_status = GateStatus.SUBSCRIPTION_EXPIRED
                else:
                    gate_status = GateStatus.ENTITLEMENT_INVALID
                return GateResult(
                    status=gate_status,
                    allowed=False,
                    entitlement=entitlement,
                    reason=reason,
                )

        # Check Starter daily active usage limit
        eff_plan = self.entitlement_mgr.get_effective_plan(account)
        if eff_plan == PlanTier.STARTER:
            if self.daily_usage_checker and self.daily_usage_checker(account):
                return GateResult(
                    status=GateStatus.LIMIT_REACHED,
                    allowed=False,
                    entitlement=entitlement,
                    required_plan=PlanTier.BASIC,
                    reason="Today's free CHARLIE time is complete. Upgrade for uninterrupted access.",
                )

        # Check Entitlement availability
        has_ent = self.entitlement_mgr.has_entitlement(account, entitlement)
        if not has_ent:
            req_plan = self.registry.get_required_plan_for_entitlement(entitlement)
            if account.subscription_status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED):
                status = GateStatus.SUBSCRIPTION_EXPIRED
                reason = f"Subscription expired. Renew to access {entitlement.value}."
            else:
                status = GateStatus.PLAN_REQUIRED
                reason = f"Feature '{entitlement.value}' requires {req_plan.value} plan or higher."

            return GateResult(
                status=status,
                allowed=False,
                entitlement=entitlement,
                required_plan=req_plan,
                reason=reason,
            )

        return GateResult(
            status=GateStatus.ALLOWED,
            allowed=True,
            entitlement=entitlement,
            required_plan=eff_plan,
            reason="Authorized.",
        )

    def guard(self, account: Optional[UserAccount], entitlement: Entitlement) -> None:
        """Raises PermissionError if feature cannot be used."""
        res = self.can_use(account, entitlement)
        if not res.allowed:
            raise PermissionError(f"[COMMERCIAL_GATE_REJECTED] {res.reason} (Status: {res.status.value})")


def gated_feature(gate: FeatureGate, get_account_fn: Callable[[], Optional[UserAccount]], entitlement: Entitlement):
    """Decorator to securely gate any function or tool execution."""
    def decorator(fn: Callable[..., Any]):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            account = get_account_fn()
            res = gate.can_use(account, entitlement)
            if not res.allowed:
                raise PermissionError(f"[GATE_LOCKED] {res.reason}")
            return fn(*args, **kwargs)
        return wrapper
    return decorator
