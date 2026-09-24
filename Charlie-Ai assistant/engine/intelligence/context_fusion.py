"""engine/intelligence/context_fusion.py — Context Fusion Engine and Minimal Relevant Subgraph Scoping."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.intelligence.entity_resolver import EntityResolver
from engine.intelligence.knowledge_graph import PersonalKnowledgeGraph
from engine.intelligence.models import Entity, EntityType, RelationType


class ContextFusionEngine:
    """Fuses multi-modal context (conversation, project memory, knowledge graph) into compact, actionable subgraphs."""

    def __init__(self, graph: PersonalKnowledgeGraph, resolver: Optional[EntityResolver] = None):
        self.graph = graph
        self.resolver = resolver or EntityResolver(graph)

    def fuse_context_for_goal(
        self,
        goal_text: str,
        active_project: Optional[str] = None,
        recent_turns: Optional[List[str]] = None,
        include_tasks: bool = True,
    ) -> Dict[str, Any]:
        """Builds a scoped, relevant context bundle for a user request without dumping entire memory."""
        fused: Dict[str, Any] = {
            "goal": goal_text,
            "focal_entities": [],
            "subgraph_entities": [],
            "relevant_tasks": [],
            "relevant_documents": [],
            "relevant_people": [],
            "relevant_meetings": [],
            "dependencies": [],
            "provenance_notes": [],
        }

        # 1. Identify focal entities from goal text or active project
        focal_entity: Optional[Entity] = None
        if active_project:
            focal_entity = self.resolver.resolve(active_project, expected_type=EntityType.PROJECT)

        if not focal_entity:
            # Try resolving from goal text
            words = goal_text.split()
            for i in range(len(words)):
                candidate = " ".join(words[i : min(i + 3, len(words))])
                found = self.resolver.resolve(candidate)
                if found:
                    focal_entity = found
                    break

        if not focal_entity:
            return fused

        fused["focal_entities"].append({
            "id": focal_entity.id,
            "name": focal_entity.canonical_name,
            "type": focal_entity.type.value,
        })

        # 2. Extract 2-hop focused subgraph
        subgraph = self.graph.query_subgraph(focal_entity.id, depth=2)
        fused["subgraph_entities"] = [e.canonical_name for e in subgraph["entities"]]

        # 3. Categorize neighbors
        for rel in subgraph["relationships"]:
            source = self.graph.get_entity(rel.source_id)
            target = self.graph.get_entity(rel.target_id)
            if not source or not target:
                continue

            other = target if source.id == focal_entity.id else source

            if other.type == EntityType.TASK:
                fused["relevant_tasks"].append(other.canonical_name)
            elif other.type in (EntityType.DOCUMENT, EntityType.FILE):
                fused["relevant_documents"].append(other.canonical_name)
            elif other.type == EntityType.PERSON:
                fused["relevant_people"].append(other.canonical_name)
            elif other.type == EntityType.MEETING:
                fused["relevant_meetings"].append(other.canonical_name)

            if rel.relation_type == RelationType.DEPENDS_ON_TASK:
                fused["dependencies"].append(f"{source.canonical_name} -> {target.canonical_name}")

            if rel.source_provenance:
                fused["provenance_notes"].append(f"{source.canonical_name} {rel.relation_type.value} {target.canonical_name} [{rel.source_provenance}]")

        return fused
