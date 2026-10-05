# actions/focus_timer.py
"""
Focus Mode / Pomodoro Timer — Charlie manages work sessions, announces breaks,
tracks productivity, and encourages the user professionally.

Commands:
  "Start focus mode"
  "Start 45 minute focus session"
  "How much time is left?"
  "Take a break"
  "End focus mode"
  "Show today's productivity"
  "Start Pomodoro"

Uses asyncio-compatible background alerting via a state file + polling.
"""

from __future__ import annotations
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

TOOL = {
    "name": "focus_timer",
    "description": (
        "Pomodoro / focus mode timer. Manages work sessions and breaks. "
        "Announces when to take a break and when to resume. "
        "Tracks total focus time per day. Encourages productivity. "
        "Trigger on: 'focus mode', 'pomodoro', 'start timer', 'work session', "
        "'how much time left', 'take a break', 'productivity stats', 'end focus'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "status", "pause", "resume", "stop", "break", "stats", "check"],
                "description": "start=begin session, status=remaining time, pause/resume=pause/unpause, stop=end, break=take a break, stats=today's productivity, check=check if break is due"
            },
            "duration_minutes": {"type": "integer", "description": "Focus session length in minutes (default 25 for Pomodoro, 0 for custom)"},
            "break_minutes": {"type": "integer", "description": "Break duration in minutes (default 5)"},
            "task_name": {"type": "string", "description": "What are you working on (optional)"},
            "mode": {"type": "string", "enum": ["pomodoro", "deep_work", "custom"], "description": "pomodoro=25/5 cycle, deep_work=90min/20min, custom=user-defined"}
        },
        "required": ["action"],
    },
}

from core.app_paths import get_config_dir

_STATE_FILE = get_config_dir() / "focus_state.json"
_LOG_FILE   = get_config_dir() / "focus_log.json"

_MODES = {
    "pomodoro":  {"work": 25, "break": 5,  "long_break": 15, "cycles_before_long": 4},
    "deep_work": {"work": 90, "break": 20, "long_break": 30, "cycles_before_long": 2},
    "custom":    {"work": 25, "break": 5,  "long_break": 15, "cycles_before_long": 4},
}


def _load_state() -> Optional[dict]:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _save_state(state: dict) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _clear_state() -> None:
    _STATE_FILE.unlink(missing_ok=True)


def _log_session(task: str, duration_min: int) -> None:
    """Append completed session to daily log."""
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        log = []
        if _LOG_FILE.exists():
            log = json.loads(_LOG_FILE.read_text(encoding="utf-8"))
        log.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "task": task,
            "minutes": duration_min,
            "time": datetime.now().strftime("%H:%M"),
        })
        _LOG_FILE.write_text(json.dumps(log, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_log() -> list:
    try:
        if _LOG_FILE.exists():
            return json.loads(_LOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _fmt_remaining(seconds: float) -> str:
    if seconds <= 0:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def run(args: Dict[str, Any]) -> str:
    action          = args.get("action", "status")
    duration_min    = args.get("duration_minutes", 0)
    break_min       = args.get("break_minutes", 0)
    task_name       = args.get("task_name", "").strip() or "Deep Work"
    mode            = args.get("mode", "pomodoro")

    # ── START ──────────────────────────────────────────────────────────────────
    if action == "start":
        cfg = _MODES.get(mode, _MODES["pomodoro"]).copy()
        if duration_min > 0:
            cfg["work"] = duration_min
        if break_min > 0:
            cfg["break"] = break_min

        now = time.monotonic()
        end = now + cfg["work"] * 60
        state = {
            "mode":         mode,
            "task":         task_name,
            "work_min":     cfg["work"],
            "break_min":    cfg["break"],
            "started":      time.time(),
            "end_epoch":    time.time() + cfg["work"] * 60,
            "cycle":        1,
            "phase":        "work",
            "paused":       False,
            "pause_start":  None,
            "total_pause":  0.0,
        }
        _save_state(state)

        tips = {
            "pomodoro":  "25 min focused work + 5 min break. Phone down, notifications off!",
            "deep_work": "90 min deep session. No interruptions — maximum flow state.",
            "custom":    f"{cfg['work']} min session. Stay in the zone!",
        }.get(mode, "")

        return (
            f"🎯 **Focus Mode — {mode.replace('_',' ').title()} Started!**\n\n"
            f"**Task:** {task_name}\n"
            f"**Duration:** {cfg['work']} minutes\n"
            f"**Break:** {cfg['break']} minutes after\n\n"
            f"💡 {tips}\n\n"
            f"I'll alert you when it's time for a break. **Let's go, you've got this! 💪**"
        )

    # ── STATUS ─────────────────────────────────────────────────────────────────
    if action in ("status", "check"):
        state = _load_state()
        if not state:
            return "No active focus session. Say 'start focus mode' to begin."

        now       = time.time()
        total_pause = state.get("total_pause", 0.0)
        if state.get("paused") and state.get("pause_start"):
            total_pause += now - state["pause_start"]

        end_epoch  = state["end_epoch"] + total_pause
        remaining  = end_epoch - now
        phase      = state["phase"]
        elapsed    = (now - state["started"] - total_pause)
        elapsed_m  = max(0, int(elapsed / 60))

        if remaining <= 0:
            # Session/break over
            if phase == "work":
                _log_session(state["task"], state["work_min"])
                state["phase"]    = "break"
                state["end_epoch"] = time.time() + state["break_min"] * 60
                state["total_pause"] = 0.0
                _save_state(state)
                return (
                    f"⏰ **Focus session complete! Excellent work on '{state['task']}'!**\n\n"
                    f"You worked for {state['work_min']} minutes. Now take a {state['break_min']}-minute break.\n"
                    f"**Stretch, hydrate, rest your eyes. You've earned it! 🎉**"
                )
            else:
                _clear_state()
                return (
                    f"☕ **Break over! Time to get back to it.**\n\n"
                    f"Say **'start focus mode'** to begin the next session. You're doing great!"
                )

        remaining_str = _fmt_remaining(remaining)
        encouragements = [
            "You're doing great, stay focused! 💪",
            "In the zone — keep going! 🔥",
            "Almost there — stay strong! ⚡",
            "Focused and productive! ✨",
        ]
        enc = encouragements[min(elapsed_m // 5, len(encouragements) - 1)]

        return (
            f"{'🎯 FOCUS' if phase == 'work' else '☕ BREAK'} | **{state['task']}**\n\n"
            f"⏱ **Time remaining:** {remaining_str}\n"
            f"📊 **Time elapsed:** {elapsed_m} min\n"
            f"🔢 **Cycle:** {state['cycle']}\n\n"
            f"{enc}"
        )

    # ── PAUSE / RESUME ─────────────────────────────────────────────────────────
    if action == "pause":
        state = _load_state()
        if not state:
            return "No active focus session."
        if state.get("paused"):
            return "Session is already paused. Say 'resume focus' to continue."
        state["paused"]     = True
        state["pause_start"] = time.time()
        _save_state(state)
        return "⏸ Focus session paused. Say **'resume focus'** when you're ready to continue."

    if action == "resume":
        state = _load_state()
        if not state:
            return "No focus session to resume."
        if not state.get("paused"):
            return "Session is not paused."
        paused_for = time.time() - (state.get("pause_start") or time.time())
        state["total_pause"] = state.get("total_pause", 0.0) + paused_for
        state["paused"]       = False
        state["pause_start"]  = None
        _save_state(state)
        remaining = state["end_epoch"] + state["total_pause"] - time.time()
        return f"▶️ Resumed! **{_fmt_remaining(remaining)}** remaining. Let's go! 💪"

    # ── BREAK ─────────────────────────────────────────────────────────────────
    if action == "break":
        state = _load_state()
        break_dur = break_min or (state.get("break_min", 5) if state else 5)
        if state:
            elapsed = (time.time() - state["started"]) / 60
            _log_session(state["task"], int(elapsed))
        state_new = {
            **(state or {}),
            "phase":     "break",
            "end_epoch": time.time() + break_dur * 60,
            "started":   time.time(),
            "total_pause": 0.0,
        }
        _save_state(state_new)
        return (
            f"☕ **Break started — {break_dur} minutes.**\n\n"
            f"Step away, stretch, drink some water. I'll let you know when it's time to resume!"
        )

    # ── STOP ──────────────────────────────────────────────────────────────────
    if action == "stop":
        state = _load_state()
        if not state:
            return "No active focus session."
        elapsed = max(0, int((time.time() - state["started"]) / 60))
        _log_session(state["task"], elapsed)
        _clear_state()
        return (
            f"⏹ Focus session stopped. Ended after **{elapsed} minutes** on **{state['task']}**.\n\n"
            f"Great effort! Your time has been logged. 📊"
        )

    # ── STATS ─────────────────────────────────────────────────────────────────
    if action == "stats":
        log = _load_log()
        if not log:
            return "No focus sessions logged yet. Start your first session with 'start focus mode'!"

        today       = datetime.now().strftime("%Y-%m-%d")
        today_log   = [e for e in log if e.get("date") == today]
        total_min   = sum(e.get("minutes", 0) for e in today_log)
        total_h, m  = divmod(total_min, 60)
        sessions    = len(today_log)

        tasks = {}
        for e in today_log:
            t = e.get("task", "Unknown")
            tasks[t] = tasks.get(t, 0) + e.get("minutes", 0)
        task_lines = "\n".join(f"  • {t}: {m} min" for t, m in sorted(tasks.items(), key=lambda x: -x[1]))

        return (
            f"📊 **Today's Productivity — {datetime.now().strftime('%A %d %B')}**\n\n"
            f"⏱ **Total focused time:** {total_h}h {m}min\n"
            f"🔢 **Sessions completed:** {sessions}\n\n"
            f"**Tasks:**\n{task_lines or '  No tasks logged'}\n\n"
            f"{'🔥 Incredible focus day!' if total_min > 120 else '💪 Good work — keep it up!'}"
        )

    return "Unknown focus action. Say 'start focus mode', 'how much time left', or 'end focus'."


def execute(**kwargs) -> Any:
    return run(kwargs)

