"""
engine/commercial/plan_registry.py — Centralized Plan Catalog, Pricing, and Entitlements.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import BillingCycle, Entitlement, PlanDefinition, PlanTier


class PlanRegistry:
    """Central authoritative catalog of commercial plans and entitlements.

    Prevents scattered `if plan == 'premium'` checks.
    """

    def __init__(self, custom_plans: Optional[Dict[PlanTier, PlanDefinition]] = None):
        self._plans: Dict[PlanTier, PlanDefinition] = custom_plans or self._build_default_catalog()

    @staticmethod
    def calculate_annual_savings(monthly_price: int = 299, annual_price: int = 2999) -> Dict[str, Any]:
        """Mathematically exact annual savings calculations.
        
        Monthly Pro: ₹299 * 12 = ₹3,588
        Annual Pro: ₹2,999
        Exact saving: ₹589 (~16.4%)
        Effective monthly: ≈₹250/month
        Strict exact math calculation.
        """
        regular_annual_cost = monthly_price * 12
        annual_saving = regular_annual_cost - annual_price
        saving_pct = round((annual_saving / regular_annual_cost) * 100, 1)
        effective_monthly = round(annual_price / 12, 2)
        effective_monthly_rounded = round(annual_price / 12)
        return {
            "monthly_price": monthly_price,
            "annual_price": annual_price,
            "regular_annual_cost": regular_annual_cost,
            "annual_saving": annual_saving,
            "saving_pct": saving_pct,
            "effective_monthly": effective_monthly,
            "effective_monthly_rounded": effective_monthly_rounded,
        }

    @classmethod
    def _build_default_catalog(cls) -> Dict[PlanTier, PlanDefinition]:
        starter_entitlements = [
            Entitlement.TEXT_CHAT,
            Entitlement.VOICE_MALE,
            Entitlement.COMPUTER_BASIC,
            Entitlement.MEMORY_BASIC,
            Entitlement.SKILLS_BASIC,
        ]

        basic_entitlements = [
            Entitlement.TEXT_CHAT,
            Entitlement.VOICE_MALE,
            Entitlement.COMPUTER_BASIC,
            Entitlement.MEMORY_BASIC,
            Entitlement.SPREADSHEET_BASIC,
            Entitlement.RESEARCH_BASIC,
            Entitlement.SKILLS_BASIC,
            Entitlement.OFFLINE_AI,
        ]

        pro_entitlements = basic_entitlements + [
            Entitlement.VOICE_FEMALE,
            Entitlement.VOICE_MULTIPLE,
            Entitlement.MEMORY_ADVANCED,
            Entitlement.KNOWLEDGE_GRAPH,
            Entitlement.CODING,
            Entitlement.SPREADSHEET_ADVANCED,
            Entitlement.GMAIL,
            Entitlement.CALENDAR,
            Entitlement.DRIVE,
            Entitlement.MULTI_AGENT,
            Entitlement.VIDEO_BASIC,
            Entitlement.PLUGINS,
            Entitlement.MULTI_DEVICE,
        ]

        pro_plus_entitlements = pro_entitlements + [
            Entitlement.COMPUTER_ADVANCED,
            Entitlement.AUTONOMY_ADVANCED,
            Entitlement.RESEARCH_DEEP,
            Entitlement.VIDEO_FILMORA,
            Entitlement.YOUTUBE_AUTOMATION,
            Entitlement.SKILL_LEARNING,
            Entitlement.MCP,
            Entitlement.CUSTOM_AGENTS,
            Entitlement.PROACTIVE_INTELLIGENCE,
        ]

        # Annual Pro gets exclusive power bonuses over monthly Pro: Deep Research, Autonomous PC, Skill Learning
        annual_pro_entitlements = pro_entitlements + [
            Entitlement.RESEARCH_DEEP,
            Entitlement.COMPUTER_ADVANCED,
            Entitlement.SKILL_LEARNING,
        ]

        # Legacy Lifetime retains full advanced entitlements permanently
        lifetime_entitlements = list(pro_plus_entitlements)

        savings = cls.calculate_annual_savings(299, 2999)

        return {
            PlanTier.STARTER: PlanDefinition(
                tier=PlanTier.STARTER,
                name="Starter",
                price_inr=0,
                billing_cycle=BillingCycle.FREE,
                tagline="Try CHARLIE",
                badge=None,
                daily_active_minutes_limit=10,
                daily_messages_limit=15,
                monthly_credits=0,
                max_devices=1,
                cloud_fair_use_tokens=5_000,
                is_recurring=False,
                benefits=[
                    "15 AI messages per day",
                    "Basic text assistant",
                    "1 voice profile",
                    "Basic file assistance & web help",
                    "Basic app launching & navigation",
                    "3-day chat history",
                    "No credit card required",
                ],
                entitlements=starter_entitlements,
            ),
            PlanTier.BASIC: PlanDefinition(
                tier=PlanTier.BASIC,
                name="Basic",
                price_inr=99,
                billing_cycle=BillingCycle.MONTHLY,
                tagline="For everyday use",
                badge=None,
                monthly_credits=500,
                max_devices=1,
                cloud_fair_use_tokens=50_000,
                is_recurring=True,
                benefits=[
                    "500 AI Credits per month",
                    "Text assistant & basic voice assistant",
                    "Document summaries & file analysis",
                    "Basic PC control & spreadsheet operations",
                    "Standard web search & local model routing",
                    "Offline AI when supported",
                    "7-day chat history",
                ],
                entitlements=basic_entitlements,
            ),
            PlanTier.PREMIUM: PlanDefinition(
                tier=PlanTier.PREMIUM,
                name="Premium",
                price_inr=199,
                billing_cycle=BillingCycle.MONTHLY,
                tagline="Best for serious users",
                badge="MOST POPULAR",
                monthly_credits=1500,
                max_devices=2,
                cloud_fair_use_tokens=250_000,
                is_recurring=True,
                benefits=[
                    "1,500 AI Credits per month",
                    "Male + Female voice switching",
                    "PDF & document/file analysis",
                    "Research Mode & Personal Knowledge Graph",
                    "AI Coding Assistant & Office/Excel operations",
                    "Gmail, Calendar & Google Drive automation",
                    "Multi-agent workflows within Pro limits",
                    "2-device access · Unlimited chat history",
                ],
                entitlements=pro_entitlements,
            ),
            PlanTier.ADVANCED: PlanDefinition(
                tier=PlanTier.ADVANCED,
                name="Advanced",
                price_inr=299,
                billing_cycle=BillingCycle.MONTHLY,
                tagline="Power users & creators",
                badge="FULL POWER",
                monthly_credits=4000,
                max_devices=5,
                cloud_fair_use_tokens=1_000_000,
                is_recurring=True,
                benefits=[
                    "4,000 AI Credits per month",
                    "Faster premium AI routing & Deep Research",
                    "Advanced coding agent & autonomous computer control",
                    "Filmora, FFmpeg & YouTube Shorts automation",
                    "Custom Agent Builder & Proactive Intelligence",
                    "Developer MCP integrations & custom plugins",
                    "Full Multi-Agent system & advanced workflows",
                    "5-device access · Priority support · BYOK support",
                ],
                entitlements=pro_plus_entitlements,
            ),
            PlanTier.PRO: PlanDefinition(
                tier=PlanTier.PRO,
                name="Pro",
                price_inr=299,
                billing_cycle=BillingCycle.MONTHLY,
                tagline="Best for serious users",
                badge="MOST POPULAR",
                monthly_credits=1500,
                max_devices=2,
                cloud_fair_use_tokens=250_000,
                is_recurring=True,
                benefits=[
                    "1,500 AI Credits per month",
                    "Male + Female voice switching",
                    "PDF & document/file analysis",
                    "Research Mode & Personal Knowledge Graph",
                    "AI Coding Assistant & Office/Excel operations",
                    "Gmail, Calendar & Google Drive automation",
                    "Multi-agent workflows within Pro limits",
                    "2-device access · Unlimited chat history",
                ],
                entitlements=pro_entitlements,
            ),
            PlanTier.PRO_PLUS: PlanDefinition(
                tier=PlanTier.PRO_PLUS,
                name="Pro+",
                price_inr=599,
                billing_cycle=BillingCycle.MONTHLY,
                tagline="Power users & creators",
                badge="BEST VALUE",
                monthly_credits=4000,
                max_devices=5,
                cloud_fair_use_tokens=1_000_000,
                is_recurring=True,
                benefits=[
                    "4,000 AI Credits per month",
                    "Faster premium AI routing & Deep Research",
                    "Advanced coding agent & autonomous computer control",
                    "Filmora, FFmpeg & YouTube Shorts automation",
                    "Custom Agent Builder & Proactive Intelligence",
                    "Developer MCP integrations & custom plugins",
                    "Full Multi-Agent system & advanced workflows",
                    "5-device access · Priority support · BYOK support",
                ],
                entitlements=pro_plus_entitlements,
            ),
            PlanTier.ANNUAL_PRO: PlanDefinition(
                tier=PlanTier.ANNUAL_PRO,
                name="Annual Pro",
                price_inr=2999,
                billing_cycle=BillingCycle.ANNUAL,
                tagline="Best yearly value · VIP Power Pack",
                badge=f"SAVE ₹{savings['annual_saving']}/YEAR",
                monthly_credits=1800,  # 1,800 credits/mo (+300 bonus credits/mo vs Pro)
                max_devices=3,          # 3 devices (vs 2 on monthly Pro)
                cloud_fair_use_tokens=300_000,
                is_recurring=True,
                regular_annual_cost=savings["regular_annual_cost"],
                annual_saving_inr=savings["annual_saving"],
                annual_saving_pct=savings["saving_pct"],
                effective_monthly_inr=savings["effective_monthly"],
                benefits=[
                    "1,800 AI Credits/month (+300 bonus credits every month vs Pro)",
                    "+500 Welcome Bonus Credits upfront on activation",
                    "Unused credit rollover (up to 2,000 credits)",
                    "3 active Windows devices (1 extra device vs monthly Pro)",
                    "Deep Research & Citation Engine unlocked",
                    "Autonomous PC Action & Script Sandbox unlocked",
                    "Self-learning custom skill memory",
                    "Dual voice: Male + Female instant switching",
                    "Priority VIP direct support & SLA guarantees",
                    f"Save ₹{savings['annual_saving']}/year (~{savings['saving_pct']}%) vs monthly",
                    f"Effective rate ≈ ₹{savings['effective_monthly_rounded']}/month",
                ],
                entitlements=annual_pro_entitlements,
            ),
            PlanTier.LIFETIME: PlanDefinition(
                tier=PlanTier.LIFETIME,
                name="Lifetime (Legacy)",
                price_inr=999,
                billing_cycle=BillingCycle.ONE_TIME,
                tagline="Legacy Entitlement",
                badge="BEST LONG-TERM VALUE",
                monthly_credits=2000,
                max_devices=1,
                cloud_fair_use_tokens=200_000,
                is_recurring=False,
                benefits=[
                    "Permanent application feature license (Legacy)",
                    "Preserved entitlement for existing license holders",
                    "All autonomous PC & video studio features",
                    "All voices unlocked permanently",
                ],
                entitlements=lifetime_entitlements,
            ),
        }

    def get_plan(self, tier: PlanTier | str) -> PlanDefinition:
        if isinstance(tier, str):
            t_str = tier.upper().strip()
            tier = PlanTier(t_str)
        t = tier
        if t not in self._plans:
            raise KeyError(f"Plan tier {tier} not found in registry.")
        return self._plans[t]

    def list_plans(self) -> List[PlanDefinition]:
        """All plans in standard test order."""
        order = [
            PlanTier.STARTER,
            PlanTier.BASIC,
            PlanTier.PREMIUM,
            PlanTier.ADVANCED,
            PlanTier.LIFETIME,
        ]
        return [self._plans[t] for t in order if t in self._plans]

    def list_public_plans(self) -> List[PlanDefinition]:
        """Publicly available plans for new purchases (Lifetime excluded)."""
        order = [
            PlanTier.STARTER,
            PlanTier.BASIC,
            PlanTier.PRO,
            PlanTier.PRO_PLUS,
            PlanTier.ANNUAL_PRO,
        ]
        return [self._plans[t] for t in order if t in self._plans]

    def get_required_plan_for_entitlement(self, entitlement: Entitlement) -> PlanTier:
        """Find the lowest tier that grants the given entitlement."""
        order = [PlanTier.STARTER, PlanTier.BASIC, PlanTier.PRO, PlanTier.PRO_PLUS]
        for t in order:
            if entitlement in self._plans[t].entitlements:
                return t
        return PlanTier.PRO_PLUS

    def export_catalog(self) -> List[Dict[str, Any]]:
        """Export reusable catalog JSON for website / mobile / docs."""
        return [
            {
                "tier": p.tier.value,
                "name": p.name,
                "price_inr": p.price_inr,
                "billing_cycle": p.billing_cycle.value,
                "tagline": p.tagline,
                "badge": p.badge,
                "monthly_credits": p.monthly_credits,
                "daily_messages_limit": p.daily_messages_limit,
                "max_devices": p.max_devices,
                "regular_annual_cost": p.regular_annual_cost,
                "annual_saving_inr": p.annual_saving_inr,
                "annual_saving_pct": p.annual_saving_pct,
                "effective_monthly_inr": p.effective_monthly_inr,
                "benefits": p.benefits,
                "entitlements": [e.value for e in p.entitlements],
            }
            for p in self.list_public_plans()
        ]
