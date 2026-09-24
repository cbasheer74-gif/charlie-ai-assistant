"""engine/router.py — Agent Router and Intent Dispatcher.

Directs user requests to the appropriate specialized agent while maintaining
one unified shared source of truth across all components.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from engine.agents.antigravity_agent import AntigravityAgent
from engine.agents.base import BaseAgent
from engine.agents.browser_agent import BrowserAgent
from engine.agents.coding_agent import CodingAgent
from engine.agents.computer_agent import ComputerAgent
from engine.agents.file_agent import FileAgent
from engine.agents.research_agent import ResearchAgent
from engine.agents.spreadsheet_agent import SpreadsheetAgent
from engine.agents.troubleshooting_agent import TroubleshootingAgent
from engine.agents.video_agent import VideoAgent
from engine.error_recovery import ErrorRecoveryEngine
from engine.memory_manager import MemoryManager
from engine.permissions import PermissionManager
from engine.rollback import RollbackManager
from engine.task_planner import TaskPlanner
from engine.verification import VerificationEngine


class AgentRouter:
    """Classifies user intent and routes execution to the correct specialist."""

    def __init__(
        self,
        memory: MemoryManager,
        planner: TaskPlanner,
        permissions: PermissionManager,
        verification: VerificationEngine,
        recovery: ErrorRecoveryEngine,
        rollback: RollbackManager,
    ):
        self.memory = memory
        self.planner = planner
        self.permissions = permissions
        self.verification = verification
        self.recovery = recovery
        self.rollback = rollback

        # Specialist instances sharing one single source of truth
        self.agents: Dict[str, BaseAgent] = {
            "spreadsheet": SpreadsheetAgent(memory, planner, permissions, verification, recovery, rollback),
            "video": VideoAgent(memory, planner, permissions, verification, recovery, rollback),
            "coding": CodingAgent(memory, planner, permissions, verification, recovery, rollback),
            "antigravity": AntigravityAgent(memory, planner, permissions, verification, recovery, rollback),
            "research": ResearchAgent(memory, planner, permissions, verification, recovery, rollback),
            "computer": ComputerAgent(memory, planner, permissions, verification, recovery, rollback),
            "file": FileAgent(memory, planner, permissions, verification, recovery, rollback),
            "browser": BrowserAgent(memory, planner, permissions, verification, recovery, rollback),
            "troubleshooting": TroubleshootingAgent(memory, planner, permissions, verification, recovery, rollback),
        }

    def route_intent(self, user_request: str) -> Tuple[str, BaseAgent]:
        """Detect request intent and return (agent_name, agent_instance)."""
        low = user_request.lower()

        # Priority 1: Specific tools and domains
        if any(w in low for w in ("antigravity", "continue in antigravity", "ide prompt")):
            return "antigravity", self.agents["antigravity"]

        if any(w in low for w in ("excel", "sheet", "spreadsheet", ".xlsx", ".csv", "clean excel")):
            return "spreadsheet", self.agents["spreadsheet"]

        if any(w in low for w in ("short", "shorts", "reel", "youtube video", "vertical video", "video edit")):
            return "video", self.agents["video"]

        if any(w in low for w in ("code", "debug", "refactor", "syntax", "git", "build", "compile")):
            return "coding", self.agents["coding"]

        if any(w in low for w in ("error", "crash", "failed", "stack trace", "why did it fail")):
            return "troubleshooting", self.agents["troubleshooting"]

        if any(w in low for w in ("trend", "trending", "latest", "today", "news")):
            return "research", self.agents["research"]

        if any(w in low for w in ("browser", "open website", "web page")):
            return "browser", self.agents["browser"]

        if any(w in low for w in ("file", "folder", "copy file", "move file", "rename")):
            return "file", self.agents["file"]

        return "computer", self.agents["computer"]

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """Fetch agent instance by class name or slug."""
        clean = name.lower().replace("agent", "").strip()
        return self.agents.get(clean) or self.agents.get(name.lower()) or self.agents.get("computer")

