"""
JARVIS Phase 11: Offline AI Manager
Detects network connectivity, switches gracefully to local AI models, and prevents crashes during internet outage.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from .models import NetworkState

logger = logging.getLogger("jarvis.ai.offline")


class OfflineAIManager:
    """Manages offline detection and routing adjustments."""

    def __init__(self, initial_state: NetworkState = NetworkState.ONLINE):
        self.network_state = initial_state

    def set_network_state(self, state: NetworkState):
        self.network_state = state
        logger.info(f"Network state set to: {state.value}")

    def is_offline(self) -> bool:
        return self.network_state == NetworkState.OFFLINE

    def check_research_allowed(self, is_live_web_query: bool = False) -> Tuple[bool, str]:
        """Validates if web search or live internet research is permissible."""
        if self.is_offline() and is_live_web_query:
            return False, "Live internet research unavailable in offline mode. Cached knowledge only."
        return True, "Research allowed."

    def get_offline_status(self) -> Dict[str, Any]:
        return {
            "network_state": self.network_state.value,
            "is_offline": self.is_offline(),
            "local_tools_ready": True,
            "local_ai_ready": True,
            "cloud_disabled": self.is_offline(),
        }
