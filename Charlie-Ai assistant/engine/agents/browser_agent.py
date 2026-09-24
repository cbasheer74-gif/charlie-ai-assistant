"""engine/agents/browser_agent.py — Browser Automation Specialist.

Distinguishes safe read-only browsing from high-impact external actions
(form submission, payments, account changes, publishing).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.agents.base import BaseAgent


class BrowserAgent(BaseAgent):
    """Specialist agent for web browsing and web automation."""

    def can_handle(self, user_intent: str) -> bool:
        low = user_intent.lower()
        return any(w in low for w in ("browser", "open website", "web page", "navigate", "search web", "download page"))
