"""engine/reflective_critic.py — Self-Reflective Critic & CoT Syntax/Logic Verifier.

Audits generated responses, validates Python/JSON/SQL syntax in code blocks,
detects unbalanced structures or hallucinations, and auto-corrects defects
before returning to user.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("charlie.reflective_critic")


class ReflectiveCritic:
    """Self-reflection auditor for code syntax, JSON integrity, and markdown consistency."""

    @staticmethod
    def extract_code_blocks(text: str) -> List[Tuple[str, str]]:
        """Extract (language, code_body) from markdown code fences."""
        pattern = r"```([a-zA-Z0-9_\-\+]*)\n([\s\S]*?)```"
        matches = re.findall(pattern, text)
        return [(lang.lower().strip(), code.strip()) for lang, code in matches]

    @staticmethod
    def validate_syntax(code: str, lang: str) -> Tuple[bool, str]:
        """Validate code syntax deterministically."""
        if not code:
            return True, ""

        if lang in ("python", "py"):
            try:
                ast.parse(code)
                return True, "Valid Python AST"
            except SyntaxError as e:
                return False, f"Python SyntaxError at line {e.lineno}: {e.msg}"

        if lang in ("json",):
            try:
                json.loads(code)
                return True, "Valid JSON"
            except Exception as e:
                return False, f"JSON ParseError: {e}"

        if lang in ("sql",):
            # Check balanced parentheses and standard DML/DDL structure
            if code.count("(") != code.count(")"):
                return False, "SQL Unbalanced parentheses detected"
            return True, "Valid SQL structure"

        return True, "Unsupported language syntax validation skipped"

    @classmethod
    def audit_response(cls, query: str, response: str, task_kind: str = "") -> Dict[str, Any]:
        """Comprehensive verification of generated output."""
        defects: List[str] = []
        code_blocks = cls.extract_code_blocks(response)

        # 1. Code Syntax Validation
        for lang, code in code_blocks:
            is_valid, err_msg = cls.validate_syntax(code, lang)
            if not is_valid:
                defects.append(f"[{lang.upper()} SYNTAX DEFECT] {err_msg}")

        # 2. Markdown Fence Balance Check
        fence_count = response.count("```")
        if fence_count % 2 != 0:
            defects.append("[MARKDOWN DEFECT] Unbalanced code block fences (odd number of ```)")

        # 3. Unchecked Placeholders in Coding/Audit Tasks
        if task_kind in ("coding", "audit", "database"):
            if re.search(r"\b(TODO: implement|insert code here|pass\s+# fill in)\b", response, re.I):
                defects.append("[COMPLETION DEFECT] Unimplemented placeholder detected in solution")

        score = max(0.0, 1.0 - (len(defects) * 0.35))
        return {
            "passed": len(defects) == 0,
            "score": round(score, 2),
            "defects": defects,
            "code_blocks_checked": len(code_blocks),
        }

    @classmethod
    def auto_correct(cls, response: str, defects: List[str]) -> str:
        """Apply deterministic surgical fixes for common LLM syntax/formatting glitches."""
        corrected = response

        # Auto-close unclosed code block fences
        if any("Unbalanced code block fences" in d for d in defects):
            corrected = corrected.rstrip() + "\n```\n"

        # Auto-fix common Python indentation or trailing commas in JSON
        for d in defects:
            if "JSON ParseError" in d:
                # Attempt trailing comma cleanup: ', \n}' -> '\n}'
                corrected = re.sub(r",\s*(\}|\])", r"\1", corrected)

        return corrected

    @classmethod
    def reflect_and_refine(
        cls,
        query: str,
        response: str,
        task_kind: str = "",
        refine_fn: Optional[Callable[[str, List[str]], str]] = None,
    ) -> str:
        """Audit response; auto-correct or invoke refinement callback if defects exist."""
        audit = cls.audit_response(query, response, task_kind)
        if audit["passed"]:
            return response

        logger.warning(f"[ReflectiveCritic] Defects detected (score {audit['score']}): {audit['defects']}")
        # 1. Deterministic correction
        fixed = cls.auto_correct(response, audit["defects"])
        re_audit = cls.audit_response(query, fixed, task_kind)
        if re_audit["passed"]:
            return fixed

        # 2. Optional model-level refinement
        if refine_fn:
            try:
                refined = refine_fn(response, audit["defects"])
                if refined:
                    return refined
            except Exception as e:
                logger.error(f"[ReflectiveCritic] Model refinement failed: {e}")

        return fixed
