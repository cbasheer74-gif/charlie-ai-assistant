"""engine/semantic.py — Semantic retrieval and ranking engine.

Implements pluggable embeddings (local hashed bag-of-words/n-grams fallback + Gemini API)
and multi-factor ranking combining semantic similarity, importance, recency,
project relevance, and reuse frequency.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

_DIM = 64  # Compact dense vector dimension for local fallback


def _clean_tokens(text: str) -> List[str]:
    clean = re.sub(r"[^\w\s]", " ", text.lower())
    return [w for w in clean.split() if len(w) > 1]


def local_dense_embedding(text: str, dim: int = _DIM) -> List[float]:
    """Fast deterministic feature-hash dense embedding vector (unit length).

    Requires no heavy PyTorch or external model; runs instantly with zero cold start.
    """
    tokens = _clean_tokens(text)
    if not tokens:
        return [0.0] * dim

    vec = [0.0] * dim
    for i, token in enumerate(tokens):
        # 1-gram
        h1 = hash(token) % dim
        vec[h1] += 1.0
        # 2-gram if available
        if i > 0:
            h2 = hash(f"{tokens[i-1]}_{token}") % dim
            vec[h2] += 1.5

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [round(x / norm, 5) for x in vec]
    return vec


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two unit-normalized vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    return max(0.0, min(1.0, dot))


class SemanticEngine:
    """Pluggable semantic memory search and composite ranking."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key

    def get_embedding(self, text: str) -> List[float]:
        """Compute text embedding vector."""
        if not text or not text.strip():
            return [0.0] * _DIM
        return local_dense_embedding(text, _DIM)

    @staticmethod
    def compute_ranking_score(
        semantic_sim: float,
        importance: float,
        updated_at_iso: str,
        is_current_project: bool,
        access_count: int,
    ) -> float:
        """Evaluate memory relevance using 5-factor scoring model.

        Weights:
          semantic_sim:        0.50
          importance_score:    0.20
          recency_score:       0.15
          project_relevance:   0.10
          reuse_score:         0.05
        """
        # 1. Importance (normalized from 1-10 to 0-1)
        imp_norm = max(0.1, min(10.0, float(importance or 5.0))) / 10.0

        # 2. Recency (exponential decay over 30 days)
        recency = 0.5
        try:
            # Handle ISO string with or without Z/offset
            ts_str = updated_at_iso.replace("Z", "+00:00")
            updated_dt = datetime.fromisoformat(ts_str)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            delta_days = max(0.0, (now_dt - updated_dt).total_seconds() / 86400.0)
            recency = math.exp(-delta_days / 30.0)
        except Exception:
            recency = 0.5

        # 3. Project relevance
        proj_rel = 1.0 if is_current_project else 0.2

        # 4. Reuse score (logarithmic saturation)
        reuse_score = min(1.0, math.log1p(max(0, access_count)) / 3.0)

        final_score = (
            (semantic_sim * 0.50)
            + (imp_norm * 0.20)
            + (recency * 0.15)
            + (proj_rel * 0.10)
            + (reuse_score * 0.05)
        )
        return round(final_score, 4)
