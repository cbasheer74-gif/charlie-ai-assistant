"""CHARLIE Intelligence Engine.

Modular, persistent intelligence architecture for computer control, memory,
task planning, specialized agents, and safety enforcement.
"""

from __future__ import annotations

__version__ = "3.0.0"

from engine.threadpool import CharlieThreadPool, TaskPriority, get_threadpool, offload

__all__ = ["CharlieThreadPool", "TaskPriority", "get_threadpool", "offload"]
