"""
JARVIS Phase 15: Bug Triage, Issue Registry, and Hotfix Management
Enforces bug reproduction before fixing, blocks v1.0 release on open P0s,
and governs post-launch emergency hotfix protocols.
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from engine.launch.models import IssueRecord, IssueSeverity, IssueStatus


class IssueRegistry:
    """Persistent issue store tracking bug lifecycle and verification evidence."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).resolve().parent.parent.parent / "config"
        self.issue_store = self.data_dir / "issue_registry.json"
        self._issues: Dict[str, IssueRecord] = {}
        self._load_issues()

    def create_issue(
        self,
        title: str,
        component: str,
        severity: IssueSeverity,
        reproduction_steps: str = "",
    ) -> IssueRecord:
        issue_id = f"BUG_{uuid.uuid4().hex[:8].upper()}"
        issue = IssueRecord(
            issue_id=issue_id,
            title=title,
            component=component,
            severity=severity,
            status=IssueStatus.NEW,
            reproduction_steps=reproduction_steps,
            reproduced=bool(reproduction_steps),
        )
        self._issues[issue_id] = issue
        self._save_issues()
        return issue

    def get_issue(self, issue_id: str) -> Optional[IssueRecord]:
        return self._issues.get(issue_id)

    def list_issues(self) -> List[IssueRecord]:
        return list(self._issues.values())

    def update_issue_status(
        self,
        issue_id: str,
        target_status: IssueStatus,
        evidence_ref: str = "",
    ) -> Dict[str, Any]:
        issue = self._issues.get(issue_id)
        if not issue:
            return {"success": False, "reason": "ISSUE_NOT_FOUND"}

        # Reproduction gate: cannot be FIXED without reproduction
        if target_status == IssueStatus.FIXED and not issue.reproduced:
            return {
                "success": False,
                "reason": "REPRODUCTION_REQUIRED: Cannot mark FIXED without reproduction evidence.",
            }

        # Verification gate: cannot be CLOSED without verification
        if target_status == IssueStatus.CLOSED and issue.status != IssueStatus.VERIFIED:
            if not evidence_ref:
                return {
                    "success": False,
                    "reason": "VERIFICATION_REQUIRED: Cannot CLOSE without verification evidence.",
                }

        issue.status = target_status
        if evidence_ref:
            issue.evidence_ref = evidence_ref
        issue.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_issues()

        return {"success": True, "issue_id": issue_id, "status": target_status.value}

    def _load_issues(self) -> None:
        if self.issue_store.exists():
            try:
                data = json.loads(self.issue_store.read_text(encoding="utf-8"))
                for d in data:
                    rec = IssueRecord(
                        issue_id=d["id"],
                        title=d["title"],
                        component=d["component"],
                        severity=IssueSeverity(d["severity"]),
                        status=IssueStatus(d["status"]),
                        reproduction_steps=d.get("reproduction_steps", ""),
                        reproduced=d.get("reproduced", False),
                        evidence_ref=d.get("evidence_ref", ""),
                        created_at=d.get("created_at", ""),
                        updated_at=d.get("updated_at", ""),
                    )
                    self._issues[rec.issue_id] = rec
            except Exception:
                pass

    def _save_issues(self) -> None:
        data = [
            {
                "id": i.issue_id,
                "title": i.title,
                "component": i.component,
                "severity": i.severity.value,
                "status": i.status.value,
                "reproduction_steps": i.reproduction_steps,
                "reproduced": i.reproduced,
                "evidence_ref": i.evidence_ref,
                "created_at": i.created_at,
                "updated_at": i.updated_at,
            }
            for i in self._issues.values()
        ]
        self.issue_store.parent.mkdir(parents=True, exist_ok=True)
        self.issue_store.write_text(json.dumps(data, indent=2), encoding="utf-8")


class BugTriageManager:
    """Evaluates launch blockers and enforces zero open P0 policy."""

    def __init__(self, registry: Optional[IssueRegistry] = None):
        self.registry = registry or IssueRegistry()

    def get_open_blockers(self) -> List[IssueRecord]:
        """Returns all unresolved P0 and unapproved P1 issues."""
        blockers = []
        for issue in self.registry.list_issues():
            if issue.status in (IssueStatus.NEW, IssueStatus.TRIAGED, IssueStatus.REPRODUCED, IssueStatus.IN_PROGRESS):
                if issue.severity == IssueSeverity.P0_CRITICAL:
                    blockers.append(issue)
                elif issue.severity == IssueSeverity.P1_HIGH:
                    blockers.append(issue)
        return blockers

    def is_launch_blocked(self) -> Dict[str, Any]:
        blockers = self.get_open_blockers()
        p0_count = sum(1 for b in blockers if b.severity == IssueSeverity.P0_CRITICAL)
        p1_count = sum(1 for b in blockers if b.severity == IssueSeverity.P1_HIGH)
        is_blocked = p0_count > 0 or p1_count > 0
        return {
            "is_blocked": is_blocked,
            "open_p0_count": p0_count,
            "open_p1_count": p1_count,
            "blocking_issues": [b.issue_id for b in blockers],
        }


class HotfixManager:
    """Governs post-launch emergency hotfix protocols."""

    def create_hotfix_plan(
        self,
        issue_id: str,
        root_cause: str,
        target_version: str,
        regression_tests: List[str],
    ) -> Dict[str, Any]:
        return {
            "hotfix_id": f"HF_{uuid.uuid4().hex[:6].upper()}",
            "issue_id": issue_id,
            "target_version": target_version,
            "root_cause": root_cause,
            "required_regression_tests": regression_tests,
            "staged_rollout_required": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
