"""core/runtime_voice_control.py — Global registry for active Charlie voice runtime.

Provides a clean, decoupled bridge allowing actions (such as actions/voice_control.py)
to access and control the live CharlieLive session without circular imports
or spawning parallel/mock audio engines.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("charlie.runtime_voice_control")

_active_runtime: Optional[Any] = None


def register_voice_runtime(runtime: Any) -> None:
    """Register the active CharlieLive / voice runtime instance."""
    global _active_runtime
    _active_runtime = runtime
    name = type(runtime).__name__ if runtime is not None else "None"
    logger.info("Voice runtime registered: %s", name)


def unregister_voice_runtime() -> None:
    """Clear the active voice runtime reference on shutdown."""
    global _active_runtime
    _active_runtime = None
    logger.info("Voice runtime unregistered.")


def get_voice_runtime() -> Optional[Any]:
    """Obtain reference to active Charlie voice runtime, if registered."""
    return _active_runtime
