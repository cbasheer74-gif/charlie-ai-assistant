"""engine/research/planner.py — Research Intent Classification, Time-Sensitivity Detection, Query Expansion, and Planning."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from engine.research.models import (
    ResearchBudget,
    ResearchIntent,
    ResearchMode,
    ResearchPlan,
)

TIME_SENSITIVE_PATTERNS = [
    re.compile(r"\b(today|aaj|current|latest|recent|trending|trend|this\s+week|right\s+now|breaking|new|2026|latest\s+version|latest\s+release)\b", re.I),
]


class TimeSensitivityDetector:
    """Detects whether user prompt or research goal requires real-time / live information."""

    @staticmethod
    def is_time_sensitive(text: str) -> bool:
        if not text:
            return False
        return any(bool(pat.search(text)) for pat in TIME_SENSITIVE_PATTERNS)

    @staticmethod
    def get_freshness_ttl_seconds(intent: ResearchIntent, time_sensitive: bool) -> int:
        if intent == ResearchIntent.TREND_DISCOVERY or intent == ResearchIntent.NEWS_MONITORING:
            return 3600 * 6  # 6 hours
        if time_sensitive:
            return 3600 * 12  # 12 hours
        if intent == ResearchIntent.SOFTWARE_RESEARCH:
            return 86400 * 3  # 3 days
        return 86400 * 7  # 7 days evergreen


class ResearchIntentClassifier:
    """Classifies user request into one of 14 specific research intents."""

    @staticmethod
    def classify(query: str) -> ResearchIntent:
        low = query.lower()

        if any(w in low for w in ("sach hai", "fact check", "verify", "is it true", "real or fake", "fake news")):
            return ResearchIntent.SOURCE_VERIFICATION
        if any(w in low for w in ("short", "shorts", "reel", "youtube topic", "channel idea", "video topic")):
            return ResearchIntent.YOUTUBE_TOPIC_RESEARCH
        if any(w in low for w in ("trend", "trending", "kya chal raha", "whats hot", "viral")):
            return ResearchIntent.TREND_DISCOVERY
        if any(w in low for w in ("competitor", "channels like", "dusre creators")):
            return ResearchIntent.COMPETITOR_RESEARCH
        if any(w in low for w in ("deep research", "in-depth", "comprehensive report", "tafseel se")):
            return ResearchIntent.DEEP_RESEARCH
        if any(w in low for w in ("compare", "vs", "versus", "difference between", "behtar kaun")):
            return ResearchIntent.COMPARISON
        if any(w in low for w in ("product", "pricing", "buy", "review", "specs", "best laptop", "phone")):
            return ResearchIntent.PRODUCT_RESEARCH
        if any(w in low for w in ("docs", "documentation", "api", "sdk", "library", "framework", "flutter", "python", "version", "install")):
            return ResearchIntent.SOFTWARE_RESEARCH
        if any(w in low for w in ("how to", "kaise kare", "tutorial", "guide", "steps to")):
            return ResearchIntent.HOW_TO_RESEARCH
        if any(w in low for w in ("news", "samachar", "breaking", "happened today", "kya hua")):
            return ResearchIntent.CURRENT_EVENT
        if any(w in low for w in ("monitor", "track", "watch", "alert me")):
            return ResearchIntent.NEWS_MONITORING
        if any(w in low for w in ("content", "script idea", "blog post", "article topic")):
            return ResearchIntent.CONTENT_RESEARCH
        if any(w in low for w in ("market", "industry", "revenue", "sector")):
            return ResearchIntent.MARKET_RESEARCH

        return ResearchIntent.FACT_LOOKUP


class QueryGenerator:
    """Expands user query into diverse, non-redundant search queries."""

    @staticmethod
    def expand_query(query: str, intent: ResearchIntent, time_sensitive: bool, region: str = "GLOBAL") -> List[str]:
        base = query.strip()
        queries = [base]

        # Region context
        region_term = f" {region}" if region and region.upper() not in ("GLOBAL", "DEFAULT") else ""

        if intent == ResearchIntent.TREND_DISCOVERY:
            queries.append(f"{base} latest developments{region_term}")
            queries.append(f"{base} current trending topics 2026")
            queries.append(f"{base} news updates{region_term}")
        elif intent == ResearchIntent.YOUTUBE_TOPIC_RESEARCH:
            queries.append(f"{base} trending YouTube topics{region_term}")
            queries.append(f"{base} viral video ideas 2026")
            queries.append(f"{base} popular discussion")
        elif intent == ResearchIntent.SOFTWARE_RESEARCH:
            queries.append(f"{base} official documentation")
            queries.append(f"{base} release notes latest")
            queries.append(f"{base} changelog github")
        elif intent == ResearchIntent.SOURCE_VERIFICATION:
            queries.append(f"{base} fact check")
            queries.append(f"{base} primary source official announcement")
        elif intent == ResearchIntent.COMPARISON:
            queries.append(f"{base} comparison benchmark review")
            queries.append(f"{base} differences pros cons")
        elif time_sensitive:
            queries.append(f"{base} 2026 updates{region_term}")
            queries.append(f"{base} recent news")

        # Deduplicate while preserving order, cap at 4 targeted queries to avoid spamming
        seen = set()
        unique = []
        for q in queries:
            norm = q.lower().strip()
            if norm not in seen:
                seen.add(norm)
                unique.append(q)
        return unique[:4]


class ResearchPlanner:
    """Plans research tasks, determines budget, subquestions, and freshness requirements."""

    def __init__(self):
        self.classifier = ResearchIntentClassifier()
        self.time_detector = TimeSensitivityDetector()
        self.query_gen = QueryGenerator()

    def create_plan(
        self,
        goal: str,
        mode: Optional[ResearchMode] = None,
        project_context: Optional[Dict[str, Any]] = None,
        preferred_region: str = "GLOBAL",
        preferred_language: str = "en",
    ) -> ResearchPlan:
        ctx = project_context or {}
        intent = self.classifier.classify(goal)
        time_sensitive = self.time_detector.is_time_sensitive(goal)

        # Region override from project memory if specified
        region = ctx.get("region") or preferred_region
        language = ctx.get("language") or preferred_language

        # Infer mode if not passed explicitly
        if mode is None:
            if "deep research" in goal.lower() or intent == ResearchIntent.DEEP_RESEARCH:
                mode = ResearchMode.DEEP
            elif intent in (ResearchIntent.FACT_LOOKUP, ResearchIntent.HOW_TO_RESEARCH) and not time_sensitive:
                mode = ResearchMode.QUICK
            else:
                mode = ResearchMode.STANDARD

        # Configure budget based on mode
        if mode == ResearchMode.QUICK:
            budget = ResearchBudget(max_queries=2, max_sources=5, max_pages=3, max_execution_time=20.0)
            min_sources = 1
        elif mode == ResearchMode.DEEP:
            budget = ResearchBudget(max_queries=6, max_sources=20, max_pages=12, max_execution_time=120.0)
            min_sources = 4
        else:  # STANDARD
            budget = ResearchBudget(max_queries=4, max_sources=10, max_pages=6, max_execution_time=45.0)
            min_sources = 2

        # Subquestions decomposition
        subquestions = self._decompose_subquestions(goal, intent, time_sensitive)

        # Generate targeted queries
        queries = self.query_gen.expand_query(goal, intent, time_sensitive, region=region)

        # Freshness TTL
        freshness_ttl = self.time_detector.get_freshness_ttl_seconds(intent, time_sensitive)

        # Preferred source domain hints
        preferred_sources = []
        if intent == ResearchIntent.SOFTWARE_RESEARCH:
            preferred_sources = ["github.com", "developer.mozilla.org", "docs.python.org", "flutter.dev"]
        elif intent == ResearchIntent.SOURCE_VERIFICATION:
            preferred_sources = ["reuters.com", "apnews.com", "bbc.com", "snopes.com"]

        return ResearchPlan(
            goal=goal,
            intent=intent,
            mode=mode,
            subquestions=subquestions,
            search_queries=queries,
            required_freshness_ttl_sec=freshness_ttl,
            preferred_sources=preferred_sources,
            min_source_count=min_sources,
            budget=budget,
            time_sensitive=time_sensitive,
            project_context=ctx,
            region=region,
            language=language,
        )

    def _decompose_subquestions(self, goal: str, intent: ResearchIntent, time_sensitive: bool) -> List[str]:
        sq = []
        if intent in (ResearchIntent.DEEP_RESEARCH, ResearchIntent.MARKET_RESEARCH):
            sq.append("What are the core established foundations and baseline facts?")
            sq.append("What are the latest developments, breakthroughs, or releases?")
            sq.append("What are the key disputes, uncertainties, or contrasting viewpoints?")
            sq.append("What are the strategic, technical, or practical implications?")
        elif intent in (ResearchIntent.TREND_DISCOVERY, ResearchIntent.YOUTUBE_TOPIC_RESEARCH):
            sq.append("What are the most recent events or developments?")
            sq.append("Which topics have multiple independent credible sources?")
            sq.append("What are creators and audiences currently engaging with?")
            sq.append("Which angle offers high visual/short-form content value?")
        elif intent == ResearchIntent.SOURCE_VERIFICATION:
            sq.append("What is the exact atomic claim being made?")
            sq.append("Is there an official primary source confirming or refuting it?")
            sq.append("Are there contradicting reports, dates, or numbers?")
        elif intent == ResearchIntent.SOFTWARE_RESEARCH:
            sq.append("What is the current official documentation/version requirement?")
            sq.append("Are there breaking changes or deprecations?")
            sq.append("What are the verified implementation steps?")
        else:
            sq.append("What are the primary established facts?")
            if time_sensitive:
                sq.append("What changed recently or today?")
            sq.append("Are there any uncertainties or conflicting sources?")
            sq.append("What are the actionable conclusions?")
        return sq
