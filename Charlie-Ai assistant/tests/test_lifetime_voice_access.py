import json
import tempfile
import unittest
from pathlib import Path

from engine.commercial.core import CommercialEngine
from engine.commercial.models import PlanTier, SubscriptionStatus


class TestLifetimeVoiceAccess(unittest.TestCase):
    def test_legacy_lifetime_account_unlocks_both_voices(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "user_account.json").write_text(json.dumps({
                "user_id": "lifetime-user",
                "display_name": "Lifetime User",
                "email": "lifetime@example.com",
                "plan": "LIFETIME",
                "subscription_status": "ACTIVE",
                "activated_devices": [],
            }), encoding="utf-8")

            engine = CommercialEngine(base_dir=base)
            self.assertEqual(
                engine.get_account().subscription_status,
                SubscriptionStatus.LIFETIME_ACTIVE,
            )
            self.assertTrue(engine.verify_voice_access("male")[0])
            self.assertTrue(engine.verify_voice_access("female")[0])

    def test_offline_startup_preserves_legacy_lifetime_voice_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = CommercialEngine(base_dir=Path(tmp))
            account = engine.get_account()
            account.plan = PlanTier.LIFETIME
            account.subscription_status = SubscriptionStatus.LIFETIME_ACTIVE
            engine.save_account(account)

            engine.startup_subscription_check()

            self.assertEqual(engine.get_account().plan, PlanTier.LIFETIME)
            self.assertTrue(engine.verify_voice_access("female")[0])

    def test_annual_pro_unlocks_both_male_and_female_voices(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = CommercialEngine(base_dir=Path(tmp))
            account = engine.get_account()
            account.plan = PlanTier.ANNUAL_PRO
            account.subscription_status = SubscriptionStatus.ACTIVE
            engine.save_account(account)

            self.assertTrue(engine.verify_voice_access("male")[0])
            self.assertTrue(engine.verify_voice_access("female")[0])

    def test_pro_unlocks_both_male_and_female_voices(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = CommercialEngine(base_dir=Path(tmp))
            account = engine.get_account()
            account.plan = PlanTier.PRO
            account.subscription_status = SubscriptionStatus.ACTIVE
            engine.save_account(account)

            self.assertTrue(engine.verify_voice_access("male")[0])
            self.assertTrue(engine.verify_voice_access("female")[0])

    def test_basic_unlocks_male_locks_female(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = CommercialEngine(base_dir=Path(tmp))
            account = engine.get_account()
            account.plan = PlanTier.BASIC
            account.subscription_status = SubscriptionStatus.ACTIVE
            engine.save_account(account)

            self.assertTrue(engine.verify_voice_access("male")[0])
            self.assertFalse(engine.verify_voice_access("female")[0])

    def test_offline_startup_preserves_annual_pro(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = CommercialEngine(base_dir=Path(tmp))
            account = engine.get_account()
            account.plan = PlanTier.ANNUAL_PRO
            account.subscription_status = SubscriptionStatus.ACTIVE
            engine.save_account(account)

            engine.startup_subscription_check()

            self.assertEqual(engine.get_account().plan, PlanTier.ANNUAL_PRO)
            self.assertTrue(engine.verify_voice_access("male")[0])
            self.assertTrue(engine.verify_voice_access("female")[0])


if __name__ == "__main__":
    unittest.main()
