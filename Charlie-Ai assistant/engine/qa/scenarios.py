"""
JARVIS Phase 13: Golden Master Scenarios Runner
Executes the 15 Golden Master Scenarios across all phases and records verifiable evidence in EvidenceRegistry.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .evidence import EvidenceRegistry
from .models import CertificationStatus, EvaluationResult, GoldenScenario

logger = logging.getLogger("jarvis.qa.scenarios")


class GoldenScenarioRunner:
    """Executes the 15 Golden Master Scenarios and stores verifiable test records."""

    def __init__(self, evidence_registry: EvidenceRegistry):
        self.evidence_registry = evidence_registry
        self._scenarios: Dict[str, GoldenScenario] = {}
        self._init_golden_scenarios()

    def _init_golden_scenarios(self):
        scenarios = [
            GoldenScenario("GM_01_MEMORY", "Memory Persistence & Superseding", "Verify fact persists across restart and new port supersedes old", "PHASE_1"),
            GoldenScenario("GM_02_COMPUTER", "Computer Control Moved Window", "Notepad automation locates editor dynamically after window move", "PHASE_2"),
            GoldenScenario("GM_03_CODING", "Coding Bug Fix with Tests", "Controlled bug resolved and verified by test suite", "PHASE_3"),
            GoldenScenario("GM_04_AUTONOMY", "Autonomy Startup Recovery", "Detects dependency issue, applies recovery, and resumes execution", "PHASE_3"),
            GoldenScenario("GM_05_VOICE", "Voice Wake & Hinglish Routing", "Wake detection, Hinglish intent parsing, and task routing", "PHASE_7"),
            GoldenScenario("GM_06_EXCEL", "Excel Formulas Preserved", "Generates summary while preserving existing formulas and headers", "PHASE_6"),
            GoldenScenario("GM_07_RESEARCH", "Research Fresh Sources & Citations", "Fresh live sources cited; stale model memory rejected", "PHASE_5"),
            GoldenScenario("GM_08_SECURITY", "Prompt Injection Defense", "Injected instructions treated strictly as inert data", "PHASE_9"),
            GoldenScenario("GM_09_BACKUP", "Disaster Recovery Restore", "Corrupted sandbox fully restored to verified pristine baseline", "PHASE_9"),
            GoldenScenario("GM_10_PLUGIN", "Plugin Sandbox Boundary", "Third-party plugin blocked from accessing unauthorized system paths", "PHASE_12"),
            GoldenScenario("GM_11_MODEL_ROUTING", "Model Routing Cost & Privacy", "Trivial task bypasses LLM; sensitive task locks to local", "PHASE_11"),
            GoldenScenario("GM_12_MOBILE", "Mobile Command Replay Prevention", "Captured mobile command nonce rejected on second attempt", "PHASE_10"),
            GoldenScenario("GM_13_RESUME", "Crash Resume Checkpoint", "Simulated crash recovers task checkpoint and continues cleanly", "PHASE_3"),
            GoldenScenario("GM_14_EMERGENCY_STOP", "Emergency Stop Immediate Halt", "Emergency stop halts automation instantly without lag", "PHASE_9"),
            GoldenScenario("GM_15_LONG_TASK", "Long Task Loop Detection", "20+ step task prevents infinite loops and bounds memory", "PHASE_3"),
        ]
        for s in scenarios:
            self._scenarios[s.scenario_id] = s

    def run_scenario(self, scenario_id: str, test_executor_fn: Callable[[], Tuple[bool, Any, str]]) -> EvaluationResult:
        """Runs scenario, verifies criteria, and records immutable evidence."""
        scen = self._scenarios.get(scenario_id)
        if not scen:
            raise ValueError(f"Unknown scenario ID: {scenario_id}")

        start_t = time.time()
        passed, actual_output, notes = test_executor_fn()
        duration = round(time.time() - start_t, 4)
        status = CertificationStatus.PASS if passed else CertificationStatus.FAIL

        ev = self.evidence_registry.record_evidence(
            test_id=scen.scenario_id,
            feature_name=scen.name,
            phase=scen.phase,
            run_id=f"run_{int(start_t*1000)}",
            expected_result=f"{scen.name} satisfies all acceptance criteria",
            actual_result=actual_output,
            status=status,
            metrics={"duration_seconds": duration},
            failure_details=None if passed else notes,
        )

        return EvaluationResult(
            scenario_id=scen.scenario_id,
            passed=passed,
            status=status,
            actual_output=actual_output,
            evidence_id=ev.evidence_id,
            duration_seconds=duration,
            notes=notes,
        )

    def list_scenarios(self) -> List[GoldenScenario]:
        return list(self._scenarios.values())
