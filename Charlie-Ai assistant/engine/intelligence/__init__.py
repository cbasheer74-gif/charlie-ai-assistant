"""engine/intelligence/__init__.py — Public Exports for JARVIS Phase 8 Intelligence Core."""

from engine.intelligence.core import IntelligenceCore
from engine.intelligence.context_fusion import ContextFusionEngine
from engine.intelligence.entity_resolver import EntityResolver
from engine.intelligence.evaluation_engine import EvaluationEngine
from engine.intelligence.knowledge_graph import KnowledgeGraphManager, PersonalKnowledgeGraph
from engine.intelligence.memory_quality import MemoryQualityManager
from engine.intelligence.models import (
    Entity,
    EntityType,
    Goal,
    ImprovementProposal,
    InterventionAction,
    Pattern,
    ProactiveEvent,
    ProposalStatus,
    ReflectionSummary,
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

__all__ = [
    "IntelligenceCore",
    "PersonalKnowledgeGraph",
    "KnowledgeGraphManager",
    "EntityResolver",
    "ContextFusionEngine",
    "GoalManager",
    "DependencyReasoner",
    "RootCauseGraph",
    "ReasoningOrchestrator",
    "PatternRecognitionEngine",
    "SelfImprovementEngine",
    "ImprovementLedger",
    "ToolReliabilityTracker",
    "ReflectionEngine",
    "EvaluationEngine",
    "NotificationBudget",
    "ProactiveIntelligenceEngine",
    "NextActionPredictor",
    "MemoryQualityManager",
    "Entity",
    "EntityType",
    "Relationship",
    "RelationType",
    "Goal",
    "Pattern",
    "ImprovementProposal",
    "ProposalStatus",
    "ProactiveEvent",
    "InterventionAction",
    "ReflectionSummary",
]
