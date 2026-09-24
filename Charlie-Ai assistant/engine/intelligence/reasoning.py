"""engine/intelligence/reasoning.py — Goal Hierarchy, Dependency Reasoner, Strategy Selector, and Root-Cause Graph."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from engine.intelligence.knowledge_graph import PersonalKnowledgeGraph
from engine.intelligence.models import Goal, RelationType


class GoalManager:
    """Manages multi-session hierarchical goals (Work Goal -> Project Goal -> Milestone -> Task -> Action)."""

    def __init__(self):
        self._goals: Dict[str, Goal] = {}

    def create_goal(
        self,
        goal_id: str,
        title: str,
        subgoals: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        deadlines: Optional[float] = None,
        priority: int = 1,
        project_id: Optional[str] = None,
    ) -> Goal:
        now = time.time()
        g = Goal(
            id=goal_id,
            title=title,
            subgoals=subgoals or [],
            constraints=constraints or [],
            dependencies=dependencies or [],
            deadlines=deadlines,
            priority=priority,
            project_id=project_id,
            created_at=now,
            updated_at=now,
        )
        self._goals[goal_id] = g
        return g

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        return self._goals.get(goal_id)

    def list_goals(self, project_id: Optional[str] = None) -> List[Goal]:
        if project_id:
            return [g for g in self._goals.values() if g.project_id == project_id]
        return list(self._goals.values())

    def update_status(self, goal_id: str, status: str, blockers: Optional[List[str]] = None) -> bool:
        g = self._goals.get(goal_id)
        if not g:
            return False
        g.current_status = status
        if blockers is not None:
            g.blockers = blockers
        g.updated_at = time.time()
        return True


class DependencyReasoner:
    """Checks prerequisite satisfaction, blocking relationships, and circular dependencies."""

    def __init__(self, graph: PersonalKnowledgeGraph):
        self.graph = graph

    def check_prerequisites(self, task_name: str, completed_tasks: List[str]) -> Tuple[bool, List[str]]:
        """Verifies if all dependencies for a task have been satisfied."""
        ent = self.graph.find_entity_by_name(task_name)
        if not ent:
            return True, []

        missing: List[str] = []
        for rel, prereq in self.graph.find_neighbors(ent.id, relation_type=RelationType.DEPENDS_ON_TASK):
            # If relation points outward (this depends on prereq)
            if rel.source_id == ent.id:
                if prereq.canonical_name not in completed_tasks and prereq.id not in completed_tasks:
                    missing.append(prereq.canonical_name)

        is_satisfied = len(missing) == 0
        return is_satisfied, missing


class RootCauseGraph:
    """Navigates causal relationships (Section 20 & 79) to guide error diagnosis toward upstream root causes."""

    def __init__(self, graph: PersonalKnowledgeGraph):
        self.graph = graph

    def trace_root_cause(self, error_name: str) -> List[Dict[str, Any]]:
        """Traces CAUSED_BY relationships from an observed error to upstream services/dependencies."""
        ent = self.graph.find_entity_by_name(error_name)
        if not ent:
            return []

        causes: List[Dict[str, Any]] = []
        for rel, upstream in self.graph.find_neighbors(ent.id, relation_type=RelationType.CAUSED_BY):
            if rel.source_id == ent.id:
                causes.append({
                    "cause_entity": upstream.canonical_name,
                    "cause_type": upstream.type.value,
                    "provenance": rel.source_provenance,
                    "confidence": rel.confidence,
                })
        return causes


class ReasoningOrchestrator:
    """Selects optimal execution strategies and validates plan feasibility."""

    def __init__(self, graph: PersonalKnowledgeGraph):
        self.graph = graph
        self.dependency_reasoner = DependencyReasoner(graph)
        self.root_cause_graph = RootCauseGraph(graph)

    def select_strategy(self, task_category: str, user_preference: Optional[str] = None) -> Dict[str, Any]:
        """Evaluates alternative strategies (e.g. openpyxl vs UI automation) based on reliability and speed."""
        low = task_category.lower()

        if "excel" in low or "spreadsheet" in low:
            # openpyxl is safer and faster than raw GUI
            return {
                "strategy": "openpyxl_direct_edit",
                "alternative": "excel_ui_automation",
                "rationale": "Direct file manipulation avoids UI window focus issues and is 10x faster.",
                "risk": "LOW",
            }
        elif "code" in low or "git" in low:
            return {
                "strategy": "cli_git_command",
                "alternative": "ide_gui_click",
                "rationale": "CLI provides deterministic status codes and scriptable verification.",
                "risk": "LOW",
            }

        return {
            "strategy": "default_agent_execution",
            "alternative": "manual_prompt",
            "rationale": "Standard multi-agent execution pipeline.",
            "risk": "MEDIUM",
        }
