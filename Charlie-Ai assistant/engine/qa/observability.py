"""
JARVIS Phase 13: Observability, Distributed Tracing & Metrics
Provides full distributed execution tracing, performance timers, and real engineering SLIs/SLOs.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from .models import MetricRecord, TraceSpan

logger = logging.getLogger("jarvis.qa.observability")


class TraceManager:
    """Manages distributed execution spans across JARVIS components without logging secrets."""

    def __init__(self):
        # trace_id -> list of TraceSpan
        self._traces: Dict[str, List[TraceSpan]] = {}

    def start_trace(self, operation: str = "user_request") -> TraceSpan:
        """Starts a new root trace."""
        trace_id = f"tr_{uuid.uuid4().hex[:12]}"
        root_span = TraceSpan(
            trace_id=trace_id,
            component="core",
            operation=operation,
            start_time=time.time(),
        )
        self._traces[trace_id] = [root_span]
        return root_span

    def start_span(self, trace_id: str, component: str, operation: str, parent_span_id: Optional[str] = None) -> TraceSpan:
        """Creates a child span within an existing trace."""
        span = TraceSpan(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            component=component,
            operation=operation,
            start_time=time.time(),
        )
        if trace_id not in self._traces:
            self._traces[trace_id] = []
        self._traces[trace_id].append(span)
        return span

    def finish_span(
        self, span: TraceSpan, status: str = "OK", output_summary: str = "", error: Optional[str] = None
    ):
        span.finish(status=status, output_summary=output_summary, error=error)
        logger.info(f"Span {span.span_id} ({span.component}.{span.operation}) finished: {status} in {span.duration}s")

    def get_trace(self, trace_id: str) -> List[TraceSpan]:
        return self._traces.get(trace_id, []).copy()


class MetricsManager:
    """Calculates factual engineering metrics (SLIs/SLOs), error rates, and latencies."""

    def __init__(self):
        self._metrics: List[MetricRecord] = []

    def record_metric(self, name: str, value: float, unit: str, component: str = "", metadata: Optional[Dict[str, Any]] = None):
        record = MetricRecord(
            metric_name=name,
            value=value,
            unit=unit,
            component=component,
            metadata=metadata or {},
        )
        self._metrics.append(record)

    def get_average_metric(self, name: str) -> float:
        matching = [m.value for m in self._metrics if m.metric_name == name]
        return round(sum(matching) / len(matching), 4) if matching else 0.0

    def compute_sli_summary(self) -> Dict[str, Any]:
        """Calculates factual Service Level Indicators without vanity scores."""
        all_metrics = {m.metric_name for m in self._metrics}
        summary = {}
        for m_name in all_metrics:
            vals = [m.value for m in self._metrics if m.metric_name == m_name]
            summary[m_name] = {
                "count": len(vals),
                "avg": round(sum(vals) / len(vals), 4),
                "min": min(vals),
                "max": max(vals),
            }
        return summary


class ObservabilityEngine:
    """Top-level telemetry coordinator unifying traces, metrics, and structured logs."""

    def __init__(self):
        self.trace_manager = TraceManager()
        self.metrics_manager = MetricsManager()

    def create_monitored_context(self, operation: str):
        return self.trace_manager.start_trace(operation)
