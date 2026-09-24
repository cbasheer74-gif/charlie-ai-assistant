"""engine/tool_registry.py — Standardized Central Tool Registry.

Exposes metadata, risk levels, parameter schemas, execution guards,
and verification/rollback hooks for all tools.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from engine.db import get_db, utc_now_iso
from engine.permissions import PermissionManager, RiskLevel
from engine.verification import VerificationEngine


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    risk_level: RiskLevel
    handler: Callable[..., Any]
    verify_fn: Optional[Callable[..., Any]] = None
    rollback_fn: Optional[Callable[..., Any]] = None


class ToolRegistry:
    """Central registry enforcing schemas, permissions, history, and verification."""

    def __init__(self, permissions: PermissionManager, verification: VerificationEngine):
        self.permissions = permissions
        self.verification = verification
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        risk_level: RiskLevel,
        handler: Callable[..., Any],
        verify_fn: Optional[Callable[..., Any]] = None,
        rollback_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            risk_level=risk_level,
            handler=handler,
            verify_fn=verify_fn,
            rollback_fn=rollback_fn,
        )

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    get_tool = get

    def execute(self, name: str, parameters: Dict[str, Any], task_id: Optional[str] = None) -> Any:
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Tool '{name}' is not registered.")

        start_time = time.perf_counter()
        status = "completed"
        res = None

        try:
            # Check permissions
            if self.permissions.requires_confirmation(tool.risk_level):
                status = "blocked_confirmation"
                return f"[CONFIRMATION_PENDING] Action '{name}' requires user confirmation."

            res = tool.handler(**parameters)
            if tool.verify_fn:
                v_ok, v_msg = tool.verify_fn(res)
                if not v_ok:
                    status = "verification_failed"
                    return f"Action succeeded but verification failed: {v_msg}"

            return res
        except Exception as e:
            status = "failed"
            raise
        finally:
            duration = round(time.perf_counter() - start_time, 3)
            self._log_execution(task_id, name, parameters, res, status, duration)

    execute_tool = execute


    def _log_execution(
        self,
        task_id: Optional[str],
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        status: str,
        duration: float,
    ) -> None:
        try:
            now = utc_now_iso()
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO tool_execution_history (
                        id, task_id, tool_name, arguments_summary, result_summary, status, duration, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        f"hist_{uuid.uuid4().hex[:12]}",
                        task_id,
                        tool_name,
                        str(args)[:300],
                        str(result)[:300],
                        status,
                        duration,
                        now,
                    ),
                )
        except Exception:
            pass
