"""
licensing_server/middleware/token_blacklist.py — In-memory JWT token blacklist for server-side logout.

Provides instant token revocation without database round-trips.
Tokens are evicted automatically once they expire (TTL-based cleanup).

Production note: replace with Redis SETEX for multi-worker deployments.
"""

from __future__ import annotations

import threading
import time
from typing import Dict


class TokenBlacklist:
    """
    Thread-safe in-memory token blacklist using JTI (JWT ID) or raw token hash.
    Expired entries are cleaned up lazily and periodically.
    """

    def __init__(self, cleanup_interval_seconds: int = 300) -> None:
        # key: jti or token_hash  ->  value: expiry unix timestamp
        self._store: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._cleanup_interval = cleanup_interval_seconds
        self._last_cleanup = time.monotonic()

    def revoke(self, token_key: str, expires_at: float) -> None:
        """
        Add token to blacklist until expires_at (unix timestamp).
        expires_at is when the JWT naturally expires — no need to store longer.
        """
        with self._lock:
            self._store[token_key] = expires_at
            self._maybe_cleanup()

    def is_revoked(self, token_key: str) -> bool:
        """Return True if token is blacklisted AND not yet expired."""
        with self._lock:
            exp = self._store.get(token_key)
            if exp is None:
                return False
            if time.time() > exp:
                # Already expired — safe to remove, not revoked in meaningful sense
                del self._store[token_key]
                return False
            return True

    def _maybe_cleanup(self) -> None:
        """Purge expired entries if cleanup interval has elapsed."""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        current_time = time.time()
        expired_keys = [k for k, exp in self._store.items() if exp <= current_time]
        for k in expired_keys:
            del self._store[k]

    def count(self) -> int:
        """Active (non-expired) revoked token count — for admin/health display."""
        current_time = time.time()
        with self._lock:
            return sum(1 for exp in self._store.values() if exp > current_time)


# Singleton instance shared across request handlers
token_blacklist = TokenBlacklist()


def revoke_token(jti_or_hash: str, expires_at: float) -> None:
    """Convenience wrapper — revoke a token by its JTI or hash."""
    token_blacklist.revoke(jti_or_hash, expires_at)


def is_token_revoked(jti_or_hash: str) -> bool:
    """Convenience wrapper — check if token is revoked."""
    return token_blacklist.is_revoked(jti_or_hash)
