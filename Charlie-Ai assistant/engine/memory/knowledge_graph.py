"""engine/memory/knowledge_graph.py — Lifelong Episodic User Knowledge Graph for CHARLIE.

Stores, evolves, and retrieves an associative entity-relationship graph of user:
- Preferences (coding style, themes, response tone)
- Active & past projects
- Collaborators & stakeholders
- Work habits & hardware setup
- Temporal weight decay and access reinforcement.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.db import get_db, init_db

logger = logging.getLogger("charlie.memory_graph")


@dataclass
class GraphNode:
    id: str
    name: str
    category: str  # preference, project, skill, person, habit, hardware
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    access_count: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    relation: str  # PREFERS, DISLIKES, WORKS_ON, USES, COLLABORATES_WITH, HAS_HABIT
    weight: float = 1.0
    last_observed: float = field(default_factory=time.time)


class UserMemoryGraph:
    """Manages an evolving lifelong semantic graph of user identity and context."""

    # Common relational extraction heuristics
    EXTRACTION_PATTERNS = [
        (re.compile(r"\b(?:i\s+prefer|i\s+like|i\s+love)\s+([^.,;!?]+)", re.I), "PREFERS", "preference"),
        (re.compile(r"\b(?:i\s+hate|i\s+dislike|don't\s+use|do\s+not\s+like)\s+([^.,;!?]+)", re.I), "DISLIKES", "preference"),
        (re.compile(r"\b(?:my\s+project\s+is|working\s+on|building)\s+([^.,;!?]+)", re.I), "WORKS_ON", "project"),
        (re.compile(r"\b(?:i\s+use|i'm\s+using|stack\s+is)\s+([^.,;!?]+)", re.I), "USES", "technology"),
        (re.compile(r"\b(?:i\s+work\s+with|collaborating\s+with)\s+([^.,;!?]+)", re.I), "COLLABORATES_WITH", "person"),
        (re.compile(r"\b(?:i\s+usually|my\s+habit\s+is|always)\s+([^.,;!?]+)", re.I), "HAS_HABIT", "habit"),
    ]

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        self._lock = threading.Lock()
        init_db(self.db_path)
        self._init_tables()
        self._ensure_root_user_node()

    def _init_tables(self) -> None:
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    properties_json TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    access_count INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    last_observed REAL NOT NULL,
                    PRIMARY KEY (source_id, target_id, relation),
                    FOREIGN KEY (source_id) REFERENCES graph_nodes(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES graph_nodes(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_source ON graph_edges(source_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_relation ON graph_edges(relation);")

    def _ensure_root_user_node(self) -> None:
        now = time.time()
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO graph_nodes (id, name, category, properties_json, confidence, access_count, created_at, updated_at)
                VALUES ('user:root', 'User', 'identity', '{}', 1.0, 1, ?, ?)
                """,
                (now, now),
            )

    def upsert_node(self, node: GraphNode) -> None:
        """Inserts or updates a graph node."""
        with self._lock, get_db(self.db_path) as conn:
            now = time.time()
            conn.execute(
                """
                INSERT INTO graph_nodes (id, name, category, properties_json, confidence, access_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    category=excluded.category,
                    properties_json=excluded.properties_json,
                    confidence=MIN(2.0, graph_nodes.confidence + 0.1),
                    access_count=graph_nodes.access_count + 1,
                    updated_at=?
                """,
                (
                    node.id,
                    node.name,
                    node.category,
                    json.dumps(node.properties),
                    node.confidence,
                    node.access_count,
                    node.created_at,
                    now,
                    now,
                ),
            )

    def upsert_edge(self, edge: GraphEdge) -> None:
        """Inserts or reinforces a relational graph edge."""
        with self._lock, get_db(self.db_path) as conn:
            now = time.time()
            conn.execute(
                """
                INSERT INTO graph_edges (source_id, target_id, relation, weight, last_observed)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation) DO UPDATE SET
                    weight=MIN(5.0, graph_edges.weight + 0.5),
                    last_observed=?
                """,
                (edge.source_id, edge.target_id, edge.relation, edge.weight, now, now),
            )

    def extract_and_integrate(self, text: str) -> List[Tuple[str, str, str]]:
        """Parses conversational utterance into facts and adds them to user graph."""
        if not text or len(text.strip()) < 4:
            return []

        clean_text = text.strip()
        extracted: List[Tuple[str, str, str]] = []

        for pattern, relation, category in self.EXTRACTION_PATTERNS:
            match = pattern.search(clean_text)
            if match:
                raw_target = match.group(1).strip()
                # Clean up target
                target_name = re.sub(r"^(a|an|the)\s+", "", raw_target, flags=re.I).strip(" .,!?:;")
                if 2 <= len(target_name) <= 60:
                    node_id = f"{category}:{target_name.lower().replace(' ', '_')}"
                    node = GraphNode(id=node_id, name=target_name, category=category)
                    edge = GraphEdge(source_id="user:root", target_id=node_id, relation=relation)

                    self.upsert_node(node)
                    self.upsert_edge(edge)
                    extracted.append(("User", relation, target_name))

        return extracted

    def get_user_facts(self, min_weight: float = 0.5) -> List[Dict[str, Any]]:
        """Retrieves active user profile facts sorted by weight."""
        with self._lock, get_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT e.relation, n.name, n.category, e.weight
                FROM graph_edges e
                JOIN graph_nodes n ON e.target_id = n.id
                WHERE e.source_id = 'user:root' AND e.weight >= ?
                ORDER BY e.weight DESC, e.last_observed DESC
                LIMIT 30
                """,
                (min_weight,),
            )
            return [
                {"relation": row[0], "entity": row[1], "category": row[2], "weight": row[3]}
                for row in cursor.fetchall()
            ]

    def format_profile_for_prompt(self) -> str:
        """Produces a concise, structured profile block for LLM prompt context."""
        facts = self.get_user_facts()
        if not facts:
            return ""

        lines = ["[Lifelong User Knowledge Graph]"]
        for f in facts[:15]:
            lines.append(f"- User {f['relation']} {f['entity']} ({f['category']})")
        return "\n".join(lines)


# Singleton
_memory_graph: Optional[UserMemoryGraph] = None
_graph_lock = threading.Lock()


def get_memory_graph() -> UserMemoryGraph:
    global _memory_graph
    with _graph_lock:
        if _memory_graph is None:
            _memory_graph = UserMemoryGraph()
        return _memory_graph
