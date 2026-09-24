"""engine/research/engine.py — InternetIntelligenceEngine: Orchestrates Search, Verification, Trend, and Content Intelligence."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.research.bridge import ResearchToActionBridge
from engine.research.collector import PageReader, RecencyEngine, SourceCollector, SourceEvaluator
from engine.research.content_engine import ContentBrief, YouTubeIntelligenceEngine
from engine.research.fact_checker import ClaimExtractor, ContradictionDetector, FactVerificationEngine
from engine.research.guard import UntrustedContentGuard
from engine.research.memory import ResearchMemoryManager
from engine.research.models import (
    AtomicClaim,
    ClaimEvidenceMap,
    ConfidenceLevel,
    ContradictionRecord,
    ResearchIntent,
    ResearchMode,
    ResearchPlan,
    ResearchReport,
    SourceRecord,
    TrendCandidate,
    VerificationStatus,
)
from engine.research.planner import QueryGenerator, ResearchIntentClassifier, ResearchPlanner, TimeSensitivityDetector
from engine.research.providers import SearchProvider, SearchProviderManager
from engine.research.synthesizer import ResearchSynthesizer
from engine.research.trend_engine import TopicClusterer, TrendDiscoveryEngine


class InternetIntelligenceEngine:
    """Core coordinator for JARVIS Phase 5 Deep Research & Internet Intelligence."""

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        search_providers: Optional[List[SearchProvider]] = None,
    ):
        self.planner = ResearchPlanner()
        self.provider_mgr = SearchProviderManager(search_providers)
        self.collector = SourceCollector()
        self.page_reader = PageReader()
        self.fact_engine = FactVerificationEngine()
        self.synthesizer = ResearchSynthesizer()
        self.memory_mgr = ResearchMemoryManager(db_path=db_path)
        self.trend_engine = TrendDiscoveryEngine()
        self.youtube_engine = YouTubeIntelligenceEngine(db_path=db_path)
        self.action_bridge = ResearchToActionBridge()
        self.guard = UntrustedContentGuard()

        self._checkpoints: Dict[str, Dict[str, Any]] = {}

    def plan_research(
        self,
        goal: str,
        mode: Optional[ResearchMode] = None,
        project_context: Optional[Dict[str, Any]] = None,
    ) -> ResearchPlan:
        return self.planner.create_plan(goal, mode=mode, project_context=project_context)

    def execute_research(
        self,
        goal: str,
        mode: Optional[ResearchMode] = None,
        project_context: Optional[Dict[str, Any]] = None,
        resume_task_id: Optional[str] = None,
    ) -> ResearchReport:
        """Executes full SEARCH -> FILTER -> READ -> COMPARE -> VERIFY -> SYNTHESIZE pipeline."""
        plan = self.plan_research(goal, mode=mode, project_context=project_context)

        # Check Cache Reuse first (if not strictly time sensitive)
        cached = self.memory_mgr.find_cached_report(
            goal, force_live_if_time_sensitive=plan.time_sensitive
        )
        if cached:
            return cached

        # Check if resuming from checkpoint
        sources: List[SourceRecord] = []
        if resume_task_id and resume_task_id in self._checkpoints:
            checkpoint_data = self._checkpoints[resume_task_id]
            sources = checkpoint_data.get("sources", [])
        else:
            task_id = f"res_{int(time.time())}_{abs(hash(goal)) % 1000}"
            # 1. Collect Sources via Query Expansion
            is_news = plan.intent in (ResearchIntent.TREND_DISCOVERY, ResearchIntent.CURRENT_EVENT, ResearchIntent.NEWS_MONITORING)
            all_raw_hits = []

            for q in plan.search_queries[:plan.budget.max_queries]:
                if not self.memory_mgr.register_query(q):
                    continue  # Skip redundant query loop
                hits = self.provider_mgr.execute_search(q, is_news=is_news, max_results=5)
                for h in hits:
                    rec = self.collector.create_record(
                        h,
                        query=q,
                        intent=plan.intent,
                        time_sensitive=plan.time_sensitive,
                        ttl_seconds=plan.required_freshness_ttl_sec,
                    )
                    all_raw_hits.append(rec)

            # 2. Deduplicate and Group Syndicated Sources
            sources = self.collector.deduplicate_and_group(all_raw_hits)[:plan.budget.max_sources]

            # Save Checkpoint for resume capability
            self._checkpoints[task_id] = {
                "goal": goal,
                "plan": plan,
                "sources": sources,
                "stage": "sources_collected",
            }

        # 3. Extract Atomic Claims across Sources
        claims: List[AtomicClaim] = []
        for s in sources:
            extracted = ClaimExtractor.extract_claims(s.snippet, source_url=s.url)
            claims.extend(extracted)

        # 4. Check Information Gain
        self.memory_mgr.track_information_gain(len(sources), len(claims))

        # 5. Verify Claims & Detect Contradictions
        evidence_maps: List[ClaimEvidenceMap] = []
        all_conflicts: List[ContradictionRecord] = []

        for c in claims[:12]:
            ev_map = self.fact_engine.verify_claim(c, sources)
            evidence_maps.append(ev_map)
            conflicts = ContradictionDetector.detect_conflicts(c, sources)
            all_conflicts.extend(conflicts)

        # 6. Synthesize Report
        report = self.synthesizer.synthesize(plan, evidence_maps, sources, all_conflicts)

        # 7. Persist to Structured Memory
        self.memory_mgr.store_report(report, is_time_sensitive=plan.time_sensitive)

        return report

    def research_trends(
        self,
        niche: str = "technology",
        region: str = "GLOBAL",
        query_override: Optional[str] = None,
    ) -> List[TrendCandidate]:
        """Discovers and normalizes momentum trends for a niche/region."""
        query = query_override or f"{niche} trending news today"
        plan = self.planner.create_plan(
            query,
            mode=ResearchMode.STANDARD,
            preferred_region=region,
        )
        is_news = True
        raw_hits = []
        for q in plan.search_queries[:3]:
            hits = self.provider_mgr.execute_search(q, is_news=is_news, max_results=6)
            for h in hits:
                raw_hits.append(self.collector.create_record(h, query=q, intent=plan.intent, time_sensitive=True))

        sources = self.collector.deduplicate_and_group(raw_hits)
        return self.trend_engine.discover_trends(sources, niche=niche, region=region)

    def research_youtube_topic(
        self,
        channel_context: Optional[Dict[str, Any]] = None,
        preferred_niche: str = "technology",
    ) -> Tuple[TrendCandidate, ContentBrief, ResearchReport]:
        """Full pipeline: Channel context -> Trend Discovery -> Fact Check -> Content Brief."""
        ctx = channel_context or {}
        region = ctx.get("region", "GLOBAL")
        niche = ctx.get("niche", preferred_niche)

        candidates = self.research_trends(niche=niche, region=region)
        if not candidates:
            # Fallback candidate
            candidates = [
                TrendCandidate(
                    topic=f"Emerging {niche.title()} Innovations in 2026",
                    summary=f"Rapid advancements across {niche} workflows and creator productivity.",
                    first_seen=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    latest_activity=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                )
            ]

        # Evaluate best candidate opportunity
        best_opp = None
        best_cand = candidates[0]
        for c in candidates:
            opp = self.youtube_engine.evaluate_opportunity(c, channel_context=ctx)
            if best_opp is None or opp["overall_opportunity_score"] > best_opp["overall_opportunity_score"]:
                best_opp = opp
                best_cand = c

        # Deep research on the chosen topic for factual verification
        report = self.execute_research(best_cand.topic, mode=ResearchMode.STANDARD, project_context=ctx)

        # Generate ContentBrief with FactLock
        brief = self.youtube_engine.generate_content_brief(best_cand, report, channel_context=ctx)

        return best_cand, brief, report
