"""engine/intelligence/knowledge_graph.py — SQLite-backed Personal Knowledge Graph Engine."""

from __future__ import annotations

import contextlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.intelligence.models import (
    Entity,
    EntityType,
    FactCertainty,
    Relationship,
    RelationType,
)


class PersonalKnowledgeGraph:
    """Relational Graph implementation storing entities, relationships, temporal state, and provenance."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_dir = Path.home() / ".jarvis"
            db_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = db_dir / "knowledge_graph.db"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    @contextlib.contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kg_entities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_verified_at REAL NOT NULL,
                    expiry REAL
                );

                CREATE TABLE IF NOT EXISTS kg_relations (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    source_provenance TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at REAL NOT NULL,
                    valid_from REAL NOT NULL,
                    valid_to REAL,
                    is_active INTEGER NOT NULL,
                    is_superseded INTEGER NOT NULL,
                    superseded_by TEXT,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES kg_entities(id),
                    FOREIGN KEY(target_id) REFERENCES kg_entities(id)
                );

                CREATE TABLE IF NOT EXISTS kg_merges (
                    id TEXT PRIMARY KEY,
                    target_id TEXT NOT NULL,
                    merged_id TEXT NOT NULL,
                    reason TEXT,
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kg_corrections (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    feedback TEXT,
                    timestamp REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_entities_name ON kg_entities(canonical_name);
                CREATE INDEX IF NOT EXISTS idx_entities_type ON kg_entities(type);
                CREATE INDEX IF NOT EXISTS idx_relations_source ON kg_relations(source_id);
                CREATE INDEX IF NOT EXISTS idx_relations_target ON kg_relations(target_id);
                CREATE INDEX IF NOT EXISTS idx_relations_active ON kg_relations(is_active);
                """
            )
            conn.commit()

    # ── Entity CRUD ───────────────────────────────────────────────────────────

    def create_entity(
        self,
        entity_id: str,
        entity_type: EntityType,
        canonical_name: str,
        aliases: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        source: str = "user_interaction",
    ) -> Entity:
        now = time.time()
        aliases_list = aliases or []
        meta_dict = metadata or {}

        entity = Entity(
            id=entity_id,
            type=entity_type,
            canonical_name=canonical_name,
            aliases=aliases_list,
            metadata=meta_dict,
            confidence=confidence,
            source=source,
            created_at=now,
            updated_at=now,
            last_verified_at=now,
        )

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO kg_entities
                (id, type, canonical_name, aliases_json, metadata_json, confidence, source, created_at, updated_at, last_verified_at, expiry)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity.id,
                    entity.type.value,
                    entity.canonical_name,
                    json.dumps(entity.aliases),
                    json.dumps(entity.metadata),
                    entity.confidence,
                    entity.source,
                    entity.created_at,
                    entity.updated_at,
                    entity.last_verified_at,
                    entity.expiry,
                ),
            )
            conn.commit()
        return entity

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM kg_entities WHERE id = ?", (entity_id,)).fetchone()
            if not row:
                return None
            return self._row_to_entity(row)

    def find_entity_by_name(self, name: str) -> Optional[Entity]:
        low = name.lower().strip()
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM kg_entities").fetchall()
            for r in rows:
                if r["canonical_name"].lower() == low:
                    return self._row_to_entity(r)
                aliases = json.loads(r["aliases_json"])
                if any(a.lower() == low for a in aliases):
                    return self._row_to_entity(r)
        return None

    def list_entities(self, entity_type: Optional[EntityType] = None) -> List[Entity]:
        with self._get_conn() as conn:
            if entity_type:
                rows = conn.execute("SELECT * FROM kg_entities WHERE type = ?", (entity_type.value,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM kg_entities").fetchall()
            return [self._row_to_entity(r) for r in rows]

    # ── Relationship Operations ───────────────────────────────────────────────

    def create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        source_provenance: str = "verified_configuration",
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Relationship]:
        # Check if user previously corrected/prohibited this relation
        if self.is_correction_recorded(source_id, target_id, relation_type):
            return None

        rel_id = f"rel_{source_id}_{relation_type.value}_{target_id}_{int(time.time()*1000)}"
        now = time.time()
        meta = metadata or {}

        rel = Relationship(
            id=rel_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            source_provenance=source_provenance,
            confidence=confidence,
            created_at=now,
            valid_from=now,
            valid_to=None,
            is_active=True,
            is_superseded=False,
            metadata=meta,
        )

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO kg_relations
                (id, source_id, target_id, relation_type, source_provenance, confidence, created_at, valid_from, valid_to, is_active, is_superseded, superseded_by, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rel.id,
                    rel.source_id,
                    rel.target_id,
                    rel.relation_type.value,
                    rel.source_provenance,
                    rel.confidence,
                    rel.created_at,
                    rel.valid_from,
                    rel.valid_to,
                    1 if rel.is_active else 0,
                    1 if rel.is_superseded else 0,
                    rel.superseded_by,
                    json.dumps(rel.metadata),
                ),
            )
            conn.commit()
        return rel

    def supersede_relation(
        self,
        old_relation_id: str,
        new_relation: Relationship,
    ) -> bool:
        """Marks old relation superseded while retaining history (Section 9 Temporal Knowledge)."""
        now = time.time()
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE kg_relations
                SET is_active = 0, is_superseded = 1, valid_to = ?, superseded_by = ?
                WHERE id = ?
                """,
                (now, new_relation.id, old_relation_id),
            )
            conn.execute(
                """
                INSERT INTO kg_relations
                (id, source_id, target_id, relation_type, source_provenance, confidence, created_at, valid_from, valid_to, is_active, is_superseded, superseded_by, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_relation.id,
                    new_relation.source_id,
                    new_relation.target_id,
                    new_relation.relation_type.value,
                    new_relation.source_provenance,
                    new_relation.confidence,
                    new_relation.created_at,
                    new_relation.valid_from,
                    new_relation.valid_to,
                    1 if new_relation.is_active else 0,
                    1 if new_relation.is_superseded else 0,
                    new_relation.superseded_by,
                    json.dumps(new_relation.metadata),
                ),
            )
            conn.commit()
        return True

    def remove_relation(self, relation_id: str) -> bool:
        with self._get_conn() as conn:
            conn.execute("UPDATE kg_relations SET is_active = 0 WHERE id = ?", (relation_id,))
            conn.commit()
        return True

    # ── Graph Traversal & Queries ─────────────────────────────────────────────

    def find_neighbors(
        self,
        entity_id: str,
        relation_type: Optional[RelationType] = None,
        active_only: bool = True,
    ) -> List[Tuple[Relationship, Entity]]:
        """Finds all adjacent entities and their connecting relationships."""
        results: List[Tuple[Relationship, Entity]] = []
        with self._get_conn() as conn:
            query = """
                SELECT r.*, e.*
                FROM kg_relations r
                JOIN kg_entities e ON (r.target_id = e.id AND r.source_id = ?)
                                   OR (r.source_id = e.id AND r.target_id = ?)
                WHERE (r.source_id = ? OR r.target_id = ?)
            """
            params: List[Any] = [entity_id, entity_id, entity_id, entity_id]

            if active_only:
                query += " AND r.is_active = 1"
            if relation_type:
                query += " AND r.relation_type = ?"
                params.append(relation_type.value)

            rows = conn.execute(query, params).fetchall()
            for row in rows:
                rel = self._row_to_relationship(row)
                # target or source entity
                ent_id = row["target_id"] if row["source_id"] == entity_id else row["source_id"]
                ent = self.get_entity(ent_id)
                if ent:
                    results.append((rel, ent))
        return results

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 3,
    ) -> Optional[List[Relationship]]:
        """BFS shortest path between two entities."""
        if source_id == target_id:
            return []

        visited: Set[str] = {source_id}
        queue: List[Tuple[str, List[Relationship]]] = [(source_id, [])]

        while queue:
            current_id, path = queue.pop(0)
            if len(path) >= max_depth:
                continue

            for rel, neighbor in self.find_neighbors(current_id, active_only=True):
                if neighbor.id == target_id:
                    return path + [rel]
                if neighbor.id not in visited:
                    visited.add(neighbor.id)
                    queue.append((neighbor.id, path + [rel]))

        return None

    def query_subgraph(
        self,
        center_id: str,
        depth: int = 2,
    ) -> Dict[str, Any]:
        """Extracts minimal, context-rich subgraph around a focal entity."""
        entities: Dict[str, Entity] = {}
        relationships: List[Relationship] = []

        center = self.get_entity(center_id)
        if not center:
            return {"entities": [], "relationships": []}

        entities[center.id] = center
        frontier: Set[str] = {center.id}

        for _ in range(depth):
            next_frontier: Set[str] = set()
            for current_id in frontier:
                for rel, neighbor in self.find_neighbors(current_id, active_only=True):
                    relationships.append(rel)
                    if neighbor.id not in entities:
                        entities[neighbor.id] = neighbor
                        next_frontier.add(neighbor.id)
            frontier = next_frontier

        # Deduplicate relationships by ID
        unique_rels = {r.id: r for r in relationships}.values()
        return {
            "center": center,
            "entities": list(entities.values()),
            "relationships": list(unique_rels),
        }

    # ── User Corrections & Provenance ─────────────────────────────────────────

    def record_correction(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        feedback: str = "",
    ) -> None:
        """Records explicit user correction to supersede relation and prevent re-creation."""
        corr_id = f"corr_{source_id}_{target_id}_{relation_type.value}"
        now = time.time()
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO kg_corrections
                (id, source_id, target_id, relation_type, feedback, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (corr_id, source_id, target_id, relation_type.value, feedback, now),
            )
            # Deactivate any existing active relations between them
            conn.execute(
                """
                UPDATE kg_relations
                SET is_active = 0, is_superseded = 1, valid_to = ?
                WHERE source_id = ? AND target_id = ? AND relation_type = ?
                """,
                (now, source_id, target_id, relation_type.value),
            )
            conn.commit()

    def is_correction_recorded(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
    ) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT id FROM kg_corrections
                WHERE source_id = ? AND target_id = ? AND relation_type = ?
                """,
                (source_id, target_id, relation_type.value),
            ).fetchone()
            return row is not None

    def get_provenance(self, relation_id: str) -> Optional[str]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT source_provenance FROM kg_relations WHERE id = ?", (relation_id,)).fetchone()
            if row:
                return str(row["source_provenance"])
        return None

    # ── Consistency Check ─────────────────────────────────────────────────────

    def check_consistency(self) -> Dict[str, Any]:
        """Detects orphan entities and superseded-active relationship conflicts."""
        with self._get_conn() as conn:
            all_entities = set(r["id"] for r in conn.execute("SELECT id FROM kg_entities").fetchall())
            rel_entities = set()
            for r in conn.execute("SELECT source_id, target_id FROM kg_relations WHERE is_active = 1").fetchall():
                rel_entities.add(r["source_id"])
                rel_entities.add(r["target_id"])

            orphans = list(all_entities - rel_entities)
            conflicts = conn.execute(
                """
                SELECT source_id, target_id, relation_type, COUNT(*) as cnt
                FROM kg_relations
                WHERE is_active = 1
                GROUP BY source_id, target_id, relation_type
                HAVING cnt > 1
                """
            ).fetchall()

            return {
                "orphan_count": len(orphans),
                "orphans": orphans,
                "conflict_count": len(conflicts),
                "conflicts": [dict(c) for c in conflicts],
                "status": "HEALTHY" if not conflicts else "ATTENTION_NEEDED",
            }

    # ── Row Converters ────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> Entity:
        return Entity(
            id=row["id"],
            type=EntityType(row["type"]),
            canonical_name=row["canonical_name"],
            aliases=json.loads(row["aliases_json"]),
            metadata=json.loads(row["metadata_json"]),
            confidence=float(row["confidence"]),
            source=row["source"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            last_verified_at=float(row["last_verified_at"]),
            expiry=float(row["expiry"]) if row["expiry"] else None,
        )

    @staticmethod
    def _row_to_relationship(row: sqlite3.Row) -> Relationship:
        return Relationship(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=RelationType(row["relation_type"]),
            source_provenance=row["source_provenance"],
            confidence=float(row["confidence"]),
            created_at=float(row["created_at"]),
            valid_from=float(row["valid_from"]),
            valid_to=float(row["valid_to"]) if row["valid_to"] else None,
            is_active=bool(row["is_active"]),
            is_superseded=bool(row["is_superseded"]),
            superseded_by=row["superseded_by"],
            metadata=json.loads(row["metadata_json"]),
        )


class KnowledgeGraphManager:
    """High-level facade over PersonalKnowledgeGraph with project context and query abstractions."""

    def __init__(self, graph: Optional[PersonalKnowledgeGraph] = None):
        self.graph = graph or PersonalKnowledgeGraph()

    def query_project_context(self, project_name: str) -> Dict[str, Any]:
        proj_entity = self.graph.find_entity_by_name(project_name)
        if not proj_entity:
            return {"found": False, "project": project_name}

        subgraph = self.graph.query_subgraph(proj_entity.id, depth=2)
        return {
            "found": True,
            "project_id": proj_entity.id,
            "canonical_name": proj_entity.canonical_name,
            "subgraph": subgraph,
        }
