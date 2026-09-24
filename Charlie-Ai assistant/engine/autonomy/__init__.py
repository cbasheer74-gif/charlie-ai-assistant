"""engine.autonomy — Autonomous Work Engine and Multi-Agent Orchestration for JARVIS."""

from engine.autonomy.context import ArtifactRecord, ArtifactRegistry, ExecutionContext
from engine.autonomy.task_graph import TaskGraph, TaskNode, TaskStatus
from engine.autonomy.classifier import TaskComplexityClassifier, GoalInterpreter, TaskComplexity
from engine.autonomy.queue_locks import TaskQueueManager, ResourceLockManager, TaskPriority
from engine.autonomy.loop_detector import LoopDetector
from engine.autonomy.replanner import Replanner
from engine.autonomy.resume_manager import ResumeManager
from engine.autonomy.guard import ExternalActionGuard, ExternalActionType
from engine.autonomy.orchestrator import AutonomyOrchestrator, AutonomyLevel

__all__ = [
    "ArtifactRecord",
    "ArtifactRegistry",
    "ExecutionContext",
    "TaskGraph",
    "TaskNode",
    "TaskStatus",
    "TaskComplexityClassifier",
    "GoalInterpreter",
    "TaskComplexity",
    "TaskQueueManager",
    "ResourceLockManager",
    "TaskPriority",
    "LoopDetector",
    "Replanner",
    "ResumeManager",
    "ExternalActionGuard",
    "ExternalActionType",
    "AutonomyOrchestrator",
    "AutonomyLevel",
]
