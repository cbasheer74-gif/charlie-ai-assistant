"""engine/agents/research_agent.py — Web Research, Fact-Checking, and Live Trend Specialist.

Integrates with Phase 5 InternetIntelligenceEngine for full evidence-driven research,
source date verification, contradiction detection, and YouTube content briefs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.agents.base import BaseAgent
from engine.research.engine import InternetIntelligenceEngine
from engine.research.models import ResearchMode, ResearchReport, TrendCandidate


class ResearchAgent(BaseAgent):
    """Specialist agent for deep internet research, fact checking, and time-sensitive trends."""

    name: str = "ResearchAgent"
    description: str = "Live internet research, trend discovery, and fact-checking specialist"

    def __init__(
        self,
        memory: Optional[Any] = None,
        planner: Optional[Any] = None,
        permissions: Optional[Any] = None,
        verification: Optional[Any] = None,
        recovery: Optional[Any] = None,
        rollback: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(
            memory=memory,
            planner=planner,
            permissions=permissions,
            verification=verification,
            recovery=recovery,
            rollback=rollback,
        )
        self._engine: Optional[InternetIntelligenceEngine] = None

    @property
    def engine(self) -> InternetIntelligenceEngine:
        if self._engine is None:
            self._engine = InternetIntelligenceEngine()
        return self._engine

    def can_handle(self, user_intent: str) -> bool:
        low = user_intent.lower()
        return any(
            w in low
            for w in (
                "trend",
                "trending",
                "latest",
                "today",
                "news",
                "research",
                "verify",
                "fact check",
                "sach hai",
                "content brief",
                "youtube idea",
            )
        )

    def research(
        self,
        query: str,
        mode: ResearchMode = ResearchMode.STANDARD,
        project_context: Optional[Dict[str, Any]] = None,
    ) -> ResearchReport:
        """Execute deep research using the full Phase 5 pipeline."""
        return self.engine.execute_research(query, mode=mode, project_context=project_context)

    def fact_check(self, claim_text: str) -> Dict[str, Any]:
        """Verify an atomic statement or news claim against primary and independent sources."""
        report = self.engine.execute_research(f"fact check {claim_text}", mode=ResearchMode.STANDARD)
        return {
            "claim": claim_text,
            "confidence": report.confidence.value,
            "confidence_reason": report.confidence_reason,
            "established_facts": report.established_facts,
            "disagreements": [
                {"dimension": c.dimension, "detail": f"{c.first_value} vs {c.second_value}"}
                for c in report.disagreements
            ],
            "sources": [s.url for s in report.sources if s.url],
        }

    def discover_trends(
        self,
        niche: str = "technology",
        region: str = "GLOBAL",
    ) -> List[TrendCandidate]:
        """Discovers current momentum trends in the given niche and region."""
        return self.engine.research_trends(niche=niche, region=region)

    def tag_trend_with_ttl(self, topic: str, summary: str, ttl_hours: int = 12) -> Dict[str, Any]:
        """Format trend findings with explicit TTL expiry metadata (backward compatibility)."""
        now = datetime.now(timezone.utc)
        iso_now = now.isoformat()
        return {
            "topic": topic,
            "summary": summary,
            "fetched_at": iso_now,
            "ttl_hours": ttl_hours,
            "is_fresh": True,
        }
