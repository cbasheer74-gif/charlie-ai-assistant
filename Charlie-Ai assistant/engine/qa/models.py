"""
JARVIS Phase 13: QA, Observability & Certification Models
Defines telemetry spans, metric structures, evidence records, golden scenarios, quality gates, and certification reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid


class CertificationStatus(str, Enum):
    NOT_TESTED = "NOT_TESTED"
    RUNNING = "RUNNING"
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReleaseDecision(str, Enum):
    CERTIFIED = "CERTIFIED"
    CONDITIONALLY_CERTIFIED = "CONDITIONALLY_CERTIFIED"
    NOT_CERTIFIED = "NOT_CERTIFIED"


class FailureSeverity(str, Enum):
    P0_CRITICAL = "P0_CRITICAL"
    P1_HIGH = "P1_HIGH"
    P2_MEDIUM = "P2_MEDIUM"
    P3_LOW = "P3_LOW"


class QualityGateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass
class TraceSpan:
    trace_id: str
    span_id: str = field(default_factory=lambda: f"span_{uuid.uuid4().hex[:8]}")
    parent_span_id: Optional[str] = None
    component: str = ""
    operation: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    duration: float = 0.0
    status: str = "RUNNING"  # "OK", "ERROR", "RUNNING"
    input_summary: str = ""
    output_summary: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finish(self, status: str = "OK", output_summary: str = "", error: Optional[str] = None):
        self.end_time = time.time()
        self.duration = round(self.end_time - self.start_time, 4)
        self.status = status
        self.output_summary = output_summary
        self.error = error


@dataclass
class MetricRecord:
    metric_name: str
    value: float
    unit: str
    timestamp: float = field(default_factory=time.time)
    component: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceRecord:
    evidence_id: str = field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:10]}")
    test_id: str = ""
    feature_name: str = ""
    phase: str = ""
    run_id: str = ""
    timestamp: float = field(default_factory=time.time)
    environment: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    expected_result: Any = None
    actual_result: Any = None
    status: CertificationStatus = CertificationStatus.NOT_TESTED
    logs: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    evidence_hash: str = ""
    failure_details: Optional[str] = None


@dataclass
class GoldenScenario:
    scenario_id: str
    name: str
    description: str
    phase: str
    required_environment: str = "WINDOWS_10"
    user_command: str = ""
    expected_steps: List[str] = field(default_factory=list)
    acceptance_criteria: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "R1_LOW"
    timeout_seconds: float = 30.0


@dataclass
class EvaluationResult:
    scenario_id: str
    passed: bool
    status: CertificationStatus
    actual_output: Any
    evidence_id: str
    duration_seconds: float
    notes: str = ""


@dataclass
class QualityGate:
    gate_id: str
    name: str
    description: str
    is_critical_p0: bool = True
    status: QualityGateStatus = QualityGateStatus.FAIL
    failure_reason: Optional[str] = None


@dataclass
class ReleaseReadinessReport:
    report_id: str
    jarvis_version: str
    build_id: str
    environment: str
    timestamp: float = field(default_factory=time.time)
    release_decision: ReleaseDecision = ReleaseDecision.NOT_CERTIFIED
    critical_gates_passed: int = 0
    total_critical_gates: int = 0
    golden_scenarios_passed: int = 0
    total_golden_scenarios: int = 0
    phase_certifications: Dict[str, CertificationStatus] = field(default_factory=dict)
    open_blockers: List[str] = field(default_factory=list)
    known_limitations: List[str] = field(default_factory=list)
    evidence_summary: Dict[str, str] = field(default_factory=dict)
