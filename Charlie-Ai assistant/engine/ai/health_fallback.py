"""
JARVIS Phase 11: Model Health Manager & Fallback Chain
Monitors provider health, trips circuit breakers on repeated errors, and executes fallbacks seamlessly.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import ModelHealthState, ModelSpec

logger = logging.getLogger("jarvis.ai.health")


class ModelHealthManager:
    """Tracks latency, consecutive failures, and availability of AI models."""

    def __init__(self, failure_threshold: int = 3, recovery_cooldown_seconds: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_cooldown = recovery_cooldown_seconds
        # model_id -> metrics
        self._metrics: Dict[str, Dict[str, Any]] = {}

    def record_success(self, model_id: str, latency: float):
        entry = self._get_or_create(model_id)
        entry["consecutive_failures"] = 0
        entry["last_success"] = time.time()
        entry["total_successes"] += 1
        entry["last_latency"] = latency
        entry["state"] = ModelHealthState.HEALTHY

    def record_failure(self, model_id: str, error_msg: str):
        entry = self._get_or_create(model_id)
        entry["consecutive_failures"] += 1
        entry["last_failure"] = time.time()
        entry["total_failures"] += 1
        entry["last_error"] = error_msg

        if entry["consecutive_failures"] >= self.failure_threshold:
            entry["state"] = ModelHealthState.UNAVAILABLE
            logger.warning(f"Circuit Breaker tripped for {model_id}: Marked UNAVAILABLE.")
        else:
            entry["state"] = ModelHealthState.DEGRADED

    def get_health(self, model_id: str) -> ModelHealthState:
        entry = self._get_or_create(model_id)
        # Check if cooldown expired for retry
        if entry["state"] == ModelHealthState.UNAVAILABLE:
            if time.time() - entry["last_failure"] > self.recovery_cooldown:
                entry["state"] = ModelHealthState.DEGRADED
                logger.info(f"Cooldown expired for {model_id}: Promoted to DEGRADED for probe.")
        return entry["state"]

    def _get_or_create(self, model_id: str) -> Dict[str, Any]:
        if model_id not in self._metrics:
            self._metrics[model_id] = {
                "consecutive_failures": 0,
                "total_failures": 0,
                "total_successes": 0,
                "last_success": 0.0,
                "last_failure": 0.0,
                "last_latency": 0.0,
                "last_error": "",
                "state": ModelHealthState.HEALTHY,
            }
        return self._metrics[model_id]


class FallbackManager:
    """Executes call with primary model, falling back sequentially if errors occur."""

    def __init__(self, health_manager: ModelHealthManager):
        self.health_manager = health_manager

    def execute_with_fallback(
        self,
        primary_model: ModelSpec,
        fallback_chain: List[ModelSpec],
        execute_fn: Callable[[ModelSpec], Dict[str, Any]],
    ) -> Tuple[bool, Dict[str, Any], str]:
        """
        Attempts execution on primary model. If it fails, falls back sequentially.
        Returns: (success: bool, result_dict: dict, final_model_id: str)
        """
        candidates = [primary_model] + fallback_chain

        last_err = ""
        for model in candidates:
            # Check if model circuit is open
            if self.health_manager.get_health(model.model_id) == ModelHealthState.UNAVAILABLE:
                logger.info(f"Skipping {model.model_id} (circuit open/unavailable).")
                continue

            try:
                start_t = time.time()
                res = execute_fn(model)
                latency = time.time() - start_t
                self.health_manager.record_success(model.model_id, latency)
                return True, res, model.model_id
            except Exception as e:
                last_err = str(e)
                logger.warning(f"Execution failed on {model.model_id}: {e}. Trying next fallback...")
                self.health_manager.record_failure(model.model_id, last_err)

        return False, {"error": f"All models in fallback chain failed. Last error: {last_err}"}, primary_model.model_id
