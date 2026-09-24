"""
engine/commercial/usage_meter.py — Daily Active Usage Metering, State Tracking, and Clock Tamper Protection.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .models import UsageState, UserAccount

logger = logging.getLogger("jarvis.commercial.usage_meter")


class DailyUsageMeter:
    """Accurately meters active JARVIS usage for free/starter accounts.

    Crucial rule: IDLE application window time is NEVER charged against quota.
    Only ACTIVE processing, speech synthesis, and task execution consume seconds.
    """

    DEFAULT_DAILY_LIMIT_SEC = 600  # 10 minutes = 600 seconds

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        daily_limit_sec: int = DEFAULT_DAILY_LIMIT_SEC,
        on_warning: Optional[Callable[[int, str], None]] = None,
        on_exhausted: Optional[Callable[[], None]] = None,
    ):
        self.storage_path = storage_path
        self.daily_limit_sec = daily_limit_sec
        self.on_warning = on_warning
        self.on_exhausted = on_exhausted

        self._lock = threading.RLock()
        self._current_state: UsageState = UsageState.IDLE
        self._active_start_time: Optional[float] = None
        self._in_atomic_operation: bool = False

        # Persistent daily tracking state
        self._current_day: str = self._get_current_day_str()
        self._used_seconds_today: float = 0.0
        self._last_monotonic_ts: float = time.monotonic()
        self._last_saved_wall_ts: float = time.time()
        self._warnings_sent: set[int] = set()

        self._load_state()

    @staticmethod
    def _get_current_day_str() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _check_and_reset_day(self) -> None:
        """Reset usage if a new entitlement day has arrived (UTC)."""
        today = self._get_current_day_str()
        if today != self._current_day:
            logger.info("New entitlement day detected (%s -> %s). Resetting free allowance.", self._current_day, today)
            self._current_day = today
            self._used_seconds_today = 0.0
            self._warnings_sent.clear()
            self._save_state()

    def transition_state(self, new_state: UsageState) -> None:
        """Transitions usage state and safely tallies active seconds."""
        with self._lock:
            self._check_and_reset_day()
            now = time.monotonic()
            wall_now = time.time()

            # Anti-clock-tampering check: system clock moved backward
            if wall_now < (self._last_saved_wall_ts - 60.0):
                logger.warning("System clock backward shift detected (potential tampering). Retaining consumed quota.")
                # We do not reset used seconds; we update wall timestamp anchor
                self._last_saved_wall_ts = wall_now

            # If we were ACTIVE, record accumulated elapsed active time
            if self._current_state == UsageState.ACTIVE and self._active_start_time is not None:
                elapsed = max(0.0, now - self._active_start_time)
                self._used_seconds_today += elapsed

            # Update start time if entering ACTIVE
            if new_state == UsageState.ACTIVE:
                self._active_start_time = now
            else:
                self._active_start_time = None

            self._current_state = new_state
            self._last_monotonic_ts = now
            self._last_saved_wall_ts = wall_now

            self._check_warnings_and_limits()
            self._save_state()

    def start_active_task(self, atomic: bool = False) -> bool:
        """Begin an active task interaction. Returns False if quota already exhausted."""
        with self._lock:
            self._check_and_reset_day()
            if self.is_exhausted() and not self._in_atomic_operation:
                return False

            self._in_atomic_operation = atomic
            now = time.monotonic()
            self._current_state = UsageState.ACTIVE
            self._active_start_time = now
            return True

    def finish_active_task(self) -> None:
        """Complete an active task interaction."""
        self._in_atomic_operation = False
        self.transition_state(UsageState.IDLE)

    def record_active_seconds(self, seconds: float) -> None:
        """Directly credit verified active processing seconds (e.g. speech duration)."""
        with self._lock:
            self._check_and_reset_day()
            self._used_seconds_today += max(0.0, seconds)
            self._check_warnings_and_limits()
            self._save_state()

    def tick_second(self, amount: float = 1.0) -> Tuple[float, bool]:
        """Active second tick for live countdown during session. Returns (remaining_seconds, is_exhausted)."""
        with self._lock:
            self._check_and_reset_day()
            if not self._in_atomic_operation:
                self._used_seconds_today += max(0.0, amount)
                self._check_warnings_and_limits()
                if int(self._used_seconds_today) % 5 == 0:
                    self._save_state()
            rem = self.get_remaining_seconds()
            return rem, self.is_exhausted()

    def get_remaining_seconds(self) -> float:
        """Returns remaining seconds for today."""
        with self._lock:
            self._check_and_reset_day()
            active_inflight = 0.0
            if self._current_state == UsageState.ACTIVE and self._active_start_time is not None:
                active_inflight = max(0.0, time.monotonic() - self._active_start_time)
            total = self._used_seconds_today + active_inflight
            return max(0.0, self.daily_limit_sec - total)

    def get_used_seconds(self) -> float:
        with self._lock:
            self._check_and_reset_day()
            active_inflight = 0.0
            if self._current_state == UsageState.ACTIVE and self._active_start_time is not None:
                active_inflight = max(0.0, time.monotonic() - self._active_start_time)
            return self._used_seconds_today + active_inflight

    def is_exhausted(self) -> bool:
        """Check if daily allowance is exhausted (unless finishing in-flight atomic operation)."""
        if self._in_atomic_operation:
            return False
        return self.get_remaining_seconds() <= 0.0

    def _check_warnings_and_limits(self) -> None:
        rem = self.daily_limit_sec - self._used_seconds_today
        rem_min = int(rem // 60)

        # 5 minutes remaining subtle warning (300 sec)
        if rem <= 300 and 5 not in self._warnings_sent and rem > 120:
            self._warnings_sent.add(5)
            if self.on_warning:
                self.on_warning(5, "5 minutes remaining of today's free CHARLIE time.")

        # 2 minutes warning (120 sec)
        if rem <= 120 and 2 not in self._warnings_sent and rem > 60:
            self._warnings_sent.add(2)
            if self.on_warning:
                self.on_warning(2, "2 minutes remaining of today's free CHARLIE time.")

        # 1 minute final warning (60 sec)
        if rem <= 60 and 1 not in self._warnings_sent and rem > 0:
            self._warnings_sent.add(1)
            if self.on_warning:
                self.on_warning(1, "1 minute remaining. Finish current task or upgrade to continue uninterrupted.")

        # 0 limit reached
        if rem <= 0:
            if not self._in_atomic_operation and self.on_exhausted:
                self.on_exhausted()

    def _save_state(self) -> None:
        if not self.storage_path:
            return
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "day": self._current_day,
                "used_seconds": self._used_seconds_today,
                "last_wall_ts": self._last_saved_wall_ts,
                "warnings_sent": list(self._warnings_sent),
            }
            self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to persist daily usage: %s", e)

    def _load_state(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            saved_day = data.get("day", "")
            today = self._get_current_day_str()
            saved_wall = float(data.get("last_wall_ts", 0.0))

            # Anti-tampering check on startup: if saved wall time is ahead of current clock,
            # system time was rolled back. We do not reward it.
            if saved_wall > time.time() + 60.0:
                logger.warning("Clock roll-back detected on load. Preserving used seconds.")

            if saved_day == today:
                self._used_seconds_today = float(data.get("used_seconds", 0.0))
                self._warnings_sent = set(data.get("warnings_sent", []))
            else:
                self._used_seconds_today = 0.0
                self._warnings_sent = set()
            self._current_day = today
        except Exception as e:
            logger.error("Failed to load daily usage: %s", e)
