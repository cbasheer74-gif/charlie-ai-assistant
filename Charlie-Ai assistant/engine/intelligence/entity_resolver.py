"""engine/intelligence/entity_resolver.py — Resolves Colloquial Aliases to Canonical Knowledge Graph Entities."""

from __future__ import annotations

import json
import re
import time
from typing import Dict, List, Optional, Tuple

from engine.intelligence.knowledge_graph import PersonalKnowledgeGraph
from engine.intelligence.models import Entity, EntityType


class EntityResolver:
    """Resolves spoken and written aliases, nicknames, and context-dependent referents."""

    COMMON_SYNONYMS: Dict[str, str] = {
        "payment app": "ZynPay",
        "mera payment wala project": "ZynPay",
        "payment project": "ZynPay",
        "zyn pay": "ZynPay",
        "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "code": "Visual Studio Code",
        "editor": "Visual Studio Code",
        "chrome": "Google Chrome",
        "browser": "Google Chrome",
        "antigravity": "Antigravity IDE",
    }

    def __init__(self, graph: PersonalKnowledgeGraph):
        self.graph = graph

    def resolve(
        self,
        query: str,
        active_project: Optional[str] = None,
        expected_type: Optional[EntityType] = None,
    ) -> Optional[Entity]:
        """Resolves a user-provided string to a canonical Entity."""
        clean = query.strip().lower()
        if not clean:
            return None

        # 1. Direct Canonical Name Match
        direct = self.graph.find_entity_by_name(clean)
        if direct and (not expected_type or direct.type == expected_type):
            return direct

        # 2. Known Common Synonyms Table
        if clean in self.COMMON_SYNONYMS:
            canonical_name = self.COMMON_SYNONYMS[clean]
            ent = self.graph.find_entity_by_name(canonical_name)
            if ent and (not expected_type or ent.type == expected_type):
                return ent

        # 3. Active Project Heuristic
        if clean in ("project", "mera project", "wahi project", "current project") and active_project:
            proj_ent = self.graph.find_entity_by_name(active_project)
            if proj_ent:
                return proj_ent

        # 4. Partial / Substring Match across all entities
        all_entities = self.graph.list_entities(expected_type)
        for ent in all_entities:
            # Check canonical name substring
            if clean in ent.canonical_name.lower() or ent.canonical_name.lower() in clean:
                return ent
            # Check aliases
            for alias in ent.aliases:
                if clean in alias.lower() or alias.lower() in clean:
                    return ent

        return None

    def merge_entities(self, primary_id: str, duplicate_id: str, reason: str = "") -> bool:
        """Merges duplicate entity into primary entity, updating relationships and aliases."""
        primary = self.graph.get_entity(primary_id)
        duplicate = self.graph.get_entity(duplicate_id)
        if not primary or not duplicate:
            return False

        # Add duplicate's canonical name and aliases to primary
        new_aliases = list(set(primary.aliases + [duplicate.canonical_name] + duplicate.aliases))
        primary.aliases = new_aliases

        with self.graph._get_conn() as conn:
            # Update primary aliases
            conn.execute(
                "UPDATE kg_entities SET aliases_json = ? WHERE id = ?",
                (json.dumps(new_aliases), primary.id),
            )
            # Re-point relationships
            conn.execute("UPDATE kg_relations SET source_id = ? WHERE source_id = ?", (primary.id, duplicate.id))
            conn.execute("UPDATE kg_relations SET target_id = ? WHERE target_id = ?", (primary.id, duplicate.id))
            # Record merge history
            conn.execute(
                "INSERT INTO kg_merges (id, target_id, merged_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                (f"m_{primary.id}_{duplicate.id}", primary.id, duplicate.id, reason, time.time()),
            )
            # Delete duplicate entity
            conn.execute("DELETE FROM kg_entities WHERE id = ?", (duplicate.id,))
            conn.commit()

        return True
