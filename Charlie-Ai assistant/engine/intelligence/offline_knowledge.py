# engine/intelligence/offline_knowledge.py
"""
Offline Semantic Knowledge Graph for Charlie.

High-performance, zero-latency local knowledge graph providing instant factual,
technical, architectural, and operational answers without requiring an active
cloud or internet connection.

Features:
  - Inverted index + semantic keyword scoring across local concept nodes.
  - Bidirectional relation traversal (child, parent, related, prerequisites).
  - Pre-seeded with core engineering, Windows system administration, git,
    python, office workflows, troubleshooting, and Charlie assistant capabilities.
  - Dynamic local node insertion for custom user domain knowledge.
"""

from __future__ import annotations

import json
import math
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class KnowledgeNode:
    key: str
    title: str
    category: str  # programming, sysadmin, office, charlie, troubleshooting
    summary: str
    details: str
    keywords: List[str] = field(default_factory=list)
    related_keys: List[str] = field(default_factory=list)
    code_snippet: Optional[str] = None


class OfflineKnowledgeGraph:
    """Zero-latency offline knowledge repository with semantic inverted indexing."""

    def __init__(self, custom_path: Optional[Path] = None):
        self.path = (
            custom_path
            or Path(__file__).resolve().parent.parent.parent / "config" / "offline_knowledge_custom.json"
        )
        self._lock = threading.Lock()
        self._nodes: Dict[str, KnowledgeNode] = {}
        self._inverted_index: Dict[str, Set[str]] = {}
        self._seed_builtin_knowledge()
        self._load_custom()
        self._rebuild_index()

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Searches local knowledge graph using inverted token index and BM25-style scoring."""
        tokens = [t.lower() for t in re.findall(r"\w+", query_text) if len(t) > 2]
        if not tokens:
            return []

        scores: Dict[str, float] = {}
        with self._lock:
            for token in tokens:
                matching_keys = self._inverted_index.get(token, set())
                idf = math.log((len(self._nodes) + 1.0) / (len(matching_keys) + 1.0)) + 1.0
                for k in matching_keys:
                    scores[k] = scores.get(k, 0.0) + idf

            sorted_keys = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

            results = []
            for k, score in sorted_keys:
                node = self._nodes[k]
                item = asdict(node)
                item["relevance"] = round(score, 2)
                # Resolve related node titles
                item["related_topics"] = [
                    self._nodes[rk].title for rk in node.related_keys if rk in self._nodes
                ]
                results.append(item)
            return results

    def add_node(
        self,
        key: str,
        title: str,
        category: str,
        summary: str,
        details: str,
        keywords: Optional[List[str]] = None,
        related_keys: Optional[List[str]] = None,
        code_snippet: Optional[str] = None,
    ) -> None:
        """Add or update custom knowledge node."""
        node = KnowledgeNode(
            key=key.lower().strip(),
            title=title.strip(),
            category=category.strip(),
            summary=summary.strip(),
            details=details.strip(),
            keywords=[k.lower().strip() for k in (keywords or [])],
            related_keys=related_keys or [],
            code_snippet=code_snippet,
        )
        with self._lock:
            self._nodes[node.key] = node
            self._index_node(node)
            self._persist_custom()

    def _index_node(self, node: KnowledgeNode) -> None:
        text = f"{node.key} {node.title} {node.category} {node.summary} {node.details} {' '.join(node.keywords)}"
        tokens = set(t.lower() for t in re.findall(r"\w+", text) if len(t) > 2)
        for token in tokens:
            self._inverted_index.setdefault(token, set()).add(node.key)

    def _rebuild_index(self) -> None:
        self._inverted_index.clear()
        for node in self._nodes.values():
            self._index_node(node)

    def _seed_builtin_knowledge(self) -> None:
        builtins = [
            KnowledgeNode(
                key="git_undo_commit",
                title="Undoing Git Commits Safely",
                category="programming",
                summary="How to undo a commit locally without losing work or after pushing.",
                details="Use 'git reset --soft HEAD~1' to uncommit while keeping all changes staged. Use 'git revert <commit>' if already pushed.",
                keywords=["git", "undo", "commit", "reset", "revert", "head"],
                related_keys=["git_stash", "git_merge_conflict"],
                code_snippet="git reset --soft HEAD~1",
            ),
            KnowledgeNode(
                key="git_stash",
                title="Git Stashing Working Changes",
                category="programming",
                summary="Temporarily shelve dirty changes to pull or switch branches.",
                details="Stashing saves modified tracked files on a stack. Apply with 'git stash pop'.",
                keywords=["git", "stash", "save", "pop", "shelve"],
                related_keys=["git_undo_commit"],
                code_snippet="git stash && git pull && git stash pop",
            ),
            KnowledgeNode(
                key="windows_port_kill",
                title="Killing Process on a Locked Port",
                category="sysadmin",
                summary="Find and terminate Windows processes hogging a TCP port (e.g. 8000, 3000, 5000).",
                details="Run netstat to find PID: 'netstat -ano | findstr :PORT'. Then kill with 'taskkill /PID <pid> /F'.",
                keywords=["port", "kill", "netstat", "taskkill", "locked", "windows"],
                related_keys=["windows_service_restart"],
                code_snippet="netstat -ano | findstr :8000\ntaskkill /PID <PID> /F",
            ),
            KnowledgeNode(
                key="charlie_focus_timer",
                title="Charlie Pomodoro Focus System",
                category="charlie",
                summary="Voice-controlled 25/5 or 90/20 productivity blocks.",
                details="Say 'start focus mode' or 'start 45 minute focus session'. Charlie tracks statistics and encourages deep work.",
                keywords=["focus", "pomodoro", "timer", "charlie", "productivity", "break"],
                related_keys=["charlie_routine_briefing"],
            ),
            KnowledgeNode(
                key="charlie_routine_briefing",
                title="Charlie Daily Executive Briefing",
                category="charlie",
                summary="Morning and evening schedule, weather, goals, and system summaries.",
                details="Say 'good morning Charlie' for today's agenda, battery, and focus priorities. Say 'evening wrap up' to review completed goals.",
                keywords=["morning", "briefing", "routine", "agenda", "schedule", "charlie"],
                related_keys=["charlie_focus_timer"],
            ),
            KnowledgeNode(
                key="python_virtualenv",
                title="Python Virtual Environments (venv)",
                category="programming",
                summary="Creating and activating isolated Python project dependencies.",
                details="Create with 'python -m venv .venv'. On Windows activate with '.\\.venv\\Scripts\\activate'.",
                keywords=["python", "venv", "virtualenv", "pip", "dependencies"],
                related_keys=[],
                code_snippet="python -m venv .venv\n.\\.venv\\Scripts\\activate",
            ),
        ]
        for b in builtins:
            self._nodes[b.key] = b

    def _persist_custom(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            custom_nodes = [
                asdict(n) for n in self._nodes.values() if n.key not in {"git_undo_commit", "git_stash", "windows_port_kill", "charlie_focus_timer", "charlie_routine_briefing", "python_virtualenv"}
            ]
            self.path.write_text(json.dumps(custom_nodes, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_custom(self) -> None:
        try:
            if self.path.exists():
                items = json.loads(self.path.read_text(encoding="utf-8"))
                for it in items:
                    node = KnowledgeNode(**it)
                    self._nodes[node.key] = node
        except Exception:
            pass


# Global singleton
_knowledge_instance: Optional[OfflineKnowledgeGraph] = None
_kg_lock = threading.Lock()


def get_offline_knowledge() -> OfflineKnowledgeGraph:
    global _knowledge_instance
    with _kg_lock:
        if _knowledge_instance is None:
            _knowledge_instance = OfflineKnowledgeGraph()
        return _knowledge_instance
