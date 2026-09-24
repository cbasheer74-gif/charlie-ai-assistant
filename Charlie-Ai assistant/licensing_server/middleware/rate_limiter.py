"""
licensing_server/middleware/rate_limiter.py — Simple in-memory rate limiting for login, activation, and transfer endpoints.

Production: replace with Redis-backed limiter (slowapi/limits).
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List

from fastapi import HTTPException, Request, status

from licensing_server.config import config


class RateLimiter:
    """Token-bucket rate limiter keyed by IP address."""

    def __init__(self):
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> None:
        """Raises 429 if rate limit exceeded."""
        now = time.time()
        cutoff = now - window_seconds

        # Clean old entries
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]

        if len(self._requests[key]) >= max_requests:
            import json
            import logging
            from datetime import datetime, timezone
            sec_logger = logging.getLogger("licensing_server.security")
            sec_logger.warning(
                json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "WARN",
                    "service": "jarvis-licensing-security",
                    "event": "RATE_LIMIT_EXCEEDED",
                    "key": key,
                    "max_requests": max_requests,
                    "window_seconds": window_seconds,
                })
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds}s.",
            )

        self._requests[key].append(now)


# Singleton
rate_limiter = RateLimiter()


def limit_login(request: Request) -> None:
    """Rate limit login attempts by IP."""
    ip = request.client.host if request.client else "unknown"
    rate_limiter.check(f"login:{ip}", config.LOGIN_RATE_LIMIT, window_seconds=60)


def limit_activation(request: Request) -> None:
    """Rate limit device activation by IP."""
    ip = request.client.host if request.client else "unknown"
    rate_limiter.check(f"activation:{ip}", config.ACTIVATION_RATE_LIMIT, window_seconds=60)


def limit_transfer(request: Request) -> None:
    """Rate limit license transfers by IP."""
    ip = request.client.host if request.client else "unknown"
    rate_limiter.check(f"transfer:{ip}", config.TRANSFER_RATE_LIMIT, window_seconds=3600)
