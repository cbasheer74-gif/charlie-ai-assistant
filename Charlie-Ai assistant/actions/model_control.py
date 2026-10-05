"""
CHARLIE Phase 11: Model Control Actions
High-level commands for inspecting model routing, token usage, budgets, and toggling offline/privacy modes.
"""

from typing import Any, Dict, List, Optional
from engine.ai.core import ModelIntelligenceLayer
from engine.ai.models import NetworkState, RoutingPolicy


class ModelControlActions:
    """Assistant action tools for multi-model intelligence."""

    def __init__(self, ai_layer: Optional[ModelIntelligenceLayer] = None):
        self.ai = ai_layer or ModelIntelligenceLayer()

    def get_model_dashboard(self) -> Dict[str, Any]:
        """Returns concise status of models, budget, tokens, and active policy."""
        models = self.ai.model_registry.list_models()
        return {
            "active_policy": self.ai.router.policy.value,
            "offline_mode": self.ai.offline_manager.is_offline(),
            "today_tokens": self.ai.token_budget.get_today_tokens(),
            "today_cost_usd": self.ai.cost_manager.get_spent_today(),
            "available_models_count": len(models),
            "models": [
                {
                    "id": m.model_id,
                    "name": m.display_name,
                    "type": m.deployment_type.value,
                    "health": m.health_state.value,
                    "cost_in": m.cost_per_1k_input,
                }
                for m in models
            ],
        }

    def set_routing_policy(self, policy_name: str) -> Dict[str, Any]:
        """Changes the active routing policy."""
        try:
            policy = RoutingPolicy(policy_name.upper())
            self.ai.router.policy = policy
            return {"success": True, "message": f"Routing policy set to {policy.value}."}
        except ValueError:
            return {
                "success": False,
                "error": f"Unknown policy '{policy_name}'. Choose from: {[p.value for p in RoutingPolicy]}",
            }

    def toggle_offline_mode(self, enable: bool) -> Dict[str, Any]:
        """Toggles offline AI mode."""
        state = NetworkState.OFFLINE if enable else NetworkState.ONLINE
        self.ai.offline_manager.set_network_state(state)
        self.ai.router.offline_mode = enable
        return {
            "success": True,
            "offline_mode": enable,
            "message": f"Offline AI mode {'ENABLED (Cloud disabled)' if enable else 'DISABLED (Cloud enabled)'}.",
        }

    def get_hardware_recommendations(self) -> Dict[str, Any]:
        """Returns hardware specifications and recommended local model sizes."""
        return self.ai.hardware_profiler.get_hardware_profile()
