"""
JARVIS Phase 11: Multi-Model AI Enums and Dataclasses
Defines deployment types, model capabilities, complexity/privacy tiers, routing policies, and task profiles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time


class DeploymentType(str, Enum):
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"


class ModelCapability(str, Enum):
    CHAT = "CHAT"
    CODING = "CODING"
    REASONING = "REASONING"
    VISION = "VISION"
    OCR = "OCR"
    EMBEDDING = "EMBEDDING"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    TOOL_USE = "TOOL_USE"
    LONG_CONTEXT = "LONG_CONTEXT"
    FAST_CLASSIFICATION = "FAST_CLASSIFICATION"
    SUMMARIZATION = "SUMMARIZATION"
    CREATIVE_WRITING = "CREATIVE_WRITING"
    RESEARCH_SYNTHESIS = "RESEARCH_SYNTHESIS"
    AUDIO = "AUDIO"


class ComplexityLevel(str, Enum):
    TRIVIAL = "TRIVIAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXPERT = "EXPERT"


class PrivacyLevel(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    PRIVATE = "PRIVATE"
    HIGHLY_SENSITIVE = "HIGHLY_SENSITIVE"
    SECRET = "SECRET"


class RoutingPolicy(str, Enum):
    QUALITY_FIRST = "QUALITY_FIRST"
    BALANCED = "BALANCED"
    COST_SAVER = "COST_SAVER"
    LOCAL_FIRST = "LOCAL_FIRST"
    PRIVACY_FIRST = "PRIVACY_FIRST"
    SPEED_FIRST = "SPEED_FIRST"


class ModelHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class NetworkState(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


@dataclass
class ModelSpec:
    model_id: str
    provider: str
    display_name: str
    deployment_type: DeploymentType
    capabilities: List[ModelCapability] = field(default_factory=list)
    context_window: int = 8192
    max_output: int = 4096
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    supports_structured_output: bool = True
    coding_strength: str = "MEDIUM"  # LOW, MEDIUM, HIGH, EXPERT
    reasoning_strength: str = "MEDIUM"  # LOW, MEDIUM, HIGH, EXPERT
    latency_tier: str = "FAST"  # VERY_FAST, FAST, MODERATE, SLOW
    cost_per_1k_input: float = 0.0  # USD
    cost_per_1k_output: float = 0.0  # USD
    privacy_compliant: bool = True
    health_state: ModelHealthState = ModelHealthState.HEALTHY
    enabled: bool = True
    priority: int = 10  # Higher = preferred
    last_verified_at: float = field(default_factory=time.time)

    def has_capability(self, cap: ModelCapability) -> bool:
        return cap in self.capabilities


@dataclass
class TaskProfile:
    task_id: str
    task_type: str  # e.g., "CODING_DEBUG", "SIMPLE_COMMAND", "SUMMARY", "VISION_INSPECT"
    complexity: ComplexityLevel = ComplexityLevel.LOW
    privacy_level: PrivacyLevel = PrivacyLevel.INTERNAL
    required_capabilities: List[ModelCapability] = field(default_factory=list)
    estimated_context_tokens: int = 500
    estimated_output_tokens: int = 200
    latency_priority: str = "MODERATE"  # HIGH, MODERATE, LOW
    quality_priority: str = "MODERATE"  # HIGH, MODERATE, LOW
    cost_priority: str = "MODERATE"  # HIGH, MODERATE, LOW
    requires_offline: bool = False
    requires_deterministic_only: bool = False
    redacted_secrets: List[str] = field(default_factory=list)


@dataclass
class RoutingDecision:
    task_id: str
    chosen_model: Optional[ModelSpec]
    fallback_chain: List[ModelSpec] = field(default_factory=list)
    is_deterministic: bool = False
    deterministic_action: Optional[str] = None
    reasoning: str = ""
    estimated_cost: float = 0.0
    privacy_enforced: bool = True
    local_only_enforced: bool = False


@dataclass
class TokenUsageRecord:
    timestamp: float
    task_id: str
    provider: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    estimated_cost: float = 0.0


@dataclass
class ModelBenchmarkResult:
    benchmark_id: str
    model_id: str
    task_type: str
    passed: bool
    latency_seconds: float
    score: float
    timestamp: float = field(default_factory=time.time)
