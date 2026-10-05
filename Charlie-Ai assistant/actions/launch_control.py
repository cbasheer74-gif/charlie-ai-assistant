"""
CHARLIE Phase 15: Launch & Release Operations Control Actions
Assistant tools for querying launch status, executing UAT scenarios,
triaging bugs, managing incidents, and evaluating Go/No-Go decisions.
"""

from typing import Any, Dict, List, Optional
from engine.launch.core import LaunchOperationsPlatform
from engine.launch.models import IncidentSeverity, IssueSeverity, UATStatus


class LaunchControlActions:
    """Assistant action tools for LaunchOperationsPlatform and v1.0 Go-Live."""

    def __init__(self, platform: Optional[LaunchOperationsPlatform] = None):
        self.platform = platform or LaunchOperationsPlatform()

    def get_launch_dashboard(self) -> Dict[str, Any]:
        """Query real-time freeze state, open blockers, rollout stage, and readiness."""
        return self.platform.get_launch_dashboard()

    def execute_uat_case(
        self,
        uat_id: str,
        passed: bool,
        actual_behavior: str,
        evidence_ref: str = "",
    ) -> Dict[str, Any]:
        """Record the outcome of a User Acceptance Test."""
        status = UATStatus.PASS if passed else UATStatus.FAIL
        return self.platform.uat_mgr.record_uat_result(
            uat_id=uat_id,
            status=status,
            actual_behavior=actual_behavior,
            evidence_ref=evidence_ref or f"EVID_{uat_id}_PASS",
        )

    def report_issue(
        self,
        title: str,
        component: str,
        severity_str: str,
        reproduction_steps: str = "",
    ) -> Dict[str, Any]:
        """Report a bug into the Issue Registry with reproduction requirement."""
        sev = IssueSeverity(severity_str)
        issue = self.platform.issue_registry.create_issue(
            title=title,
            component=component,
            severity=sev,
            reproduction_steps=reproduction_steps,
        )
        return {
            "issue_id": issue.issue_id,
            "title": issue.title,
            "severity": issue.severity.value,
            "reproduced": issue.reproduced,
            "status": issue.status.value,
        }

    def declare_production_incident(
        self,
        title: str,
        severity_str: str,
        subsystem: str,
    ) -> Dict[str, Any]:
        """Declare an active production incident and trigger automated containment."""
        sev = IncidentSeverity(severity_str)
        inc = self.platform.incident_mgr.declare_incident(title=title, severity=sev, subsystem=subsystem)
        containment = self.platform.incident_mgr.execute_automated_containment(inc.incident_id)
        return {
            "incident_id": inc.incident_id,
            "severity": inc.severity.value,
            "lifecycle": inc.lifecycle.value,
            "containment_actions": containment["actions_taken"],
        }

    def evaluate_go_no_go(self, phase13_certified: bool = True) -> Dict[str, Any]:
        """Compute deterministic release decision for v1.0."""
        report = self.platform.evaluate_v1_release_decision(phase13_certified=phase13_certified)
        return {
            "decision": report.decision.value,
            "score": report.checklist_score,
            "open_blockers": report.open_blockers,
            "accepted_limitations": report.accepted_limitations,
            "rc_build": report.release_candidate_build,
        }

    def advance_rollout_stage(self) -> Dict[str, Any]:
        """Progressively advance staged deployment cohort."""
        return self.platform.rollout_mgr.advance_stage()
