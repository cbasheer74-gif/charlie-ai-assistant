"""engine/skills/resolver.py — Skill Matching and Multi-Factor Ranking Engine.

Resolves natural language requests to learned procedural skills considering
trigger phrases, semantic intent, project relevance, confidence, and reliability metrics.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from engine.skills.db import SkillDatabase
from engine.skills.models import Skill, SkillStatus


class SkillResolver:
    """Matches user requests to the most appropriate registered Skill."""

    def __init__(self, skill_db: SkillDatabase):
        self.db = skill_db

    def resolve(
        self,
        user_request: str,
        active_project: Optional[str] = None,
        active_application: Optional[str] = None,
        min_threshold: float = 0.50,
    ) -> List[Tuple[Skill, float]]:
        """Rank and return candidate skills with confidence scores."""
        all_skills = self.db.list_skills()
        # Filter out disabled skills
        candidate_skills = [s for s in all_skills if s.status != SkillStatus.DISABLED]

        scored: List[Tuple[Skill, float]] = []
        req_norm = user_request.lower().strip()
        req_tokens = set(re.findall(r"\w+", req_norm))

        for skill in candidate_skills:
            score = self._compute_score(
                skill=skill,
                request_text=req_norm,
                request_tokens=req_tokens,
                active_project=active_project,
                active_application=active_application,
            )
            if score >= min_threshold:
                scored.append((skill, round(score, 3)))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _compute_score(
        self,
        skill: Skill,
        request_text: str,
        request_tokens: set[str],
        active_project: Optional[str],
        active_application: Optional[str],
    ) -> float:
        # 1. Trigger phrase match (weight: 0.45)
        trigger_score = 0.0
        for trg in skill.triggers:
            phrase_clean = trg.phrase.lower().strip()
            if phrase_clean in request_text or request_text in phrase_clean:
                trigger_score = max(trigger_score, 1.0)
            else:
                trg_tokens = set(re.findall(r"\w+", phrase_clean))
                if trg_tokens:
                    overlap = len(request_tokens.intersection(trg_tokens)) / len(trg_tokens)
                    trigger_score = max(trigger_score, overlap * 0.8)

        # 2. Intent token overlap (weight: 0.25)
        intent_tokens = set(re.findall(r"\w+", skill.intent.lower()))
        intent_score = 0.0
        if intent_tokens:
            intent_score = len(request_tokens.intersection(intent_tokens)) / len(intent_tokens)

        # Backfill trigger score from intent if no explicit triggers registered
        if not skill.triggers and intent_score > 0:
            trigger_score = intent_score

        # 3. Base Skill Confidence & Trust Status (weight: 0.15)
        status_boost = {
            SkillStatus.TRUSTED: 1.0,
            SkillStatus.STABLE: 0.85,
            SkillStatus.LEARNING: 0.65,
            SkillStatus.DRAFT: 0.40,
            SkillStatus.DEGRADED: 0.20,
        }.get(skill.status, 0.5)
        confidence_score = (skill.confidence * 0.6) + (status_boost * 0.4)

        # 4. Project relevance (weight: 0.10)
        project_score = 0.5
        if active_project:
            p_low = active_project.lower()
            if p_low in skill.name.lower() or p_low in skill.intent.lower():
                project_score = 1.0

        # 5. Success history boost (weight: 0.05)
        total_runs = skill.success_count + skill.failure_count
        history_score = (skill.success_count / total_runs) if total_runs > 0 else 0.5

        # Composite Ranking Formula
        final_score = (
            (trigger_score * 0.45)
            + (intent_score * 0.25)
            + (confidence_score * 0.15)
            + (project_score * 0.10)
            + (history_score * 0.05)
        )
        return min(1.0, final_score)
