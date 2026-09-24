"""engine/intelligence/evaluation_engine.py — Evaluation Engine and Automated Regression Protection."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.intelligence.models import ImprovementProposal, ProposalStatus
from engine.intelligence.self_improvement import ImprovementLedger


class EvaluationEngine:
    """Runs targeted test suites to validate improvement candidates and guard against regressions (Section 32 & 33)."""

    def __init__(self, ledger: Optional[ImprovementLedger] = None):
        self.ledger = ledger
        self._test_benchmarks: Dict[str, Callable[[], bool]] = {}

    def register_benchmark(self, name: str, test_func: Callable[[], bool]) -> None:
        self._test_benchmarks[name] = test_func

    def run_evaluations(self) -> Tuple[bool, List[str]]:
        """Runs all registered benchmarks. Returns (all_passed, failing_tests)."""
        failing: List[str] = []
        for name, test_fn in self._test_benchmarks.items():
            try:
                ok = test_fn()
                if not ok:
                    failing.append(name)
            except Exception as e:
                failing.append(f"{name} (error: {e})")

        return len(failing) == 0, failing

    def evaluate_and_guard(
        self,
        proposal: ImprovementProposal,
        benchmark_name: str,
    ) -> bool:
        """Executes targeted benchmark for proposal. If benchmark fails, triggers immediate rollback/rejection."""
        test_fn = self._test_benchmarks.get(benchmark_name)
        if not test_fn:
            return True

        try:
            passed = test_fn()
        except Exception:
            passed = False

        if not passed:
            # Regression detected!
            proposal.status = ProposalStatus.REJECTED
            if self.ledger:
                self.ledger.rollback_improvement(proposal.id, reason=f"Regression failed in benchmark: {benchmark_name}")
            return False

        return True
