"""engine/threadpool.py — High-Performance Background Threadpool Offload Engine.

Provides centralized, prioritized worker pools for offloading heavy CPU/IO tasks
(OCR, RAG embeddings, file indexing, model pre-processing) away from the UI thread.
"""
from __future__ import annotations

import atexit
import enum
import functools
import logging
import os
import queue
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

logger = logging.getLogger("charlie.threadpool")

T = TypeVar("T")


class TaskPriority(enum.IntEnum):
    """Task execution priorities (lower integer value = higher priority)."""
    CRITICAL = 0   # User-facing real-time interactions (e.g. barge-in, voice interrupt)
    HIGH     = 1   # Active command processing, LLM stream decoding
    NORMAL   = 2   # Standard background tasks (RAG query, DB writes)
    LOW      = 3   # Indexing, memory summarization, cache eviction
    IDLE     = 4   # Telemetry, periodic cleanups


class PrioritizedTask:
    """Wrapper for items in the priority queue."""
    def __init__(
        self,
        priority: int,
        seq: int,
        fn: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        future: Future,
        name: str = "",
    ):
        self.priority = priority
        self.seq = seq
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.future = future
        self.name = name or fn.__name__
        self.enqueued_at = time.time()

    def __lt__(self, other: PrioritizedTask) -> bool:
        if self.priority == other.priority:
            return self.seq < other.seq
        return self.priority < other.priority


class CharlieThreadPool:
    """Enterprise-grade background threadpool with priority scheduling and telemetry."""

    def __init__(
        self,
        max_workers: Optional[int] = None,
        thread_name_prefix: str = "CharlieWorker",
    ):
        cpu_cnt = os.cpu_count() or 4
        self._max_workers = max_workers or max(4, min(32, cpu_cnt * 2))
        self._prefix = thread_name_prefix
        self._queue: queue.PriorityQueue[PrioritizedTask] = queue.PriorityQueue()
        self._workers: List[threading.Thread] = []
        self._shutdown = False
        self._seq = 0
        self._lock = threading.Lock()

        # Telemetry
        self._completed_count = 0
        self._failed_count = 0
        self._total_exec_time = 0.0

        self._start_workers()
        atexit.register(self.shutdown, wait=False)

    def _start_workers(self) -> None:
        with self._lock:
            for i in range(self._max_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    name=f"{self._prefix}-{i+1}",
                    daemon=True,
                )
                t.start()
                self._workers.append(t)

    def _worker_loop(self) -> None:
        while not self._shutdown:
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task is None:
                self._queue.task_done()
                break

            if task.future.cancelled():
                self._queue.task_done()
                continue

            # Execute
            t_start = time.time()
            try:
                if not task.future.set_running_or_notify_cancel():
                    self._queue.task_done()
                    continue

                res = task.fn(*task.args, **task.kwargs)
                task.future.set_result(res)
                with self._lock:
                    self._completed_count += 1
                    self._total_exec_time += (time.time() - t_start)
            except BaseException as exc:
                task.future.set_exception(exc)
                with self._lock:
                    self._failed_count += 1
                logger.error(f"[ThreadPool] Task {task.name} failed: {exc}", exc_info=False)
            finally:
                self._queue.task_done()

    def submit(
        self,
        fn: Callable[..., T],
        *args: Any,
        priority: TaskPriority = TaskPriority.NORMAL,
        name: str = "",
        **kwargs: Any,
    ) -> Future[T]:
        """Submit a callable with priority scheduling. Returns a standard concurrent.futures.Future."""
        if self._shutdown:
            fut: Future[T] = Future()
            fut.set_exception(RuntimeError("CharlieThreadPool is shut down"))
            return fut

        fut = Future()
        with self._lock:
            self._seq += 1
            seq = self._seq

        task = PrioritizedTask(
            priority=int(priority),
            seq=seq,
            fn=fn,
            args=args,
            kwargs=kwargs,
            future=fut,
            name=name,
        )
        self._queue.put(task)
        return fut

    def run_with_callback(
        self,
        fn: Callable[..., T],
        *args: Any,
        on_success: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        name: str = "",
        **kwargs: Any,
    ) -> Future[T]:
        """Runs task asynchronously and fires success/error callbacks on completion."""
        fut = self.submit(fn, *args, priority=priority, name=name, **kwargs)

        def _done(f: Future[T]) -> None:
            exc = f.exception()
            if exc:
                if on_error:
                    try:
                        on_error(exc)
                    except Exception as cb_err:
                        logger.error(f"Callback on_error failed: {cb_err}")
            else:
                if on_success:
                    try:
                        on_success(f.result())
                    except Exception as cb_err:
                        logger.error(f"Callback on_success failed: {cb_err}")

        fut.add_done_callback(_done)
        return fut

    def execute_with_timeout(
        self,
        fn: Callable[..., T],
        *args: Any,
        timeout_sec: float = 5.0,
        default: Optional[T] = None,
        priority: TaskPriority = TaskPriority.HIGH,
        **kwargs: Any,
    ) -> Optional[T]:
        """Execute a task in background with synchronous timeout waiting."""
        fut = self.submit(fn, *args, priority=priority, **kwargs)
        try:
            return fut.result(timeout=timeout_sec)
        except Exception as e:
            logger.warning(f"execute_with_timeout timed out/failed for {fn.__name__}: {e}")
            fut.cancel()
            return default

    def stats(self) -> Dict[str, Any]:
        """Return pool telemetry and execution statistics."""
        with self._lock:
            q_size = self._queue.qsize()
            comp = self._completed_count
            fail = self._failed_count
            avg_time = (self._total_exec_time / comp) if comp > 0 else 0.0

        return {
            "workers_total": self._max_workers,
            "tasks_queued": q_size,
            "tasks_completed": comp,
            "tasks_failed": fail,
            "avg_exec_sec": round(avg_time, 4),
        }

    def shutdown(self, wait: bool = True, cancel_futures: bool = True) -> None:
        """Gracefully stop all worker threads."""
        self._shutdown = True
        if cancel_futures:
            while not self._queue.empty():
                try:
                    task = self._queue.get_nowait()
                    if task and not task.future.done():
                        task.future.cancel()
                    self._queue.task_done()
                except Exception:
                    break

        if wait:
            for t in self._workers:
                if t.is_alive():
                    t.join(timeout=1.0)


# Global Singleton
_global_pool: Optional[CharlieThreadPool] = None


def get_threadpool() -> CharlieThreadPool:
    """Access global high-performance threadpool singleton."""
    global _global_pool
    if _global_pool is None:
        _global_pool = CharlieThreadPool()
    return _global_pool


def offload(priority: TaskPriority = TaskPriority.NORMAL, name: str = ""):
    """Decorator to automatically execute a function on the background threadpool."""
    def decorator(func: Callable[..., T]) -> Callable[..., Future[T]]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Future[T]:
            return get_threadpool().submit(
                func,
                *args,
                priority=priority,
                name=name or func.__name__,
                **kwargs,
            )
        return wrapper
    return decorator
