"""engine/intelligence/pattern_engine.py — Pattern Recognition, Event Thresholding, and Habit Learning."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from engine.intelligence.models import Pattern


class PatternRecognitionEngine:
    """Detects recurring patterns across user commands, workflows, errors, and habits (>1 event threshold)."""

    def __init__(self, min_event_threshold: int = 2):
        self.min_event_threshold = min_event_threshold
        self._event_history: List[Dict[str, Any]] = []
        self._known_patterns: Dict[str, Pattern] = {}

    def record_event(
        self,
        event_type: str,
        signature: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Pattern]:
        """Records an event and evaluates if it crosses the threshold to form a stable pattern."""
        now = time.time()
        meta = metadata or {}
        event = {
            "type": event_type,
            "signature": signature,
            "metadata": meta,
            "timestamp": now,
        }
        self._event_history.append(event)

        # Count occurrences of this signature
        matching = [e for e in self._event_history if e["signature"] == signature and e["type"] == event_type]
        count = len(matching)

        if count < self.min_event_threshold:
            return None

        # Pattern threshold met!
        time_span = matching[-1]["timestamp"] - matching[0]["timestamp"]
        pattern_id = f"pat_{event_type}_{abs(hash(signature)) % 10000}"

        recommended_action = None
        if event_type == "WORKFLOW_SEQUENCE":
            recommended_action = f"Suggest creating a reusable Skill for: {signature}"
        elif event_type == "REPEATED_ERROR":
            recommended_action = f"Suggest creating an automated startup/health check for: {signature}"

        pattern = Pattern(
            id=pattern_id,
            pattern_type=event_type,
            description=f"Repeated {event_type}: '{signature}' occurred {count} times.",
            event_count=count,
            time_span_sec=time_span,
            consistency_score=1.0,
            confidence=min(0.5 + (count * 0.15), 0.95),
            trigger_conditions={"signature": signature},
            recommended_action=recommended_action,
            last_detected_at=now,
        )
        self._known_patterns[pattern_id] = pattern
        return pattern

    def list_patterns(self, pattern_type: Optional[str] = None) -> List[Pattern]:
        if pattern_type:
            return [p for p in self._known_patterns.values() if p.pattern_type == pattern_type]
        return list(self._known_patterns.values())

    def get_skill_recommendations(self) -> List[str]:
        """Returns actionable skill recommendations derived from detected repeated habits."""
        recs: List[str] = []
        for p in self._known_patterns.values():
            if p.pattern_type == "WORKFLOW_SEQUENCE" and p.recommended_action:
                recs.append(p.recommended_action)
        return recs
