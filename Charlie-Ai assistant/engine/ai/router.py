"""
JARVIS Phase 11: Model Router, Routing Policies & Vision Router
Routes tasks to the optimal local or cloud model based on capability, privacy, complexity, and cost.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    ComplexityLevel,
    DeploymentType,
    ModelCapability,
    ModelHealthState,
    ModelSpec,
    PrivacyLevel,
    RoutingDecision,
    RoutingPolicy,
    TaskProfile,
)
from .registry import ModelRegistry

logger = logging.getLogger("jarvis.ai.router")


class VisionRouter:
    """Decides whether a visual query can be handled via OCR/accessibility or requires cloud vision."""

    @staticmethod
    def route_vision_request(has_complex_layout: bool = False, requires_color_analysis: bool = False) -> str:
        if not has_complex_layout and not requires_color_analysis:
            return "LOCAL_OCR"
        return "CLOUD_VISION"


class ModelSelectionExplainer:
    """Generates concise, human-readable explanations of routing decisions without leaking chain-of-thought."""

    @staticmethod
    def explain(decision: RoutingDecision, profile: TaskProfile) -> str:
        if decision.is_deterministic:
            return f"Task '{profile.task_type}' is deterministic ({profile.complexity.value}). Executed via rule engine with zero LLM tokens."

        if not decision.chosen_model:
            return f"No suitable model found matching required capabilities: {[c.value for c in profile.required_capabilities]}."

        m = decision.chosen_model
        reasons = []

        if decision.local_only_enforced:
            reasons.append(f"privacy policy enforces local-only ({profile.privacy_level.value})")
        elif m.deployment_type == DeploymentType.LOCAL:
            reasons.append(f"task complexity ({profile.complexity.value}) fits local model '{m.display_name}'")
        else:
            reasons.append(f"task complexity ({profile.complexity.value}) requires cloud reasoning/coding power")

        if ModelCapability.CODING in profile.required_capabilities:
            reasons.append(f"coding strength: {m.coding_strength}")

        return f"Selected {m.display_name} ({m.deployment_type.value}) because " + ", and ".join(reasons) + "."


class ModelRouter:
    """Orchestrates model selection, fallback chains, and policy enforcement."""

    def __init__(self, registry: ModelRegistry, default_policy: RoutingPolicy = RoutingPolicy.BALANCED):
        self.registry = registry
        self.policy = default_policy
        self.vision_router = VisionRouter()
        self.explainer = ModelSelectionExplainer()
        self.budget_capped = False
        self.offline_mode = False

    def route(
        self,
        profile: TaskProfile,
        policy_override: Optional[RoutingPolicy] = None,
        user_model_override: Optional[str] = None,
    ) -> RoutingDecision:
        """Determines the optimal model and fallback chain for a task."""
        policy = policy_override or self.policy

        # 1. Deterministic Rule Engine Bypass
        if profile.requires_deterministic_only:
            dec = RoutingDecision(
                task_id=profile.task_id,
                chosen_model=None,
                fallback_chain=[],
                is_deterministic=True,
                deterministic_action="EXECUTE_DETERMINISTIC_TOOL",
                reasoning="Deterministic task bypassed LLM completely.",
                estimated_cost=0.0,
            )
            return dec

        # 2. Check for Manual User Model Override
        if user_model_override:
            m = self.registry.get_model(user_model_override)
            if m and m.health_state != ModelHealthState.UNAVAILABLE:
                return RoutingDecision(
                    task_id=profile.task_id,
                    chosen_model=m,
                    fallback_chain=self._build_fallback_chain(m, profile),
                    reasoning=f"User manually requested model override: {m.display_name}.",
                    estimated_cost=m.cost_per_1k_input * (profile.estimated_context_tokens / 1000.0),
                )

        # 3. Privacy Enforcement
        enforce_local = (
            profile.privacy_level in (PrivacyLevel.HIGHLY_SENSITIVE, PrivacyLevel.SECRET)
            or policy in (RoutingPolicy.LOCAL_FIRST, RoutingPolicy.PRIVACY_FIRST)
            or self.offline_mode
            or self.budget_capped
        )

        # 4. Filter Available Healthy Models
        available_models = self.registry.list_models(
            deployment=DeploymentType.LOCAL if enforce_local else None,
            only_healthy=True,
            only_enabled=True,
        )

        # 5. Filter by Capabilities
        eligible_models = []
        for m in available_models:
            meets_all_caps = all(m.has_capability(cap) for cap in profile.required_capabilities)
            if meets_all_caps:
                eligible_models.append(m)

        if not eligible_models:
            # Handle capability mismatch or missing local capability
            return RoutingDecision(
                task_id=profile.task_id,
                chosen_model=None,
                fallback_chain=[],
                reasoning=f"Capability mismatch: No available model satisfies {[c.value for c in profile.required_capabilities]}.",
                local_only_enforced=enforce_local,
            )

        # 6. Rank Models Based on Policy and Complexity
        chosen_model = self._select_best_model(eligible_models, profile, policy, enforce_local)
        fallback_chain = self._build_fallback_chain(chosen_model, profile)

        cost = (profile.estimated_context_tokens / 1000.0) * chosen_model.cost_per_1k_input + (
            profile.estimated_output_tokens / 1000.0
        ) * chosen_model.cost_per_1k_output

        decision = RoutingDecision(
            task_id=profile.task_id,
            chosen_model=chosen_model,
            fallback_chain=fallback_chain,
            is_deterministic=False,
            reasoning=self.explainer.explain(
                RoutingDecision(
                    task_id=profile.task_id,
                    chosen_model=chosen_model,
                    fallback_chain=fallback_chain,
                    local_only_enforced=enforce_local,
                ),
                profile,
            ),
            estimated_cost=round(cost, 6),
            local_only_enforced=enforce_local,
        )

        return decision

    def _select_best_model(
        self, models: List[ModelSpec], profile: TaskProfile, policy: RoutingPolicy, enforce_local: bool
    ) -> ModelSpec:
        """Selects the best model according to policy and complexity."""
        # If complexity is TRIVIAL or LOW, prioritize local or cheap models
        if profile.complexity in (ComplexityLevel.TRIVIAL, ComplexityLevel.LOW) or policy == RoutingPolicy.COST_SAVER:
            # Prefer local zero-cost first
            locals_found = [m for m in models if m.deployment_type == DeploymentType.LOCAL]
            if locals_found:
                return locals_found[0]
            # Next cheapest cloud
            return min(models, key=lambda m: m.cost_per_1k_input)

        # If complexity is HIGH or EXPERT
        if profile.complexity in (ComplexityLevel.HIGH, ComplexityLevel.EXPERT):
            if not enforce_local:
                # Prefer cloud strong model with expert coding/reasoning
                clouds = [m for m in models if m.deployment_type == DeploymentType.CLOUD and m.coding_strength == "EXPERT"]
                if clouds:
                    return clouds[0]
            # If local enforced, select strongest local model (highest priority)
            return models[0]

        # Balanced / Default
        if enforce_local:
            return models[0]

        # In balanced mode, use local unless complexity >= MEDIUM and cloud is available
        if profile.complexity == ComplexityLevel.MEDIUM and policy == RoutingPolicy.QUALITY_FIRST:
            clouds = [m for m in models if m.deployment_type == DeploymentType.CLOUD]
            if clouds:
                return clouds[0]

        return models[0]

    def _build_fallback_chain(self, primary: ModelSpec, profile: TaskProfile) -> List[ModelSpec]:
        """Builds fallback list of models sharing the required capabilities."""
        all_models = self.registry.list_models(only_healthy=True, only_enabled=True)
        fallbacks = []
        for m in all_models:
            if m.model_id != primary.model_id:
                if all(m.has_capability(cap) for cap in profile.required_capabilities):
                    fallbacks.append(m)
        return fallbacks
