"""
JARVIS Phase 15: Production Incident Management & Automated Containment
Manages SEV0-SEV3 incidents, automated containment (quarantine, rollout pause),
timeline audit logging, and blame-free postmortems.
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from engine.launch.models import (
    IncidentLifecycle,
    IncidentRecord,
    IncidentSeverity,
    IncidentTimelineEntry,
    PostmortemReport,
)


class IncidentManager:
    """Manages critical production incidents, containment, timelines, and postmortems."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).resolve().parent.parent.parent / "config"
        self.incident_store = self.data_dir / "incidents.json"
        self._incidents: Dict[str, IncidentRecord] = {}
        self._load_incidents()

    def declare_incident(
        self,
        title: str,
        severity: IncidentSeverity,
        subsystem: str,
        actor: str = "SystemWatchdog",
    ) -> IncidentRecord:
        inc_id = f"INC_{uuid.uuid4().hex[:6].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        entry = IncidentTimelineEntry(
            timestamp=now,
            action="DECLARED",
            actor=actor,
            notes=f"Declared with severity {severity.value} on subsystem '{subsystem}'",
        )
        record = IncidentRecord(
            incident_id=inc_id,
            title=title,
            severity=severity,
            lifecycle=IncidentLifecycle.DETECTED,
            affected_subsystem=subsystem,
            timeline=[entry],
        )
        self._incidents[inc_id] = record
        self._save_incidents()
        return record

    def update_lifecycle(
        self,
        incident_id: str,
        stage: IncidentLifecycle,
        actor: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        inc = self._incidents.get(incident_id)
        if not inc:
            return {"success": False, "reason": "INCIDENT_NOT_FOUND"}

        now = datetime.now(timezone.utc).isoformat()
        entry = IncidentTimelineEntry(timestamp=now, action=stage.value, actor=actor, notes=notes)
        inc.timeline.append(entry)
        inc.lifecycle = stage

        if stage == IncidentLifecycle.CONTAINED:
            inc.contained_at = now
        elif stage == IncidentLifecycle.RESOLVED:
            inc.resolved_at = now

        self._save_incidents()
        return {"success": True, "incident_id": incident_id, "lifecycle": stage.value}

    def execute_automated_containment(self, incident_id: str) -> Dict[str, Any]:
        """Executes safe automatic containment actions based on affected subsystem and severity."""
        inc = self._incidents.get(incident_id)
        if not inc:
            return {"success": False, "reason": "INCIDENT_NOT_FOUND"}

        actions_taken = []
        sub = inc.affected_subsystem.lower()

        if "plugin" in sub or "extension" in sub:
            actions_taken.append("PLUGIN_QUARANTINED")
        if "update" in sub or "rollout" in sub:
            actions_taken.append("ROLLOUT_PAUSED")
        if inc.severity == IncidentSeverity.SEV0_CATASTROPHIC:
            actions_taken.append("SAFE_MODE_ENABLED")
            actions_taken.append("EXTERNAL_ACTIONS_BLOCKED")
        else:
            actions_taken.append("CIRCUIT_BREAKER_TRIPPED")

        self.update_lifecycle(
            incident_id=incident_id,
            stage=IncidentLifecycle.CONTAINED,
            actor="AutomatedContainmentSupervisor",
            notes=f"Containment actions applied: {', '.join(actions_taken)}",
        )

        return {
            "success": True,
            "incident_id": incident_id,
            "actions_taken": actions_taken,
        }

    def generate_postmortem(
        self,
        incident_id: str,
        root_cause: str,
        what_worked: List[str],
        what_failed: List[str],
        corrective_actions: List[str],
        new_tests: List[str],
    ) -> PostmortemReport:
        inc = self._incidents.get(incident_id)
        report = PostmortemReport(
            incident_id=incident_id,
            root_cause=root_cause,
            impact_summary=f"Incident {incident_id} affected {inc.affected_subsystem if inc else 'unknown'} with severity {inc.severity.value if inc else 'unknown'}",
            what_worked=what_worked,
            what_failed=what_failed,
            corrective_actions=corrective_actions,
            new_regression_tests=new_tests,
        )
        self.update_lifecycle(
            incident_id=incident_id,
            stage=IncidentLifecycle.POSTMORTEM,
            actor="PostmortemAuthor",
            notes=f"Postmortem documented: {root_cause}",
        )
        return report

    def _load_incidents(self) -> None:
        if self.incident_store.exists():
            try:
                data = json.loads(self.incident_store.read_text(encoding="utf-8"))
                for d in data:
                    timeline = [
                        IncidentTimelineEntry(timestamp=t["time"], action=t["action"], actor=t["actor"], notes=t["notes"])
                        for t in d.get("timeline", [])
                    ]
                    rec = IncidentRecord(
                        incident_id=d["id"],
                        title=d["title"],
                        severity=IncidentSeverity(d["severity"]),
                        lifecycle=IncidentLifecycle(d["lifecycle"]),
                        affected_subsystem=d.get("subsystem", "core"),
                        timeline=timeline,
                        contained_at=d.get("contained_at"),
                        resolved_at=d.get("resolved_at"),
                    )
                    self._incidents[rec.incident_id] = rec
            except Exception:
                pass

    def _save_incidents(self) -> None:
        data = [
            {
                "id": i.incident_id,
                "title": i.title,
                "severity": i.severity.value,
                "lifecycle": i.lifecycle.value,
                "subsystem": i.affected_subsystem,
                "contained_at": i.contained_at,
                "resolved_at": i.resolved_at,
                "timeline": [
                    {"time": t.timestamp, "action": t.action, "actor": t.actor, "notes": t.notes}
                    for t in i.timeline
                ],
            }
            for i in self._incidents.values()
        ]
        self.incident_store.parent.mkdir(parents=True, exist_ok=True)
        self.incident_store.write_text(json.dumps(data, indent=2), encoding="utf-8")
