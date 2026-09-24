"""engine/skills/corrections.py — Skill Correction Manager & Adaptive Preference Learning.

Captures user corrections during/after task execution, classifies scope
(ONE_TIME, PROJECT, SKILL, GLOBAL), tracks occurrence frequency, and promotes
recurring corrections into persistent Skill defaults.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional

from engine.skills.db import SkillDatabase
from engine.skills.models import SkillCorrection


class SkillCorrectionManager:
    """Manages procedural user corrections, scopes, and preference promotion."""

    def __init__(self, skill_db: SkillDatabase):
        self.db = skill_db

    def record_correction(
        self,
        skill_id: str,
        user_correction: str,
        original_behavior: str = "",
        corrected_behavior: str = "",
        explicit_scope: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> SkillCorrection:
        """Analyze, scope, and store a user correction."""
        scope = explicit_scope or self._classify_scope(user_correction, project_name)

        # Retrieve existing corrections for this skill to calculate recurring confidence
        existing = self.db.get_corrections(skill_id)
        similar_count = sum(
            1 for c in existing
            if self._is_similar_correction(c.user_correction, user_correction)
        )
        new_confidence = min(3.0, 1.0 + (similar_count * 0.5))

        corr_id = f"corr_{uuid.uuid4().hex[:8]}"
        correction = SkillCorrection(
            id=corr_id,
            skill_id=skill_id,
            original_behavior=original_behavior,
            user_correction=user_correction,
            corrected_behavior=corrected_behavior or user_correction,
            scope=scope,
            confidence=new_confidence,
        )

        self.db.record_correction(correction)

        # If recurring correction (count >= 2) and scoped to SKILL or GLOBAL, promote to skill defaults
        if scope in ("SKILL", "GLOBAL") and similar_count >= 1:
            self._promote_correction_to_skill(skill_id, user_correction)

        return correction

    def get_corrections(self, skill_id: Optional[str] = None) -> List[SkillCorrection]:
        return self.db.get_corrections(skill_id)

    def apply_corrections_to_variables(
        self, skill_id: str, current_vars: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply active persistent corrections as variable overrides."""
        updated = dict(current_vars)
        corrections = self.db.get_corrections(skill_id)

        for c in reversed(corrections):
            if c.scope in ("SKILL", "GLOBAL") and c.confidence >= 1.5:
                # Infer variable override (e.g. "duration 30", "keep 30 sec")
                extracted = self._extract_variable_override(c.user_correction)
                for var_k, var_v in extracted.items():
                    updated[var_k] = var_v

        return updated

    def _classify_scope(self, text: str, project_name: Optional[str]) -> str:
        """Classify scope into ONE_TIME, PROJECT, SKILL, or GLOBAL."""
        low = text.lower()

        # One time indicators
        if any(p in low for p in ("sirf is baar", "only this time", "just for now", "aaj ke liye", "this once", "temporary")):
            return "ONE_TIME"

        # Global indicators
        if any(p in low for p in ("har jagah", "everywhere", "globally", "all skills", "hamesha ke liye", "universal")):
            return "GLOBAL"

        # Project indicators
        if project_name and project_name.lower() in low or any(p in low for p in ("is project mein", "in this project", "for this repo")):
            return "PROJECT"

        # Default to SKILL preference for future runs
        return "SKILL"

    def _is_similar_correction(self, text_a: str, text_b: str) -> bool:
        """Determine if two corrections target the same concept."""
        toks_a = set(re.findall(r"\w+", text_a.lower()))
        toks_b = set(re.findall(r"\w+", text_b.lower()))
        if not toks_a or not toks_b:
            return False
        overlap = len(toks_a.intersection(toks_b)) / min(len(toks_a), len(toks_b))
        return overlap >= 0.5

    def _extract_variable_override(self, text: str) -> Dict[str, Any]:
        """Extract explicit numeric or string parameters from correction text."""
        result: Dict[str, Any] = {}
        low = text.lower()

        # Duration match (e.g. 30 sec, 30s, duration 30)
        dur_match = re.search(r"(\d+)\s*(?:sec|seconds|s|second)", low)
        if dur_match:
            result["duration"] = int(dur_match.group(1))

        # Output folder or format
        if "excel" in low or "xlsx" in low:
            result["format"] = "xlsx"
        elif "csv" in low:
            result["format"] = "csv"

        return result

    def _promote_correction_to_skill(self, skill_id: str, correction_text: str) -> None:
        """Promote a repeated correction directly into the Skill's default variables."""
        skill = self.db.get_skill(skill_id)
        if not skill:
            return

        overrides = self._extract_variable_override(correction_text)
        if not overrides:
            return

        modified = False
        for var in skill.variables:
            if var.name.lower() in overrides:
                var.default = overrides[var.name.lower()]
                modified = True

        if modified:
            skill.version += 1
            self.db.save_skill(
                skill,
                changelog=f"Auto-promoted user correction into defaults: {correction_text}",
            )
