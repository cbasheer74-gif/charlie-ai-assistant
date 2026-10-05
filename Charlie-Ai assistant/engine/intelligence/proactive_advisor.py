# engine/intelligence/proactive_advisor.py
"""
Predictive Proactive Assistant & Background Context Daemon for Charlie.

Continuously observes system state, calendar, tasks, work habits, and environment
to formulate non-intrusive, timely, and actionable recommendations.

Nudge Categories:
  - CRITICAL        : Battery dying, critical RAM/CPU load, disk space.
  - EFFICIENCY      : Cluttered desktop, runaway processes, unhandled inbox items.
  - HEALTH_WELLNESS : Long uninterrupted work blocks, hydration, late night strain.
  - OPPORTUNITY     : Unfinished tasks from personal hub, upcoming events, morning briefing.

Rate-limited per category to prevent notification fatigue.
"""

from __future__ import annotations

import json
import os
import platform
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ProactiveNudge:
    category: str  # CRITICAL, EFFICIENCY, HEALTH_WELLNESS, OPPORTUNITY
    title: str
    message: str
    suggested_action: str
    action_tool: Optional[str] = None
    created_at: float = 0.0


def _config_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config"


_SETTINGS_FILE = _config_dir() / "proactive_settings.json"
_HISTORY_FILE = _config_dir() / "proactive_history.json"
_LAST_STATE_FILE = _config_dir() / "proactive_advisory.json"

_DEFAULT_SETTINGS = {
    "enabled": True,
    "check_battery": True,
    "check_resources": True,
    "check_tasks": True,
    "check_briefing": True,
    "check_wellness": True,
    "check_clutter": True,
    "voice_alerts": False,
    "poll_interval_sec": 30,
}


def load_proactive_settings() -> Dict[str, Any]:
    try:
        if _SETTINGS_FILE.exists():
            data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            merged = dict(_DEFAULT_SETTINGS)
            merged.update(data)
            return merged
    except Exception:
        pass
    return dict(_DEFAULT_SETTINGS)


def save_proactive_settings(settings: Dict[str, Any]) -> None:
    try:
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


class ProactiveAdvisor:
    """Evaluates context heuristics and issues proactive advisory interventions."""

    COOLDOWNS = {
        "CRITICAL": 300.0,         # 5 minutes
        "EFFICIENCY": 1800.0,       # 30 minutes
        "HEALTH_WELLNESS": 3600.0,  # 60 minutes
        "OPPORTUNITY": 2400.0,      # 40 minutes
    }

    def __init__(self):
        self._last_nudge_time: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._session_start = time.monotonic()
        self._last_briefing_date: str = ""
        self._recent_nudges: List[ProactiveNudge] = []
        self._load_history()

    def _load_history(self):
        try:
            if _HISTORY_FILE.exists():
                items = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
                for it in items[-10:]:
                    self._recent_nudges.append(ProactiveNudge(**it))
        except Exception:
            pass

    def _save_history(self, nudge: ProactiveNudge):
        try:
            self._recent_nudges.append(nudge)
            if len(self._recent_nudges) > 20:
                self._recent_nudges = self._recent_nudges[-20:]
            _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            _HISTORY_FILE.write_text(
                json.dumps([asdict(n) for n in self._recent_nudges], indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def get_recent_nudges(self) -> List[ProactiveNudge]:
        with self._lock:
            return list(self._recent_nudges)

    def evaluate_all(self, context: Optional[Dict[str, Any]] = None) -> Optional[ProactiveNudge]:
        """Runs all contextual heuristics and returns the highest priority pending nudge, if any."""
        settings = load_proactive_settings()
        if not settings.get("enabled", True):
            return None

        with self._lock:
            now = time.monotonic()

            # 1. Critical Battery Check
            if settings.get("check_battery", True):
                batt_nudge = self._check_battery(now)
                if batt_nudge:
                    return self._dispatch(batt_nudge)

            # 2. Critical Resource Spikes (CPU / RAM > 92%)
            if settings.get("check_resources", True):
                res_nudge = self._check_system_resources(now)
                if res_nudge:
                    return self._dispatch(res_nudge)

            # 3. Morning Executive Briefing
            if settings.get("check_briefing", True):
                brief_nudge = self._check_morning_briefing(now)
                if brief_nudge:
                    return self._dispatch(brief_nudge)

            # 4. Personal Hub Task Deadlines & Reminders
            if settings.get("check_tasks", True):
                task_nudge = self._check_tasks_deadlines(now)
                if task_nudge:
                    return self._dispatch(task_nudge)

            # 5. Health & Wellness Check (Continuous Session Duration)
            if settings.get("check_wellness", True):
                wellness_nudge = self._check_work_duration(now)
                if wellness_nudge:
                    return self._dispatch(wellness_nudge)

            # 6. Efficiency Check (Cluttered Workspace)
            if settings.get("check_clutter", True):
                clutter_nudge = self._check_desktop_clutter(now)
                if clutter_nudge:
                    return self._dispatch(clutter_nudge)

            # 7. Opportunity Check (Late Night / Wrap Up)
            wrapup_nudge = self._check_evening_wrapup(now)
            if wrapup_nudge:
                return self._dispatch(wrapup_nudge)

            return None

    def _check_battery(self, now: float) -> Optional[ProactiveNudge]:
        if not self._can_fire("CRITICAL", now):
            return None
        try:
            import psutil
            batt = psutil.sensors_battery()
            if batt and not batt.power_plugged and batt.percent <= 20:
                return ProactiveNudge(
                    category="CRITICAL",
                    title="Low Battery Warning",
                    message=f"Laptop battery is down to {int(batt.percent)}% on discharge. Charlie recommends plugging in power.",
                    suggested_action="Connect power adapter",
                    action_tool="system_monitor",
                    created_at=time.time(),
                )
        except Exception:
            pass
        return None

    def _check_system_resources(self, now: float) -> Optional[ProactiveNudge]:
        if not self._can_fire("CRITICAL", now):
            return None
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            if cpu >= 94 or mem >= 92:
                top_proc = "a background task"
                try:
                    procs = sorted(
                        [p for p in psutil.process_iter(['name', 'cpu_percent']) if p.info['name']],
                        key=lambda x: x.info.get('cpu_percent', 0),
                        reverse=True,
                    )
                    if procs:
                        top_proc = procs[0].info['name']
                except Exception:
                    pass

                return ProactiveNudge(
                    category="CRITICAL",
                    title="High System Load Alert",
                    message=f"System usage elevated: CPU {int(cpu)}%, RAM {int(mem)}% (top process: {top_proc}).",
                    suggested_action="Inspect system processes",
                    action_tool="system_monitor",
                    created_at=time.time(),
                )
        except Exception:
            pass
        return None

    def _check_morning_briefing(self, now: float) -> Optional[ProactiveNudge]:
        if not self._can_fire("OPPORTUNITY", now):
            return None
        now_dt = datetime.now()
        today_str = now_dt.strftime("%Y-%m-%d")
        # Trigger between 8:00 AM and 11:00 AM once per day
        if 8 <= now_dt.hour <= 11 and self._last_briefing_date != today_str:
            self._last_briefing_date = today_str
            return ProactiveNudge(
                category="OPPORTUNITY",
                title="Morning Executive Briefing",
                message="Good morning! Your executive briefing with today's priorities and schedule is ready.",
                suggested_action="Listen to morning briefing",
                action_tool="daily_briefing",
                created_at=time.time(),
            )
        return None

    def _check_tasks_deadlines(self, now: float) -> Optional[ProactiveNudge]:
        if not self._can_fire("OPPORTUNITY", now):
            return None
        try:
            from memory.personal_hub import load_hub
            hub = load_hub()
            tasks = hub.get("tasks", [])
            for t in tasks:
                if t.get("status") in ("pending", "open", "in_progress") and t.get("priority") in ("high", "urgent"):
                    return ProactiveNudge(
                        category="OPPORTUNITY",
                        title="Priority Task Pending",
                        message=f"Reminder for urgent item: '{t['title']}'. Would you like assistance tackling this?",
                        suggested_action="Review pending tasks",
                        action_tool="tasks",
                        created_at=time.time(),
                    )
        except Exception:
            pass
        return None

    def _check_work_duration(self, now: float) -> Optional[ProactiveNudge]:
        if not self._can_fire("HEALTH_WELLNESS", now):
            return None
        elapsed_min = (now - self._session_start) / 60.0
        if elapsed_min >= 90.0:
            self._session_start = now  # Reset session block
            return ProactiveNudge(
                category="HEALTH_WELLNESS",
                title="Continuous Focus Advisory",
                message="You have been actively working for 90 minutes. A quick 5-minute hydration break will refresh your mind.",
                suggested_action="Take a 5-minute break",
                action_tool="focus_timer",
                created_at=time.time(),
            )
        return None

    def _check_desktop_clutter(self, now: float) -> Optional[ProactiveNudge]:
        if not self._can_fire("EFFICIENCY", now):
            return None
        try:
            desktop = Path.home() / "Desktop"
            if desktop.exists():
                loose_files = [f for f in desktop.iterdir() if f.is_file() and not f.name.startswith(".")]
                if len(loose_files) >= 15:
                    return ProactiveNudge(
                        category="EFFICIENCY",
                        title="Desktop Tidy Suggestion",
                        message=f"There are {len(loose_files)} loose files cluttering your desktop. Would you like Charlie to organize them into neat category folders?",
                        suggested_action="Organize desktop files",
                        action_tool="file_organizer",
                        created_at=time.time(),
                    )
        except Exception:
            pass
        return None

    def _check_evening_wrapup(self, now: float) -> Optional[ProactiveNudge]:
        if not self._can_fire("OPPORTUNITY", now):
            return None
        current_hour = datetime.now().hour
        if current_hour >= 20:  # 8 PM or later
            return ProactiveNudge(
                category="OPPORTUNITY",
                title="End-of-Day Wrap-Up",
                message="Evening approaches. Would you like a quick review of today's achievements and open tasks?",
                suggested_action="Run evening debrief",
                action_tool="routine_briefing",
                created_at=time.time(),
            )
        return None

    def _can_fire(self, category: str, now: float) -> bool:
        last = self._last_nudge_time.get(category, 0.0)
        cooldown = self.COOLDOWNS.get(category, 1800.0)
        return (now - last) >= cooldown

    def _dispatch(self, nudge: ProactiveNudge) -> ProactiveNudge:
        now = time.monotonic()
        self._last_nudge_time[nudge.category] = now
        try:
            _LAST_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _LAST_STATE_FILE.write_text(json.dumps(asdict(nudge), indent=2), encoding="utf-8")
        except Exception:
            pass
        self._save_history(nudge)
        return nudge


class ProactiveDaemon:
    """Thread-safe background daemon that polls proactive advisor and notifies UI."""

    def __init__(self, advisor: Optional[ProactiveAdvisor] = None, on_nudge: Optional[Callable[[ProactiveNudge], None]] = None):
        self.advisor = advisor or get_proactive_advisor()
        self.on_nudge = on_nudge
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return True
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._worker_loop, name="CharlieProactiveDaemon", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def is_running(self) -> bool:
        return self._running

    def run_once(self) -> Optional[ProactiveNudge]:
        nudge = self.advisor.evaluate_all()
        if nudge and callable(self.on_nudge):
            try:
                self.on_nudge(nudge)
            except Exception as e:
                print(f"[ProactiveDaemon] on_nudge callback error: {e}")
        return nudge

    def _worker_loop(self):
        # Initial settle pause before starting checks
        self._stop_event.wait(8.0)
        while self._running and not self._stop_event.is_set():
            settings = load_proactive_settings()
            poll_interval = max(10, int(settings.get("poll_interval_sec", 30)))
            if settings.get("enabled", True):
                try:
                    self.run_once()
                except Exception as e:
                    print(f"[ProactiveDaemon] loop exception: {e}")

            if self._stop_event.wait(poll_interval):
                break

    def get_status(self) -> Dict[str, Any]:
        settings = load_proactive_settings()
        recent = self.advisor.get_recent_nudges()
        return {
            "running": self._running,
            "settings": settings,
            "recent_nudge_count": len(recent),
            "last_nudge": asdict(recent[-1]) if recent else None,
        }


# Global singletons
_advisor_instance: Optional[ProactiveAdvisor] = None
_daemon_instance: Optional[ProactiveDaemon] = None
_adv_lock = threading.RLock()


def get_proactive_advisor() -> ProactiveAdvisor:
    global _advisor_instance
    with _adv_lock:
        if _advisor_instance is None:
            _advisor_instance = ProactiveAdvisor()
        return _advisor_instance


def get_proactive_daemon() -> ProactiveDaemon:
    global _daemon_instance
    advisor = get_proactive_advisor()
    with _adv_lock:
        if _daemon_instance is None:
            _daemon_instance = ProactiveDaemon(advisor=advisor)
        return _daemon_instance
