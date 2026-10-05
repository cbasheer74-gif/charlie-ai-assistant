"""
licensing_server/middleware/rate_limiter.py — Multi-layer in-memory rate limiter.

Layers:
  1. IP-based sliding window  — blocks spray attacks.
  2. Email-keyed lockout     — tracks per-account failures, locks after threshold.
  3. Lockout escalation      — 5 min base, doubles per extra strike.
  4. Retry-After header      — RFC 6585 compliant response.
  5. Structured security log — JSON audit trail for every block event.

Production note: replace _requests/_lockouts dicts with Redis for multi-worker deployment.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, Request, status

from licensing_server.config import config

sec_logger = logging.getLogger("licensing_server.security")

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Login IP limits
LOGIN_IP_MAX = int(config.LOGIN_RATE_LIMIT)   # default 10
LOGIN_IP_WINDOW = 60                           # seconds

# Per-email account lockout (brute-force protection)
LOGIN_EMAIL_FAIL_MAX = 5                       # failures before lockout
LOGIN_LOCKOUT_BASE_SECONDS = 300              # 5 minutes base lockout
LOGIN_LOCKOUT_MAX_SECONDS = 86400             # cap at 24 hours

# Admin login limits (tighter)
ADMIN_IP_MAX = 5
ADMIN_IP_WINDOW = 60


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_ip(request: Request) -> str:
    """Extract real client IP, respecting trusted reverse-proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _log_block(event: str, key: str, detail: str, retry_after: int = 0) -> None:
    from datetime import datetime, timezone
    sec_logger.warning(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "WARN",
        "service": "charlie-licensing-security",
        "event": event,
        "key": key,
        "detail": detail,
        "retry_after_seconds": retry_after,
    }))


def _raise_rate_limit(max_req: int, window: int, retry_after: Optional[int] = None) -> None:
    secs = retry_after if retry_after is not None else window
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Rate limit exceeded. Max {max_req} attempts per {window}s. Retry after {secs}s.",
        headers={"Retry-After": str(secs)},
    )


def _raise_lockout(email: str, unlock_in: int) -> None:
    mins = unlock_in // 60
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Account temporarily locked due to repeated failures. Retry in {mins} minute(s).",
        headers={"Retry-After": str(unlock_in)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Core Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Sliding-window rate limiter + per-email progressive lockout tracker.
    Thread-safe for single-process use. Use Redis for multi-worker.
    """

    def __init__(self) -> None:
        self._requests: Dict[str, List[float]] = defaultdict(list)

        # email -> (fail_count, lockout_until, lockout_duration)
        self._email_fails: Dict[str, Tuple[int, float, int]] = {}

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> None:
        """Sliding-window check. Raises 429 on breach."""
        now = time.monotonic()
        cutoff = now - window_seconds
        bucket = self._requests[key]

        # Prune old timestamps
        self._requests[key] = [t for t in bucket if t > cutoff]

        if len(self._requests[key]) >= max_requests:
            _log_block("RATE_LIMIT_EXCEEDED", key, f"{len(self._requests[key])}/{max_requests} in {window_seconds}s")
            _raise_rate_limit(max_requests, window_seconds)

        self._requests[key].append(now)

    # ── Email-keyed login lockout ─────────────────────────────────────────────

    def record_login_failure(self, email: str) -> None:
        """Increment failure counter; impose progressive lockout after threshold."""
        now = time.monotonic()
        fail_count, lockout_until, prev_duration = self._email_fails.get(email, (0, 0.0, 0))

        # Reset stale state (if previous lockout fully expired)
        if lockout_until and now > lockout_until + LOGIN_LOCKOUT_BASE_SECONDS:
            fail_count = 0
            prev_duration = 0

        fail_count += 1

        if fail_count >= LOGIN_EMAIL_FAIL_MAX:
            # Escalate: double the duration each lockout cycle, capped at 24h
            new_duration = min(
                max(LOGIN_LOCKOUT_BASE_SECONDS, prev_duration * 2) if prev_duration else LOGIN_LOCKOUT_BASE_SECONDS,
                LOGIN_LOCKOUT_MAX_SECONDS,
            )
            new_lockout = now + new_duration
            self._email_fails[email] = (fail_count, new_lockout, new_duration)
            _log_block(
                "ACCOUNT_LOCKOUT",
                email,
                f"fail_count={fail_count}, locked_for={new_duration}s",
                retry_after=int(new_duration),
            )
        else:
            self._email_fails[email] = (fail_count, lockout_until, prev_duration)

    def check_email_lockout(self, email: str) -> None:
        """Raises 429 if email is currently locked out."""
        now = time.monotonic()
        if email not in self._email_fails:
            return

        fail_count, lockout_until, _ = self._email_fails[email]
        if lockout_until and now < lockout_until:
            unlock_in = int(lockout_until - now)
            _log_block("ACCOUNT_LOCKOUT_ENFORCED", email, f"blocked, unlock_in={unlock_in}s", retry_after=unlock_in)
            _raise_lockout(email, unlock_in)

    def record_login_success(self, email: str) -> None:
        """Clears lockout state on successful login."""
        if email in self._email_fails:
            del self._email_fails[email]

    def get_lockout_status(self, email: str) -> dict:
        """Returns lockout state dict for admin/debug inspection."""
        now = time.monotonic()
        if email not in self._email_fails:
            return {"locked": False, "fail_count": 0}

        fail_count, lockout_until, duration = self._email_fails[email]
        locked = lockout_until and now < lockout_until
        return {
            "locked": bool(locked),
            "fail_count": fail_count,
            "unlock_in_seconds": max(0, int(lockout_until - now)) if locked else 0,
            "lockout_duration": duration,
        }

    def get_all_active_lockouts(self) -> List[dict]:
        """Returns list of currently locked accounts with remaining duration."""
        now = time.monotonic()
        results = []
        for email, (fail_count, lockout_until, duration) in self._email_fails.items():
            if lockout_until and now < lockout_until:
                results.append({
                    "email": email,
                    "fail_count": fail_count,
                    "unlock_in_seconds": int(lockout_until - now),
                    "lockout_duration": duration,
                })
        return results

    def unlock_email(self, email: str) -> bool:
        """Admin manual unlock for email account."""
        norm = email.lower().strip()
        if norm in self._email_fails:
            del self._email_fails[norm]
            return True
        return False

    def reset_ip(self, ip: str) -> int:
        """Admin manual reset of rate-limit buckets for an IP."""
        removed = 0
        clean_ip = ip.strip()
        for prefix in ("login:", "activation:", "transfer:", "register:", "pwreset:", "crash:", "admin_login:"):
            key = f"{prefix}{clean_ip}"
            if key in self._requests:
                del self._requests[key]
                removed += 1
        return removed


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

rate_limiter = RateLimiter()


# ─────────────────────────────────────────────────────────────────────────────
# Public helper functions used by routes
# ─────────────────────────────────────────────────────────────────────────────

def limit_login(request: Request, email: Optional[str] = None) -> None:
    """
    Two-stage login rate limiting:
      1. IP sliding window (fast spray protection).
      2. Per-email lockout (brute-force account protection).
    """
    ip = _get_ip(request)
    rate_limiter.check(f"login:{ip}", LOGIN_IP_MAX, window_seconds=LOGIN_IP_WINDOW)

    if email:
        normalized = email.lower().strip()
        rate_limiter.check_email_lockout(normalized)


def record_login_success(email: str) -> None:
    """Call after a confirmed successful login to reset lockout state."""
    rate_limiter.record_login_success(email.lower().strip())


def record_login_failure(email: str) -> None:
    """Call after a confirmed failed login to increment failure counter."""
    rate_limiter.record_login_failure(email.lower().strip())


def limit_activation(request: Request) -> None:
    """Rate limit device activation by IP."""
    ip = _get_ip(request)
    rate_limiter.check(f"activation:{ip}", config.ACTIVATION_RATE_LIMIT, window_seconds=60)


def limit_transfer(request: Request) -> None:
    """Rate limit license transfers by IP."""
    ip = _get_ip(request)
    rate_limiter.check(f"transfer:{ip}", config.TRANSFER_RATE_LIMIT, window_seconds=3600)


def limit_register(request: Request) -> None:
    """Rate limit registrations by IP (max 5/min)."""
    ip = _get_ip(request)
    rate_limiter.check(f"register:{ip}", 5, window_seconds=60)


def limit_password_reset(request: Request) -> None:
    """Rate limit password reset requests by IP (max 5/min)."""
    ip = _get_ip(request)
    rate_limiter.check(f"pwreset:{ip}", 5, window_seconds=60)


def limit_crash_report(request: Request) -> None:
    """Rate limit crash reports by IP (max 20/min)."""
    ip = _get_ip(request)
    rate_limiter.check(f"crash:{ip}", 20, window_seconds=60)


def limit_admin_login(request: Request) -> None:
    """Tighter rate limit for admin panel authentication (max 5/min per IP)."""
    ip = _get_ip(request)
    rate_limiter.check(f"admin_login:{ip}", ADMIN_IP_MAX, window_seconds=ADMIN_IP_WINDOW)


def get_active_lockouts() -> List[dict]:
    """Retrieve all accounts currently under rate-limit lockout."""
    return rate_limiter.get_all_active_lockouts()


def unlock_account(email: str) -> bool:
    """Admin unlock for a locked account."""
    return rate_limiter.unlock_email(email)


def reset_ip_limits(ip: str) -> int:
    """Admin reset of all rate limits for an IP address."""
    return rate_limiter.reset_ip(ip)
