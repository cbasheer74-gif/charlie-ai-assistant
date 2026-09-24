"""
engine/commercial/paywall_manager.py — Paywall Modals, Cooldown Rate-Limiting, and Comparison Matrix.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .models import Entitlement, GateResult, PlanTier
from .plan_registry import PlanRegistry

logger = logging.getLogger("jarvis.commercial.paywall")


class PaywallManager:
    """Manages paywall triggers, upsell rate-limiting, and locked modal payloads."""

    UPSELL_COOLDOWN_SEC = 60.0  # Prevent spamming modals repeatedly

    def __init__(self, plan_registry: PlanRegistry):
        self.registry = plan_registry
        self._last_modal_shown_time: float = 0.0

    def should_suppress_upsell(self) -> bool:
        """Rate-limits visual upsell dialogs to avoid disrupting user workflows."""
        now = time.monotonic()
        if (now - self._last_modal_shown_time) < self.UPSELL_COOLDOWN_SEC:
            return True
        return False

    def mark_modal_displayed(self) -> None:
        self._last_modal_shown_time = time.monotonic()

    def get_starter_paywall_payload(self) -> Dict[str, Any]:
        """Generates exact copy payload for Starter 10-minute exhaustion modal."""
        self.mark_modal_displayed()
        return {
            "type": "STARTER_DAILY_LIMIT",
            "title": "Today's free CHARLIE time is complete.",
            "message": (
                "You've used your 10 free minutes for today. "
                "Upgrade for uninterrupted CHARLIE access, or continue tomorrow when your free allowance resets."
            ),
            "primary_button": "Upgrade Now",
            "secondary_button": "View Plans",
            "dismiss_button": "Come Back Tomorrow",
            "allows_app_browsing": True,
        }

    def get_feature_locked_payload(self, gate_result: GateResult) -> Dict[str, Any]:
        """Generates locked feature notification/modal payload."""
        req_plan = gate_result.required_plan or PlanTier.BASIC
        plan_def = self.registry.get_plan(req_plan)
        return {
            "type": "FEATURE_LOCKED",
            "title": f"Feature Locked ({gate_result.entitlement.value})",
            "message": f"This capability requires {plan_def.name} ({req_plan.value}) or higher.",
            "required_plan": req_plan.value,
            "plan_price": f"₹{plan_def.price_inr}",
            "plan_tagline": plan_def.tagline,
            "button_text": f"Upgrade to {plan_def.name}",
        }


class PricingUIManager:
    """Provides presentation-ready catalog data and complete feature comparison matrix."""

    FEATURE_COMPARISON_ROWS = [
        # 1. Usage Allowance & Pricing
        ("Monthly / Base Price", {"STARTER": "₹0", "BASIC": "₹149 / mo", "PRO": "₹299 / mo", "PRO_PLUS": "₹599 / mo", "ANNUAL_PRO": "₹2,999 / yr (Save ₹589)"}),
        ("Monthly Credits", {"STARTER": "15 msgs/day", "BASIC": "500 credits", "PRO": "1,500 credits", "PRO_PLUS": "4,000 credits", "ANNUAL_PRO": "1,800 credits (+300 bonus)"}),
        ("Welcome Bonus Credits", {"STARTER": "—", "BASIC": "—", "PRO": "—", "PRO_PLUS": "—", "ANNUAL_PRO": "✓ +500 Credits"}),
        ("Credit Rollover", {"STARTER": "—", "BASIC": "—", "PRO": "—", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓ Up to 2,000 cr"}),
        ("Effective Rate", {"STARTER": "₹0", "BASIC": "₹149 / mo", "PRO": "₹299 / mo", "PRO_PLUS": "₹599 / mo", "ANNUAL_PRO": "≈₹250 / mo"}),
        ("Active Devices", {"STARTER": "1 PC", "BASIC": "1 PC", "PRO": "2 PCs", "PRO_PLUS": "5 PCs", "ANNUAL_PRO": "3 PCs (+1 Extra)"}),
        ("Credit Add-on Packs", {"STARTER": "—", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),

        # 2. Voice & Core Intelligence
        ("Male Voice Engine", {"STARTER": "✓", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("Female Voice Engine", {"STARTER": "—", "BASIC": "—", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("Dual Voice Switching", {"STARTER": "—", "BASIC": "—", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("Whisper Audio Transcription", {"STARTER": "✓", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("Contextual Memory", {"STARTER": "Basic", "BASIC": "Standard", "PRO": "Advanced Graph", "PRO_PLUS": "Deep Knowledge", "ANNUAL_PRO": "Advanced Graph"}),
        ("Offline Model Routing", {"STARTER": "—", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),

        # 3. Desktop Autonomy & Tools
        ("App Launcher & Snapper", {"STARTER": "✓", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("Bulk File Organizer", {"STARTER": "—", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("Mouse & Keyboard Control", {"STARTER": "—", "BASIC": "—", "PRO": "Basic Hooks", "PRO_PLUS": "Autonomous Vision", "ANNUAL_PRO": "Enhanced Hooks"}),
        ("Terminal Sandbox", {"STARTER": "—", "BASIC": "Standard", "PRO": "Advanced", "PRO_PLUS": "Full Root Sandbox", "ANNUAL_PRO": "Advanced"}),
        ("Web Research Agent", {"STARTER": "—", "BASIC": "Basic Summary", "PRO": "Multi-source Deep", "PRO_PLUS": "Crawl & Extract", "ANNUAL_PRO": "Deep Research & Citations"}),
        ("Playwright Automation", {"STARTER": "—", "BASIC": "—", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("Excel & Data Modeling", {"STARTER": "—", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),

        # 4. Creative & Video Production
        ("FFmpeg Automation", {"STARTER": "—", "BASIC": "—", "PRO": "Basic Cuts", "PRO_PLUS": "NVENC Studio", "ANNUAL_PRO": "Basic Cuts"}),
        ("Filmora 14 Studio", {"STARTER": "—", "BASIC": "—", "PRO": "Timeline Hook", "PRO_PLUS": "Full Automation", "ANNUAL_PRO": "Timeline Hook"}),
        ("Auto-cut Silence", {"STARTER": "—", "BASIC": "—", "PRO": "—", "PRO_PLUS": "✓ Native", "ANNUAL_PRO": "—"}),
        ("Dynamic Subtitle Sync", {"STARTER": "—", "BASIC": "—", "PRO": "Standard", "PRO_PLUS": "Kinetic Sync", "ANNUAL_PRO": "Standard"}),
        ("YouTube Auto-Publish", {"STARTER": "—", "BASIC": "—", "PRO": "—", "PRO_PLUS": "✓ Direct API", "ANNUAL_PRO": "—"}),

        # 5. Developer & Extensibility
        ("Multi-Agent Task Graph", {"STARTER": "—", "BASIC": "—", "PRO": "✓", "PRO_PLUS": "✓ Complex DAG", "ANNUAL_PRO": "✓"}),
        ("Custom Python Plugins", {"STARTER": "—", "BASIC": "—", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("MCP Protocol Tools", {"STARTER": "—", "BASIC": "—", "PRO": "—", "PRO_PLUS": "✓ Unlimited", "ANNUAL_PRO": "—"}),
        ("Local LLM Endpoints", {"STARTER": "—", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("Self-Correction Loop", {"STARTER": "—", "BASIC": "Single Retry", "PRO": "Multi-turn Loop", "PRO_PLUS": "DAG Rollback", "ANNUAL_PRO": "Multi-turn Loop"}),

        # 6. Security, Licensing & Support
        ("Zero Telemetry", {"STARTER": "✓", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("RSA-2048 Signed License", {"STARTER": "✓", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("Encrypted Local DB", {"STARTER": "✓", "BASIC": "✓", "PRO": "✓", "PRO_PLUS": "✓", "ANNUAL_PRO": "✓"}),
        ("Customer Support", {"STARTER": "Community", "BASIC": "Email", "PRO": "Priority Email", "PRO_PLUS": "VIP Dedicated", "ANNUAL_PRO": "VIP 1-on-1 Direct Support"}),
        ("Inference Priority", {"STARTER": "Standard", "BASIC": "Standard", "PRO": "High", "PRO_PLUS": "Ultra Top", "ANNUAL_PRO": "High"}),
        ("Annual Savings", {"STARTER": "—", "BASIC": "—", "PRO": "—", "PRO_PLUS": "—", "ANNUAL_PRO": "Save ₹589 (~16.4%)"}),
    ]

    def __init__(self, plan_registry: PlanRegistry):
        self.registry = plan_registry

    def get_comparison_table(self) -> List[Dict[str, Any]]:
        """Returns structured comparison matrix for UI rendering."""
        return [
            {
                "feature": row[0],
                "starter": row[1].get("STARTER", "—"),
                "basic": row[1].get("BASIC", "—"),
                "pro": row[1].get("PRO", "—"),
                "pro_plus": row[1].get("PRO_PLUS", "—"),
                "annual_pro": row[1].get("ANNUAL_PRO", "—"),
            }
            for row in self.FEATURE_COMPARISON_ROWS
        ]
