"""
JARVIS Phase 11: Modular Prompt Compiler & Response Validator
Builds domain-scoped prompts without monolithic bloat, and validates structured outputs before execution.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.ai.compiler")


class PromptCompiler:
    """Assembles minimum required prompt modules based on the task domain."""

    MODULES = {
        "SECURITY_CORE": "Security Rules: Never execute unverified destructive actions without confirmation.",
        "CODING_RULES": "Coding Rules: Write clean, type-safe Python code. Always verify syntax and test cases.",
        "RESEARCH_RULES": "Research Rules: Rely strictly on verified source evidence. Date-check every claim.",
        "COMPUTER_RULES": "Computer Rules: Verify UI element bounding boxes before clicking.",
        "MEMORY_RULES": "Memory Rules: Preserve critical facts, IDs, and user constraints accurately.",
    }

    def compile(
        self,
        task_type: str,
        user_prompt: str,
        additional_context: Optional[str] = None,
    ) -> str:
        """Assembles prompt with only relevant domain modules."""
        modules_to_load = ["SECURITY_CORE"]

        if "CODING" in task_type:
            modules_to_load.append("CODING_RULES")
        elif "RESEARCH" in task_type:
            modules_to_load.append("RESEARCH_RULES")
        elif "COMPUTER" in task_type:
            modules_to_load.append("COMPUTER_RULES")
        elif "MEMORY" in task_type:
            modules_to_load.append("MEMORY_RULES")

        system_block = "\n".join(f"[{m}] {self.MODULES[m]}" for m in modules_to_load)

        parts = [f"=== SYSTEM INSTRUCTIONS ===\n{system_block}"]
        if additional_context:
            parts.append(f"=== CONTEXT ===\n{additional_context.strip()}")
        parts.append(f"=== USER REQUEST ===\n{user_prompt.strip()}")

        return "\n\n".join(parts)


class ResponseValidator:
    """Validates model responses, ensuring valid JSON schema and safe tool parameters."""

    @staticmethod
    def validate_json_output(response_text: str, required_fields: Optional[List[str]] = None) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Validates if text is valid JSON and contains required schema fields."""
        clean = response_text.strip()
        # Strip markdown ```json blocks if present
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-zA-Z]*\n", "", clean)
            clean = re.sub(r"\n```$", "", clean)

        try:
            data = json.loads(clean)
            if not isinstance(data, dict):
                return False, None, "Parsed JSON is not an object dictionary."

            if required_fields:
                missing = [f for f in required_fields if f not in data]
                if missing:
                    return False, None, f"Missing required JSON fields: {missing}"

            return True, data, "Valid JSON schema."
        except json.JSONDecodeError as e:
            return False, None, f"JSON parse error: {str(e)}"

    @staticmethod
    def validate_tool_arguments(tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates tool parameters against basic safety rules."""
        if not isinstance(args, dict):
            return False, "Tool arguments must be a dictionary."

        # Reject dangerous keys
        for k, v in args.items():
            if isinstance(v, str) and any(cmd in v.lower() for cmd in ["format c:", "rmdir /s /q", "del /f /s /q c:"]):
                return False, f"Dangerous command string detected in argument '{k}'."

        return True, "Tool arguments validated."
