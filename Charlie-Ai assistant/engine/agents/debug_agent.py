"""engine/agents/debug_agent.py — Debug Agent for Error Diagnosis & Fix Generation.

Classifies runtime/build errors, locates root cause, consults error memories,
and proposes minimal targeted patches.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from engine.agents.contract import AgentContract, AgentResult

if TYPE_CHECKING:
    from engine.autonomy.context import ExecutionContext
    from engine.autonomy.task_graph import TaskNode

from engine.error_recovery import ErrorRecoveryEngine
from engine.memory_manager import MemoryManager


class DebugAgent(AgentContract):
    name = "DebugAgent"
    description = "Diagnoses software failures, classifies root causes, and applies verified fixes."

    def __init__(self, memory_manager: MemoryManager, error_recovery: Optional[ErrorRecoveryEngine] = None):
        self.memory = memory_manager
        self.recovery = error_recovery or ErrorRecoveryEngine(memory_manager)

    def can_handle(self, task: TaskNode) -> bool:
        low = (task.name + " " + task.description + " " + (task.tool or "")).lower()
        return any(w in low for w in ("debug", "diagnose", "root cause", "syntax error", "traceback", "fix failure"))

    def execute(self, task: TaskNode, context: ExecutionContext) -> AgentResult:
        error_text = task.inputs.get("error") or (context.errors[-1]["error"] if context.errors else "Unknown error")
        target_file = task.inputs.get("file")

        # 1. Consult Error Memories
        signature = self.recovery.extract_signature(error_text)
        known_solution = self.recovery.find_known_solution(signature, application=context.project_id)

        observations: List[str] = [f"Analyzed error signature: {signature}"]
        recommendation = ""

        if known_solution:
            observations.append(f"Found existing error fix in memory: {known_solution[:80]}")
            recommendation = f"Apply known fix: {known_solution}"
            return AgentResult(
                status="SUCCESS",
                output={"signature": signature, "known_solution": known_solution, "strategy": "known_fix"},
                observations=observations,
                next_recommendation=recommendation,
            )

        # 2. Heuristic Classification & Diagnosis
        diagnosis = "General runtime error"
        suggested_fix = ""

        if "syntaxerror" in error_text.lower():
            diagnosis = "Python Syntax Error"
            suggested_fix = "Inspect line in target file and balance parenthesis/indentation."
        elif "modulenotfounderror" in error_text.lower() or "no module named" in error_text.lower():
            mod = re.findall(r"No module named '([^']+)'", error_text)
            mod_name = mod[0] if mod else "dependency"
            diagnosis = f"Missing dependency: {mod_name}"
            suggested_fix = f"Verify package path or install {mod_name} in virtual environment."
        elif "port" in error_text.lower() and ("in use" in error_text.lower() or "already used" in error_text.lower()):
            diagnosis = "Port conflict error"
            suggested_fix = "Terminate stale development process on conflicting port."

        observations.append(f"Diagnosis: {diagnosis}")

        return AgentResult(
            status="SUCCESS",
            output={
                "signature": signature,
                "diagnosis": diagnosis,
                "suggested_fix": suggested_fix,
                "strategy": "heuristic_diagnosis",
            },
            observations=observations,
            next_recommendation=suggested_fix or "Inspect traceback lines",
        )
