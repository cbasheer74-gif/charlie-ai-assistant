"""
JARVIS Phase 11: Model, Provider, and Capability Registries
Maintains available models, metadata, provider configurations, and capabilities.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .models import DeploymentType, ModelCapability, ModelHealthState, ModelSpec

logger = logging.getLogger("jarvis.ai.registry")


class CapabilityRegistry:
    """Tracks mappings between discrete AI capabilities and models."""

    def __init__(self):
        # capability -> list of model_ids
        self._cap_map: Dict[ModelCapability, List[str]] = {cap: [] for cap in ModelCapability}

    def register_model_capabilities(self, model_id: str, capabilities: List[ModelCapability]):
        for cap in capabilities:
            if cap in self._cap_map and model_id not in self._cap_map[cap]:
                self._cap_map[cap].append(model_id)

    def unregister_model(self, model_id: str):
        for cap_list in self._cap_map.values():
            if model_id in cap_list:
                cap_list.remove(model_id)

    def get_models_with_capability(self, capability: ModelCapability) -> List[str]:
        return self._cap_map.get(capability, []).copy()


class ModelRegistry:
    """Manages configured AI models across local and cloud providers."""

    def __init__(self, capability_registry: Optional[CapabilityRegistry] = None):
        self.capability_registry = capability_registry or CapabilityRegistry()
        self._models: Dict[str, ModelSpec] = {}
        self._init_default_models()

    def _init_default_models(self):
        """Initializes default reference models for Local and Cloud."""
        qwen35 = ModelSpec(
            model_id="local_qwen35",
            provider="ollama",
            display_name="Qwen 3.5 Local Agent",
            deployment_type=DeploymentType.LOCAL,
            capabilities=[
                ModelCapability.CHAT, ModelCapability.CODING,
                ModelCapability.REASONING, ModelCapability.VISION,
                ModelCapability.OCR, ModelCapability.TOOL_USE,
                ModelCapability.STRUCTURED_OUTPUT, ModelCapability.LONG_CONTEXT,
            ],
            supports_vision=True,
            context_window=262144,
            max_output=8192,
            coding_strength="HIGH",
            reasoning_strength="HIGH",
            latency_tier="MODERATE",
            priority=18,
        )

        # 1. Local Small / Fast Model (e.g. Llama 3.2 3B / Qwen 2.5 3B)
        m_local_small = ModelSpec(
            model_id="local_fast_small",
            provider="ollama",
            display_name="Local Fast 3B",
            deployment_type=DeploymentType.LOCAL,
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.FAST_CLASSIFICATION,
                ModelCapability.SUMMARIZATION,
                ModelCapability.TOOL_USE,
                ModelCapability.OCR,
            ],
            context_window=8192,
            max_output=2048,
            coding_strength="LOW",
            reasoning_strength="LOW",
            latency_tier="VERY_FAST",
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
            priority=15,
        )

        # 2. Local Coding & Reasoning Model (e.g. Qwen 2.5 Coder 7B / DeepSeek-R1 8B)
        m_local_code = ModelSpec(
            model_id="local_coder_7b",
            provider="ollama",
            display_name="Local Coder 7B",
            deployment_type=DeploymentType.LOCAL,
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.CODING,
                ModelCapability.REASONING,
                ModelCapability.TOOL_USE,
                ModelCapability.STRUCTURED_OUTPUT,
            ],
            context_window=16384,
            max_output=4096,
            coding_strength="MEDIUM",
            reasoning_strength="MEDIUM",
            latency_tier="FAST",
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
            priority=12,
        )

        # 3. Cloud Balanced Coding & Reasoning (e.g. Claude 3.5 Sonnet / GPT-4o)
        m_cloud_strong = ModelSpec(
            model_id="cloud_strong_reasoning",
            provider="openai_compatible",
            display_name="Cloud Premium Reasoning",
            deployment_type=DeploymentType.CLOUD,
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.CODING,
                ModelCapability.REASONING,
                ModelCapability.LONG_CONTEXT,
                ModelCapability.STRUCTURED_OUTPUT,
                ModelCapability.RESEARCH_SYNTHESIS,
                ModelCapability.TOOL_USE,
            ],
            context_window=128000,
            max_output=8192,
            coding_strength="EXPERT",
            reasoning_strength="EXPERT",
            latency_tier="MODERATE",
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
            priority=20,
        )

        # 4. Cloud Vision Model (e.g. GPT-4o Vision / Gemini Flash Vision)
        m_cloud_vision = ModelSpec(
            model_id="cloud_vision_multimodal",
            provider="openai_compatible",
            display_name="Cloud Vision & Multimodal",
            deployment_type=DeploymentType.CLOUD,
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.VISION,
                ModelCapability.OCR,
                ModelCapability.TOOL_USE,
            ],
            supports_vision=True,
            context_window=64000,
            max_output=4096,
            coding_strength="HIGH",
            reasoning_strength="HIGH",
            latency_tier="FAST",
            cost_per_1k_input=0.001,
            cost_per_1k_output=0.004,
            priority=18,
        )

        # 5. Cloud Cheap / Fast Model (e.g. Gemini Flash / Haiku / GPT-4o-mini)
        m_cloud_fast = ModelSpec(
            model_id="cloud_fast_cheap",
            provider="openai_compatible",
            display_name="Cloud Fast Mini",
            deployment_type=DeploymentType.CLOUD,
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.FAST_CLASSIFICATION,
                ModelCapability.SUMMARIZATION,
                ModelCapability.TOOL_USE,
            ],
            context_window=32000,
            max_output=4096,
            coding_strength="LOW",
            reasoning_strength="LOW",
            latency_tier="VERY_FAST",
            cost_per_1k_input=0.00015,
            cost_per_1k_output=0.0006,
            priority=8,
        )

        for m in [qwen35, m_local_small, m_local_code, m_cloud_strong, m_cloud_vision, m_cloud_fast]:
            self.register_model(m)

    def register_model(self, model: ModelSpec):
        self._models[model.model_id] = model
        self.capability_registry.register_model_capabilities(model.model_id, model.capabilities)
        logger.info(f"Registered model {model.model_id} ({model.deployment_type.value})")

    def unregister_model(self, model_id: str):
        if model_id in self._models:
            del self._models[model_id]
            self.capability_registry.unregister_model(model_id)

    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        return self._models.get(model_id)

    def list_models(
        self,
        deployment: Optional[DeploymentType] = None,
        only_healthy: bool = True,
        only_enabled: bool = True,
    ) -> List[ModelSpec]:
        res = []
        for m in self._models.values():
            if only_enabled and not m.enabled:
                continue
            if only_healthy and m.health_state == ModelHealthState.UNAVAILABLE:
                continue
            if deployment and m.deployment_type != deployment:
                continue
            res.append(m)
        return sorted(res, key=lambda x: x.priority, reverse=True)

    def update_health(self, model_id: str, state: ModelHealthState):
        if model_id in self._models:
            self._models[model_id].health_state = state
            logger.info(f"Updated health for {model_id} -> {state.value}")


class ProviderRegistry:
    """Registry of active provider instances."""

    def __init__(self):
        self._providers: Dict[str, Any] = {}

    def register_provider(self, provider_id: str, provider_instance: Any):
        self._providers[provider_id] = provider_instance

    def get_provider(self, provider_id: str) -> Optional[Any]:
        return self._providers.get(provider_id)

    def list_providers(self) -> List[str]:
        return list(self._providers.keys())
