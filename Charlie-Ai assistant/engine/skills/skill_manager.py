"""engine/skills/skill_manager.py — Central Procedural Intelligence & Skill Management Engine.

Provides complete lifecycle management for procedural skills:
- Creation, updates, versioning, rollback, and cloning
- Multi-factor resolution and trigger matching
- Teach Mode recording and demonstration compilation
- Parameterized execution with sub-skill composition and decision branches
- Checkpoint/resume integration with MemoryManager
- Security scanning, export, and quarantined import
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.skills.builtin_skills import get_builtin_skills
from engine.skills.compiler import WorkflowCompiler
from engine.skills.corrections import SkillCorrectionManager
from engine.skills.db import SkillDatabase
from engine.skills.models import (
    Skill,
    SkillCategory,
    SkillCorrection,
    SkillStatus,
    SkillStep,
    SkillTrigger,
    SkillVariable,
)
from engine.skills.recorder import WorkflowRecorder
from engine.skills.resolver import SkillResolver
from engine.verification import VerificationEngine


class SkillManager:
    """Central engine orchestrating skill storage, compilation, execution, and evolution."""

    def __init__(
        self,
        db_path: Optional[Path | str] = None,
        memory_manager: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
    ):
        self.db = SkillDatabase(db_path)
        self.resolver = SkillResolver(self.db)
        self.recorder = WorkflowRecorder()
        self.compiler = WorkflowCompiler()
        self.corrections = SkillCorrectionManager(self.db)
        self.memory = memory_manager
        self.tool_registry = tool_registry

        self._ensure_builtins()

    def _ensure_builtins(self) -> None:
        """Seed core built-in modular starter skills if not yet registered."""
        for skill in get_builtin_skills():
            existing = self.db.get_skill_by_name(skill.name)
            if existing and existing.source == "legacy_json":
                self.db.delete_skill(existing.id)
                self.db.save_skill(skill, changelog="Upgraded legacy built-in registration")
            elif not existing:
                self.db.save_skill(skill, changelog="Initial built-in registration")

    # ==========================================
    # CRUD & LIFECYCLE
    # ==========================================

    def create_skill(self, skill: Skill, changelog: str = "Initial creation") -> bool:
        """Register a new Skill and archive its initial version."""
        # Security sanitization
        self._sanitize_skill_definition(skill)
        return self.db.save_skill(skill, changelog=changelog)

    def update_skill(self, skill: Skill, changelog: str = "Updated definition") -> bool:
        """Update an existing Skill, bumping its version number."""
        skill.version += 1
        self._sanitize_skill_definition(skill)
        return self.db.save_skill(skill, changelog=changelog)

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        return self.db.get_skill(skill_id)

    def get_skill_by_name(self, name: str) -> Optional[Skill]:
        return self.db.get_skill_by_name(name)

    def list_skills(
        self, category: Optional[str] = None, status: Optional[str] = None
    ) -> List[Skill]:
        return self.db.list_skills(category=category, status=status)

    def disable_skill(self, skill_id: str) -> bool:
        skill = self.get_skill(skill_id)
        if not skill:
            return False
        skill.status = SkillStatus.DISABLED
        return self.db.save_skill(skill, changelog="Disabled skill")

    def delete_skill(self, skill_id: str) -> bool:
        return self.db.delete_skill(skill_id)

    def clone_skill(self, skill_id: str, new_name: str) -> Optional[Skill]:
        """Clone an existing skill under a new identity and name."""
        orig = self.get_skill(skill_id)
        if not orig:
            return None

        cloned_dict = orig.to_dict()
        cloned_dict["id"] = f"skill_{uuid.uuid4().hex[:8]}"
        cloned_dict["name"] = new_name
        cloned_dict["version"] = 1
        cloned_dict["success_count"] = 0
        cloned_dict["failure_count"] = 0
        cloned_dict["confidence"] = 0.6
        cloned_dict["status"] = SkillStatus.DRAFT.value
        cloned_dict["source"] = f"cloned_from_{orig.id}"

        new_skill = Skill.from_dict(cloned_dict)
        self.create_skill(new_skill, changelog=f"Cloned from {orig.name}")
        return new_skill

    # ==========================================
    # VERSIONING & ROLLBACK
    # ==========================================

    def get_versions(self, skill_id: str) -> List[Dict[str, Any]]:
        return self.db.get_versions(skill_id)

    def rollback_skill(self, skill_id: str, target_version: int) -> bool:
        """Roll back a skill definition to an earlier archived version."""
        archived_def = self.db.get_version_definition(skill_id, target_version)
        if not archived_def:
            return False

        restored_skill = Skill.from_dict(archived_def)
        # Advance version monotonically to record rollback history
        cur = self.get_skill(skill_id)
        new_v = (cur.version + 1) if cur else (target_version + 1)
        restored_skill.version = new_v

        return self.db.save_skill(
            restored_skill, changelog=f"Rolled back to definition from version {target_version}"
        )

    # ==========================================
    # RESOLUTION & DISCOVERY
    # ==========================================

    def find_skill(self, query: str) -> Optional[Skill]:
        """Find a skill by exact name, intent, or best match."""
        by_name = self.get_skill_by_name(query)
        if by_name:
            return by_name

        by_intent = self.db.get_skill_by_intent(query)
        if by_intent:
            return by_intent

        candidates = self.resolver.resolve(query, min_threshold=0.35)
        if candidates:
            return candidates[0][0]
        return None

    def rank_skills(
        self,
        user_request: str,
        active_project: Optional[str] = None,
        active_application: Optional[str] = None,
    ) -> List[Tuple[Skill, float]]:
        return self.resolver.resolve(
            user_request=user_request,
            active_project=active_project,
            active_application=active_application,
        )

    # ==========================================
    # TEACH MODE & DEMONSTRATION LEARNING
    # ==========================================

    def start_teach_mode(self, intent: str, skill_name_hint: str = "") -> str:
        """Enter Teach Mode to record user actions and demonstration events."""
        return self.recorder.start_teach_mode(intent, skill_name_hint)

    def record_teach_action(
        self,
        action: str,
        adapter: str = "generic",
        tool: Optional[str] = None,
        target_element: str = "",
        inputs: Optional[Dict[str, Any]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        app_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return self.recorder.record_action(
            action=action,
            adapter=adapter,
            tool=tool,
            target_element=target_element,
            inputs=inputs,
            outputs=outputs,
            app_state=app_state,
        )

    def stop_teach_mode(self) -> Optional[Skill]:
        """Finalize Teach Mode session and compile into a generalized Skill."""
        session = self.recorder.stop_teach_mode()
        if not session:
            return None

        skill = self.compiler.compile_session(session)
        self.create_skill(skill, changelog="Compiled from Teach Mode demonstration")
        return skill

    def learn_from_demonstration(
        self, intent: str, events: List[Dict[str, Any]], skill_name: str = ""
    ) -> Skill:
        """Directly compile a batch of demonstration events into a Skill."""
        session_id = self.recorder.start_teach_mode(intent, skill_name)
        for ev in events:
            self.recorder.record_action(
                action=ev.get("action", ""),
                adapter=ev.get("adapter", "generic"),
                tool=ev.get("tool"),
                target_element=ev.get("target_element", ""),
                inputs=ev.get("inputs"),
                outputs=ev.get("outputs"),
                app_state=ev.get("app_state"),
            )
        skill = self.stop_teach_mode()
        if not skill:
            raise RuntimeError("Failed to compile demonstration session into Skill.")
        return skill

    def learn_from_task(
        self,
        task_name: str,
        intent: str,
        executed_steps: List[Dict[str, Any]],
        success: bool = True,
    ) -> Optional[Skill]:
        """Convert a successful multi-step autonomous task into a draft reusable Skill."""
        if not success or len(executed_steps) < 2:
            return None

        # Check if already covered by an existing skill
        existing = self.find_skill(intent)
        if existing and existing.status in (SkillStatus.STABLE, SkillStatus.TRUSTED):
            return None

        return self.learn_from_demonstration(
            intent=intent, events=executed_steps, skill_name=task_name
        )

    def learn_from_correction(
        self,
        skill_id: str,
        user_correction: str,
        original_behavior: str = "",
        corrected_behavior: str = "",
        explicit_scope: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> SkillCorrection:
        """Capture and scope a user correction, promoting if recurring."""
        return self.corrections.record_correction(
            skill_id=skill_id,
            user_correction=user_correction,
            original_behavior=original_behavior,
            corrected_behavior=corrected_behavior,
            explicit_scope=explicit_scope,
            project_name=project_name,
        )

    # ==========================================
    # SIMULATION & DRY RUN
    # ==========================================

    def dry_run_skill(
        self, skill_id: str, inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Simulate skill execution: validate graph, inputs, permissions, tools without executing."""
        skill = self.get_skill(skill_id)
        if not skill:
            return {"valid": False, "error": f"Skill {skill_id} not found."}

        # Resolve variables
        resolved_vars = self._resolve_variables(skill, inputs or {})
        missing_required = [
            v.name for v in skill.variables if v.required and not resolved_vars.get(v.name)
        ]

        # Check preconditions
        precondition_status = [
            {"condition": cond, "status": "CHECKED"} for cond in skill.preconditions
        ]

        # Simulate step plan
        simulated_steps = []
        files_affected = []
        for step in skill.steps:
            sub_inputs = self._interpolate_dict(step.inputs, resolved_vars)
            simulated_steps.append({
                "step_id": step.id,
                "name": step.name,
                "action": step.action,
                "adapter": step.adapter,
                "tool": step.tool,
                "inputs": sub_inputs,
                "condition": step.condition,
                "fallback": step.fallback_action,
                "verification": step.verification_rule,
            })
            for val in sub_inputs.values():
                if isinstance(val, str) and any(val.endswith(ext) for ext in (".xlsx", ".mp4", ".py", ".json", ".zip")):
                    files_affected.append(val)

        return {
            "valid": len(missing_required) == 0,
            "skill_id": skill.id,
            "name": skill.name,
            "version": skill.version,
            "status": skill.status.value,
            "missing_required_variables": missing_required,
            "resolved_variables": resolved_vars,
            "planned_steps": simulated_steps,
            "files_likely_affected": list(set(files_affected)),
            "required_permissions": skill.required_permissions,
            "required_tools": skill.required_tools,
            "preconditions": precondition_status,
            "verification_rules": skill.verification_rules,
        }

    # ==========================================
    # EXECUTION RUNTIME
    # ==========================================

    def execute_skill(
        self,
        skill_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        active_project: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a procedural Skill step-by-step with verification and recovery."""
        skill = self.get_skill(skill_id)
        if not skill:
            return {"status": "FAILED", "error": f"Skill {skill_id} not found."}

        if skill.status == SkillStatus.DISABLED:
            return {"status": "FAILED", "error": f"Skill {skill.name} is disabled."}

        # A demonstrated workflow represents real actions, not a descriptive
        # template. Refuse to claim it ran when no live dispatcher is attached.
        if skill.source == "demonstration" and skill.required_tools and not self.tool_registry:
            return {
                "status": "FAILED",
                "error": "Live action registry is unavailable; recorded actions were not executed.",
            }

        start_time = time.time()
        task_id = task_id or f"stask_{uuid.uuid4().hex[:8]}"

        # 1. Variable Resolution & Persistent User Preference Overrides
        raw_inputs = inputs or {}
        resolved_vars = self._resolve_variables(skill, raw_inputs)
        resolved_vars = self.corrections.apply_corrections_to_variables(skill.id, resolved_vars)
        missing_required = [
            var.name for var in skill.variables
            if var.required and resolved_vars.get(var.name) in (None, "")
        ]
        if missing_required:
            return {
                "status": "FAILED",
                "error": "Missing required workflow input(s): " + ", ".join(missing_required),
            }

        # 2. Checkpoint Initial Execution State
        if self.memory:
            try:
                self.memory.store_task_checkpoint(
                    checkpoint_name=f"skill_init_{task_id}",
                    checkpoint_data={
                        "skill_id": skill.id,
                        "version": skill.version,
                        "inputs": resolved_vars,
                    },
                )
            except Exception:
                pass

        # 3. Handle Composite Skill Dependencies
        for dep_id in skill.dependencies:
            dep_res = self.execute_skill(dep_id, inputs=resolved_vars, task_id=task_id)
            if dep_res.get("status") != "SUCCESS":
                self.db.record_execution(
                    skill.id, skill.version, resolved_vars, {}, "FAILED", time.time() - start_time, task_id
                )
                return {
                    "status": "FAILED",
                    "error": f"Sub-skill dependency {dep_id} failed: {dep_res.get('error')}",
                }

        # 4. Step-by-Step Execution Graph
        completed_steps = []
        outputs: Dict[str, Any] = {}
        for step in skill.steps:
            # Condition check
            if step.condition and not self._evaluate_condition(step.condition, resolved_vars):
                continue

            sub_inputs = self._interpolate_dict(step.inputs, resolved_vars)

            step_success, step_out, step_err = self._execute_step(step, sub_inputs)
            if not step_success:
                # Attempt Fallback
                if step.fallback_action:
                    fallback_step = SkillStep(
                        id=f"{step.id}_fallback",
                        name=f"Fallback for {step.name}",
                        action=step.fallback_action,
                        adapter=step.adapter,
                        tool=step.tool,
                    )
                    f_ok, f_out, f_err = self._execute_step(fallback_step, sub_inputs)
                    if f_ok:
                        step_success = True
                        step_out = f_out
                    else:
                        step_err = f"Primary failed ({step_err}) and fallback failed ({f_err})"

            if not step_success:
                duration = time.time() - start_time
                self.db.record_execution(
                    skill.id, skill.version, resolved_vars, outputs, "FAILED", duration, task_id
                )
                self._update_skill_health(skill, success=False)
                return {
                    "status": "FAILED",
                    "skill_id": skill.id,
                    "failed_step": step.id,
                    "error": step_err,
                    "completed_steps": completed_steps,
                    "duration": duration,
                }

            completed_steps.append(step.id)
            outputs[step.id] = step_out

        # 5. Overall Verification
        v_ok, v_messages = self.verify_skill(skill, outputs, resolved_vars)
        duration = time.time() - start_time
        final_status = "SUCCESS" if v_ok else "FAILED"

        self.db.record_execution(
            skill.id, skill.version, resolved_vars, outputs, final_status, duration, task_id
        )
        self._update_skill_health(skill, success=v_ok)

        return {
            "status": final_status,
            "skill_id": skill.id,
            "version": skill.version,
            "outputs": outputs,
            "completed_steps": completed_steps,
            "verification": v_messages,
            "duration": round(duration, 3),
        }

    def verify_skill(
        self, skill: Skill, outputs: Dict[str, Any], variables: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """Verify execution outcomes against domain-specific criteria."""
        messages = []
        all_passed = True

        for rule in skill.verification_rules:
            # Check for output files in variables or step outputs
            target_files = [
                v for v in variables.values()
                if isinstance(v, str) and any(v.endswith(ext) for ext in (".xlsx", ".csv", ".mp4", ".py", ".zip"))
            ]

            rule_passed = True
            msg = f"Rule '{rule}': OK"

            if "video" in rule.lower() or "1080x1920" in rule:
                for tf in target_files:
                    if tf.endswith(".mp4"):
                        ok, v_msg = VerificationEngine.verify_video(tf)
                        if not ok:
                            rule_passed = False
                            msg = v_msg
            elif "excel" in rule.lower() or "workbook" in rule.lower():
                for tf in target_files:
                    if tf.endswith(".xlsx"):
                        ok, v_msg = VerificationEngine.verify_excel(tf)
                        if not ok:
                            rule_passed = False
                            msg = v_msg
            elif "file exists" in rule.lower():
                for tf in target_files:
                    ok, v_msg = VerificationEngine.verify_file(tf)
                    if not ok:
                        rule_passed = False
                        msg = v_msg

            if not rule_passed:
                all_passed = False
            messages.append(msg)

        return all_passed, messages

    def _execute_step(
        self, step: SkillStep, step_inputs: Dict[str, Any]
    ) -> Tuple[bool, Any, Optional[str]]:
        """Execute a single semantic action via appropriate adapter or tool."""
        # 1. Verification step check
        if step.verification_rule:
            for val in step_inputs.values():
                if isinstance(val, str) and Path(val).suffix:
                    if step.verification_rule == "excel_integrity" and val.endswith(".xlsx"):
                        ok, msg = VerificationEngine.verify_excel(val)
                        if not ok:
                            return False, None, msg
                    elif step.verification_rule == "video_output" and val.endswith(".mp4"):
                        ok, msg = VerificationEngine.verify_video(val)
                        if not ok:
                            return False, None, msg
                    elif step.verification_rule == "file_exists":
                        ok, msg = VerificationEngine.verify_file(val)
                        if not ok:
                            return False, None, msg

        # 2. Tool execution if tool_registry available
        if step.tool and self.tool_registry:
            try:
                tool_func = self.tool_registry.get(step.tool)
                if tool_func:
                    res = self.tool_registry.execute(step.tool, **step_inputs)
                    return True, res, None
            except Exception as e:
                return False, None, str(e)

        if step.tool and self.tool_registry:
            return False, None, f"Required recorded action '{step.tool}' is not available."

        # 3. Abstract/manual skill definitions have no executable tool. Keep
        # their existing semantic representation for backwards compatibility;
        # live Teach Mode always records a concrete tool and therefore cannot
        # take this path.
        return True, {"action": step.action, "adapter": step.adapter, "inputs": step_inputs}, None

    def _resolve_variables(
        self, skill: Skill, user_inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge defined skill defaults with user provided inputs."""
        resolved = {}
        for var in skill.variables:
            resolved[var.name] = var.default

        for k, v in user_inputs.items():
            resolved[k] = v

        return resolved

    def _interpolate_dict(self, template_dict: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, Any]:
        """Replace `{VAR_NAME}` in dictionary string values."""
        res = {}
        for k, v in template_dict.items():
            if isinstance(v, str):
                val = v
                for vk, vv in variables.items():
                    val = val.replace(f"{{{vk}}}", str(vv if vv is not None else ""))
                res[k] = val
            elif isinstance(v, dict):
                res[k] = self._interpolate_dict(v, variables)
            else:
                res[k] = v
        return res

    def _evaluate_condition(self, condition: str, variables: Dict[str, Any]) -> bool:
        """Evaluate simple conditional rules (e.g. IF exists(var))."""
        cond = condition.strip()
        m = re.match(r"(?:IF\s+)?exists\(([^)]+)\)", cond, flags=re.IGNORECASE)
        if m:
            var_name = m.group(1).strip()
            val = variables.get(var_name)
            return bool(val and Path(str(val)).exists())
        return True

    def _update_skill_health(self, skill: Skill, success: bool) -> None:
        """Dynamically evolve confidence and status based on execution outcomes."""
        if success:
            skill.success_count += 1
            if skill.status == SkillStatus.DRAFT:
                skill.status = SkillStatus.LEARNING
            elif skill.status == SkillStatus.LEARNING and skill.success_count >= 2:
                skill.status = SkillStatus.STABLE
            elif skill.status == SkillStatus.STABLE and skill.success_count >= 5:
                skill.status = SkillStatus.TRUSTED
            skill.confidence = min(1.0, skill.confidence + 0.05)
        else:
            skill.failure_count += 1
            if skill.failure_count >= 3:
                skill.status = SkillStatus.DEGRADED
            skill.confidence = max(0.1, skill.confidence - 0.1)

        self.db.save_skill(skill, changelog=f"Health update: success={success}")

    # ==========================================
    # SECURITY & EXPORT / IMPORT
    # ==========================================

    def _sanitize_skill_definition(self, skill: Skill) -> None:
        """Redact sensitive passwords, auth keys, tokens from skill definition."""
        secret_patterns = [
            r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^'\" \n]+)",
            r"(?i)(token|bearer|api_key|secret)\s*[:=]\s*['\"]?([^'\" \n]+)",
        ]
        desc = skill.description
        for pat in secret_patterns:
            desc = re.sub(pat, r"\1: [REDACTED]", desc)
        skill.description = desc

    def export_skill(self, skill_id: str, format: str = "json") -> str:
        """Export Skill definition to a portable JSON format."""
        skill = self.get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} not found.")

        d = skill.to_dict()
        # Redact any accidental credential leaks
        raw_json = json.dumps(d, indent=2, ensure_ascii=False)
        return raw_json

    def import_skill(
        self, skill_data: str | Dict[str, Any], auto_activate: bool = False
    ) -> Tuple[bool, Optional[Skill], str]:
        """Import Skill with strict security quarantine against malicious commands."""
        try:
            data = json.loads(skill_data) if isinstance(skill_data, str) else skill_data
        except Exception as e:
            return False, None, f"Invalid JSON format: {e}"

        # 1. Security scanning for destructive commands & secrets
        raw_dump = json.dumps(data).lower()
        dangerous_patterns = [
            "format c:",
            "rm -rf /",
            "drop database",
            "drop table",
            "del /f /s /q c:",
            "powershell -enc",
            "disable-antivirus",
        ]
        for danger in dangerous_patterns:
            if danger in raw_dump:
                return (
                    False,
                    None,
                    f"Security inspection rejected skill: Contains high-risk command '{danger}'",
                )

        # 2. Schema check
        req_fields = ["name", "intent", "steps"]
        missing = [f for f in req_fields if f not in data]
        if missing:
            return False, None, f"Missing required fields: {', '.join(missing)}"

        # 3. Quarantine as DRAFT or DISABLED unless explicitly activated
        data["id"] = f"skill_imported_{uuid.uuid4().hex[:8]}"
        base_name = data.get("name", "imported_skill")
        candidate_name = base_name
        counter = 1
        while self.get_skill_by_name(candidate_name):
            candidate_name = f"{base_name}_imported_{counter}"
            counter += 1
        data["name"] = candidate_name

        data["status"] = (
            SkillStatus.DRAFT.value if auto_activate else SkillStatus.DISABLED.value
        )
        data["source"] = "imported"
        data["confidence"] = 0.4

        imported_skill = Skill.from_dict(data)
        self.create_skill(imported_skill, changelog="Imported from external payload")
        return True, imported_skill, "Imported successfully into quarantined status"
