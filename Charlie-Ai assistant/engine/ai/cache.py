"""
JARVIS Phase 11: Response Cache & File Context Invalidation
Caches deterministic and stable model transformations, invalidating on file changes or TTL expiry.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("jarvis.ai.cache")


class ResponseCache:
    """Stores reusable model responses keyed by prompt and file content hashes."""

    def __init__(self, default_ttl_seconds: float = 3600.0):
        self.default_ttl = default_ttl_seconds
        # key -> {response, created_at, expires_at, file_hashes}
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, prompt: str, file_contents: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        """Retrieves cached response if prompt matches, files are unchanged, and TTL has not expired."""
        key = self._generate_key(prompt)
        entry = self._cache.get(key)
        if not entry:
            return None

        # Check TTL
        if time.time() > entry["expires_at"]:
            del self._cache[key]
            return None

        # Check if underlying files changed
        if file_contents:
            current_hashes = {p: hashlib.sha256(c.encode()).hexdigest() for p, c in file_contents.items()}
            if current_hashes != entry.get("file_hashes", {}):
                logger.info(f"Cache invalidated for prompt due to file content change.")
                del self._cache[key]
                return None

        logger.info(f"Semantic Cache Hit for prompt: {prompt[:40]}")
        return entry["response"]

    def put(
        self,
        prompt: str,
        response: Dict[str, Any],
        file_contents: Optional[Dict[str, str]] = None,
        ttl_seconds: Optional[float] = None,
    ):
        """Stores response in cache."""
        key = self._generate_key(prompt)
        file_hashes = (
            {p: hashlib.sha256(c.encode()).hexdigest() for p, c in file_contents.items()}
            if file_contents
            else {}
        )
        ttl = ttl_seconds or self.default_ttl
        self._cache[key] = {
            "prompt": prompt,
            "response": response,
            "created_at": time.time(),
            "expires_at": time.time() + ttl,
            "file_hashes": file_hashes,
        }

    def invalidate(self, prompt: str):
        key = self._generate_key(prompt)
        self._cache.pop(key, None)

    def clear(self):
        self._cache.clear()

    def _generate_key(self, prompt: str) -> str:
        norm = prompt.strip().lower()
        return hashlib.sha256(norm.encode()).hexdigest()
