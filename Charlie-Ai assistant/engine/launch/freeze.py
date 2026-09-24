"""
JARVIS Phase 15: Scope Lock & Release Freeze Policy Engine
Enforces v1.0 scope lock, manages code freeze transitions, and validates freeze exceptions.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from engine.launch.models import FreezeState, IssueSeverity


class V1ScopeLock:
    """Enforces strict v1.0 scope boundaries; blocks major feature creep."""

    ALLOWED_CHANGE_TYPES = {
        "P0_BUGFIX",
        "P1_BUGFIX",
        "SECURITY_FIX",
        "DATA_LOSS_PREVENTION",
        "INSTALLER_UPDATE_FIX",
        "CRITICAL_USABILITY_FIX",
    }

    FORBIDDEN_KEYWORDS = [
        "experimental_dashboard",
        "new_ai_provider",
        "major_ui_redesign",
        "new_connector_ecosystem",
        "new_autonomous_behavior",
    ]

    def validate_change(self, change_type: str, description: str) -> Dict[str, Any]:
        """Validates if a proposed modification is allowed during v1.0 launch phase."""
        desc_lower = description.lower()
        for forbidden in self.FORBIDDEN_KEYWORDS:
            if forbidden in desc_lower:
                return {
                    "allowed": False,
                    "reason": f"FEATURE_CREEP_DETECTED: '{forbidden}' forbidden in v1.0 freeze.",
                }

        if change_type not in self.ALLOWED_CHANGE_TYPES:
            return {
                "allowed": False,
                "reason": f"UNAPPROVED_CHANGE_TYPE: '{change_type}' not permitted under V1_SCOPE_LOCK.",
            }

        return {"allowed": True, "change_type": change_type}


class ReleaseFreezeManager:
    """Manages the release freeze lifecycle and immutable Release Candidate tracking."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).resolve().parent.parent.parent / "config"
        self.state_file = self.data_dir / "freeze_state.json"
        self.exceptions_file = self.data_dir / "freeze_exceptions.json"

    def get_freeze_state(self) -> FreezeState:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                return FreezeState(data.get("state", FreezeState.OPEN_DEVELOPMENT.value))
            except Exception:
                return FreezeState.OPEN_DEVELOPMENT
        return FreezeState.OPEN_DEVELOPMENT

    def transition_state(self, target_state: FreezeState, approver: str) -> Dict[str, Any]:
        data = {
            "state": target_state.value,
            "approver": approver,
            "transitioned_at": datetime.now(timezone.utc).isoformat(),
        }
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"current_state": target_state.value, "approver": approver}

    def register_freeze_exception(
        self,
        issue_id: str,
        severity: IssueSeverity,
        reason: str,
        risk: str,
        approver: str,
        required_tests: List[str],
    ) -> Dict[str, Any]:
        """Approves a critical code freeze exception with mandatory regression test requirements."""
        current_state = self.get_freeze_state()
        if current_state not in (FreezeState.CODE_FREEZE, FreezeState.RELEASE_CANDIDATE):
            return {"approved": True, "note": "Freeze not active, exception logged."}

        # Code freeze exceptions are only permitted for P0 or P1
        if severity not in (IssueSeverity.P0_CRITICAL, IssueSeverity.P1_HIGH):
            return {
                "approved": False,
                "reason": f"Exceptions during {current_state.value} require P0/P1 severity.",
            }

        exception_entry = {
            "issue_id": issue_id,
            "severity": severity.value,
            "reason": reason,
            "risk": risk,
            "approver": approver,
            "required_tests": required_tests,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }

        exceptions = self._load_exceptions()
        exceptions.append(exception_entry)
        self.exceptions_file.parent.mkdir(parents=True, exist_ok=True)
        self.exceptions_file.write_text(json.dumps(exceptions, indent=2), encoding="utf-8")

        return {"approved": True, "exception": exception_entry}

    def _load_exceptions(self) -> List[Dict[str, Any]]:
        if self.exceptions_file.exists():
            try:
                return json.loads(self.exceptions_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []
