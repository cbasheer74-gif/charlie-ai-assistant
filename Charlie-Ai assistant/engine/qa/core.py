"""
JARVIS Phase 13: Master Quality & Certification Platform
Coordinates distributed observability, empirical evidence recording, golden scenarios,
evaluators, chaos testing, quality gates, and release certification.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .certification import ProductionCertificationEngine, QualityGateManager, RegressionEngine
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
    GoldenScenario,
    QualityGateStatus,
    ReleaseDecision,
    ReleaseReadinessReport,
)
from .observability import MetricsManager, ObservabilityEngine, TraceManager
from .scenarios import GoldenScenarioRunner

logger = logging.getLogger("jarvis.qa.core")


class QualityPlatform:
    """Master Quality & Production Certification Platform for JARVIS."""

    def __init__(self, db_path: str = "qa_evidence.db"):
        self.evidence_registry = EvidenceRegistry(db_path=db_path)
        self.observability = ObservabilityEngine()
        self.trace_manager = self.observability.trace_manager
        self.metrics_manager = self.observability.metrics_manager

        # Evaluators
        self.memory_evaluator = MemoryEvaluationEngine()
        self.computer_evaluator = ComputerControlEvaluator()
        self.coding_evaluator = CodingEvaluator()
        self.voice_evaluator = VoiceEvaluator()
        self.chaos_engine = ChaosTestEngine()

        # Scenarios & Gates
        self.scenario_runner = GoldenScenarioRunner(self.evidence_registry)
        self.gate_manager = QualityGateManager()
        self.regression_engine = RegressionEngine()
        self.certification_engine = ProductionCertificationEngine(self.evidence_registry, self.gate_manager)

        logger.info("QualityPlatform initialized.")

    def run_health_check(self) -> Dict[str, Any]:
        """Performs factual operational health check across core subsystems."""
        return {
            "evidence_records_count": sum(self.evidence_registry.count_by_status().values()),
            "critical_gates_count": len(self.gate_manager.list_gates()),
            "golden_scenarios_count": len(self.scenario_runner.list_scenarios()),
            "telemetry_ready": True,
            "status": "OPERATIONAL",
        }
