"""
JARVIS Phase 11: Model Performance Tracker & Routing Learning
Tracks empirical success, latency, and cost per task type to learn optimal routing weights.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .models import ModelBenchmarkResult

logger = logging.getLogger("jarvis.ai.performance")


class ModelPerformanceTracker:
    """Tracks historical model success rates and adjusts priority dynamically."""

    def __init__(self):
        # (model_id, task_type) -> list of results
        self._history: Dict[str, List[ModelBenchmarkResult]] = {}

    def record_run(
        self,
        model_id: str,
        task_type: str,
        passed: bool,
        latency_seconds: float,
        score: float = 1.0,
    ):
        key = f"{model_id}:{task_type}"
        if key not in self._history:
            self._history[key] = []

        result = ModelBenchmarkResult(
            benchmark_id=f"bench_{int(time.time()*1000)}",
            model_id=model_id,
            task_type=task_type,
            passed=passed,
            latency_seconds=latency_seconds,
            score=score if passed else 0.0,
        )
        self._history[key].append(result)
        logger.info(f"Performance recorded: {key} -> passed={passed}, latency={latency_seconds:.2f}s")

    def get_success_rate(self, model_id: str, task_type: str) -> float:
        key = f"{model_id}:{task_type}"
        results = self._history.get(key, [])
        if not results:
            return 0.5  # Neutral default for untested models
        passes = sum(1 for r in results if r.passed)
        return round(passes / len(results), 3)

    def should_escalate_model(self, model_id: str, task_type: str, failure_threshold: int = 2) -> bool:
        """Determines if a model has repeatedly failed this task type and should be escalated."""
        key = f"{model_id}:{task_type}"
        results = self._history.get(key, [])
        if len(results) < failure_threshold:
            return False
        # Check last N runs
        recent = results[-failure_threshold:]
        return all(not r.passed for r in recent)
