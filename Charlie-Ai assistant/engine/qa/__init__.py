"""
JARVIS Phase 13: QA, Observability & Certification Package
Exposes QualityPlatform, EvidenceRegistry, TraceManager, MetricsManager, Evaluators, and CertificationEngine.
"""

from .certification import ProductionCertificationEngine, QualityGateManager, RegressionEngine
from .core import QualityPlatform
from .evaluators import (
    ChaosTestEngine,
    CodingEvaluator,
    ComputerControlEvaluator,
    MemoryEvaluationEngine,
    VoiceEvaluator,
)
from .evidence import EvidenceRegistry
from .models import (
    CertificationStatus,
    EvaluationResult,
    EvidenceRecord,
    FailureSeverity,
    GoldenScenario,
    MetricRecord,
    QualityGate,
    QualityGateStatus,
    ReleaseDecision,
    ReleaseReadinessReport,
    TraceSpan,
)
from .observability import MetricsManager, ObservabilityEngine, TraceManager
from .scenarios import GoldenScenarioRunner

__all__ = [
    "QualityPlatform",
    "EvidenceRegistry",
    "ObservabilityEngine",
    "TraceManager",
    "MetricsManager",
    "MemoryEvaluationEngine",
    "ComputerControlEvaluator",
    "CodingEvaluator",
    "VoiceEvaluator",
    "ChaosTestEngine",
    "GoldenScenarioRunner",
    "QualityGateManager",
    "RegressionEngine",
    "ProductionCertificationEngine",
    "CertificationStatus",
    "ReleaseDecision",
    "FailureSeverity",
    "QualityGateStatus",
    "TraceSpan",
    "MetricRecord",
    "EvidenceRecord",
    "GoldenScenario",
    "EvaluationResult",
    "QualityGate",
    "ReleaseReadinessReport",
]
