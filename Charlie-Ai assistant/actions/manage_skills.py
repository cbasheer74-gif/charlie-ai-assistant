"""Persistent, user-taught workflows and procedural skills for CHARLIE.

Backbone integration with engine.skills.SkillManager while preserving
backward compatibility with the legacy JSON store and action interface.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from engine.skills.models import SkillCategory, SkillStatus
from engine.skills.skill_manager import SkillManager
from engine.skills import teach_runtime

_LOCK = threading.Lock()
_MAX_NAME = 80
_MAX_WORKFLOW = 10_000

_SKILL_MANAGER = None


def _get_manager() -> SkillManager:
    global _SKILL_MANAGER
    if _SKILL_MANAGER is None:
        _SKILL_MANAGER = SkillManager()
        # The live dispatcher and the compiler must share the same recorder.
        _SKILL_MANAGER.recorder = teach_runtime.get_recorder()
    return _SKILL_MANAGER


class _ActionRegistryAdapter:
    """Expose the live action registry in the shape SkillManager expects."""

    def __init__(self, registry, context: dict):
        self.registry = registry
        self.context = context

    def get(self, name: str):
        return name if self.registry and self.registry.has(name) else None

    def execute(self, name: str, **inputs):
        if not self.registry or not self.registry.has(name):
            raise KeyError(f"Recorded action '{name}' is not available.")
        return self.registry.run(name, inputs, self.context)


from core.app_paths import get_memory_dir

_LEGACY_STORE = get_memory_dir() / "skills.json"
_STORE = _LEGACY_STORE  # kept patchable for existing tests


def _store() -> Path:
    if _STORE != _LEGACY_STORE:
        return _STORE
    try:
        from memory.profile_manager import profile_dir
        return profile_dir() / "skills.json"
    except Exception:
        return _LEGACY_STORE


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _key(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")[:_MAX_NAME]


def _sync_legacy_store(mgr: SkillManager) -> None:
    """Sync modern skills to legacy memory/skills.json for backward compatibility."""
    try:
        skills = mgr.list_skills()
        out = {}
        for s in skills:
            k = _key(s.name)
            out[k] = {
                "name": s.name[:_MAX_NAME],
                "workflow": f"Intent: {s.intent}\nSteps: " + "; ".join(step.name for step in s.steps),
                "updated": s.updated_at,
                "uses": s.success_count,
            }
        store = _store()
        store.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix="charlie-skills-", suffix=".json", dir=store.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(out, stream, ensure_ascii=False, indent=2)
        os.replace(temp, store)
    except Exception:
        pass


def manage_skills(parameters: dict | None = None, player=None, action_registry=None, **_unused) -> str:
    params = parameters or {}
    action = str(params.get("action", "")).strip().lower()
    name = str(params.get("name", "")).strip()

    mgr = _get_manager()

    with _LOCK:
        if action == "start_teach":
            intent = str(params.get("workflow") or params.get("intent") or name).strip()
            if not name or not intent:
                return "Teach Mode needs a workflow name and a short description of its purpose."
            if teach_runtime.is_recording():
                state = teach_runtime.status()
                return f"Teach Mode is already recording '{state.get('name', 'a workflow')}'."
            if any(_key(skill.name) == _key(name) for skill in mgr.list_skills()):
                return f"A skill named '{name}' already exists. Choose a new name or delete the old skill first."
            session_id = mgr.start_teach_mode(intent, name)
            if player:
                player.write_log(f"TEACH MODE: Recording â€” {name[:90]}")
            return (
                f"TEACH MODE STARTED ({session_id}) for '{name}'. Perform the workflow now using "
                "Charlie actions. When finished, ask me to stop teaching and save it."
            )

        if action == "teach_status":
            state = teach_runtime.status()
            if not state.get("recording"):
                return "Teach Mode is not recording."
            return (
                f"Teach Mode is recording '{state.get('name')}'. "
                f"Captured {state.get('event_count', 0)} successful action(s)."
            )

        if action == "cancel_teach":
            if not teach_runtime.cancel():
                return "Teach Mode is not recording."
            if player:
                player.write_log("TEACH MODE: Cancelled")
            return "Teach Mode cancelled. No skill was saved."

        if action == "stop_teach":
            state = teach_runtime.status()
            if not state.get("recording"):
                return "Teach Mode is not recording."
            if state.get("event_count", 0) == 0:
                return "No successful Charlie actions were captured yet. Perform the workflow or cancel Teach Mode."
            skill = mgr.stop_teach_mode()
            if not skill:
                return "Teach Mode could not compile the recorded workflow."
            _sync_legacy_store(mgr)
            if player:
                player.write_log(f"TEACH MODE: Saved â€” {skill.name[:90]}")
            return (
                f"TEACH MODE SAVED: '{skill.name}' with {len(skill.steps)} real action step(s). "
                "It remains DRAFT until successful replays increase its confidence."
            )

        if action in ("learn", "teach"):
            workflow = str(params.get("workflow", "")).strip()
            if not name or not workflow:
                return "A skill needs both a short name and its workflow or intent."

            # Use compiler to turn demonstration/instructions into structured skill
            steps_data = []
            for line in workflow.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    steps_data.append({"action": line, "target_element": line})

            skill = mgr.learn_from_demonstration(
                intent=workflow if len(workflow) < 120 else name,
                events=steps_data if steps_data else [{"action": workflow}],
                skill_name=name,
            )
            _sync_legacy_store(mgr)

            if player:
                player.write_log(f"SKILL: Learned — {skill.name[:90]} (v{skill.version})")
            return f"Saved skill '{skill.name}' (v{skill.version}, Status: {skill.status.value}). Reusable procedure compiled."

        if action == "list":
            skills = mgr.list_skills()
            if not skills:
                return "No saved skills yet. Teach one by saying what workflow to remember."
            lines = ["Saved skills:"]
            for s in skills:
                lines.append(
                    f"- {s.name} (v{s.version}, {s.status.value}, used {s.success_count} times, confidence {s.confidence:.2f})"
                )
            return "\n".join(lines)

        if action == "get":
            skill = mgr.find_skill(name)
            if not skill:
                return f"No saved skill named '{name}'."

            step_desc = "\n".join(f"  {idx+1}. {st.name} ({st.action})" for idx, st in enumerate(skill.steps))
            var_desc = ", ".join(f"{v.name}={v.default}" for v in skill.variables) or "None"
            return (
                f"SKILL: {skill.name} (v{skill.version}, Status: {skill.status.value})\n"
                f"Intent: {skill.intent}\n"
                f"Variables: {var_desc}\n"
                f"Workflow Steps:\n{step_desc}"
            )

        if action in ("forget", "delete"):
            skill = mgr.find_skill(name)
            if not skill:
                return f"No saved skill named '{name}'."
            mgr.delete_skill(skill.id)
            _sync_legacy_store(mgr)
            if player:
                player.write_log(f"SKILL: Forgotten — {skill.name[:90]}")
            return f"Forgot skill '{skill.name}'."

        if action == "execute":
            skill = mgr.find_skill(name)
            if not skill:
                return f"No saved skill named '{name}'."
            if not action_registry:
                return "Live action registry is unavailable; refusing to simulate this workflow."
            mgr.tool_registry = _ActionRegistryAdapter(
                action_registry,
                {"player": player, "action_registry": action_registry},
            )
            inputs = params.get("inputs", {})
            res = mgr.execute_skill(skill.id, inputs=inputs)
            if res.get("status") != "SUCCESS":
                return (
                    f"Execution of '{skill.name}' FAILED at "
                    f"{res.get('failed_step', 'an unknown step')}: {res.get('error', 'unknown error')}"
                )
            return (
                f"Execution of '{skill.name}': SUCCESS; "
                f"{len(res.get('completed_steps', []))} step(s) completed "
                f"in {res.get('duration')}s."
            )

        if action == "dry_run":
            skill = mgr.find_skill(name)
            if not skill:
                return f"No saved skill named '{name}'."
            sim = mgr.dry_run_skill(skill.id, inputs=params.get("inputs", {}))
            return json.dumps(sim, indent=2)

        if action == "rollback":
            skill = mgr.find_skill(name)
            target_v = int(params.get("version", 1))
            if not skill:
                return f"No saved skill named '{name}'."
            ok = mgr.rollback_skill(skill.id, target_version=target_v)
            return f"Rollback to v{target_v}: {'SUCCESS' if ok else 'FAILED'}."

    return (
        "action must be start_teach, teach_status, stop_teach, cancel_teach, learn, "
        "list, get, forget, execute, dry_run, or rollback."
    )


TOOL = {
    "name": "manage_skills",
    "description": (
        "Teach Charlie a reusable workflow by recording real tool actions. Use start_teach with a name "
        "and purpose, perform the requested actions, then use stop_teach. Also lists, previews, dry-runs, "
        "executes, rolls back, and deletes learned workflows."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "start_teach | teach_status | stop_teach | cancel_teach | learn | list | get | forget | execute | dry_run | rollback",
            },
            "name": {"type": "STRING", "description": "Short workflow name."},
            "workflow": {
                "type": "STRING",
                "description": "Purpose/intent for start_teach, or plain-language workflow for learn.",
            },
            "intent": {
                "type": "STRING",
                "description": "Optional short purpose of the workflow being recorded.",
            },
            "inputs": {
                "type": "OBJECT",
                "description": "Optional inputs/variables for execution or dry_run.",
            },
            "version": {
                "type": "INTEGER",
                "description": "Target version for rollback action.",
            },
        },
        "required": ["action"],
    },
    "handler": manage_skills,
}
