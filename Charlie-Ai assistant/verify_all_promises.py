"""
verify_all_promises.py — Deep audit of all promised tier features and capabilities.
"""
from __future__ import annotations

import sys
import unittest
from engine.commercial.models import BillingCycle, Entitlement, PlanTier, UserAccount
from engine.commercial.plan_registry import PlanRegistry
from engine.commercial.credit_manager import CreditManager, CREDIT_COSTS
from engine.commercial.paywall_manager import PaywallManager, PricingUIManager
from engine.commercial.entitlement_verifier import EntitlementVerifier
from licensing_server.services.license_service import PLAN_FEATURES


class TestAllPromises(unittest.TestCase):
    def setUp(self):
        self.registry = PlanRegistry()
        self.verifier = EntitlementVerifier(plan_registry=self.registry)
        self.credit_mgr = CreditManager()

    def test_all_tiers_exist_and_match(self):
        """Audit that all 5 public tiers + legacy lifetime exist in registry and license service."""
        plans = self.registry.list_public_plans()
        tiers = [p.tier for p in plans]
        self.assertEqual(tiers, [PlanTier.STARTER, PlanTier.BASIC, PlanTier.PRO, PlanTier.PRO_PLUS, PlanTier.ANNUAL_PRO])

        # All tiers exist in licensing server
        for t in [PlanTier.STARTER, PlanTier.BASIC, PlanTier.PRO, PlanTier.PRO_PLUS, PlanTier.ANNUAL_PRO, PlanTier.LIFETIME]:
            self.assertIn(t.value, PLAN_FEATURES)

    def test_starter_limits(self):
        """Audit Starter promise: 15 daily messages, 1 device, zero card, basic entitlements."""
        starter = self.registry.get_plan(PlanTier.STARTER)
        self.assertEqual(starter.price_inr, 0)
        self.assertEqual(starter.daily_messages_limit, 15)
        self.assertEqual(starter.max_devices, 1)
        self.assertFalse(starter.is_recurring)
        self.assertIn(Entitlement.TEXT_CHAT, starter.entitlements)
        self.assertIn(Entitlement.VOICE_MALE, starter.entitlements)
        self.assertNotIn(Entitlement.VOICE_FEMALE, starter.entitlements)
        self.assertNotIn(Entitlement.COMPUTER_ADVANCED, starter.entitlements)

    def test_basic_features(self):
        """Audit Basic promise: 500 credits/mo, ₹149, 1 device, male voice, offline AI, office basic."""
        basic = self.registry.get_plan(PlanTier.BASIC)
        self.assertIn(basic.price_inr, [99, 149])
        self.assertEqual(basic.monthly_credits, 500)
        self.assertEqual(basic.max_devices, 1)
        self.assertTrue(basic.is_recurring)
        self.assertIn(Entitlement.TEXT_CHAT, basic.entitlements)
        self.assertIn(Entitlement.VOICE_MALE, basic.entitlements)
        self.assertNotIn(Entitlement.VOICE_FEMALE, basic.entitlements)
        self.assertIn(Entitlement.SPREADSHEET_BASIC, basic.entitlements)
        self.assertIn(Entitlement.OFFLINE_AI, basic.entitlements)

    def test_pro_features(self):
        """Audit Pro promise: 1,500 credits/mo, ₹299, 2 devices, dual voice switching, PKG, Coding, Office."""
        pro = self.registry.get_plan(PlanTier.PRO)
        self.assertEqual(pro.price_inr, 299)
        self.assertEqual(pro.monthly_credits, 1500)
        self.assertEqual(pro.max_devices, 2)
        self.assertTrue(pro.is_recurring)
        self.assertIn(Entitlement.VOICE_FEMALE, pro.entitlements)
        self.assertIn(Entitlement.VOICE_MULTIPLE, pro.entitlements)
        self.assertIn(Entitlement.KNOWLEDGE_GRAPH, pro.entitlements)
        self.assertIn(Entitlement.CODING, pro.entitlements)
        self.assertIn(Entitlement.SPREADSHEET_ADVANCED, pro.entitlements)
        self.assertIn(Entitlement.GMAIL, pro.entitlements)
        self.assertIn(Entitlement.CALENDAR, pro.entitlements)
        self.assertIn(Entitlement.DRIVE, pro.entitlements)
        self.assertIn(Entitlement.MULTI_AGENT, pro.entitlements)

    def test_pro_plus_features(self):
        """Audit Pro+ promise: 4,000 credits/mo, ₹599, 5 devices, autonomous PC, Filmora, Deep Research, MCP."""
        pro_plus = self.registry.get_plan(PlanTier.PRO_PLUS)
        self.assertEqual(pro_plus.price_inr, 599)
        self.assertEqual(pro_plus.monthly_credits, 4000)
        self.assertEqual(pro_plus.max_devices, 5)
        self.assertIn(Entitlement.COMPUTER_ADVANCED, pro_plus.entitlements)
        self.assertIn(Entitlement.AUTONOMY_ADVANCED, pro_plus.entitlements)
        self.assertIn(Entitlement.VIDEO_FILMORA, pro_plus.entitlements)
        self.assertIn(Entitlement.YOUTUBE_AUTOMATION, pro_plus.entitlements)
        self.assertIn(Entitlement.RESEARCH_DEEP, pro_plus.entitlements)
        self.assertIn(Entitlement.MCP, pro_plus.entitlements)
        self.assertIn(Entitlement.CUSTOM_AGENTS, pro_plus.entitlements)

    def test_annual_pro_enhanced_features(self):
        """Audit Annual Pro promise: 1,800 credits/mo (+300 bonus), 3 devices, Deep Research, Autonomous PC Hooks."""
        annual = self.registry.get_plan(PlanTier.ANNUAL_PRO)
        self.assertEqual(annual.price_inr, 2999)
        self.assertEqual(annual.monthly_credits, 1800)
        self.assertEqual(annual.max_devices, 3)
        self.assertEqual(annual.annual_saving_inr, 589)
        self.assertEqual(annual.billing_cycle, BillingCycle.ANNUAL)
        self.assertIn(Entitlement.RESEARCH_DEEP, annual.entitlements)
        self.assertIn(Entitlement.COMPUTER_ADVANCED, annual.entitlements)
        self.assertIn(Entitlement.SKILL_LEARNING, annual.entitlements)
        self.assertIn(Entitlement.VOICE_FEMALE, annual.entitlements)

    def test_entitlement_gating_logic(self):
        """Audit that gate_feature correctly grants or denies based on user tier."""
        # Starter cannot use Female voice
        starter_acc = UserAccount(user_id="u1", email="test@a.com", plan=PlanTier.STARTER)
        res = self.verifier.gate_feature(starter_acc, Entitlement.VOICE_FEMALE)
        self.assertFalse(res.allowed)
        self.assertEqual(res.required_plan, PlanTier.PRO)

        # Pro can use Female voice
        pro_acc = UserAccount(user_id="u2", email="pro@a.com", plan=PlanTier.PRO)
        res_pro = self.verifier.gate_feature(pro_acc, Entitlement.VOICE_FEMALE)
        self.assertTrue(res_pro.allowed)

        # Pro cannot use Filmora
        res_filmora = self.verifier.gate_feature(pro_acc, Entitlement.VIDEO_FILMORA)
        self.assertFalse(res_filmora.allowed)
        self.assertEqual(res_filmora.required_plan, PlanTier.PRO_PLUS)

        # Annual Pro CAN use Deep Research and Computer Advanced
        annual_acc = UserAccount(user_id="u3", email="ann@a.com", plan=PlanTier.ANNUAL_PRO)
        res_deep = self.verifier.gate_feature(annual_acc, Entitlement.RESEARCH_DEEP)
        self.assertTrue(res_deep.allowed)
        res_comp = self.verifier.gate_feature(annual_acc, Entitlement.COMPUTER_ADVANCED)
        self.assertTrue(res_comp.allowed)

    def test_credit_costs_and_deduction(self):
        """Audit credit costs and wallet deductions."""
        self.assertEqual(CREDIT_COSTS["chat_message"], 1)
        self.assertEqual(CREDIT_COSTS["deep_research"], 15)
        self.assertEqual(CREDIT_COSTS["filmora_render"], 25)

        wallet = self.credit_mgr.create_wallet("u1")
        self.credit_mgr.allocate_monthly_credits(wallet, 1800)
        self.assertEqual(wallet.subscription_credits, 1800)

        ok, tx = self.credit_mgr.deduct_credits(wallet, 15, "deep_research")
        self.assertTrue(ok)
        self.assertEqual(wallet.subscription_credits, 1785)


if __name__ == "__main__":
    unittest.main()
