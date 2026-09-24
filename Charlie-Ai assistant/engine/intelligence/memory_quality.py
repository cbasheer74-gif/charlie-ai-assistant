"""engine/intelligence/memory_quality.py — Memory Quality Management, Conflict Resolution, and Health Metrics."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from engine.intelligence.knowledge_graph import PersonalKnowledgeGraph
from engine.intelligence.models import RelationType


class MemoryQualityManager:
    """Manages memory hygiene, supersedes conflicting facts (e.g. port 3008 -> 3010), and tracks health (Section 35–39)."""

    SOURCE_TRUST_HIERARCHY: Dict[str, float] = {
        "verified_configuration": 1.0,
        "tool_observation": 0.9,
        "explicit_user_statement": 0.85,
        "project_file": 0.8,
        "official_docs": 0.75,
        "inference": 0.4,
    }

    def __init__(self, graph: PersonalKnowledgeGraph):
        self.graph = graph

    def resolve_conflicting_relation(
        self,
        source_id: str,
        target_id_new: str,
        relation_type: RelationType,
        new_provenance: str = "verified_configuration",
    ) -> bool:
        """Resolves conflicting relationship facts by marking older ones superseded (Section 38 & Test 102)."""
        now = time.time()
        with self.graph._get_conn() as conn:
            # Find active relations with same source and relation type
            rows = conn.execute(
                """
                SELECT id FROM kg_relations
                WHERE source_id = ? AND relation_type = ? AND is_active = 1
                """,
                (source_id, relation_type.value),
            ).fetchall()

            new_rel_id = f"rel_{source_id}_{relation_type.value}_{target_id_new}_{int(now*1000)}"

            for r in rows:
                conn.execute(
                    """
                    UPDATE kg_relations
                    SET is_active = 0, is_superseded = 1, valid_to = ?, superseded_by = ?
                    WHERE id = ?
                    """,
                    (now, new_rel_id, r["id"]),
                )

            # Insert new active relation
            confidence = self.SOURCE_TRUST_HIERARCHY.get(new_provenance, 0.8)
            conn.execute(
                """
                INSERT INTO kg_relations
                (id, source_id, target_id, relation_type, source_provenance, confidence, created_at, valid_from, valid_to, is_active, is_superseded, superseded_by, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_rel_id,
                    source_id,
                    target_id_new,
                    relation_type.value,
                    new_provenance,
                    confidence,
                    now,
                    now,
                    None,
                    1,
                    0,
                    None,
                    "{}",
                ),
            )
            conn.commit()
        return True

    def get_memory_health_stats(self) -> Dict[str, Any]:
        """Calculates active, superseded, orphan, and conflict statistics."""
        with self.graph._get_conn() as conn:
            total_entities = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
            total_active_relations = conn.execute("SELECT COUNT(*) FROM kg_relations WHERE is_active = 1").fetchone()[0]
            total_superseded = conn.execute("SELECT COUNT(*) FROM kg_relations WHERE is_superseded = 1").fetchone()[0]

            consistency = self.graph.check_consistency()

            return {
                "total_entities": total_entities,
                "active_relations": total_active_relations,
                "superseded_relations": total_superseded,
                "orphan_entities": consistency["orphan_count"],
                "conflicts": consistency["conflict_count"],
                "health_status": consistency["status"],
            }
