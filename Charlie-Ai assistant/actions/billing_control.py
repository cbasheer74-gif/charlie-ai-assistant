"""
actions/billing_control.py — Assistant Action Tool for Commercial Plans, Billing, and Quotas.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from engine.commercial.core import get_commercial_engine
from engine.commercial.models import Entitlement, PlanTier


def billing_control(parameters: dict, **_unused) -> str:
    """Entry point action for querying plan status, checking entitlements, or viewing pricing."""
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()
    engine = get_commercial_engine()

    try:
        if action == "status":
            account = engine.get_account()
            time_status = engine.get_starter_time_status()
            devices = engine.device_mgr.list_user_devices(account.user_id)
            quota = engine.quota_mgr.get_quota_state(account)

            lines = [
                "### CHARLIE Commercial & Subscription Status",
                f"- **Account User ID**: `{account.user_id}`",
                f"- **Current Plan**: **{account.plan.value}**",
                f"- **Subscription Status**: {account.subscription_status.value}",
            ]

            if time_status["is_starter"]:
                lines.append(f"- **Daily Allowance**: {time_status['used_str']} used / {time_status['rem_str']} remaining")
                lines.append(f"- **Quota Exhausted**: {'YES (Upgrade Required)' if time_status['is_exhausted'] else 'NO'}")
            else:
                lines.append("- **Application Time**: Unlimited")

            lines.append(f"- **Active Device Seats**: {len(devices)} active")
            lines.append(f"- **Cloud AI Mode**: {'BYOK (User Private Key)' if quota.byok_active else f'Included Quota ({quota.tokens_consumed:,} / {quota.tokens_total_allowance:,} tokens)'}")

            if account.cancel_at_period_end:
                lines.append("- **Note**: Subscription scheduled to cancel at end of current period.")

            return "\n".join(lines)

        if action == "catalog":
            plans = engine.plan_registry.list_plans()
            lines = ["### Available CHARLIE Commercial Plans:"]
            for p in plans:
                price = f"₹{p.price_inr}/mo" if p.is_recurring else (f"₹{p.price_inr} one-time" if p.price_inr > 0 else "FREE")
                badge_str = f" [{p.badge}]" if p.badge else ""
                lines.append(f"- **{p.name}** ({price}){badge_str}: {p.tagline}")
            return "\n".join(lines)

        if action == "check_feature":
            feature_name = str(params.get("feature") or "").strip().upper()
            try:
                ent = Entitlement(feature_name)
                res = engine.can_use(ent)
                if res.allowed:
                    return f"Feature **{feature_name}** is **UNLOCKED** on your current plan ({engine.get_account().plan.value})."
                return f"Feature **{feature_name}** is **LOCKED**. {res.reason}"
            except ValueError:
                return f"Unknown entitlement: {feature_name}"

        return f"Unknown billing action: {action}"
    except Exception as e:
        return f"Billing Control error: {str(e)}"
