"""engine/skills/compiler.py — Workflow Compiler & Parameter Generalization Engine.

Transforms raw demonstrations or task executions into generalized, parameter-driven
Skill objects, inferring variables and abstracting hardcoded constants.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.skills.models import (
    Skill,
    SkillCategory,
    SkillStatus,
    SkillStep,
    SkillTrigger,
    SkillVariable,
)
from engine.skills.recorder import RecordedEvent, RecordedSession


class WorkflowCompiler:
    """Compiles recorded sessions or task executions into reusable procedural skills."""

    MONTH_NAMES = (
        "september", "november", "december", "february", "january",
        "october", "august", "april", "march", "july", "june", "may",
        "sept", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    )

    def compile_session(self, session: RecordedSession) -> Skill:
        """Compile a recorded Teach Mode session into a generalized Skill."""
        skill_id = f"skill_{uuid.uuid4().hex[:8]}"
        clean_name = re.sub(r"[^a-zA-Z0-9_]+", "_", session.skill_name_hint).strip("_")

        # 1. Parameter & Variable Inference
        variables, generalized_events = self._parameterize_events(session.events)

        # 2. Categorization
        category = self._infer_category(session.intent, session.events)

        # 3. Construct Steps
        steps: List[SkillStep] = []
        for idx, ev in enumerate(generalized_events):
            step_id = f"step_{idx + 1}"
            step = SkillStep(
                id=step_id,
                name=ev.target_element or ev.action.replace("_", " ").title(),
                description=f"Perform {ev.action} using {ev.adapter}",
                action=ev.action,
                adapter=ev.adapter,
                tool=ev.tool,
                inputs=ev.inputs,
                outputs=ev.outputs,
                dependencies=[f"step_{idx}"] if idx > 0 else [],
                verification_rule=self._infer_step_verification(ev.action, category),
            )
            steps.append(step)

        # 4. Generate Natural Triggers
        triggers = [
            SkillTrigger(phrase=session.intent.lower()),
            SkillTrigger(phrase=session.skill_name_hint.replace("_", " ").lower()),
        ]

        # 5. Required Tools & Agents
        req_tools = list({ev.tool for ev in generalized_events if ev.tool})
        req_agents = [self._infer_agent(category)]

        # 6. Overall Verification Rules
        v_rules = self._generate_verification_rules(category)

        return Skill(
            id=skill_id,
            name=clean_name,
            description=f"Learned procedural workflow for: {session.intent}",
            intent=session.intent,
            category=category,
            status=SkillStatus.DRAFT,
            version=1,
            triggers=triggers,
            variables=variables,
            steps=steps,
            required_agents=req_agents,
            required_tools=req_tools,
            required_permissions=self._infer_permissions(category),
            preconditions=self._infer_preconditions(category),
            verification_rules=v_rules,
            confidence=0.6,
            source="demonstration",
        )

    def _parameterize_events(
        self, events: List[RecordedEvent]
    ) -> Tuple[List[SkillVariable], List[RecordedEvent]]:
        """Identify changing values (file paths, dates, filenames) and extract variables."""
        variables: Dict[str, SkillVariable] = {}
        generalized: List[RecordedEvent] = []

        for ev in events:
            new_inputs = dict(ev.inputs)
            for k, v in ev.inputs.items():
                if isinstance(v, str):
                    # Teach Mode never persists credentials. It records a named
                    # placeholder which becomes a required runtime variable.
                    secret_placeholder = re.fullmatch(r"\{([A-Z][A-Z0-9_]*)\}", v)
                    if secret_placeholder:
                        var_name = secret_placeholder.group(1)
                        if var_name not in variables:
                            variables[var_name] = SkillVariable(
                                name=var_name,
                                type="string",
                                default=None,
                                description=f"Sensitive runtime value for {k}",
                                required=True,
                            )
                        new_inputs[k] = v
                        continue

                    # Check for Month names in strings
                    low_v = v.lower()
                    matched_month = None
                    for m in self.MONTH_NAMES:
                        pattern = r"(?<![a-zA-Z])" + re.escape(m) + r"(?![a-zA-Z])"
                        if re.search(pattern, low_v):
                            matched_month = m
                            var_name = "REPORT_MONTH"
                            if var_name not in variables:
                                variables[var_name] = SkillVariable(
                                    name=var_name,
                                    type="string",
                                    default=m.capitalize(),
                                    description="Target reporting month",
                                    required=False,
                                )
                            break

                    # Check for file path
                    is_file = any(v.lower().endswith(ext) for ext in (".xlsx", ".csv", ".mp4", ".py", ".json"))
                    if is_file:
                        var_name = f"INPUT_{k.upper()}"
                        default_val = v
                        if matched_month:
                            pattern = r"(?<![a-zA-Z])" + re.escape(matched_month) + r"(?![a-zA-Z])"
                            default_val = re.sub(pattern, "{REPORT_MONTH}", v, flags=re.IGNORECASE)
                        if var_name not in variables:
                            variables[var_name] = SkillVariable(
                                name=var_name,
                                type="file_path",
                                default=default_val,
                                description=f"File path for {k}",
                                required=True,
                            )
                        new_inputs[k] = f"{{{var_name}}}"
                    elif matched_month:
                        pattern = r"(?<![a-zA-Z])" + re.escape(matched_month) + r"(?![a-zA-Z])"
                        new_inputs[k] = re.sub(pattern, "{REPORT_MONTH}", v, flags=re.IGNORECASE)

            ev_copy = RecordedEvent(
                timestamp=ev.timestamp,
                action=ev.action,
                adapter=ev.adapter,
                tool=ev.tool,
                target_element=ev.target_element,
                inputs=new_inputs,
                outputs=ev.outputs,
                app_state=ev.app_state,
            )
            generalized.append(ev_copy)

        return list(variables.values()), generalized

    def _infer_category(self, intent: str, events: List[RecordedEvent]) -> SkillCategory:
        low = intent.lower()
        if any(w in low for w in ("excel", "sheet", "xlsx", "spreadsheet", "report", "csv")):
            return SkillCategory.SPREADSHEET
        if any(w in low for w in ("youtube", "short", "reel")):
            return SkillCategory.YOUTUBE
        if any(w in low for w in ("video", "clip", "transcode", "render")):
            return SkillCategory.VIDEO
        if any(w in low for w in ("code", "git", "test", "build", "bug", "refactor")):
            return SkillCategory.CODING
        if any(w in low for w in ("antigravity", "ide")):
            return SkillCategory.ANTIGRAVITY
        if any(w in low for w in ("browser", "web", "scrape")):
            return SkillCategory.BROWSER
        if any(w in low for w in ("file", "folder", "copy", "move")):
            return SkillCategory.FILES
        return SkillCategory.AUTOMATION

    def _infer_agent(self, category: SkillCategory) -> str:
        mapping = {
            SkillCategory.SPREADSHEET: "SpreadsheetAgent",
            SkillCategory.VIDEO: "VideoAgent",
            SkillCategory.YOUTUBE: "VideoAgent",
            SkillCategory.CODING: "CodingAgent",
            SkillCategory.ANTIGRAVITY: "AntigravityAgent",
            SkillCategory.BROWSER: "BrowserAgent",
            SkillCategory.FILES: "FileAgent",
            SkillCategory.RESEARCH: "ResearchAgent",
        }
        return mapping.get(category, "GeneralAgent")

    def _infer_permissions(self, category: SkillCategory) -> List[str]:
        if category in (SkillCategory.SPREADSHEET, SkillCategory.FILES, SkillCategory.CODING):
            return ["FILE_READ", "FILE_WRITE"]
        if category in (SkillCategory.VIDEO, SkillCategory.YOUTUBE):
            return ["FILE_READ", "FILE_WRITE", "MEDIA_PROCESS"]
        if category == SkillCategory.BROWSER:
            return ["BROWSER_CONTROL", "NETWORK_ACCESS"]
        return ["SAFE_WRITE"]

    def _infer_preconditions(self, category: SkillCategory) -> List[str]:
        if category == SkillCategory.SPREADSHEET:
            return ["Input workbook exists and is readable", "openpyxl library installed"]
        if category in (SkillCategory.VIDEO, SkillCategory.YOUTUBE):
            return ["FFmpeg installed on PATH", "Output directory writable"]
        if category == SkillCategory.CODING:
            return ["Git repository initialized", "Working directory clean"]
        return ["Prerequisites verified"]

    def _infer_step_verification(self, action: str, category: SkillCategory) -> Optional[str]:
        low = action.lower()
        if "save" in low or "export" in low:
            if category == SkillCategory.SPREADSHEET:
                return "excel_integrity"
            if category in (SkillCategory.VIDEO, SkillCategory.YOUTUBE):
                return "video_output"
            return "file_exists"
        if "compile" in low or "syntax" in low:
            return "python_syntax"
        return None

    def _generate_verification_rules(self, category: SkillCategory) -> List[str]:
        if category == SkillCategory.SPREADSHEET:
            return ["Workbook loads cleanly without corruption", "Summary calculations non-empty", "Formulas intact"]
        if category in (SkillCategory.VIDEO, SkillCategory.YOUTUBE):
            return ["Output video file exists", "Resolution matches 1080x1920 (9:16)", "Audio stream present"]
        if category == SkillCategory.CODING:
            return ["Zero syntax errors", "Modified tests pass"]
        return ["Target artifact exists and passes domain checks"]
