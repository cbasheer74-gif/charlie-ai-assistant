"""engine/intelligence/proactive_engine.py — Proactive Intelligence, Intervention Policy, Notification Budget, and Next-Action Predictor."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from engine.intelligence.models import (
    InterventionAction,
    ProactiveEvent,
)


class NotificationBudget:
    """Controls notification cadence, suppresses spam, groups related alerts, and enforces cooldowns (Section 43 & Test 111)."""

    def __init__(
        self,
        cooldown_sec: float = 60.0,
        max_notifications_per_hour: int = 5,
        quiet_hours: bool = False,
    ):
        self.cooldown_sec = cooldown_sec
        self.max_notifications_per_hour = max_notifications_per_hour
        self.quiet_hours = quiet_hours
        self._sent_notifications: List[float] = []
        self._last_sent_by_type: Dict[str, float] = {}
        self._suppressed_count: int = 0

    def should_deliver(self, trigger_type: str, importance: float) -> Tuple[bool, str]:
        """Determines if a notification should be delivered now or suppressed/grouped."""
        if self.quiet_hours and importance < 0.9:
            return False, "QUIET_HOURS"

        now = time.time()

        # Cooldown check for identical trigger type
        last_sent = self._last_sent_by_type.get(trigger_type, 0.0)
        if (now - last_sent) < self.cooldown_sec:
            self._suppressed_count += 1
            return False, "COOLDOWN_ACTIVE"

        # Rate limit check per hour
        one_hour_ago = now - 3600.0
        self._sent_notifications = [t for t in self._sent_notifications if t >= one_hour_ago]
        if len(self._sent_notifications) >= self.max_notifications_per_hour:
            self._suppressed_count += 1
            return False, "HOURLY_BUDGET_EXCEEDED"

        self._sent_notifications.append(now)
        self._last_sent_by_type[trigger_type] = now
        return True, "DELIVER"

    def group_notifications(self, events: List[ProactiveEvent]) -> List[str]:
        """Summarizes multiple related events to prevent user notification spam."""
        if not events:
            return []
        if len(events) <= 2:
            return [e.message for e in events]

        by_type: Dict[str, int] = defaultdict(int)
        for e in events:
            by_type[e.trigger_type] += 1

        summaries = [f"{count} {trigger} events pending." for trigger, count in by_type.items()]
        return [f"Summary: {', '.join(summaries)}"]


class InterventionPolicy:
    """Decides appropriate proactive intervention tier based on risk, importance, and urgency (Section 42)."""

    @staticmethod
    def evaluate(event: ProactiveEvent) -> InterventionAction:
        # Strictly forbidden high-impact external actions (Section 91)
        if event.risk >= 0.8:
            return InterventionAction.ASK

        if event.trigger_type == "MEETING_UPCOMING":
            # Safe proactive action: prepare draft brief, notify user (Section 44 & 92)
            return InterventionAction.PREPARE_DRAFT

        if event.importance >= 0.8 and event.urgency >= 0.7:
            return InterventionAction.NOTIFY
        elif event.importance >= 0.5:
            return InterventionAction.SURFACE_IN_UI

        return InterventionAction.LOG


class NextActionPredictor:
    """Predicts logical next workflow steps based on active project, completed task, and usual habits (Section 49)."""

    WORKFLOW_CHAINS: Dict[str, str] = {
        "code_feature": "run_unit_tests",
        "run_unit_tests": "git_commit_changes",
        "excel_report_generated": "verify_and_save_report",
        "research_brief_created": "generate_video_script",
        "video_script_created": "start_video_render",
        "video_exported": "verify_export_integrity",
    }

    def predict_next_action(self, last_completed_action: str) -> Optional[str]:
        key = last_completed_action.lower().strip()
        for pattern, next_act in self.WORKFLOW_CHAINS.items():
            if pattern in key or key in pattern:
                return next_act
        return None


class ProactiveIntelligenceEngine:
    """Coordinates proactive situation detection, safe draft preparation, and spam-controlled alerts."""

    def __init__(self, budget: Optional[NotificationBudget] = None):
        self.budget = budget or NotificationBudget()
        self.policy = InterventionPolicy()
        self.predictor = NextActionPredictor()
        self._event_queue: List[ProactiveEvent] = []

    def check_upcoming_meeting(
        self,
        meeting_title: str,
        minutes_remaining: float,
        project_name: Optional[str] = None,
        has_docs: bool = True,
    ) -> Optional[ProactiveEvent]:
        """Proactively detects upcoming meetings (Test 105) and safely prepares a meeting brief without sending comms."""
        if minutes_remaining <= 45.0:
            msg = f"{meeting_title} {int(minutes_remaining)} min mein hai. "
            if project_name:
                msg += f"{project_name} meeting brief ready hai."
            else:
                msg += "Brief ready hai."

            event = ProactiveEvent(
                id=f"evt_meet_{int(time.time()*1000)}",
                trigger_type="MEETING_UPCOMING",
                importance=0.85,
                urgency=0.8,
                confidence=0.95,
                risk=0.2,  # Low risk: internal draft only
                target_project=project_name,
                title=f"Upcoming: {meeting_title}",
                message=msg,
                suggested_action="PREPARE_MEETING_BRIEF",
                action_taken=InterventionAction.PREPARE_DRAFT,
            )
            self._event_queue.append(event)
            return event
        return None

    def check_deadline_proximity(
        self,
        task_name: str,
        hours_remaining: float,
        project_name: Optional[str] = None,
    ) -> Optional[ProactiveEvent]:
        """Proactively surfaces approaching deadlines with budget enforcement (Test 106)."""
        if hours_remaining <= 24.0:
            allowed, _ = self.budget.should_deliver("DEADLINE_APPROACHING", importance=0.8)
            action = InterventionAction.NOTIFY if allowed else InterventionAction.LOG

            event = ProactiveEvent(
                id=f"evt_dead_{int(time.time()*1000)}",
                trigger_type="DEADLINE_APPROACHING",
                importance=0.8,
                urgency=0.75,
                confidence=0.9,
                risk=0.1,
                target_project=project_name,
                title=f"Deadline Approaching: {task_name}",
                message=f"Deadline alert: '{task_name}' is due in {hours_remaining:.1f} hours.",
                suggested_action="REVIEW_TASK",
                action_taken=action,
            )
            self._event_queue.append(event)
            return event
        return None
