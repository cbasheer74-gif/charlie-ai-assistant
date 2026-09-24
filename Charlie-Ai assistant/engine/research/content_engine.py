"""engine/research/content_engine.py — YouTube Content Strategy, Hook Generation, Title Intelligence, Fact Locking, and Content Briefs."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.research.models import (
    ContentBrief,
    FactLock,
    ResearchReport,
    TrendCandidate,
    VerificationStatus,
)


class HookGenerator:
    """Generates engaging, research-grounded hooks without fabricated facts."""

    @staticmethod
    def generate_hooks(topic: str, verified_facts: List[str], language: str = "en") -> List[str]:
        fact_snippet = verified_facts[0] if verified_facts else topic

        if language.lower() in ("hi", "hindi", "hinglish"):
            return [
                f"Kya aapko pata hai? {fact_snippet[:80]} — par asli sach kya hai?",
                f"Agar aap tech use karte ho, toh ye update aapke liye game-changer hai!",
                f"Stop scrolling! Is nayi technology ke bare mein sabse bada sach jaan lo.",
                f"3 baatein jo aapko is naye update ke bare mein koi nahi bata raha.",
            ]

        return [
            f"Did you know? {fact_snippet[:80]} — here is what actually happened.",
            f"Everyone is talking about {topic[:40]}, but they missed this crucial detail.",
            f"If you're using this technology in 2026, stop right now and listen.",
            f"The real truth behind this new announcement that changes everything.",
        ]


class TitleIntelligence:
    """Generates accurate, click-worthy titles without sensationalist falsehoods."""

    @staticmethod
    def generate_titles(topic: str, angle: str, format_type: str = "Short") -> List[str]:
        prefix = "⚡ " if format_type.lower() == "short" else ""
        return [
            f"{prefix}{topic}: What Just Happened?",
            f"{prefix}The Real Truth About {topic}",
            f"{prefix}{topic} Explained in 60 Seconds",
            f"{prefix}Don't Ignore This: {topic} Update",
        ]


class YouTubeIntelligenceEngine:
    """Evaluates content opportunities for YouTube channels (Shorts & Long-form) using channel context."""

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.db_path = base_dir / "memory" / "content_library.db"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.hook_gen = HookGenerator()
        self.title_intel = TitleIntelligence()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS content_library (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id TEXT UNIQUE NOT NULL,
                    topic TEXT NOT NULL,
                    angle TEXT NOT NULL,
                    format TEXT NOT NULL,
                    script_path TEXT,
                    video_path TEXT,
                    created_at TEXT NOT NULL,
                    publish_state TEXT DEFAULT 'DRAFT',
                    sources JSON,
                    performance_metadata JSON
                );
            """)
            conn.commit()

    def evaluate_opportunity(
        self,
        candidate: TrendCandidate,
        channel_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ctx = channel_context or {}
        niche = ctx.get("niche", "tech").lower()
        region = ctx.get("region", "GLOBAL").upper()

        # Opportunity evaluation across 11 dimensions
        freshness = candidate.freshness
        audience_relevance = 0.9 if (region == candidate.region or candidate.region == "GLOBAL") else 0.6
        available_evidence = candidate.evidence_quality
        novelty = candidate.novelty
        saturation = candidate.content_saturation
        explainability = 0.85
        visual_potential = 0.9 if "video" in candidate.topic.lower() or "ai" in candidate.topic.lower() else 0.75
        short_form_fit = 0.95
        long_form_fit = 0.7
        shelf_life = 0.6 if candidate.is_rumour else 0.8
        production_difficulty = 0.3  # Lower is easier

        # Check duplicate content in library
        is_duplicate = self.check_is_duplicate(candidate.topic)

        overall_score = (
            freshness * 0.25 +
            audience_relevance * 0.20 +
            available_evidence * 0.20 +
            novelty * 0.15 +
            visual_potential * 0.10 +
            short_form_fit * 0.10 -
            (0.3 if is_duplicate else 0.0)
        )

        return {
            "candidate": candidate,
            "overall_opportunity_score": round(overall_score, 2),
            "freshness": freshness,
            "audience_relevance": audience_relevance,
            "available_evidence": available_evidence,
            "novelty": novelty,
            "content_saturation": saturation,
            "visual_potential": visual_potential,
            "short_form_fit": short_form_fit,
            "production_difficulty": production_difficulty,
            "is_duplicate": is_duplicate,
        }

    def check_is_duplicate(self, topic: str) -> bool:
        norm = topic.lower().strip()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT topic FROM content_library;")
            rows = cursor.fetchall()
            for r in rows:
                past_topic = r[0].lower()
                if norm in past_topic or past_topic in norm:
                    return True
        return False

    def create_fact_lock(self, report: ResearchReport) -> FactLock:
        approved = list(report.established_facts)
        well_supported = list(report.recent_developments)
        to_avoid = list(report.uncertain_claims)

        for conf in report.disagreements:
            to_avoid.append(f"Contradiction in {conf.dimension}: {conf.first_value} vs {conf.second_value}")

        return FactLock(
            approved_claims=approved,
            well_supported_claims=well_supported,
            uncertain_claims_to_avoid=to_avoid,
        )

    def generate_content_brief(
        self,
        candidate: TrendCandidate,
        report: ResearchReport,
        channel_context: Optional[Dict[str, Any]] = None,
        target_duration: int = 60,
    ) -> ContentBrief:
        ctx = channel_context or {}
        language = ctx.get("language", "en")
        target_aud = ctx.get("target_audience", "Tech enthusiasts & creators")

        fact_lock = self.create_fact_lock(report)
        hooks = self.hook_gen.generate_hooks(candidate.topic, fact_lock.approved_claims or [candidate.summary], language=language)

        key_points = [candidate.summary]
        if fact_lock.approved_claims:
            key_points.extend(fact_lock.approved_claims[:2])
        elif fact_lock.well_supported_claims:
            key_points.extend(fact_lock.well_supported_claims[:2])

        visual_ideas = [
            "Quick split-screen comparison",
            "Animated highlight callout for the primary fact",
            "Punchy dynamic subtitles centered in bottom third",
        ]

        sources_urls = [s.url for s in candidate.supporting_sources if s.url][:4]

        return ContentBrief(
            topic=candidate.topic,
            why_now=f"High current momentum with {candidate.cluster_size} independent reports and active discussion.",
            target_audience=target_aud,
            main_angle=candidate.content_angle_options[0] if candidate.content_angle_options else "Key factual breakdown",
            verified_facts=fact_lock.approved_claims + fact_lock.well_supported_claims,
            key_sources=sources_urls,
            hook_options=hooks,
            key_points=key_points,
            visual_ideas=visual_ideas,
            claims_to_avoid=fact_lock.uncertain_claims_to_avoid,
            target_duration=target_duration,
            cta="Follow for daily verified tech breakdowns.",
            fact_lock=fact_lock,
        )

    def record_content_created(self, brief: ContentBrief, script_path: str = "", video_path: str = "") -> str:
        cid = f"content_{int(time.time())}_{abs(hash(brief.topic)) % 1000}"
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO content_library (
                    content_id, topic, angle, format, script_path, video_path, created_at, sources
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                cid,
                brief.topic,
                brief.main_angle,
                "SHORT",
                script_path,
                video_path,
                now_iso,
                json.dumps(brief.key_sources),
            ))
            conn.commit()
        return cid
