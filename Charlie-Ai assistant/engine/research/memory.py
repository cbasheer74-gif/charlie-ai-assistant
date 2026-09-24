"""engine/research/memory.py — Research Memory Persistence, TTL Expiration, Cache Reuse, and Loop Detection."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from engine.research.models import ConfidenceLevel, ResearchReport, SourceRecord


class ResearchMemoryManager:
    """Manages structured research persistence, TTL expiry, cache reuse, and search loop detection."""

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.db_path = base_dir / "memory" / "research_memory.db"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._seen_queries: Set[str] = set()
        self._consecutive_zero_gains = 0

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    topic_key TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL,
                    established_facts JSON,
                    recent_developments JSON,
                    confidence TEXT NOT NULL,
                    confidence_reason TEXT,
                    sources JSON,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    is_time_sensitive INTEGER DEFAULT 0
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_topic_key ON research_reports (topic_key);")
            conn.commit()

    @staticmethod
    def _topic_key(topic: str) -> str:
        import re
        return re.sub(r"[^a-z0-9]+", "_", topic.strip().lower()).strip("_")

    def store_report(self, report: ResearchReport, is_time_sensitive: bool = False) -> None:
        key = self._topic_key(report.research_goal)
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expires_at = report.expires_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400))

        sources_payload = [
            {"url": s.url, "title": s.title, "domain": s.domain, "published_at": s.published_at}
            for s in report.sources[:10]
        ]

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO research_reports (
                    topic, topic_key, summary, established_facts, recent_developments,
                    confidence, confidence_reason, sources, created_at, expires_at, is_time_sensitive
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(topic_key) DO UPDATE SET
                    summary=excluded.summary,
                    established_facts=excluded.established_facts,
                    recent_developments=excluded.recent_developments,
                    confidence=excluded.confidence,
                    confidence_reason=excluded.confidence_reason,
                    sources=excluded.sources,
                    created_at=excluded.created_at,
                    expires_at=excluded.expires_at,
                    is_time_sensitive=excluded.is_time_sensitive;
            """, (
                report.research_goal,
                key,
                report.summary,
                json.dumps(report.established_facts),
                json.dumps(report.recent_developments),
                report.confidence.value,
                report.confidence_reason,
                json.dumps(sources_payload),
                now_iso,
                expires_at,
                1 if is_time_sensitive else 0,
            ))
            conn.commit()

    def find_cached_report(self, topic: str, force_live_if_time_sensitive: bool = True) -> Optional[ResearchReport]:
        key = self._topic_key(topic)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM research_reports WHERE topic_key = ?;", (key,)).fetchone()
            if not row:
                return None

            # Check expiry
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            expires_at = row["expires_at"]
            if expires_at and expires_at < now_iso:
                # Expired cache!
                return None

            # If time-sensitive and live search requested, bypass cache
            if row["is_time_sensitive"] and force_live_if_time_sensitive:
                return None

            sources = [
                SourceRecord(
                    url=s.get("url", ""),
                    title=s.get("title", ""),
                    domain=s.get("domain", ""),
                    published_at=s.get("published_at"),
                ) for s in json.loads(row["sources"] or "[]")
            ]

            return ResearchReport(
                research_goal=row["topic"],
                time_context=row["created_at"],
                summary=row["summary"],
                established_facts=json.loads(row["established_facts"] or "[]"),
                recent_developments=json.loads(row["recent_developments"] or "[]"),
                confidence=ConfidenceLevel(row["confidence"]),
                confidence_reason=row["confidence_reason"] or "",
                sources=sources,
                expires_at=row["expires_at"],
                is_reused_from_cache=True,
            )

    # ── Search Loop & Information Gain Detection ──────────────────────────────

    def register_query(self, query: str) -> bool:
        """Returns False if query was already searched in this session (redundancy loop)."""
        norm = query.strip().lower()
        if norm in self._seen_queries:
            return False
        self._seen_queries.add(norm)
        return True

    def track_information_gain(self, new_sources: int, new_claims: int) -> bool:
        """Returns False if search yields negligible information gain repeatedly."""
        gain = new_sources * 2 + new_claims * 3
        if gain == 0:
            self._consecutive_zero_gains += 1
        else:
            self._consecutive_zero_gains = 0

        # Stop if 3 consecutive searches yielded zero new information
        return self._consecutive_zero_gains < 3
