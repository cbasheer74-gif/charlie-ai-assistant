# engine/intelligence/episodic_memory.py
"""
Episodic Long-Term Memory for Charlie.

Records, indexes, and recalls specific user sessions, milestones, decisions,
project contexts, and preferences across reboots and conversations.

Features:
  - Episode recording with timestamp, tags, entities, importance, and outcome.
  - Time-decayed relevance scoring (Ebbinghaus-inspired retention curve).
  - Multi-factor search: semantic tags, entity matching, keyword overlap, importance.
  - Auto-compaction to keep persistent storage compact and fast.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class Episode:
    id: str
    timestamp: float
    summary: str
    tags: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    importance: int = 5  # 1 to 10
    outcome: str = "success"  # success, failure, neutral, pending
    details: Dict[str, Any] = field(default_factory=dict)

    def age_days(self, now: Optional[float] = None) -> float:
        current = now or time.time()
        return max(0.0, (current - self.timestamp) / 86400.0)

    def retention_weight(self, now: Optional[float] = None) -> float:
        """Calculates retention score factoring age and importance."""
        age = self.age_days(now)
        # Higher importance decays much slower
        decay_rate = max(0.02, (11 - self.importance) * 0.015)
        return float(self.importance) * math.exp(-decay_rate * age)


class EpisodicMemoryManager:
    """Thread-safe persistent episodic memory repository."""

    MAX_EPISODES = 500

    def __init__(self, storage_path: Optional[Path] = None):
        self.path = (
            storage_path
            or Path(__file__).resolve().parent.parent.parent / "config" / "episodic_memory.json"
        )
        self._lock = threading.Lock()
        self._episodes: List[Episode] = []
        self._load()

    def record_episode(
        self,
        summary: str,
        tags: Optional[List[str]] = None,
        entities: Optional[List[str]] = None,
        importance: int = 5,
        outcome: str = "success",
        details: Optional[Dict[str, Any]] = None,
    ) -> Episode:
        """Store a new episode into long-term memory."""
        ep_id = f"ep_{int(time.time())}_{len(self._episodes) + 1}"
        ep = Episode(
            id=ep_id,
            timestamp=time.time(),
            summary=summary.strip(),
            tags=[t.lower().strip() for t in (tags or [])],
            entities=[e.strip() for e in (entities or [])],
            importance=max(1, min(10, importance)),
            outcome=outcome,
            details=details or {},
        )
        with self._lock:
            self._episodes.append(ep)
            if len(self._episodes) > self.MAX_EPISODES:
                self._compact()
            self._save()
        return ep

    def recall(
        self,
        query: str,
        tag_filter: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Find most relevant episodes for a given query or context."""
        tokens = set(re.findall(r"\w+", query.lower()))
        tag_set = set(t.lower() for t in (tag_filter or []))

        with self._lock:
            now = time.time()
            scored: List[tuple[float, Episode]] = []

            for ep in self._episodes:
                # Tag filtering
                if tag_set and not tag_set.intersection(ep.tags):
                    continue

                # Token matching
                ep_tokens = set(re.findall(r"\w+", ep.summary.lower()))
                for t in ep.tags:
                    ep_tokens.add(t)
                for e in ep.entities:
                    ep_tokens.update(re.findall(r"\w+", e.lower()))

                overlap = len(tokens.intersection(ep_tokens))
                text_score = overlap / (len(tokens) + 1) if tokens else 0.5
                retention = ep.retention_weight(now)

                final_score = (text_score * 0.7) + (retention * 0.3)
                if final_score > 0.05:
                    scored.append((final_score, ep))

            scored.sort(key=lambda x: x[0], reverse=True)
            results = []
            for score, ep in scored[:top_k]:
                data = asdict(ep)
                data["relevance_score"] = round(score, 3)
                data["date_str"] = datetime.fromtimestamp(ep.timestamp).strftime("%Y-%m-%d %H:%M")
                results.append(data)
            return results

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return most recent episodes chronologically."""
        with self._lock:
            sorted_eps = sorted(self._episodes, key=lambda x: x.timestamp, reverse=True)
            return [asdict(ep) for ep in sorted_eps[:limit]]

    def _compact(self) -> None:
        """Prune low-importance, older episodes to maintain memory budget."""
        now = time.time()
        self._episodes.sort(key=lambda ep: ep.retention_weight(now), reverse=True)
        self._episodes = self._episodes[: int(self.MAX_EPISODES * 0.8)]

    def _load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._episodes = [Episode(**item) for item in raw]
        except Exception:
            self._episodes = []

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = [asdict(ep) for ep in self._episodes]
            self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


# Global singleton
_manager_instance: Optional[EpisodicMemoryManager] = None
_lock = threading.Lock()


def get_episodic_memory() -> EpisodicMemoryManager:
    global _manager_instance
    with _lock:
        if _manager_instance is None:
            _manager_instance = EpisodicMemoryManager()
        return _manager_instance
