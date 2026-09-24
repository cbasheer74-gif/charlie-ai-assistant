"""engine/agents/coding_agent.py — Senior Software Engineering Specialist.

Inspects git repositories, identifies architecture and dependencies, executes targeted
code modifications with backup safety, and runs syntax verification.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from engine.autonomy.task_graph import TaskNode

from engine.agents.base import BaseAgent


class CodingAgent(BaseAgent):
    """Specialist agent for software engineering, debugging, and targeted refactoring."""

    def can_handle(self, target: Union[str, TaskNode]) -> bool:
        if isinstance(target, str):
            low = target.lower()
        else:
            low = f"{getattr(target, 'name', '')} {getattr(target, 'description', '')} {getattr(target, 'tool', '')}".lower()
        return any(w in low for w in ("code", "debug", "refactor", "syntax", "git", "build", "test", "compile", "dependency"))

    def inspect_project(self, repo_path: Path | str) -> Dict[str, Any]:
        """Inspect git status, stack indicators, and recent modifications."""
        p = Path(repo_path).resolve()
        if not p.is_dir():
            return {"error": f"Project directory {p} does not exist."}

        # 1. Stack detection
        stack = []
        if (p / "package.json").exists(): stack.append("Node.js")
        if (p / "requirements.txt").exists() or (p / "pyproject.toml").exists(): stack.append("Python")
        if (p / "pubspec.yaml").exists(): stack.append("Flutter/Dart")
        if (p / "pom.xml").exists() or (p / "build.gradle").exists(): stack.append("Java/Kotlin")

        # 2. Git status
        git_status = "Not a git repository"
        git_branch = "None"
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        if (p / ".git").exists():
            try:
                res_b = subprocess.run(["git", "branch", "--show-current"], cwd=p, capture_output=True, text=True, timeout=5, **flags)
                if res_b.returncode == 0:
                    git_branch = res_b.stdout.strip()
                res_s = subprocess.run(["git", "status", "--short"], cwd=p, capture_output=True, text=True, timeout=5, **flags)
                if res_s.returncode == 0:
                    git_status = res_s.stdout.strip() or "Clean working tree"
            except Exception:
                pass

        return {
            "root": str(p),
            "detected_stack": stack or ["General"],
            "git_branch": git_branch,
            "git_status": git_status,
        }

    def apply_targeted_fix(
        self,
        file_path: Path | str,
        new_content: str,
        workspace_root: Optional[Path | str] = None,
    ) -> Dict[str, Any]:
        """Backup file, write updated content, and verify syntax."""
        p = Path(file_path).resolve()
        root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()

        try:
            if not p.is_relative_to(root):
                return {"status": "failed", "error": f"Target path {p} is outside allowed workspace {root}."}
        except (AttributeError, ValueError):
            return {"status": "failed", "error": f"Target path {p} is invalid or outside workspace."}

        if not p.is_file():
            return {"status": "failed", "error": f"File {p.name} does not exist."}

        # Safe backup before write
        backup = self.rollback.backup_file(p)
        try:
            p.write_text(new_content, encoding="utf-8")
            ok, v_msg = self.verification.verify_code(p)
            if not ok:
                # Syntax failed — rollback immediately
                if backup:
                    self.rollback.restore_file(backup, p)
                return {
                    "status": "rolled_back",
                    "error": f"Syntax verification failed: {v_msg}. Reverted to previous state.",
                }

            return {
                "status": "success",
                "file": str(p),
                "verification": v_msg,
                "backup": str(backup) if backup else "",
            }
        except Exception as e:
            if backup:
                self.rollback.restore_file(backup, p)
            return {"status": "failed", "error": str(e)}
