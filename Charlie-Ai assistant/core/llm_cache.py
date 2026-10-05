"""core/llm_cache.py — High-Performance Multi-Tier LLM Response Cache.

Provides L1 (Memory LRU) + L2 (SQLite Persistent) caching for LLM inferences.
Bypasses cache for real-time temporal and dynamic queries.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("charlie.llm_cache")

_BYPASS_PATTERNS = re.compile(
    r"\b(time|date|today|now|current|weather|battery|cpu|ram|process|random|latest|recent)\b",
    re.IGNORECASE,
)


class LLMResponseCache:
    """Multi-tier LRU + SQLite cache for LLM queries."""

    def __init__(self, max_ram_entries: int = 1024, db_path: Optional[Path] = None):
        if db_path is None:
            from core.llm_client import BASE_DIR
            db_path = BASE_DIR / "config" / "llm_cache.db"
        self._db_path = Path(db_path)
        self._max_ram = max_ram_entries
        self._ram_cache: OrderedDict[str, str] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self._db_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS response_cache (
                        hash_key TEXT PRIMARY KEY,
                        prompt_norm TEXT NOT NULL,
                        model_name TEXT NOT NULL,
                        response_text TEXT NOT NULL,
                        hit_count INTEGER DEFAULT 1,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires ON response_cache(expires_at);")
                conn.commit()
        except Exception as e:
            logger.warning(f"Cache DB init failed: {e}")

    @staticmethod
    def is_cacheable(prompt: str) -> bool:
        if not prompt or len(prompt.strip()) < 3:
            return False
        # Do not cache real-time or dynamic queries
        if _BYPASS_PATTERNS.search(prompt):
            return False
        return True

    @staticmethod
    def compute_hash(prompt: str, model_name: str = "") -> str:
        norm = " ".join(prompt.lower().strip().split())
        raw = f"{model_name.lower().strip()}|{norm}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, prompt: str, model_name: str = "") -> Optional[str]:
        if not self.is_cacheable(prompt):
            self._misses += 1
            return None

        h = self.compute_hash(prompt, model_name)
        now = time.time()

        # 1. L1 RAM Hit
        if h in self._ram_cache:
            self._ram_cache.move_to_end(h)
            self._hits += 1
            return self._ram_cache[h]

        # 2. L2 SQLite Hit
        try:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT response_text, expires_at, hit_count FROM response_cache WHERE hash_key = ?",
                    (h,),
                ).fetchone()
                if row:
                    resp, expires_at, count = row
                    if expires_at > now:
                        conn.execute(
                            "UPDATE response_cache SET hit_count = hit_count + 1 WHERE hash_key = ?",
                            (h,),
                        )
                        conn.commit()
                        self._put_ram(h, resp)
                        self._hits += 1
                        return resp
                    else:
                        conn.execute("DELETE FROM response_cache WHERE hash_key = ?", (h,))
                        conn.commit()
        except Exception as e:
            logger.debug(f"Cache read error: {e}")

        self._misses += 1
        return None

    def put(self, prompt: str, response: str, model_name: str = "", ttl_sec: float = 86400.0) -> None:
        if not self.is_cacheable(prompt) or not response or len(response.strip()) < 2:
            return

        h = self.compute_hash(prompt, model_name)
        now = time.time()
        expires = now + ttl_sec

        self._put_ram(h, response)

        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO response_cache (hash_key, prompt_norm, model_name, response_text, hit_count, created_at, expires_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(hash_key) DO UPDATE SET
                    response_text = excluded.response_text,
                    expires_at = excluded.expires_at,
                    hit_count = hit_count + 1;
                    """,
                    (h, prompt.strip()[:500], model_name, response, now, expires),
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Cache write error: {e}")

    def _put_ram(self, h: str, val: str) -> None:
        self._ram_cache[h] = val
        self._ram_cache.move_to_end(h)
        if len(self._ram_cache) > self._max_ram:
            self._ram_cache.popitem(last=False)

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        ratio = (self._hits / total * 100.0) if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": f"{ratio:.1f}%",
            "ram_entries": len(self._ram_cache),
        }

    def clear(self) -> None:
        self._ram_cache.clear()
        try:
            with self._connection() as conn:
                conn.execute("DELETE FROM response_cache;")
                conn.commit()
        except Exception:
            pass


_instance: Optional[LLMResponseCache] = None


def get_llm_cache() -> LLMResponseCache:
    global _instance
    if _instance is None:
        _instance = LLMResponseCache()
    return _instance
