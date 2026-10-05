"""
tests/test_commercial_monetization.py — Test Suite for CHARLIE v1.0 Commercial Monetization Gap Closure.

Certifies all 26 requirement areas from Section 101 of the Commercial Monetization Engine Specification:
1. Plan Registry
2. Starter Plan Defaults
3. 10-Minute Active Usage Meter (Idle time excluded)
4. Usage Warnings (5m, 2m, 1m)
5. Atomic Task Limit Expiry Safety
6. Daily Reset
7. Clock Abuse Tamper Protection
8. Basic Plan Male Voice Gate
9. Premium Voice Unlock (Male + Female)
10. Advanced Full Entitlement (Filmora, MCP, Autonomy)
11. Lifetime Permanent License (No Monthly Renewal)
12. Cloud Cost Protection & BYOK Decoupling
13. FeatureGate Backend Enforcement
14. Local License Tamper Rejection
15. Signed Offline License Validation
16. Expired Offline License Revalidation
17. Device Seat Licensing Limits
18. Device Revocation
19. Server Payment Cryptographic Verification
20. Webhook Signature & Replay Protection
21. Immediate Upgrade Unlock (No restart required)
22. Safe Downgrade & Data Preservation
23. Grace Period Management
24. Receipt Metadata (No card data stored)
25. Paywall Upsell Rate-Limiting
26. Billing Audit Logging Integration
"""

import json
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.commercial.billing_manager import BillingAuditManager, BillingManager, GracePeriodManager
from engine.commercial.cloud_policy import CloudComputeMode, CloudUsagePolicy, QuotaManager
from engine.commercial.core import CommercialEngine
from engine.commercial.entitlement_manager import EntitlementManager
from engine.commercial.feature_gate import FeatureGate
from engine.commercial.license_manager import DeviceLicenseManager, OfflineLicenseManager
from engine.commercial.models import (
    Entitlement,
    GateStatus,
    PlanTier,
    SignedLicense,
    SubscriptionStatus,
    UsageState,
    UserAccount,
)
from engine.commercial.payment_provider import MockPaymentProvider
from engine.commercial.paywall_manager import PaywallManager, PricingUIManager
from engine.commercial.plan_registry import PlanRegistry
from engine.commercial.usage_meter import DailyUsageMeter


class TestCommercialMonetization(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.signing_secret = "test_super_secret_signing_key_9876543210"
        self.payment_provider = MockPaymentProvider(webhook_secret="test_webhook_secret_123")
        self.engine = CommercialEngine(
            base_dir=self.temp_dir,
            payment_provider=self.payment_provider,
            signing_secret=self.signing_secret,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Plan Registry
    def test_01_plan_registry(self):
        reg = self.engine.plan_registry
        plans = reg.list_plans()
        self.assertEqual(len(plans), 5)
        tiers = [p.tier for p in plans]
        self.assertEqual(tiers, [PlanTier.STARTER, PlanTier.BASIC, PlanTier.PRO, PlanTier.PRO_PLUS, PlanTier.ANNUAL_PRO])

        # Exact Pricing Checks
        self.assertEqual(reg.get_plan(PlanTier.STARTER).price_inr, 0)
        self.assertIn(reg.get_plan(PlanTier.BASIC).price_inr, [99, 149])
        self.assertEqual(reg.get_plan(PlanTier.PRO).price_inr, 299)
        self.assertEqual(reg.get_plan(PlanTier.PRO_PLUS).price_inr, 599)
        self.assertEqual(reg.get_plan(PlanTier.ANNUAL_PRO).price_inr, 2999)
        self.assertEqual(reg.get_plan(PlanTier.LIFETIME).price_inr, 999)

        # Positioning Badges
        self.assertEqual(reg.get_plan(PlanTier.PRO).badge, "MOST POPULAR")
        self.assertEqual(reg.get_plan(PlanTier.PRO_PLUS).badge, "BEST VALUE")
        self.assertEqual(reg.get_plan(PlanTier.ANNUAL_PRO).badge, "SAVE ₹589/YEAR + VIP BONUSES")
        self.assertEqual(reg.get_plan(PlanTier.LIFETIME).badge, "BEST LONG-TERM VALUE")

    # 2. Starter Plan Defaults
    def test_02_starter_plan_defaults(self):
        starter = self.engine.plan_registry.get_plan(PlanTier.STARTER)
        self.assertEqual(starter.daily_active_minutes_limit, 10)
        self.assertEqual(starter.max_devices, 1)
        self.assertFalse(starter.is_recurring)
        self.assertIn(Entitlement.TEXT_CHAT, starter.entitlements)
        self.assertIn(Entitlement.VOICE_MALE, starter.entitlements)
        self.assertNotIn(Entitlement.VOICE_FEMALE, starter.entitlements)

    # 3. 10-Minute Active Usage Meter (Idle time excluded)
    def test_03_active_usage_meter_idle_exclusion(self):
        meter = DailyUsageMeter(
            storage_path=self.temp_dir / "test_usage.json",
            daily_limit_sec=600,
        )
        self.assertEqual(meter.get_remaining_seconds(), 600.0)

        # Transition to IDLE: window open for 1 hour should consume 0 seconds
        meter.transition_state(UsageState.IDLE)
        time.sleep(0.05)
        meter.transition_state(UsageState.IDLE)
        self.assertEqual(meter.get_used_seconds(), 0.0)
        self.assertEqual(meter.get_remaining_seconds(), 600.0)

        # Transition to ACTIVE: consumes time
        meter.record_active_seconds(120.0)  # 2 minutes active
        self.assertAlmostEqual(meter.get_used_seconds(), 120.0, delta=1.0)
        self.assertAlmostEqual(meter.get_remaining_seconds(), 480.0, delta=1.0)

    # 4. Usage Warnings (5m, 2m, 1m)
    def test_04_usage_warnings(self):
        warnings_received = []

        def on_warn(minute, msg):
            warnings_received.append(minute)

        meter = DailyUsageMeter(
            storage_path=self.temp_dir / "test_warn_usage.json",
            daily_limit_sec=600,
            on_warning=on_warn,
        )

        # Consume down to 5m remaining (300s)
        meter.record_active_seconds(310.0)
        self.assertIn(5, warnings_received)

        # Consume down to 2m remaining (120s)
        meter.record_active_seconds(180.0)
        self.assertIn(2, warnings_received)

        # Consume down to 1m remaining (60s)
        meter.record_active_seconds(60.0)
        self.assertIn(1, warnings_received)

    # 5. Atomic Task Limit Expiry Safety
    def test_05_atomic_task_safety(self):
        exhausted_called = []
        meter = DailyUsageMeter(
            storage_path=self.temp_dir / "test_atomic.json",
            daily_limit_sec=600,
            on_exhausted=lambda: exhausted_called.append(True),
        )
        meter.record_active_seconds(599.0)  # 1 second left

        # Start atomic task (e.g. file writing or checkpointing)
        ok = meter.start_active_task(atomic=True)
        self.assertTrue(ok)
        meter.record_active_seconds(10.0)  # Exceeds limit during atomic work

        # In atomic operation, is_exhausted returns False to prevent in-flight corruption
        self.assertFalse(meter.is_exhausted())

        # Completing atomic operation triggers safe shutdown
        meter.finish_active_task()
        self.assertTrue(meter.is_exhausted())

    # 6. Daily Reset
    def test_06_daily_reset(self):
        meter = DailyUsageMeter(
            storage_path=self.temp_dir / "test_reset.json",
            daily_limit_sec=600,
        )
        meter.record_active_seconds(600.0)
        self.assertTrue(meter.is_exhausted())

        # Simulate arrival of new entitlement day
        meter._current_day = "2026-01-01"
        meter._check_and_reset_day()
        self.assertFalse(meter.is_exhausted())
        self.assertEqual(meter.get_remaining_seconds(), 600.0)

    # 7. Clock Abuse Tamper Protection
    def test_07_clock_tamper_protection(self):
        meter = DailyUsageMeter(
            storage_path=self.temp_dir / "test_tamper.json",
            daily_limit_sec=600,
        )
        meter.record_active_seconds(400.0)

        # Tamper: shift recorded wall clock far into future, then load with current clock
        meter._last_saved_wall_ts = time.time() + 86400  # 1 day in future
        meter._save_state()

        # Re-load from disk
        meter2 = DailyUsageMeter(
            storage_path=self.temp_dir / "test_tamper.json",
            daily_limit_sec=600,
        )
        # Consumed quota must be preserved, not wiped
        self.assertAlmostEqual(meter2.get_used_seconds(), 400.0, delta=1.0)

    # 8. Basic Plan Male Voice Gate
    def test_08_basic_plan_voice_male_only(self):
        user = UserAccount("u1", "Bob", "bob@example.com", PlanTier.BASIC, SubscriptionStatus.ACTIVE)
        self.engine.save_account(user)

        ok_male, _ = self.engine.verify_voice_access("male")
        self.assertTrue(ok_male)

        ok_female, reason = self.engine.verify_voice_access("female")
        self.assertFalse(ok_female)
        self.assertIn("Premium", reason)

    # 9. Premium Voice Unlock (Male + Female)
    def test_09_premium_plan_voice_both(self):
        user = UserAccount("u2", "Alice", "alice@example.com", PlanTier.PREMIUM, SubscriptionStatus.ACTIVE)
        self.engine.save_account(user)

        ok_male, _ = self.engine.verify_voice_access("male")
        self.assertTrue(ok_male)

        ok_female, _ = self.engine.verify_voice_access("female")
        self.assertTrue(ok_female)

    # 10. Advanced Full Entitlement (Filmora, MCP, Autonomy)
    def test_10_advanced_plan_all_voices_and_features(self):
        user = UserAccount("u3", "Charlie", "charlie@example.com", PlanTier.ADVANCED, SubscriptionStatus.ACTIVE)
        self.engine.save_account(user)

        for ent in (Entitlement.VIDEO_FILMORA, Entitlement.MCP, Entitlement.AUTONOMY_ADVANCED, Entitlement.VOICE_FEMALE):
            res = self.engine.can_use(ent)
            self.assertTrue(res.allowed)
            self.assertEqual(res.status, GateStatus.ALLOWED)

    # 11. Lifetime Permanent License (No Monthly Renewal)
    def test_11_lifetime_permanent_license(self):
        user = UserAccount("u4", "Dave", "dave@example.com", PlanTier.LIFETIME, SubscriptionStatus.LIFETIME_ACTIVE)
        self.engine.save_account(user)

        # Permanent Advanced features
        self.assertTrue(self.engine.can_use(Entitlement.VIDEO_FILMORA).allowed)
        self.assertTrue(self.engine.can_use(Entitlement.MCP).allowed)

        # Does not have renewal date
        self.assertIsNone(user.current_period_end)
        self.assertFalse(user.cancel_at_period_end)

    # 12. Cloud Cost Protection & BYOK Decoupling
    def test_12_cloud_cost_protection(self):
        user = UserAccount("u5", "Eve", "eve@example.com", PlanTier.LIFETIME, SubscriptionStatus.LIFETIME_ACTIVE)
        quota_mgr = self.engine.quota_mgr
        policy = self.engine.cloud_policy

        # Consume all fair-use tokens
        state = quota_mgr.get_quota_state(user)
        quota_mgr.record_token_consumption(user, state.tokens_total_allowance + 1000)
        self.assertFalse(quota_mgr.is_cloud_quota_available(user))

        # Cloud policy routes to Local AI when quota exhausted
        mode, msg = policy.evaluate_model_execution_mode(user, requires_cloud_model=False)
        self.assertEqual(mode, CloudComputeMode.LOCAL_AI)

        # Activating BYOK restores cloud execution without app owner cost
        quota_mgr.set_byok(user, provider="google_gemini", active=True)
        mode_byok, _ = policy.evaluate_model_execution_mode(user, requires_cloud_model=True)
        self.assertEqual(mode_byok, CloudComputeMode.BYOK)

    # 13. FeatureGate Backend Enforcement
    def test_13_feature_gate_backend_enforcement(self):
        user = UserAccount("u6", "Frank", "frank@example.com", PlanTier.BASIC, SubscriptionStatus.ACTIVE)
        gate = self.engine.feature_gate

        # Direct backend call to locked entitlement raises PermissionError
        with self.assertRaises(PermissionError):
            gate.guard(user, Entitlement.VIDEO_FILMORA)

    # 14. Local License Tamper Rejection
    def test_14_local_tamper_rejection(self):
        lic_mgr = self.engine.offline_license_mgr
        # Generate authentic license for BASIC
        lic = lic_mgr.sign_license("user_tamper", PlanTier.BASIC, ["VOICE_MALE"], "device_1")

        # Attacker tampers in-memory or JSON to ADVANCED
        tampered = SignedLicense(
            user_id=lic.user_id,
            plan=PlanTier.ADVANCED,  # Forged upgrade
            issued_at=lic.issued_at,
            valid_until=lic.valid_until,
            features=["VIDEO_FILMORA", "MCP"],
            device_id=lic.device_id,
            signature=lic.signature,
        )
        ok, reason = lic_mgr.verify_license(tampered, current_device_id="device_1")
        self.assertFalse(ok)
        self.assertIn("tampering", reason.lower())

    # 15. Signed Offline License Validation
    def test_15_signed_offline_license(self):
        lic_mgr = self.engine.offline_license_mgr
        lic = lic_mgr.sign_license("user_off", PlanTier.PREMIUM, ["VOICE_FEMALE"], "dev_laptop", validity_days=14)

        ok, msg = lic_mgr.verify_license(lic, current_device_id="dev_laptop")
        self.assertTrue(ok)
        self.assertEqual(msg, "Valid offline license.")

    # 16. Expired Offline License Revalidation
    def test_16_expired_offline_license(self):
        lic_mgr = self.engine.offline_license_mgr
        # Generate expired license
        past_dt = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        lic = SignedLicense(
            user_id="user_exp",
            plan=PlanTier.PREMIUM,
            issued_at=past_dt,
            valid_until=past_dt,
            features=["VOICE_FEMALE"],
            device_id="dev_1",
            signature="bogus_sig",
        )
        # Compute valid signature for the expired payload
        raw = lic_mgr._canonical_payload("user_exp", "PREMIUM", past_dt, past_dt, ["VOICE_FEMALE"], "dev_1")
        import hashlib, hmac
        lic.signature = hmac.new(lic_mgr._secret, raw, hashlib.sha256).hexdigest()

        ok, reason = lic_mgr.verify_license(lic, current_device_id="dev_1")
        self.assertFalse(ok)
        self.assertIn("expired", reason.lower())

    # 17. Device Seat Licensing Limits
    def test_17_device_license_limits(self):
        dev_mgr = self.engine.device_mgr
        user = UserAccount("u7", "Grace", "grace@example.com", PlanTier.BASIC, SubscriptionStatus.ACTIVE)

        # Basic plan allows exactly 1 device
        ok1, _ = dev_mgr.register_device(user, "pc_1", "Workstation")
        self.assertTrue(ok1)

        ok2, msg2 = dev_mgr.register_device(user, "pc_2", "Laptop")
        self.assertFalse(ok2)
        self.assertIn("Device limit", msg2)

    # 18. Device Revocation
    def test_18_device_revocation(self):
        dev_mgr = self.engine.device_mgr
        user = UserAccount("u8", "Hank", "hank@example.com", PlanTier.PREMIUM, SubscriptionStatus.ACTIVE)
        dev_mgr.register_device(user, "phone_1", "Pixel Phone")
        self.assertTrue(dev_mgr.is_device_authorized(user, "phone_1"))

        revoked = dev_mgr.revoke_device(user, "phone_1")
        self.assertTrue(revoked)
        self.assertFalse(dev_mgr.is_device_authorized(user, "phone_1"))

    # 19. Server Payment Cryptographic Verification
    def test_19_server_payment_verification(self):
        user = UserAccount("u9", "Ivy", "ivy@example.com", PlanTier.STARTER, SubscriptionStatus.FREE)
        bm = self.engine.billing_mgr

        # Checkout initiated
        session = bm.initiate_checkout(user, PlanTier.PREMIUM)
        self.assertIsNotNone(session.order_id)

        # Attempt fake spoof without valid signature -> REJECT
        ok_fake, _ = bm.verify_and_activate_purchase(user, PlanTier.PREMIUM, session.order_id, "pay_fake", "invalid_sig")
        self.assertFalse(ok_fake)
        self.assertEqual(user.plan, PlanTier.STARTER)

        # Valid cryptographic signature from gateway -> APPROVE
        valid_sig = self.payment_provider.generate_valid_signature(session.order_id, "pay_real_123")
        ok_real, msg = bm.verify_and_activate_purchase(user, PlanTier.PREMIUM, session.order_id, "pay_real_123", valid_sig)
        self.assertTrue(ok_real)
        self.assertEqual(user.plan, PlanTier.PREMIUM)
        self.assertEqual(user.subscription_status, SubscriptionStatus.ACTIVE)

    # 20. Webhook Signature & Replay Protection
    def test_20_webhook_signature_and_replay(self):
        provider = self.payment_provider
        payload = json.dumps({"event_id": "evt_abc_123", "type": "payment.captured", "amount": 19900}).encode("utf-8")

        # Bad signature
        ok_bad, _ = provider.handle_webhook(payload, "bad_signature")
        self.assertFalse(ok_bad)

        # Good signature
        import hashlib, hmac
        good_sig = hmac.new(provider.webhook_secret, payload, hashlib.sha256).hexdigest()
        ok_good, data = provider.handle_webhook(payload, good_sig)
        self.assertTrue(ok_good)
        self.assertEqual(data["event_id"], "evt_abc_123")

        # Replay attack attempt
        ok_replay, err_replay = provider.handle_webhook(payload, good_sig)
        self.assertFalse(ok_replay)
        self.assertIn("Replay detected", err_replay["error"])

    # 21. Immediate Upgrade Unlock (No restart required)
    def test_21_upgrade_immediate_unlock(self):
        user = UserAccount("u10", "Jack", "jack@example.com", PlanTier.STARTER, SubscriptionStatus.FREE)
        self.engine.save_account(user)

        # Female voice locked initially
        self.assertFalse(self.engine.can_use(Entitlement.VOICE_FEMALE).allowed)

        # Complete payment verification
        bm = self.engine.billing_mgr
        session = bm.initiate_checkout(user, PlanTier.PREMIUM)
        sig = self.payment_provider.generate_valid_signature(session.order_id, "pay_instant_999")
        ok, _ = bm.verify_and_activate_purchase(user, PlanTier.PREMIUM, session.order_id, "pay_instant_999", sig)
        self.assertTrue(ok)

        # Immediately unlocked in active runtime
        self.assertTrue(self.engine.can_use(Entitlement.VOICE_FEMALE).allowed)

    # 22. Safe Downgrade & Data Preservation
    def test_22_downgrade_data_preservation(self):
        user = UserAccount(
            "u11", "Kelly", "kelly@example.com", PlanTier.ADVANCED, SubscriptionStatus.ACTIVE,
            current_period_end=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        self.engine.billing_mgr.process_period_end_expiry(user)

        # Switched to Starter, but account identity & references remain 100% intact
        self.assertEqual(user.plan, PlanTier.STARTER)
        self.assertEqual(user.subscription_status, SubscriptionStatus.EXPIRED)
        self.assertEqual(user.user_id, "u11")

    # 23. Grace Period Management
    def test_23_grace_period_handling(self):
        user = UserAccount(
            "u12", "Leo", "leo@example.com", PlanTier.PREMIUM, SubscriptionStatus.ACTIVE,
            current_period_end=datetime.now(timezone.utc) - timedelta(hours=12),
        )
        grace = GracePeriodManager(grace_days=3)
        grace.activate_grace_period(user)

        # Within grace period, effective plan still retains paid features
        self.assertEqual(user.subscription_status, SubscriptionStatus.GRACE_PERIOD)
        self.assertFalse(grace.is_grace_expired(user))
        self.assertEqual(self.engine.entitlement_mgr.get_effective_plan(user), PlanTier.PREMIUM)

    # 24. Receipt Metadata (No card data stored)
    def test_24_receipt_metadata(self):
        bm = self.engine.billing_mgr
        user = UserAccount("u13", "Mia", "mia@example.com", PlanTier.BASIC, SubscriptionStatus.ACTIVE)
        session = bm.initiate_checkout(user, PlanTier.BASIC)
        sig = self.payment_provider.generate_valid_signature(session.order_id, "pay_rcpt_1")
        bm.verify_and_activate_purchase(user, PlanTier.BASIC, session.order_id, "pay_rcpt_1", sig)

        receipts = bm.receipt_mgr.get_user_receipts(user.user_id)
        self.assertEqual(len(receipts), 1)
        r = receipts[0]
        self.assertEqual(r.amount_paise, 9900)
        self.assertEqual(r.plan, PlanTier.BASIC)
        self.assertFalse(hasattr(r, "card_number"))
        self.assertFalse(hasattr(r, "cvv"))

    # 25. Paywall Upsell Rate-Limiting
    def test_25_paywall_upsell_throttling(self):
        pm = PaywallManager(self.engine.plan_registry)
        self.assertFalse(pm.should_suppress_upsell())

        # Showing paywall modal triggers cooldown
        payload = pm.get_starter_paywall_payload()
        self.assertEqual(payload["title"], "Today's free CHARLIE time is complete.")
        self.assertTrue(pm.should_suppress_upsell())

    # 26. Billing Audit Logging Integration
    def test_26_billing_audit_logging(self):
        audit_events = []

        class MockAuditEngine:
            def record_event(self, **kwargs):
                audit_events.append(kwargs)

        audit_mgr = BillingAuditManager(audit_engine=MockAuditEngine())
        audit_mgr.record_billing_event("PLAN_UPGRADED", "usr_100", "PREMIUM", "Clean upgrade without leaking secret_key_abc")

        self.assertEqual(len(audit_events), 1)
        evt = audit_events[0]
        self.assertEqual(evt["origin"], "COMMERCIAL_BILLING")
        self.assertEqual(evt["action"], "PLAN_UPGRADED")
        self.assertEqual(evt["target"], "usr_100")


if __name__ == "__main__":
    unittest.main()
