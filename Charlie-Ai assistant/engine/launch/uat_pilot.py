"""
JARVIS Phase 15: User Acceptance Testing (UAT) & Pilot Program Engine
Executes multi-persona UAT scenarios, manages pilot cohort progression,
and collects privacy-safe user feedback.
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from engine.launch.models import (
    FeedbackItem,
    PilotRegistration,
    PilotStage,
    UATCase,
    UATPersona,
    UATStatus,
)


class UATManager:
    """Manages User Acceptance Test execution across realistic user personas."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).resolve().parent.parent.parent / "config"
        self.uat_store = self.data_dir / "uat_cases.json"
        self._cases: Dict[str, UATCase] = {}
        self._initialize_golden_uat_cases()

    def get_case(self, uat_id: str) -> Optional[UATCase]:
        return self._cases.get(uat_id)

    def list_cases(self) -> List[UATCase]:
        return list(self._cases.values())

    def record_uat_result(
        self,
        uat_id: str,
        status: UATStatus,
        actual_behavior: str,
        evidence_ref: str,
        feedback: str = "",
    ) -> Dict[str, Any]:
        case = self._cases.get(uat_id)
        if not case:
            return {"success": False, "reason": "CASE_NOT_FOUND"}

        case.status = status
        case.actual_behavior = actual_behavior
        case.evidence_ref = evidence_ref
        case.feedback = feedback
        self._save_cases()

        return {
            "success": True,
            "uat_id": uat_id,
            "status": status.value,
            "evidence_ref": evidence_ref,
        }

    def _initialize_golden_uat_cases(self) -> None:
        defaults = [
            UATCase(
                uat_id="UAT_BEGINNER_01",
                user_persona=UATPersona.BEGINNER,
                scenario_name="First-Run Setup and Simple Automation",
                preconditions=["Clean Windows installation", "Zero developer tools installed"],
                steps=["Run JARVIS-Setup.exe", "Complete onboarding", "Ask to open Notepad", "Exit JARVIS"],
                expected_behavior="Install, onboarding, and Notepad control succeed without opening terminal.",
            ),
            UATCase(
                uat_id="UAT_DEVELOPER_02",
                user_persona=UATPersona.DEVELOPER,
                scenario_name="Coding Project Checkpoint and Test Execution",
                preconditions=["Repository with test suite cloned"],
                steps=["Say 'Last coding project continue karo'", "Run unit tests", "Inspect test status"],
                expected_behavior="Project memory retrieved, checkpoint restored, tests executed independently.",
            ),
            UATCase(
                uat_id="UAT_OFFICE_03",
                user_persona=UATPersona.OFFICE_USER,
                scenario_name="Daily Brief and Excel Summary",
                preconditions=["Calendar events and monthly spreadsheet present"],
                steps=["Request daily brief", "Generate monthly report from workbook"],
                expected_behavior="Accurate brief generated, Excel formulas preserved with verified totals.",
            ),
            UATCase(
                uat_id="UAT_CONTENT_04",
                user_persona=UATPersona.CONTENT_CREATOR,
                scenario_name="Trend Hunting and Video Scripting",
                preconditions=["Web connection active"],
                steps=["Ask for today's tech trends", "Create 30s Short script brief"],
                expected_behavior="Fresh web research with verified citations and structured video brief.",
            ),
            UATCase(
                uat_id="UAT_VOICE_05",
                user_persona=UATPersona.VOICE,
                scenario_name="Hinglish Voice Commands and Emergency Stop",
                preconditions=["Microphone connected"],
                steps=["Say 'Hey Jarvis, Chrome kholo'", "Say 'Stop'"],
                expected_behavior="Wake detected, Hinglish recognized, browser opened, automation halted immediately.",
            ),
            UATCase(
                uat_id="UAT_GENERAL_06",
                user_persona=UATPersona.GENERAL_USER,
                scenario_name="Safe Web Query and Settings Discovery",
                preconditions=["Standard desktop session"],
                steps=["Ask for local weather", "Navigate to Settings", "Locate Privacy controls"],
                expected_behavior="Accurate response without terminal prompts, privacy options visible.",
            ),
        ]
        for c in defaults:
            self._cases[c.uat_id] = c

    def _save_cases(self) -> None:
        data = [
            {
                "uat_id": c.uat_id,
                "persona": c.user_persona.value,
                "scenario": c.scenario_name,
                "status": c.status.value,
                "actual": c.actual_behavior,
                "evidence": c.evidence_ref,
            }
            for c in self._cases.values()
        ]
        self.uat_store.parent.mkdir(parents=True, exist_ok=True)
        self.uat_store.write_text(json.dumps(data, indent=2), encoding="utf-8")


class PilotManager:
    """Manages pilot cohort progression (Dogfood -> Alpha -> Beta -> RC)."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).resolve().parent.parent.parent / "config"
        self.pilot_store = self.data_dir / "pilot_devices.json"
        self._devices: Dict[str, PilotRegistration] = {}

    def register_device(
        self,
        cohort: Any,
        os_info: str = "Windows 10 x64",
        ram_gb: float = 16.0,
    ) -> PilotRegistration:
        if isinstance(cohort, str):
            cohort = PilotStage(cohort)
        dev_id = f"PILOT_{uuid.uuid4().hex[:8].upper()}"
        reg = PilotRegistration(
            device_id=dev_id,
            cohort=cohort,
            os_info=os_info,
            ram_gb=ram_gb,
            channel="BETA" if cohort == PilotStage.CLOSED_BETA else "STABLE",
        )
        self._devices[dev_id] = reg
        self._save_devices()
        return reg

    def evaluate_cohort_health(self, cohort: PilotStage) -> Dict[str, Any]:
        cohort_devs = [d for d in self._devices.values() if d.cohort == cohort]
        total = len(cohort_devs)
        healthy = sum(1 for d in cohort_devs if d.last_health_state == "HEALTHY")
        return {
            "cohort": cohort.value,
            "total_devices": total,
            "healthy_devices": healthy,
            "health_rate_percent": round((healthy / total * 100.0) if total > 0 else 100.0, 1),
            "gate_passed": total == 0 or (healthy / total >= 0.95),
        }

    def _save_devices(self) -> None:
        data = [
            {
                "device_id": d.device_id,
                "cohort": d.cohort.value,
                "os": d.os_info,
                "ram": d.ram_gb,
                "health": d.last_health_state,
            }
            for d in self._devices.values()
        ]
        self.pilot_store.parent.mkdir(parents=True, exist_ok=True)
        self.pilot_store.write_text(json.dumps(data, indent=2), encoding="utf-8")


class FeedbackManager:
    """Manages structured user feedback with privacy-safe diagnostic previews."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).resolve().parent.parent.parent / "config"
        self.feedback_store = self.data_dir / "user_feedback.json"
        self._items: List[FeedbackItem] = []

    def submit_feedback(
        self,
        category: str,
        description: str,
        component: Optional[str] = None,
        rating: int = 5,
    ) -> FeedbackItem:
        fb_id = f"FB_{uuid.uuid4().hex[:8].upper()}"
        item = FeedbackItem(
            feedback_id=fb_id,
            category=category,
            description=description,
            timestamp=datetime.now(timezone.utc).isoformat(),
            component=component,
            rating=rating,
        )
        self._items.append(item)
        self._save_feedback()
        return item

    def get_feedback_count(self) -> int:
        return len(self._items)

    def _save_feedback(self) -> None:
        data = [
            {
                "id": f.feedback_id,
                "category": f.category,
                "description": f.description,
                "component": f.component,
                "rating": f.rating,
                "timestamp": f.timestamp,
            }
            for f in self._items
        ]
        self.feedback_store.parent.mkdir(parents=True, exist_ok=True)
        self.feedback_store.write_text(json.dumps(data, indent=2), encoding="utf-8")
