"""engine/autonomy/queue_locks.py — Priority Task Queue & Granular Resource Lock Manager.

Prevents conflicting agents from simultaneously driving the mouse, keyboard,
shared files, or project repositories.
"""

from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class TaskPriority(int, Enum):
    URGENT = 0   # System emergency, rollback, cancellation
    HIGH = 1     # User interactive commands
    NORMAL = 2   # Standard autonomous tasks
    LOW = 3      # Background indexing, cleanup


@dataclass(order=True)
class QueuedTask:
    priority: int
    created_at: float = field(compare=True)
    task_id: str = field(compare=False)
    goal: str = field(compare=False)
    project_id: Optional[str] = field(default=None, compare=False)
    status: str = field(default="QUEUED", compare=False)
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)


class TaskQueueManager:
    """Thread-safe priority queue for autonomous and interactive tasks."""

    def __init__(self):
        self._queue: List[QueuedTask] = []
        self._lock = threading.RLock()
        self._tasks_by_id: Dict[str, QueuedTask] = {}

    def enqueue(
        self,
        task_id: str,
        goal: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> QueuedTask:
        with self._lock:
            q_task = QueuedTask(
                priority=priority.value,
                created_at=time.time(),
                task_id=task_id,
                goal=goal,
                project_id=project_id,
                metadata=metadata or {},
            )
            heapq.heappush(self._queue, q_task)
            self._tasks_by_id[task_id] = q_task
            return q_task

    def dequeue(self) -> Optional[QueuedTask]:
        with self._lock:
            if not self._queue:
                return None
            task = heapq.heappop(self._queue)
            task.status = "RUNNING"
            # Prune terminal tasks if dictionary grows excessively
            if len(self._tasks_by_id) > 500:
                terminal_ids = [
                    tid for tid, t in self._tasks_by_id.items()
                    if t.status in ("COMPLETED", "CANCELLED", "FAILED")
                ]
                for tid in terminal_ids[:100]:
                    self._tasks_by_id.pop(tid, None)
            return task

    def peek(self) -> Optional[QueuedTask]:
        with self._lock:
            return self._queue[0] if self._queue else None

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks_by_id.get(task_id)
            if task:
                task.status = "CANCELLED"
                # Filter out of heap
                self._queue = [t for t in self._queue if t.task_id != task_id]
                heapq.heapify(self._queue)
                return True
            return False

    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    def all_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "task_id": t.task_id,
                    "goal": t.goal,
                    "priority": t.priority,
                    "status": t.status,
                    "project_id": t.project_id,
                }
                for t in self._tasks_by_id.values()
            ]


class ResourceLockManager:
    """Guarantees mutually exclusive access to OS resources (mouse, keyboard, files, repos)."""

    def __init__(self):
        self._locks: Dict[str, str] = {}   # resource_name -> owner_task_id
        self._counts: Dict[str, int] = {}  # resource_name -> reentrancy depth
        self._lock = threading.RLock()

    @staticmethod
    def _normalize(name: str) -> str:
        s = name.strip()
        if any(sep in s for sep in ("/", "\\")) or (len(s) >= 2 and s[1] == ":"):
            from pathlib import Path
            try:
                return str(Path(s).resolve()).lower()
            except Exception:
                pass
        return s.lower()

    def acquire(self, resource_name: str, owner_task_id: str, timeout_sec: float = 2.0) -> bool:
        norm = self._normalize(resource_name)
        start = time.time()

        while time.time() - start < timeout_sec:
            with self._lock:
                current_owner = self._locks.get(norm)
                if current_owner is None:
                    self._locks[norm] = owner_task_id
                    self._counts[norm] = 1
                    return True
                elif current_owner == owner_task_id:
                    self._counts[norm] = self._counts.get(norm, 0) + 1
                    return True
            time.sleep(0.05)

        return False

    def release(self, resource_name: str, owner_task_id: str) -> bool:
        norm = self._normalize(resource_name)
        with self._lock:
            if self._locks.get(norm) == owner_task_id:
                count = self._counts.get(norm, 1) - 1
                if count <= 0:
                    del self._locks[norm]
                    self._counts.pop(norm, None)
                else:
                    self._counts[norm] = count
                return True
            return False

    def release_all(self, owner_task_id: str) -> int:
        """Release all resources currently held by a given task (e.g. at completion or crash)."""
        released = 0
        with self._lock:
            to_remove = [res for res, owner in self._locks.items() if owner == owner_task_id]
            for res in to_remove:
                del self._locks[res]
                self._counts.pop(res, None)
                released += 1
        return released

    def is_locked(self, resource_name: str) -> bool:
        norm = self._normalize(resource_name)
        with self._lock:
            return norm in self._locks

    def get_owner(self, resource_name: str) -> Optional[str]:
        norm = self._normalize(resource_name)
        with self._lock:
            return self._locks.get(norm)
