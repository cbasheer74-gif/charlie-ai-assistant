"""
engine/commercial/core.py — CommercialEngine: Central Authority for Commercial Monetization.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .billing_manager import BillingAuditManager, BillingManager, ReceiptManager
from .cloud_policy import CloudUsagePolicy, QuotaManager
from .device_identity import DeviceIdentityManager
from .entitlement_manager import EntitlementManager
from .entitlement_verifier import EntitlementVerifier
from .feature_gate import FeatureGate
from .license_manager import DeviceLicenseManager, OfflineLicenseManager
from .licensing_client import LicensingClient
from .models import (
    Entitlement,
    GateResult,
    GateStatus,
    PlanTier,
    SubscriptionStatus,
    UsageState,
    UserAccount,
)
from .credit_manager import CreditManager
from .payment_provider import MockPaymentProvider, PaymentProvider
from .paywall_manager import PaywallManager, PricingUIManager
from .plan_registry import PlanRegistry
from .usage_meter import DailyUsageMeter

logger = logging.getLogger("jarvis.commercial.core")

_GLOBAL_COMMERCIAL_ENGINE: Optional[CommercialEngine] = None


class CommercialEngine:
    """Master coordinating runtime for Commercial Monetization, Licensing, Pricing, and Entitlements.

    Integrates with SecurityCore, CredentialVault, ModelRouter, Voice Engine, and UI.
    Server-side licensing is the AUTHORITY. Local plan field is a cache, not the truth.
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        payment_provider: Optional[PaymentProvider] = None,
        server_url: Optional[str] = None,
        audit_engine: Optional[Any] = None,
        signing_secret: Optional[str] = None,
    ):
        self.base_dir = Path(base_dir) if base_dir else (Path.home() / ".jarvis" / "commercial")
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.account_file = self.base_dir / "user_account.json"
        self._entitlement_cache_file = self.base_dir / "signed_entitlement.token"

        # 1. Plan Catalog & Entitlements
        self.plan_registry = PlanRegistry()
        self.entitlement_mgr = EntitlementManager(self.plan_registry)

        # 2. Device Identity (privacy-safe)
        self.device_identity = DeviceIdentityManager(data_dir=self.base_dir / "identity")
        self._device_id = self.device_identity.get_device_id()

        # 3. Entitlement Verifier (RSA public key)
        self.entitlement_verifier = EntitlementVerifier()

        # 4. Licensing Client (HTTPS → server)
        self.licensing_client = LicensingClient(
            server_url=server_url,
            data_dir=self.base_dir / "licensing",
        )

        # 5. Licensing (local cache — NOT the authority)
        self.offline_license_mgr = OfflineLicenseManager(
            storage_path=self.base_dir / "license.json",
            secret=signing_secret,
        )
        self.device_mgr = DeviceLicenseManager(
            plan_registry=self.plan_registry,
            storage_path=self.base_dir / "devices.json",
        )

        # 6. Usage Metering
        self.usage_meter = DailyUsageMeter(
            storage_path=self.base_dir / "daily_usage.json",
            daily_limit_sec=600,  # 10 minutes
        )

        # 7. Load cached entitlement token
        self._cached_entitlement_token: Optional[str] = self._load_cached_entitlement_token()

        # 8. Feature Gate (with server-authority verification)
        self.feature_gate = FeatureGate(
            entitlement_manager=self.entitlement_mgr,
            plan_registry=self.plan_registry,
            daily_usage_checker=lambda acc: self.usage_meter.is_exhausted(),
            device_id=self._device_id,
            entitlement_verifier=self.entitlement_verifier,
            cached_entitlement_token=self._cached_entitlement_token,
        )
        if not server_url or signing_secret:
            self.feature_gate.strict_server_check = False

        # 9. Cloud Quotas & Cost Protection
        self.quota_mgr = QuotaManager(self.plan_registry)
        self.cloud_policy = CloudUsagePolicy(self.quota_mgr)

        # 10. Payment & Billing
        self.payment_provider = payment_provider or MockPaymentProvider()
        self.audit_mgr = BillingAuditManager(audit_engine=audit_engine)
        self.billing_mgr = BillingManager(
            plan_registry=self.plan_registry,
            payment_provider=self.payment_provider,
            offline_license_mgr=self.offline_license_mgr,
            audit_manager=self.audit_mgr,
        )

        # 11. Paywall & Pricing Presentation
        self.paywall_mgr = PaywallManager(self.plan_registry)
        self.pricing_ui_mgr = PricingUIManager(self.plan_registry)

        # 12. Credit Accounting & Wallet Manager
        self.credit_mgr = CreditManager()

        # Active Session Account
        self._current_account: UserAccount = self._load_or_create_account()
        if not self._current_account.credit_wallet:
            self._current_account.credit_wallet = self.credit_mgr.wallet

    # ---------------------------------------------------------------------------
    # Account Management
    # ---------------------------------------------------------------------------

    def _load_or_create_account(self) -> UserAccount:
        if self.account_file.exists():
            try:
                data = json.loads(self.account_file.read_text(encoding="utf-8"))
                account = UserAccount(
                    user_id=data["user_id"],
                    display_name=data.get("display_name", "JARVIS User"),
                    email=data.get("email", "user@jarvis.local"),
                    plan=PlanTier(data.get("plan", PlanTier.STARTER.value)),
                    subscription_status=SubscriptionStatus(data.get("subscription_status", SubscriptionStatus.FREE.value)),
                    billing_customer_id=data.get("billing_customer_id"),
                    cancel_at_period_end=data.get("cancel_at_period_end", False),
                    activated_devices=data.get("activated_devices", []),
                )
                # Older desktop builds stored a purchased Lifetime plan as the
                # generic ACTIVE state.  Normalise that legacy value so the
                # permanent plan keeps its offline voice access after restart.
                if (account.plan == PlanTier.LIFETIME
                        and account.subscription_status == SubscriptionStatus.ACTIVE):
                    account.subscription_status = SubscriptionStatus.LIFETIME_ACTIVE
                    self.save_account(account)
                return account
            except Exception as e:
                logger.error("Failed to load user account: %s", e)

        # Default new installation: automatically assign STARTER
        default_account = UserAccount(
            user_id="usr_default_local",
            display_name="JARVIS User",
            email="user@jarvis.local",
            plan=PlanTier.STARTER,
            subscription_status=SubscriptionStatus.FREE,
        )
        self.save_account(default_account)
        return default_account

    def get_account(self) -> UserAccount:
        return self._current_account

    def save_account(self, account: UserAccount) -> None:
        self._current_account = account
        try:
            self.account_file.parent.mkdir(parents=True, exist_ok=True)
            raw = {
                "user_id": account.user_id,
                "display_name": account.display_name,
                "email": account.email,
                "plan": account.plan.value,
                "subscription_status": account.subscription_status.value,
                "billing_customer_id": account.billing_customer_id,
                "cancel_at_period_end": account.cancel_at_period_end,
                "activated_devices": account.activated_devices,
            }
            self.account_file.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            # Keep credit wallet in sync with plan
            if hasattr(self, "credit_mgr"):
                plan_def = self.plan_registry.get_plan(account.plan)
                if self.credit_mgr.wallet.plan_tier != account.plan:
                    self.credit_mgr.wallet.plan_tier = account.plan
                    self.credit_mgr.wallet.subscription_credits = plan_def.monthly_credits
                    # Welcome bonus for Annual Pro
                    if account.plan == PlanTier.ANNUAL_PRO:
                        self.credit_mgr.wallet.purchased_credits += 500
                    self.credit_mgr.save_wallet()
                    account.credit_wallet = self.credit_mgr.wallet
        except Exception as e:
            logger.error("Failed to save user account: %s", e)

    # ---------------------------------------------------------------------------
    # Entitlement & Gate Helpers
    # ---------------------------------------------------------------------------

    def can_use(self, entitlement: Entitlement, offline_mode: bool = False) -> GateResult:
        """Central entry point to verify entitlement for current user."""
        offline_valid = True
        if offline_mode:
            cached = self.offline_license_mgr.load_cached_license()
            if cached:
                ok, _ = self.offline_license_mgr.verify_license(cached)
                offline_valid = ok
            else:
                offline_valid = False

        return self.feature_gate.can_use(
            account=self._current_account,
            entitlement=entitlement,
            offline_mode=offline_mode,
            offline_license_valid=offline_valid,
        )

    def guard(self, entitlement: Entitlement) -> None:
        """Strict exception-raising gatekeeper for actions."""
        res = self.can_use(entitlement)
        if not res.allowed:
            raise PermissionError(f"[COMMERCIAL_GATE_LOCKED] {res.reason}")

    def verify_voice_access(self, persona: str) -> Tuple[bool, str]:
        """Validates voice entitlement according to exact plan policy.

        Starter / Basic: MALE ONLY.
        Pro / Annual Pro / Pro+ / Lifetime: MALE + FEMALE.
        """
        persona_clean = persona.lower().strip()
        account = self._current_account
        is_paid_active = account.subscription_status in (
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.LIFETIME_ACTIVE,
            SubscriptionStatus.GRACE_PERIOD,
        )

        # Paid tiers with male + female voice unlocked
        if is_paid_active:
            if account.plan in (PlanTier.ANNUAL_PRO, PlanTier.PRO, PlanTier.PRO_PLUS, PlanTier.PREMIUM, PlanTier.ADVANCED, PlanTier.LIFETIME):
                if persona_clean in ("male", "default", "female"):
                    return True, f"{persona.title()} voice unlocked."
            elif account.plan == PlanTier.BASIC:
                if persona_clean in ("male", "default"):
                    return True, "Male voice unlocked."
                elif persona_clean == "female":
                    return False, "Female voice requires Pro/Premium plan or higher."

        # Default / Starter tier: Male voice is available on free tier, female is locked
        if persona_clean in ("male", "default"):
            return True, "Male voice unlocked."

        if persona_clean == "female":
            res = self.can_use(Entitlement.VOICE_FEMALE)
            if not res.allowed:
                return False, "Female voice requires Pro/Premium plan or higher."
            return True, "Female voice unlocked."

        # Other custom / third-party voices
        res = self.can_use(Entitlement.VOICE_MULTIPLE)
        if not res.allowed:
            return False, "Additional voices require Pro or Pro+ plan."
        return True, "Voice unlocked."

    # ---------------------------------------------------------------------------
    # Active Usage Metering Wrappers
    # ---------------------------------------------------------------------------

    def start_active_interaction(self, atomic: bool = False) -> bool:
        """Called when assistant begins processing user speech/query/action."""
        eff_plan = self.entitlement_mgr.get_effective_plan(self._current_account)
        if eff_plan != PlanTier.STARTER:
            # Paid plans have unlimited active application time
            return True
        return self.usage_meter.start_active_task(atomic=atomic)

    def finish_active_interaction(self) -> None:
        """Called when assistant finishes processing or speaking."""
        eff_plan = self.entitlement_mgr.get_effective_plan(self._current_account)
        if eff_plan != PlanTier.STARTER:
            return
        self.usage_meter.finish_active_task()

    def get_starter_time_status(self) -> Dict[str, Any]:
        """Returns formatted remaining time for UI indicators."""
        eff_plan = self.entitlement_mgr.get_effective_plan(self._current_account)
        if eff_plan != PlanTier.STARTER:
            return {
                "is_starter": False,
                "plan": eff_plan.value,
                "label": f"{eff_plan.value} · Active",
                "remaining_seconds": None,
                "used_seconds": None,
            }

        rem_sec = int(self.usage_meter.get_remaining_seconds())
        used_sec = int(self.usage_meter.get_used_seconds())
        rem_min = rem_sec // 60
        rem_s = rem_sec % 60
        used_min = used_sec // 60
        used_s = used_sec % 60

        return {
            "is_starter": True,
            "plan": "STARTER",
            "label": f"Starter · {rem_min}:{rem_s:02d} left today",
            "used_str": f"{used_min}:{used_s:02d}",
            "rem_str": f"{rem_min}:{rem_s:02d}",
            "remaining_seconds": rem_sec,
            "used_seconds": used_sec,
            "is_exhausted": self.usage_meter.is_exhausted(),
        }

    def tick_starter_second(self, amount: float = 1.0) -> Dict[str, Any]:
        """Ticks down starter plan allowance while application is actively in use."""
        eff_plan = self.entitlement_mgr.get_effective_plan(self._current_account)
        if eff_plan == PlanTier.STARTER:
            self.usage_meter.tick_second(amount)
        return self.get_starter_time_status()

    # ---------------------------------------------------------------------------
    # Startup & Lifecycle Check
    # ---------------------------------------------------------------------------

    def startup_subscription_check(self) -> None:
        """Subscription + device validation at app launch.

        Flow:
          1. Verify cached signed entitlement (RSA + device + expiry)
          2. If valid and not needing revalidation → use cached plan
          3. If online → refresh entitlement from server
          4. If mismatch or expired → fall back to STARTER
        """
        # Process expired billing periods
        self.billing_mgr.process_period_end_expiry(self._current_account)

        # Paid subscriptions or lifetime purchases on standalone/offline desktop
        # predate or operate without the RSA entitlement cache. Preserve their active
        # entitlement instead of downgrading the account merely because it is offline.
        if (self._current_account.plan != PlanTier.STARTER
                and self._current_account.subscription_status in (
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.LIFETIME_ACTIVE,
                    SubscriptionStatus.GRACE_PERIOD,
                )
                and not self._cached_entitlement_token
                and not self.licensing_client.is_logged_in()):
            logger.info("Using active subscription (%s) in offline/standalone mode.", self._current_account.plan.value)
            return

        # Verify cached signed entitlement
        if self._cached_entitlement_token:
            ok, reason, payload = self.entitlement_verifier.full_verify(
                self._cached_entitlement_token, self._device_id
            )
            if ok and payload and not self.entitlement_verifier.needs_revalidation(payload):
                logger.info("Cached entitlement valid. Plan: %s", payload.plan)
                return

            if ok and payload and self.entitlement_verifier.needs_revalidation(payload):
                logger.info("Cached entitlement valid but needs revalidation.")
            else:
                logger.warning("Cached entitlement invalid: %s", reason)

        # Try online refresh
        if self.licensing_client.is_logged_in():
            try:
                fingerprint = self.device_identity.get_device_fingerprint()
                success, msg, token = self.licensing_client.refresh_entitlement(
                    self._device_id, fingerprint
                )
                if success and token:
                    self._update_cached_entitlement(token)
                    logger.info("Entitlement refreshed from server.")
                    return
                else:
                    logger.warning("Server refresh failed: %s", msg)
                    if "REVOKED" in msg.upper() or "SUSPEND" in msg.upper():
                        logger.critical("Remote license revoked or suspended by server: %s", msg)
                        self._cached_entitlement_token = None
                        if self._entitlement_cache_file.exists():
                            try:
                                self._entitlement_cache_file.unlink()
                            except Exception:
                                pass
                        self._current_account.plan = PlanTier.STARTER
                        self._current_account.subscription_status = SubscriptionStatus.SUSPENDED
                        self.save_account(self._current_account)
                        self.feature_gate.set_cached_token("")
                        return
            except Exception as e:
                logger.warning("Online refresh error (offline?): %s", e)

        # Offline fallback: check if cached entitlement still within grace period
        if self._cached_entitlement_token:
            ok, _, payload = self.entitlement_verifier.verify_token(self._cached_entitlement_token)
            if ok and payload and not self.entitlement_verifier.is_expired(payload):
                logger.info("Using cached entitlement in offline mode. Plan: %s", payload.plan)
                return

        # No valid entitlement: fall to STARTER
        if self._current_account.plan != PlanTier.STARTER:
            logger.warning("No valid entitlement. Falling back to STARTER.")
            self._current_account.plan = PlanTier.STARTER
            self._current_account.subscription_status = SubscriptionStatus.EXPIRED
            self.save_account(self._current_account)
            self.feature_gate.set_cached_token("")

    # ---------------------------------------------------------------------------
    # Device Conflict & Transfer
    # ---------------------------------------------------------------------------

    def check_second_pc_conflict(self) -> Optional[dict]:
        """Check if another PC is already active for this account.

        Returns conflict info dict or None if no conflict.
        """
        if not self.licensing_client.is_logged_in():
            return None

        fingerprint = self.device_identity.get_device_fingerprint()
        public_key = self.device_identity.get_public_key()
        device_name = self.device_identity.get_device_name()

        result = self.licensing_client.activate_device(
            device_id=self._device_id,
            fingerprint_hash=fingerprint,
            device_public_key=public_key,
            device_name=device_name,
        )

        if result.success:
            # No conflict — activated successfully
            if result.token:
                self._update_cached_entitlement(result.token)
                self._current_account.plan = PlanTier(result.plan)
                self.save_account(self._current_account)
            return None

        if result.message == "DEVICE_CONFLICT":
            return {
                "conflict": True,
                "active_device_name": result.conflict_device_name,
                "active_device_id": result.conflict_device_id,
            }

        return None

    def execute_license_transfer(self) -> Tuple[bool, str]:
        """Transfer license from old PC to this PC. Atomic server-side operation."""
        if not self.licensing_client.is_logged_in():
            return False, "Login required for license transfer."

        fingerprint = self.device_identity.get_device_fingerprint()
        public_key = self.device_identity.get_public_key()
        device_name = self.device_identity.get_device_name()

        result = self.licensing_client.transfer_license(
            device_id=self._device_id,
            fingerprint_hash=fingerprint,
            device_public_key=public_key,
            device_name=device_name,
        )

        if result.success and result.token:
            self._update_cached_entitlement(result.token)
            self._current_account.plan = PlanTier(result.plan)
            self.save_account(self._current_account)
            return True, "License transferred to this PC."

        return False, result.message

    # ---------------------------------------------------------------------------
    # Entitlement Token Cache
    # ---------------------------------------------------------------------------

    def _load_cached_entitlement_token(self) -> Optional[str]:
        if self._entitlement_cache_file.exists():
            try:
                return self._entitlement_cache_file.read_text(encoding="utf-8").strip()
            except Exception:
                pass
        return None

    def _update_cached_entitlement(self, token: str) -> None:
        """Persist signed entitlement token and update FeatureGate."""
        self._cached_entitlement_token = token
        self.feature_gate.set_cached_token(token)
        try:
            self._entitlement_cache_file.write_text(token, encoding="utf-8")
        except Exception as e:
            logger.error("Failed to cache entitlement token: %s", e)

    @property
    def device_id(self) -> str:
        return self._device_id


def get_commercial_engine() -> CommercialEngine:
    """Singleton getter for CommercialEngine."""
    global _GLOBAL_COMMERCIAL_ENGINE
    if _GLOBAL_COMMERCIAL_ENGINE is None:
        _GLOBAL_COMMERCIAL_ENGINE = CommercialEngine()
    return _GLOBAL_COMMERCIAL_ENGINE
