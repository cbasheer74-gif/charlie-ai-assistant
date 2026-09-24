"""
JARVIS Phase 11: Master AI Orchestration Layer
Unified ModelIntelligenceLayer connecting Task Profiler, Privacy, Router, Budget, Cache,
Offline Engine, and Verification.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .cache import ResponseCache
from .compiler_validator import PromptCompiler, ResponseValidator
from .context_budget import ContextBudgetManager, CostManager, SemanticContextCompressor, TokenBudgetManager
from .hardware import HardwareProfiler
from .health_fallback import FallbackManager, ModelHealthManager
from .models import (
    ComplexityLevel,
    DeploymentType,
    ModelCapability,
    ModelHealthState,
    ModelSpec,
    NetworkState,
    PrivacyLevel,
    RoutingDecision,
    RoutingPolicy,
    TaskProfile,
)
from .offline import OfflineAIManager
from .performance import ModelPerformanceTracker
from .profiler import TaskProfiler
from .providers import CloudProvider, LocalProvider
from .registry import CapabilityRegistry, ModelRegistry, ProviderRegistry
from .router import ModelRouter, VisionRouter

logger = logging.getLogger("jarvis.ai.core")


class ModelIntelligenceLayer:
    """Master Multi-Model Intelligence Layer for JARVIS."""

    def __init__(self):
        # 1. Registries & Hardware
        self.capability_registry = CapabilityRegistry()
        self.model_registry = ModelRegistry(self.capability_registry)
        self.provider_registry = ProviderRegistry()
        self.hardware_profiler = HardwareProfiler()

        # 2. Providers
        self.local_provider = LocalProvider()
        self.cloud_provider = CloudProvider()
        self.provider_registry.register_provider("ollama", self.local_provider)
        self.provider_registry.register_provider("openai_compatible", self.cloud_provider)

        # 3. Profilers & Routers
        self.task_profiler = TaskProfiler()
        self.router = ModelRouter(self.model_registry)
        self.vision_router = VisionRouter()

        # 4. Context & Budget
        self.context_budget = ContextBudgetManager()
        self.token_budget = TokenBudgetManager()
        self.cost_manager = CostManager()
        self.context_compressor = SemanticContextCompressor()

        # 5. Cache & Performance
        self.cache = ResponseCache()
        self.health_manager = ModelHealthManager()
        self.fallback_manager = FallbackManager(self.health_manager)
        self.performance_tracker = ModelPerformanceTracker()

        # 6. Compiler, Validator & Offline
        self.compiler = PromptCompiler()
        self.validator = ResponseValidator()
        self.offline_manager = OfflineAIManager()

        logger.info("ModelIntelligenceLayer initialized.")

    def process_request(
        self,
        prompt: str,
        user_metadata: Optional[Dict[str, Any]] = None,
        file_contents: Optional[Dict[str, str]] = None,
        policy_override: Optional[RoutingPolicy] = None,
        user_model_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full Pipeline Execution:
        USER REQUEST -> TASK PROFILE -> PRIVACY CHECK -> CACHE -> ROUTER -> PROMPT COMPILER -> MODEL -> VALIDATION
        """
        meta = user_metadata or {}

        # 1. Task Profiling & Privacy Classification
        profile, sanitized_prompt = self.task_profiler.profile_task(prompt, user_metadata=meta)

        # 2. Check Deterministic Bypass
        if profile.requires_deterministic_only:
            return {
                "success": True,
                "is_deterministic": True,
                "action": "EXECUTE_DETERMINISTIC",
                "message": f"Deterministic execution: {sanitized_prompt}",
                "model_used": None,
                "tokens_used": 0,
                "cost_usd": 0.0,
            }

        # 3. Check Semantic Cache
        cached = self.cache.get(sanitized_prompt, file_contents=file_contents)
        if cached:
            return {
                "success": True,
                "from_cache": True,
                "response": cached,
                "model_used": "cache",
                "tokens_used": 0,
                "cost_usd": 0.0,
            }

        # 4. Enforce Offline / Budget Settings on Router
        self.router.offline_mode = self.offline_manager.is_offline()
        self.router.budget_capped = self.cost_manager.is_cost_cap_reached() or self.token_budget.is_daily_cap_exceeded()

        # 5. Model Routing
        decision = self.router.route(
            profile,
            policy_override=policy_override,
            user_model_override=user_model_override,
        )

        if not decision.chosen_model:
            return {
                "success": False,
                "error": decision.reasoning,
                "details": "No available model satisfies task requirements.",
            }

        chosen_model = decision.chosen_model

        # 6. Modular Prompt Compilation
        compiled_prompt = self.compiler.compile(
            task_type=profile.task_type,
            user_prompt=sanitized_prompt,
            additional_context="\n".join(f"{k}: {v[:200]}" for k, v in file_contents.items()) if file_contents else None,
        )

        # 7. Execution with Fallback Chain
        def execute_fn(model: ModelSpec) -> Dict[str, Any]:
            provider = self.provider_registry.get_provider(model.provider)
            if not provider:
                raise ValueError(f"Provider '{model.provider}' not registered.")
            return provider.generate(model=model, prompt=compiled_prompt)

        ok, result, final_model_id = self.fallback_manager.execute_with_fallback(
            primary_model=chosen_model,
            fallback_chain=decision.fallback_chain,
            execute_fn=execute_fn,
        )

        if not ok:
            return {
                "success": False,
                "error": result.get("error", "Execution failed across all fallback models."),
                "decision": decision,
            }

        # 8. Record Usage & Budget Accounting
        in_toks = result.get("input_tokens", 100)
        out_toks = result.get("output_tokens", 50)
        cost = result.get("cost_usd", 0.0)

        self.token_budget.record_usage(
            task_id=profile.task_id,
            provider=chosen_model.provider,
            model_id=final_model_id,
            input_tokens=in_toks,
            output_tokens=out_toks,
            cost=cost,
        )
        self.cost_manager.add_cost(cost)
        self.performance_tracker.record_run(
            model_id=final_model_id,
            task_type=profile.task_type,
            passed=True,
            latency_seconds=result.get("duration_seconds", 0.1),
        )

        # 9. Store in Cache if eligible
        if profile.privacy_level != PrivacyLevel.SECRET:
            self.cache.put(sanitized_prompt, result, file_contents=file_contents)

        return {
            "success": True,
            "response": result,
            "decision": decision,
            "model_used": final_model_id,
            "tokens_used": in_toks + out_toks,
            "cost_usd": cost,
            "privacy_level": profile.privacy_level.value,
        }
