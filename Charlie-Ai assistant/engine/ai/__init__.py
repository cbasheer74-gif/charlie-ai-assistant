"""
charlie Phase 11: Multi-Model Intelligence Package
Exposes model orchestration, registry, routing, budget, caching, and offline AI components.
"""

from .cache import ResponseCache
from .compiler_validator import PromptCompiler, ResponseValidator
from .context_budget import ContextBudgetManager, CostManager, SemanticContextCompressor, TokenBudgetManager
from .core import ModelIntelligenceLayer
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
    TokenUsageRecord,
)
from .offline import OfflineAIManager
from .performance import ModelPerformanceTracker
from .profiler import ComplexityEstimator, PrivacyClassifier, TaskProfiler
from .providers import BaseModelProvider, CloudProvider, LocalProvider
from .registry import CapabilityRegistry, ModelRegistry, ProviderRegistry
from .router import ModelRouter, ModelSelectionExplainer, VisionRouter

__all__ = [
    "ModelIntelligenceLayer",
    "ModelRegistry",
    "ProviderRegistry",
    "CapabilityRegistry",
    "HardwareProfiler",
    "BaseModelProvider",
    "LocalProvider",
    "CloudProvider",
    "TaskProfiler",
    "ComplexityEstimator",
    "PrivacyClassifier",
    "ModelRouter",
    "VisionRouter",
    "ModelSelectionExplainer",
    "ContextBudgetManager",
    "TokenBudgetManager",
    "CostManager",
    "SemanticContextCompressor",
    "ResponseCache",
    "ModelHealthManager",
    "FallbackManager",
    "OfflineAIManager",
    "PromptCompiler",
    "ResponseValidator",
    "ModelPerformanceTracker",
    "DeploymentType",
    "ModelCapability",
    "ComplexityLevel",
    "PrivacyLevel",
    "RoutingPolicy",
    "ModelHealthState",
    "NetworkState",
    "ModelSpec",
    "TaskProfile",
    "RoutingDecision",
    "TokenUsageRecord",
]
