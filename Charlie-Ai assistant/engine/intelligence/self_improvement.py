"""engine/intelligence/self_improvement.py — Bounded Self-Improvement, Tool Reliability, Ledger, and Reflection."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from engine.intelligence.models import (
    ImprovementProposal,
    ProposalStatus,
    ReflectionSummary,
)


class ToolReliabilityTracker:
    """Tracks tool invocation outcomes across environments and categories (Section 76)."""

    def __init__(self):
        self._stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"success": 0, "failure": 0})

    def record_outcome(self, tool_name: str, success: bool) -> None:
        if success:
            self._stats[tool_name]["success"] += 1
        else:
            self._stats[tool_name]["failure"] += 1

    def get_success_rate(self, tool_name: str) -> float:
        stats = self._stats.get(tool_name)
        if not stats:
            return 1.0
        total = stats["success"] + stats["failure"]
        if total == 0:
            return 1.0
        return stats["success"] / total

    def compare_tools(self, tool_a: str, tool_b: str) -> str:
        """Returns the more reliable tool based on observed success rate."""
        rate_a = self.get_success_rate(tool_a)
        rate_b = self.get_success_rate(tool_b)
        return tool_a if rate_a >= rate_b else tool_b


class ImprovementLedger:
    """Persistent audit log of all learning proposals, applied changes, and rollback states (Section 30)."""

    def __init__(self):
        self.proposals: Dict[str, ImprovementProposal] = {}
        self.history: List[Dict[str, Any]] = []

    def record_proposal(self, proposal: ImprovementProposal) -> None:
        self.proposals[proposal.id] = proposal

    def apply_improvement(self, proposal_id: str) -> bool:
        prop = self.proposals.get(proposal_id)
        if not prop:
            return False

        # Strictly block uncontrolled code modification without approval (Section 28)
        if prop.requires_code_modification and prop.status != ProposalStatus.APPROVED:
            return False

        prop.status = ProposalStatus.APPLIED
        prop.resolved_at = time.time()
        self.history.append({
            "id": prop.id,
            "action": "APPLIED",
            "proposed_change": prop.proposed_change,
            "scope": prop.scope,
            "timestamp": time.time(),
        })
        return True

    def rollback_improvement(self, proposal_id: str, reason: str = "") -> bool:
        prop = self.proposals.get(proposal_id)
        if not prop:
            return False

        prop.status = ProposalStatus.ROLLED_BACK
        prop.resolved_at = time.time()
        self.history.append({
            "id": prop.id,
            "action": "ROLLED_BACK",
            "reason": reason,
            "timestamp": time.time(),
        })
        return True

    def list_applied(self) -> List[ImprovementProposal]:
        return [p for p in self.proposals.values() if p.status == ProposalStatus.APPLIED]


class ReflectionEngine:
    """Performs concise, structured machine-oriented reflection after significant task execution (Section 34)."""

    def __init__(self):
        self._reflections: List[ReflectionSummary] = []

    def reflect_on_task(
        self,
        goal: str,
        outcome: str,
        what_worked: Optional[List[str]] = None,
        what_failed: Optional[List[str]] = None,
        user_corrections: Optional[List[str]] = None,
        new_knowledge: Optional[List[str]] = None,
        reusable_procedure: Optional[str] = None,
        possible_improvement: Optional[str] = None,
    ) -> ReflectionSummary:
        ref = ReflectionSummary(
            goal=goal,
            outcome=outcome,
            what_worked=what_worked or [],
            what_failed=what_failed or [],
            user_corrections=user_corrections or [],
            new_knowledge=new_knowledge or [],
            reusable_procedure=reusable_procedure,
            possible_improvement=possible_improvement,
            timestamp=time.time(),
        )
        self._reflections.append(ref)
        return ref

    def get_latest_reflection(self) -> Optional[ReflectionSummary]:
        return self._reflections[-1] if self._reflections else None


class SelfImprovementEngine:
    """Safe bounded self-improvement engine. Distinguishes low-risk preference updates from code modification."""

    def __init__(
        self,
        ledger: Optional[ImprovementLedger] = None,
        tracker: Optional[ToolReliabilityTracker] = None,
    ):
        self.ledger = ledger or ImprovementLedger()
        self.tracker = tracker or ToolReliabilityTracker()
        self.reflection_engine = ReflectionEngine()
        self.tool_preferences: Dict[str, str] = {}  # category -> preferred_tool

    def evaluate_tool_improvement(
        self,
        category: str,
        failing_tool: str,
        succeeding_tool: str,
    ) -> ImprovementProposal:
        """Identifies tool reliability discrepancy and creates a safe internal ranking proposal."""
        rate_fail = self.tracker.get_success_rate(failing_tool)
        rate_succ = self.tracker.get_success_rate(succeeding_tool)

        prop_id = f"imp_{category}_{int(time.time()*1000)}"
        prop = ImprovementProposal(
            id=prop_id,
            problem=f"Tool '{failing_tool}' has lower reliability ({rate_fail:.1%}) in category '{category}'.",
            evidence=f"'{succeeding_tool}' observed success rate is {rate_succ:.1%}.",
            proposed_change=f"Set default tool preference for '{category}' to '{succeeding_tool}'.",
            scope="INTERNAL_RANKING",
            expected_benefit=f"Higher automated task completion in {category}.",
            risk_level="LOW",
            test_plan="Run regression test suite on category actions.",
            rollback_plan=f"Revert default tool for '{category}' back to '{failing_tool}'.",
            status=ProposalStatus.PROPOSED,
            before_metrics={"preferred_tool": failing_tool, "success_rate": rate_fail},
            after_metrics={"preferred_tool": succeeding_tool, "success_rate": rate_succ},
            requires_code_modification=False,
            created_at=time.time(),
        )
        self.ledger.record_proposal(prop)

        # Apply low-risk preference update automatically
        self.tool_preferences[category] = succeeding_tool
        self.ledger.apply_improvement(prop.id)
        return prop

    def propose_code_modification(
        self,
        problem: str,
        proposed_code_change: str,
        test_plan: str,
        rollback_plan: str,
    ) -> ImprovementProposal:
        """Strictly blocks automatic direct self-rewrite (Section 28); logs proposal requiring human approval."""
        prop_id = f"imp_code_{int(time.time()*1000)}"
        prop = ImprovementProposal(
            id=prop_id,
            problem=problem,
            evidence="Code improvement opportunity detected.",
            proposed_change=proposed_code_change,
            scope="SOURCE_CODE",
            expected_benefit="Architectural/performance enhancement.",
            risk_level="HIGH",
            test_plan=test_plan,
            rollback_plan=rollback_plan,
            status=ProposalStatus.PROPOSED,
            requires_code_modification=True,
            created_at=time.time(),
        )
        self.ledger.record_proposal(prop)
        return prop
