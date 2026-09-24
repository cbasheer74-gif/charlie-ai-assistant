"""engine/skills/recorder.py — Workflow Recorder & Teach Mode Action Capture.

Captures semantic user demonstrations, tool calls, and UI state changes without
recording raw mouse coordinate jitter.
"""

from __future__ import annotations

import time
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class RecordedEvent:
    timestamp: float
    action: str              # e.g. open_application, select_sheet, filter_column, save_file
    adapter: str             # e.g. ExcelAdapter, VideoAdapter, WindowsAdapter
    tool: Optional[str] = None
    target_element: str = "" # e.g. "Export Button", "Sales Worksheet" (semantic, not x,y)
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    app_state: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecordedSession:
    session_id: str
    intent: str
    skill_name_hint: str
    events: List[RecordedEvent] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WorkflowRecorder:
    """Records high-signal demonstration workflows during Teach Mode."""

    def __init__(self):
        self._active_session: Optional[RecordedSession] = None
        self._lock = threading.RLock()

    def start_teach_mode(self, intent: str, skill_name_hint: str = "") -> str:
        with self._lock:
            if self._active_session is not None:
                raise RuntimeError("Teach Mode is already recording a workflow.")
            session_id = f"teach_{uuid.uuid4().hex[:8]}"
            self._active_session = RecordedSession(
                session_id=session_id,
                intent=intent,
                skill_name_hint=skill_name_hint or intent.replace(" ", "_"),
            )
            return session_id

    def is_recording(self) -> bool:
        with self._lock:
            return self._active_session is not None

    def record_action(
        self,
        action: str,
        adapter: str = "generic",
        tool: Optional[str] = None,
        target_element: str = "",
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        app_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record a semantic step (strictly filters out raw coordinate clicks)."""
        with self._lock:
            if not self._active_session:
                return False

            # Drop raw coordinate noise if no semantic element or action is present
            if action == "mouse_click" and not target_element and not inputs:
                return False

            event = RecordedEvent(
                timestamp=time.time(),
                action=action,
                adapter=adapter,
                tool=tool,
                target_element=target_element,
                inputs=inputs or {},
                outputs=outputs or {},
                app_state=app_state or {},
            )
            self._active_session.events.append(event)
            return True

    def stop_teach_mode(self) -> Optional[RecordedSession]:
        with self._lock:
            if not self._active_session:
                return None
            session = self._active_session
            session.completed_at = datetime.now().isoformat()
            self._active_session = None
            return session

    def get_current_session(self) -> Optional[RecordedSession]:
        with self._lock:
            return self._active_session
