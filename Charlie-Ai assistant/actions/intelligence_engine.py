"""actions/intelligence_engine.py — CHARLIE Intelligence & Task Planning Engine Action.

Exposes task planning, durable checkpoints, semantic memory retrieval,
verification, and rollback controls directly to the assistant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from engine.error_recovery import ErrorRecoveryEngine
from engine.memory_manager import MemoryManager
from engine.permissions import PermissionManager
from engine.rollback import RollbackManager
from engine.task_planner import TaskPlanner
from engine.verification import VerificationEngine

_mem_mgr = MemoryManager()
_perm_mgr = PermissionManager()
_verify_eng = VerificationEngine()
_recovery_eng = ErrorRecoveryEngine(_mem_mgr)
_rollback_mgr = RollbackManager()
_planner = TaskPlanner(_mem_mgr)


def task_planner(parameters: dict, **_unused) -> str:
    """Multi-step goal decomposition and checkpointing tool."""
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()
    goal = str(params.get("goal") or "").strip()
    project = str(params.get("project") or "").strip() or None
    evidence = str(params.get("evidence") or "").strip()

    if action == "plan":
        if not goal:
            return "Please provide a goal to plan."
        plan = _planner.plan_goal(goal, project_name=project)
        steps_summary = "\n".join(f"{s.index + 1}. [{s.tool}] {s.name}" for s in plan.steps)
        return f"Plan created (ID: {plan.id}) for: {goal}\nSteps:\n{steps_summary}"

    if action == "advance":
        next_step = _planner.advance_step(evidence=evidence)
        if not next_step:
            return "Active plan completed successfully!"
        return f"Advanced to step {next_step.index + 1}: [{next_step.tool}] {next_step.name}"

    if action == "fail":
        err = str(params.get("error") or "Unknown error")
        _planner.fail_step(err)
        return f"Plan step marked as failed: {err}"

    if action == "resume":
        res = _planner.resume_task(project_name=project)
        if not res:
            return "No recent task found to resume."
        return (
            f"Resuming Task: {res['goal']}\n"
            f"Status: {res['status']}\n"
            f"Last Checkpoint: {res['last_checkpoint']}\n"
            f"Next Action: {res['next_action']}"
        )

    # status
    active = _planner.get_active_plan()
    if not active:
        return "No active task plan currently running."
    curr = active.steps[active.current_step] if active.current_step < len(active.steps) else None
    step_desc = f"Step {active.current_step + 1}/{len(active.steps)}: {curr.name if curr else 'Done'}"
    return f"Active Plan: {active.goal} | Status: {active.status} | {step_desc}"


def memory_engine(parameters: dict, **_unused) -> str:
    """Structured SQLite memory management tool."""
    params = parameters or {}
    action = str(params.get("action") or "recall").strip().lower()
    query = str(params.get("query") or "").strip()
    category = str(params.get("category") or "notes").strip()
    key = str(params.get("key") or "").strip()
    val = str(params.get("value") or "").strip()
    project = str(params.get("project") or "").strip()

    if action == "remember":
        if not val:
            return "Provide a value to remember."
        res = _mem_mgr.remember(category, f"{key}: {val}" if key else val)
        return f"Remembered in {category}: {res.get('content')}"

    if action == "set_project_fact":
        if not project or not key or not val:
            return "Provide project, key, and value."
        _mem_mgr.set_project_memory(project, category, key, val)
        return f"Saved project fact for {project}: {category}.{key} = {val}"

    if action == "project_status":
        if not project:
            return "Provide project name."
        ctx = _mem_mgr.get_project_context(project)
        if not ctx:
            return f"No records found for project '{project}'."
        facts = ctx.get("facts", {})
        fact_lines = [f"- {cat}.{k}: {v}" for cat, kvs in facts.items() for k, v in kvs.items()]
        last_t = ctx.get("last_task")
        t_str = f"Last task: {last_t.get('goal')} ({last_t.get('status')})" if last_t else "No task history."
        return f"Project: {project}\nFacts:\n" + ("\n".join(fact_lines) or "- None") + f"\n{t_str}"

    if action == "store_solution":
        sig = str(params.get("error_signature") or "").strip()
        fix = str(params.get("solution") or "").strip()
        if not sig or not fix:
            return "Provide error_signature and solution."
        _mem_mgr.store_error_solution(
            error_signature=sig,
            root_cause="Resolved during task",
            successful_fix=fix,
            project_name=project or None,
            verification="Verified by user/action",
        )
        return f"Saved error solution for: {sig}"

    # recall / search
    return _mem_mgr.recall(query or val, project_name=project or None)


def knowledge_graph_action(parameters: dict, **_unused) -> str:
    """Queries or updates the Personal Knowledge Graph (Phase 8)."""
    from engine.intelligence.core import IntelligenceCore
    core = IntelligenceCore()
    params = parameters or {}
    action = str(params.get("action") or "query").strip().lower()
    entity = str(params.get("entity") or "").strip()
    source = str(params.get("source") or "").strip()
    target = str(params.get("target") or "").strip()
    relation = str(params.get("relation") or "").strip()

    if action == "query":
        if not entity:
            return "Please provide an entity to query."
        res = core.query_entity_relations(entity)
        if not res.get("found"):
            return f"Entity '{entity}' not found in Knowledge Graph."
        neighbors = "\n".join(f"- {n['relation']} -> {n['target_name']} ({n['target_type']})" for n in res["neighbors"])
        return f"Entity: {res['canonical_name']} [{res['type']}]\nConnected to:\n" + (neighbors or "- No connections.")

    if action == "provenance":
        if not source or not target or not relation:
            return "Provide source, target, and relation to inspect provenance."
        prov = core.explain_knowledge(source, target, relation)
        return prov or f"No active provenance found for {source} -> {relation} -> {target}."

    if action == "correct":
        if not source or not target or not relation:
            return "Provide source, target, and relation to correct."
        ok = core.record_user_correction(source, target, relation, feedback=str(params.get("feedback") or ""))
        return f"Correction recorded. Relation deactivated and blocked: {ok}"

    if action == "health":
        h = core.get_health_report()
        return (
            f"CHARLIE Health: {h['status']}\n"
            f"Knowledge Graph: {h['knowledge_graph']['total_entities']} entities, {h['knowledge_graph']['active_relations']} active relations\n"
            f"Patterns Detected: {h['patterns_detected']}\n"
            f"Improvements Applied: {h['improvements_applied']}"
        )

    return "Unknown action. Supported: query, provenance, correct, health."


TOOL = {
    "name": "task_planner",
    "description": (
        "Decompose goals into structured steps, record verified checkpoints, "
        "advance tasks, or resume interrupted work ('continue', 'resume', 'where did we stop')."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["plan", "advance", "fail", "resume", "status"],
                "description": "Action to perform: plan a goal, advance completed step, fail, resume, or check status.",
            },
            "goal": {"type": "STRING", "description": "High level task goal to plan."},
            "project": {"type": "STRING", "description": "Associated project name if applicable."},
            "evidence": {"type": "STRING", "description": "Tangible evidence/output observed for the completed step."},
            "error": {"type": "STRING", "description": "Error reason if step failed."},
        },
    },
    "handler": task_planner,
}

