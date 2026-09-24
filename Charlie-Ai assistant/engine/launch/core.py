"""
JARVIS Phase 15: Master Launch Operations Platform
Unifies scope freeze, multi-persona UAT, pilot cohorts, issue triage,
incident containment, Go/No-Go release gates, and staged v1.0 rollout.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from engine.launch.freeze import ReleaseFreezeManager, V1ScopeLock
from engine.launch.incidents import IncidentManager
from engine.launch.models import FreezeState, GoNoGoDecision, GoNoGoReport, IncidentSeverity, IssueSeverity
from engine.launch.readiness import (
    GoNoGoManager,
    KnownIssuesManager,
    PostLaunchMonitor,
    ReleaseReadinessManager,
    RolloutManager,
    UserCommunicationManager,
)
from engine.launch.support import OperationalRunbookManager, SupportManager
from engine.launch.triage_issues import BugTriageManager, HotfixManager, IssueRegistry
from engine.launch.uat_pilot import FeedbackManager, PilotManager, UATManager


class LaunchOperationsPlatform:
    """Master platform coordinating final launch gates, UAT, triage, and v1.0 go-live."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).resolve().parent.parent.parent / "config"
        self.scope_lock = V1ScopeLock()
        self.freeze_mgr = ReleaseFreezeManager(self.data_dir)
        self.uat_mgr = UATManager(self.data_dir)
        self.pilot_mgr = PilotManager(self.data_dir)
        self.feedback_mgr = FeedbackManager(self.data_dir)
        self.issue_registry = IssueRegistry(self.data_dir)
        self.triage_mgr = BugTriageManager(self.issue_registry)
        self.hotfix_mgr = HotfixManager()
        self.support_mgr = SupportManager(self.data_dir)
        self.runbooks = OperationalRunbookManager()
        self.incident_mgr = IncidentManager(self.data_dir)
        self.known_issues_mgr = KnownIssuesManager(self.data_dir)
        self.readiness_mgr = ReleaseReadinessManager()
        self.go_no_go_mgr = GoNoGoManager()
        self.rollout_mgr = RolloutManager()
        self.post_launch_monitor = PostLaunchMonitor()
        self.comms_mgr = UserCommunicationManager()

    def get_launch_dashboard(self) -> Dict[str, Any]:
        """Provides a real-time factual overview of launch gates and operations."""
        triage_status = self.triage_mgr.is_launch_blocked()
        active_rollout = self.rollout_mgr.get_active_stage()
        monitor_summary = self.post_launch_monitor.get_summary()

        return {
            "freeze_state": self.freeze_mgr.get_freeze_state().value,
            "uat_cases_count": len(self.uat_mgr.list_cases()),
            "open_blockers": triage_status["blocking_issues"],
            "is_launch_blocked": triage_status["is_blocked"],
            "active_rollout_stage": active_rollout.stage.value,
            "rollout_percentage": active_rollout.percentage,
            "rollout_paused": active_rollout.auto_paused,
            "known_issues_count": len(self.known_issues_mgr.list_known_issues()),
            "post_launch_health": monitor_summary["status"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def evaluate_v1_release_decision(self, phase13_certified: bool = True) -> GoNoGoReport:
        """Determines release decision based strictly on verified gates."""
        triage = self.triage_mgr.is_launch_blocked()
        checklist = self.readiness_mgr.evaluate_readiness(
            phase13_certified=phase13_certified,
            open_p0_count=triage["open_p0_count"],
            accepted_p1_count=triage["open_p1_count"],
        )
        blockers = list(triage["blocking_issues"])
        accepted_lims = [ki.title for ki in self.known_issues_mgr.list_known_issues()]
        return self.go_no_go_mgr.evaluate_decision(
            checklist=checklist,
            open_blockers=blockers,
            accepted_limitations=accepted_lims,
            rc_build="v1.0.0-rc1",
        )

    def execute_launch_rehearsal(self) -> Dict[str, Any]:
        """Runs a complete end-to-end launch drill."""
        # 1. Transition to Code Freeze
        self.freeze_mgr.transition_state(FreezeState.CODE_FREEZE, "ReleaseManager")

        # 2. Evaluate Decision
        decision_report = self.evaluate_v1_release_decision(phase13_certified=True)

        # 3. Simulate Pilot Cohort Evaluation
        pilot_health = self.pilot_mgr.evaluate_cohort_health(self.pilot_mgr.register_device(cohort="CLOSED_BETA").cohort)

        # 4. Self diagnosis check
        diag = self.support_mgr.run_self_diagnosis()

        return {
            "rehearsal_status": "SUCCESS",
            "decision": decision_report.decision.value,
            "gates_score": decision_report.checklist_score,
            "pilot_health": pilot_health,
            "support_diagnosis": diag,
            "freeze_state": self.freeze_mgr.get_freeze_state().value,
        }
