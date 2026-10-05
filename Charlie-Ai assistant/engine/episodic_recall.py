"""engine/episodic_recall.py — Associative Episodic Recall Memory Engine.

Indexes historical interaction episodes, user goals, and project states with
dense semantic vectors, composite scoring (similarity + recency + importance),
and auto-surfaces relevant historical context into active prompts.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.db import get_db, init_db
from engine.semantic import cosine_similarity, local_dense_embedding

logger = logging.getLogger("charlie.episodic_recall")


class EpisodicRecallEngine:
    """Manages associative episodic memory indexing and multi-factor recall."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        init_db(self.db_path)
        self._init_table()

    def _init_table(self) -> None:
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodic_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    embedding_json TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 5.0,
                    access_count INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    language TEXT NOT NULL DEFAULT 'auto'
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_user ON episodic_memories(user_id);")
            # Migrate older DBs that pre-date the language column
            try:
                conn.execute("ALTER TABLE episodic_memories ADD COLUMN language TEXT NOT NULL DEFAULT 'auto'")
            except Exception:
                pass  # column already exists

    @staticmethod
    def _active_language() -> str:
        """Read the user's active language from personal hub."""
        try:
            from memory.personal_hub import load_hub
            lang = load_hub().get("speech", {}).get("language", "auto")
            return (lang or "auto").lower().strip()
        except Exception:
            return "auto"

    def record_episode(
        self,
        summary: str,
        tags: Optional[List[str]] = None,
        importance: float = 5.0,
        user_id: str = "default_user",
        language: Optional[str] = None,
    ) -> str:
        """Store an episodic event with dense semantic vector embedding and language tag."""
        clean_summary = summary.strip()
        if not clean_summary:
            return ""

        # Resolve language: explicit > hub preference > auto
        lang = (language or "").strip().lower() or self._active_language()

        now = time.time()
        ep_id = f"ep_{int(now * 1000)}"
        tags_list = tags or []
        # Dense feature vector
        vec = local_dense_embedding(f"{clean_summary} {' '.join(tags_list)}")

        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO episodic_memories
                (id, user_id, summary, tags_json, embedding_json, importance, access_count, created_at, last_accessed, language)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?);
                """,
                (ep_id, user_id, clean_summary, json.dumps(tags_list), json.dumps(vec), importance, now, now, lang),
            )
        return ep_id

    def recall_relevant(
        self,
        query: str,
        top_k: int = 3,
        user_id: str = "default_user",
        min_score: float = 0.25,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Multi-factor associative recall: similarity (50%) + recency (25%) + importance (15%) + frequency (10%).
        Language-match bonus (+0.10) applied when episode language matches the query language.
        """
        q_vec = local_dense_embedding(query)
        active_lang = (language or self._active_language()).lower()
        now = time.time()
        candidates: List[Dict[str, Any]] = []

        with get_db(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, summary, tags_json, embedding_json, importance,
                       access_count, created_at, last_accessed,
                       COALESCE(language, 'auto') as language
                FROM episodic_memories
                WHERE user_id = ?;
                """,
                (user_id,),
            ).fetchall()

            for r in rows:
                vec = json.loads(r["embedding_json"])
                sim = cosine_similarity(q_vec, vec)

                # Exponential decay for recency (half-life: 7 days = 604,800s)
                age_s = max(0.0, now - r["created_at"])
                recency = math.exp(-age_s / 604800.0)

                # Importance normalized to 0.0 - 1.0 (clamped from 0-10)
                norm_imp = min(1.0, max(0.0, r["importance"] / 10.0))

                # Access frequency log boost
                freq = min(1.0, math.log1p(r["access_count"]) / 4.0)

                # Language match bonus
                ep_lang = (r["language"] or "auto").lower()
                lang_bonus = 0.10 if (
                    active_lang not in ("auto", "") and ep_lang not in ("auto", "")
                    and ep_lang == active_lang
                ) else 0.0

                composite_score = (
                    (sim * 0.50)
                    + (recency * 0.25)
                    + (norm_imp * 0.15)
                    + (freq * 0.10)
                    + lang_bonus
                )

                if composite_score >= min_score:
                    candidates.append({
                        "id": r["id"],
                        "summary": r["summary"],
                        "tags": json.loads(r["tags_json"]),
                        "score": round(composite_score, 3),
                        "similarity": round(sim, 3),
                        "language": ep_lang,
                    })

        # Rank descending
        candidates.sort(key=lambda x: x["score"], reverse=True)
        top = candidates[:top_k]

        # Update last_accessed & access_count for recalled items
        if top:
            with get_db(self.db_path) as conn:
                for item in top:
                    conn.execute(
                        "UPDATE episodic_memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?;",
                        (now, item["id"]),
                    )

        return top

    def format_recall_prompt(self, query: str, top_k: int = 3, user_id: str = "default_user") -> str:
        """Format recalled memories into a concise prompt enrichment block."""
        recalled = self.recall_relevant(query, top_k=top_k, user_id=user_id)
        if not recalled:
            return ""
        lines = ["[RELEVANT HISTORICAL EPISODES — Associative Memory]"]
        for ep in recalled:
            lang = ep.get("language", "auto")
            lang_tag = f" [{lang.upper()}]" if lang not in ("auto", "") else ""
            lines.append(f"- (relevance: {ep['score']}{lang_tag}) {ep['summary']}")
        return "\n" + "\n".join(lines) + "\n"
