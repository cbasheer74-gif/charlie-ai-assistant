"""engine/intelligence/core.py — IntelligenceCore: Unifies Knowledge Graph, Reasoning, Patterns, Proactive, and Self-Improvement."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.intelligence.context_fusion import ContextFusionEngine
from engine.intelligence.entity_resolver import EntityResolver
from engine.intelligence.evaluation_engine import EvaluationEngine
from engine.intelligence.knowledge_graph import KnowledgeGraphManager, PersonalKnowledgeGraph
from engine.intelligence.memory_quality import MemoryQualityManager
from engine.intelligence.models import (
    Entity,
    EntityType,
    ImprovementProposal,
    ProactiveEvent,
    Relationship,
    RelationType,
)
from engine.intelligence.pattern_engine import PatternRecognitionEngine
from engine.intelligence.proactive_engine import (
    NextActionPredictor,
    NotificationBudget,
    ProactiveIntelligenceEngine,
)
from engine.intelligence.reasoning import (
    DependencyReasoner,
    GoalManager,
    ReasoningOrchestrator,
    RootCauseGraph,
)
from engine.intelligence.self_improvement import (
    ImprovementLedger,
    ReflectionEngine,
    SelfImprovementEngine,
    ToolReliabilityTracker,
)


class IntelligenceCore:
    """Central Intelligence coordinator for JARVIS Phase 8."""

    def __init__(self, db_path: Optional[Path] = None):
        self.graph = PersonalKnowledgeGraph(db_path=db_path)
        self.graph_manager = KnowledgeGraphManager(self.graph)
        self.entity_resolver = EntityResolver(self.graph)
        self.context_fusion = ContextFusionEngine(self.graph, self.entity_resolver)

        self.goal_manager = GoalManager()
        self.dependency_reasoner = DependencyReasoner(self.graph)
        self.root_cause_graph = RootCauseGraph(self.graph)
        self.reasoning = ReasoningOrchestrator(self.graph)

        self.pattern_engine = PatternRecognitionEngine()
        self.tool_tracker = ToolReliabilityTracker()
        self.ledger = ImprovementLedger()
        self.reflection_engine = ReflectionEngine()
        self.self_improvement = SelfImprovementEngine(ledger=self.ledger, tracker=self.tool_tracker)
        self.evaluation_engine = EvaluationEngine(ledger=self.ledger)

        self.notification_budget = NotificationBudget()
        self.proactive_engine = ProactiveIntelligenceEngine(budget=self.notification_budget)
        self.next_action_predictor = NextActionPredictor()
        self.memory_quality = MemoryQualityManager(self.graph)

    # ── High-Level Assistant Facade ───────────────────────────────────────────

    def query_entity_relations(self, entity_name: str) -> Dict[str, Any]:
        """Queries the knowledge graph neighborhood for an entity name."""
        ent = self.entity_resolver.resolve(entity_name)
        if not ent:
            return {"found": False, "query": entity_name}

        neighbors = self.graph.find_neighbors(ent.id, active_only=True)
        return {
            "found": True,
            "entity_id": ent.id,
            "canonical_name": ent.canonical_name,
            "type": ent.type.value,
            "neighbors": [
                {
                    "relation": rel.relation_type.value,
                    "target_name": neighbor.canonical_name,
                    "target_type": neighbor.type.value,
                    "provenance": rel.source_provenance,
                }
                for rel, neighbor in neighbors
            ],
        }

    def explain_knowledge(self, source_name: str, target_name: str, relation_type_str: str) -> Optional[str]:
        """Explains provenance of a graph fact (Section 89 & Test 114: 'ye kaise pata hai?')."""
        src = self.entity_resolver.resolve(source_name)
        tgt = self.entity_resolver.resolve(target_name)
        if not src or not tgt:
            return None

        try:
            rel_type = RelationType(relation_type_str)
        except ValueError:
            return None

        with self.graph._get_conn() as conn:
            row = conn.execute(
                """
                SELECT source_provenance, confidence, created_at
                FROM kg_relations
                WHERE source_id = ? AND target_id = ? AND relation_type = ? AND is_active = 1
                """,
                (src.id, tgt.id, rel_type.value),
            ).fetchone()
            if row:
                return f"Source: {row['source_provenance']} (confidence: {row['confidence']:.2f})"
        return None

    def record_user_correction(self, subject_name: str, target_name: str, relation_type_str: str, feedback: str = "") -> bool:
        """Records explicit user correction to supersede relation and prevent re-creation (Test 110)."""
        src = self.entity_resolver.resolve(subject_name)
        tgt = self.entity_resolver.resolve(target_name)
        if not src or not tgt:
            return False

        try:
            rel_type = RelationType(relation_type_str)
        except ValueError:
            return False

        self.graph.record_correction(src.id, tgt.id, rel_type, feedback=feedback)
        return True

    def get_health_report(self) -> Dict[str, Any]:
        """Provides complete subsystem health check (Section 96 & 97)."""
        mem_stats = self.memory_quality.get_memory_health_stats()
        patterns = self.pattern_engine.list_patterns()
        improvements = self.ledger.list_applied()

        return {
            "status": "WORKING",
            "knowledge_graph": mem_stats,
            "patterns_detected": len(patterns),
            "improvements_applied": len(improvements),
            "notification_budget_suppressed": self.notification_budget._suppressed_count,
        }
