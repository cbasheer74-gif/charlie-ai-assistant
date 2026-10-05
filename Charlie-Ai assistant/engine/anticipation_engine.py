"""engine/anticipation_engine.py — Proactive Anticipation & Intent Prediction Engine.

Analyzes temporal context, historical workflows, and recent task completions to
predict the user's next logical action with confidence scoring.

Habit Learning (new):
  Every suggestion the user accepts or ignores is recorded in a local SQLite
  table. Learned transition frequencies are blended with static priors using a
  Bayesian-style weighted average so predictions improve automatically over time
  without any ML dependencies.

  Public API:
    AnticipationEngine.predict_next_actions(last_task_kind, hour, active_window_title)
        -> List[Dict]   (same shape as before -- backward-compatible)

    AnticipationEngine.record_feedback(prior_action, suggested_action, accepted)
        -> None          (call this when user taps Accept / Dismiss on a suggestion)

    HabitTracker.stats(prior_action)
        -> Dict          (debug: show raw learned counts for a given prior)
"""

from __future__ import annotations

import atexit
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("charlie.anticipation_engine")

# ---------------------------------------------------------------------------
# Static prior transition matrix  P(next | prior)  -- baseline before learning
# ---------------------------------------------------------------------------
WORKFLOW_TRANSITION_PROBABILITIES: Dict[str, List[Tuple[str, float, str]]] = {
    "coding": [
        ("audit",       0.45, "Audit recently modified code for syntax errors and edge cases"),
        ("devops",      0.30, "Build container image or generate deployment pipeline"),
        ("test_runner", 0.25, "Execute test suite to verify code changes"),
    ],
    "meeting": [
        ("export_notes",       0.50, "Export meeting action items and decision summary"),
        ("corporate_email",    0.35, "Draft executive follow-up email to stakeholders"),
        ("calendar_schedule",  0.15, "Schedule follow-up review session"),
    ],
    "database": [
        ("api_design",       0.40, "Draft API endpoints for new database schema"),
        ("sql_optimization", 0.35, "Verify execution query plan and index coverage"),
        ("db_backup",        0.25, "Generate database snapshot and backup verification"),
    ],
    "vision_scan": [
        ("ocr_transcription",  0.60, "Copy transcribed text and labels to clipboard"),
        ("web_search",         0.30, "Search technical specifications for identified object"),
        ("step_by_step_guide", 0.10, "Generate operating guide for scanned device"),
    ],
    "interview": [
        ("feedback_report", 0.65, "Export STAR interview performance scorecard"),
        ("deep_dive_review", 0.35, "Practice weaker technical topics identified in session"),
    ],
    "devops": [
        ("audit",           0.40, "Verify deployed container health and logs"),
        ("test_runner",     0.35, "Run integration test suite post-deploy"),
        ("corporate_email", 0.25, "Send deployment status update"),
    ],
    "audit": [
        ("coding",          0.50, "Fix identified issues in editor"),
        ("test_runner",     0.30, "Run tests to confirm bug is resolved"),
        ("corporate_email", 0.20, "Draft bug report for stakeholders"),
    ],
    "research": [
        ("corporate_email", 0.40, "Write summary memo of findings"),
        ("coding",          0.35, "Prototype proof-of-concept from research"),
        ("export_notes",    0.25, "Export research notes"),
    ],
}

# How much weight to give learned data vs static priors.
# alpha = 0 -> pure static, alpha = 1 -> pure learned.
# Ramps from 0 -> MAX_ALPHA as observations accumulate.
_MAX_ALPHA = 0.85
_ALPHA_RAMP_OBSERVATIONS = 20   # reach max weight after ~20 accepted suggestions


# ---------------------------------------------------------------------------
# Habit Tracker -- SQLite backend, thread-safe singleton
# ---------------------------------------------------------------------------

def _get_habit_db_path() -> Path:
    """Resolve the habit DB path alongside the main memory DB."""
    try:
        import sys
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).resolve().parent.parent
        mem_dir = base / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        return mem_dir / "habit_memory.db"
    except Exception:
        return Path("habit_memory.db")


class HabitTracker:
    """Thread-safe, SQLite-backed store for action acceptance history.

    Schema:
        habits(id, prior_action TEXT, suggested_action TEXT,
               accepted INTEGER,   -- 1=accept, 0=dismiss
               ts INTEGER)         -- unix timestamp

    All writes are idempotent-safe. DB is created on first use.
    """

    _instance: Optional["HabitTracker"] = None
    _class_lock = threading.RLock()

    def __new__(cls) -> "HabitTracker":
        with cls._class_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._db_path = _get_habit_db_path()
                inst._conn_lock = threading.RLock()
                inst._conn = None
                inst._ensure_schema()
                atexit.register(lambda: inst.close() if inst else None)
                cls._instance = inst
            return cls._instance

    # -- Internal helpers -----------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        with self._conn_lock:
            if self._conn is None:
                self._conn = sqlite3.connect(
                    str(self._db_path),
                    check_same_thread=False,
                    timeout=10,
                )
                self._conn.row_factory = sqlite3.Row
            return self._conn

    def _ensure_schema(self) -> None:
        try:
            conn = self._connect()
            with self._conn_lock:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS habits (
                        id               INTEGER PRIMARY KEY AUTOINCREMENT,
                        prior_action     TEXT    NOT NULL,
                        suggested_action TEXT    NOT NULL,
                        accepted         INTEGER NOT NULL DEFAULT 0,
                        ts               INTEGER NOT NULL
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_habit_prior ON habits(prior_action)"
                )
                conn.commit()
        except Exception as exc:
            logger.warning("HabitTracker schema error: %s", exc)

    # -- Public API -----------------------------------------------------------

    def record(self, prior_action: str, suggested_action: str, accepted: bool) -> None:
        """Persist one feedback event."""
        if not prior_action or not suggested_action:
            return
        try:
            import time
            conn = self._connect()
            with self._conn_lock:
                conn.execute(
                    "INSERT INTO habits(prior_action, suggested_action, accepted, ts) "
                    "VALUES (?, ?, ?, ?)",
                    (prior_action.lower(), suggested_action.lower(),
                     1 if accepted else 0, int(time.time())),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("HabitTracker.record error: %s", exc)

    def learned_transitions(
        self,
        prior_action: str,
        min_observations: int = 1,
    ) -> Dict[str, float]:
        """Return normalised accept-rate per suggested_action for a given prior.

        Only includes actions with >= min_observations total events.
        Returns {} if no data.
        """
        if not prior_action:
            return {}
        try:
            conn = self._connect()
            with self._conn_lock:
                rows = conn.execute(
                    """
                    SELECT suggested_action,
                           SUM(accepted)  AS accepts,
                           COUNT(*)       AS total
                    FROM   habits
                    WHERE  prior_action = ?
                    GROUP  BY suggested_action
                    HAVING COUNT(*) >= ?
                    """,
                    (prior_action.lower(), min_observations),
                ).fetchall()

            if not rows:
                return {}

            # Laplace-smoothed accept rates
            rates: Dict[str, float] = {}
            for row in rows:
                accept_rate = (row["accepts"] + 1) / (row["total"] + 2)
                rates[row["suggested_action"]] = accept_rate

            # Normalise so weights sum to 1
            total = sum(rates.values()) or 1.0
            return {k: v / total for k, v in rates.items()}

        except Exception as exc:
            logger.warning("HabitTracker.learned_transitions error: %s", exc)
            return {}

    def total_observations(self, prior_action: str) -> int:
        """Total events recorded for a given prior action."""
        try:
            conn = self._connect()
            with self._conn_lock:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM habits WHERE prior_action = ?",
                    (prior_action.lower(),),
                ).fetchone()
            return row["n"] if row else 0
        except Exception:
            return 0

    def stats(self, prior_action: str) -> Dict[str, Any]:
        """Debug helper -- returns raw counts for a given prior."""
        try:
            conn = self._connect()
            with self._conn_lock:
                rows = conn.execute(
                    """
                    SELECT suggested_action,
                           SUM(accepted) AS accepts,
                           COUNT(*)      AS total
                    FROM   habits
                    WHERE  prior_action = ?
                    GROUP  BY suggested_action
                    ORDER  BY total DESC
                    """,
                    (prior_action.lower(),),
                ).fetchall()
            return {
                "prior": prior_action,
                "transitions": [dict(r) for r in rows],
                "total_observations": sum(r["total"] for r in rows),
            }
        except Exception as exc:
            return {"error": str(exc)}

    def close(self) -> None:
        """Close SQLite connection and clean up resources."""
        with self._conn_lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Anticipation Engine
# ---------------------------------------------------------------------------

class AnticipationEngine:
    """Predicts next user action using static priors blended with learned habits.

    Learning works automatically:
      - Call record_feedback(prior, action, accepted=True/False) whenever
        the user taps Accept or Dismiss on a suggestion chip in the UI.
      - predict_next_actions() progressively trusts the learned signal
        more than static priors as observations accumulate.
    """

    @classmethod
    def record_feedback(
        cls,
        prior_action: str,
        suggested_action: str,
        accepted: bool,
    ) -> None:
        """Record user's accept/dismiss response to a suggestion.

        Call this from the UI suggestion chip handler:
            AnticipationEngine.record_feedback("coding", "audit", accepted=True)
        """
        try:
            HabitTracker().record(prior_action, suggested_action, accepted)
        except Exception as exc:
            logger.warning("record_feedback error: %s", exc)

    @classmethod
    def _blend(
        cls,
        prior_action: str,
        static_priors: List[Tuple[str, float, str]],
        learned: Dict[str, float],
        n_obs: int,
    ) -> List[Dict[str, Any]]:
        """Blend static prior probabilities with learned accept-rates.

        Alpha (learned weight) ramps linearly from 0 -> MAX_ALPHA as
        n_obs goes from 0 -> ALPHA_RAMP_OBSERVATIONS.
        """
        alpha = min(n_obs / _ALPHA_RAMP_OBSERVATIONS, 1.0) * _MAX_ALPHA

        static_map: Dict[str, Tuple[float, str]] = {
            act: (prob, reason) for act, prob, reason in static_priors
        }

        all_actions: set = set(static_map.keys()) | set(learned.keys())

        blended: List[Dict[str, Any]] = []
        for action in all_actions:
            s_prob, reason = static_map.get(action, (0.0, "Learned from your workflow"))
            l_prob = learned.get(action, 0.0)
            confidence = (1 - alpha) * s_prob + alpha * l_prob

            if confidence < 0.05:
                continue

            if action not in static_map:
                trigger = "habit_learned"
            elif action not in learned and n_obs > _ALPHA_RAMP_OBSERVATIONS:
                trigger = "workflow_static"
            else:
                trigger = "workflow_transition"

            blended.append({
                "action":       action,
                "confidence":   round(confidence, 3),
                "trigger":      trigger,
                "reason":       reason,
                "prompt":       f"Ready to run {action}: {reason}?",
                "learned":      action in learned,
                "prior_action": prior_action,
            })

        return blended

    @classmethod
    def predict_next_actions(
        cls,
        last_task_kind: Optional[str] = None,
        hour: Optional[int] = None,
        active_window_title: str = "",
    ) -> List[Dict[str, Any]]:
        """Compute ranked action predictions with confidence scores.

        Same return shape as before -- backward-compatible.
        """
        predictions: List[Dict[str, Any]] = []
        h = datetime.now().hour if hour is None else hour
        tracker = HabitTracker()

        # 1. Workflow Transition Signals (highest confidence)
        if last_task_kind and last_task_kind in WORKFLOW_TRANSITION_PROBABILITIES:
            static_priors = WORKFLOW_TRANSITION_PROBABILITIES[last_task_kind]
            learned = tracker.learned_transitions(last_task_kind)
            n_obs = tracker.total_observations(last_task_kind)
            predictions.extend(cls._blend(last_task_kind, static_priors, learned, n_obs))

        # 2. Window Context Signals (IDE, Terminal, Browser)
        win = active_window_title.lower()
        if "visual studio code" in win or ".py" in win or ".js" in win:
            predictions.append({
                "action":       "code_audit",
                "confidence":   0.35,
                "trigger":      "active_window_ide",
                "reason":       "Active in code editor; ready for bug inspection",
                "prompt":       "Inspect active code file for bugs?",
                "learned":      False,
                "prior_action": "window_context",
            })
        elif "terminal" in win or "powershell" in win or "cmd" in win:
            predictions.append({
                "action":       "sysadmin",
                "confidence":   0.30,
                "trigger":      "active_window_terminal",
                "reason":       "Active in command line; ready for system diagnostics",
                "prompt":       "Run system health check?",
                "learned":      False,
                "prior_action": "window_context",
            })
        elif any(k in win for k in ("chrome", "firefox", "edge", "browser")):
            predictions.append({
                "action":       "web_search",
                "confidence":   0.28,
                "trigger":      "active_window_browser",
                "reason":       "Active in browser; ready to research or summarise page",
                "prompt":       "Summarise current page?",
                "learned":      False,
                "prior_action": "window_context",
            })

        # 3. Temporal Routine Signals
        if 8 <= h < 11:
            predictions.append({
                "action":       "morning_briefing",
                "confidence":   0.25,
                "trigger":      "temporal_morning",
                "reason":       "Morning schedule: review priorities, weather, and world news",
                "prompt":       "Deliver morning briefing and daily priorities?",
                "learned":      False,
                "prior_action": "temporal",
            })
        elif 12 <= h < 14:
            predictions.append({
                "action":       "lunch_break",
                "confidence":   0.20,
                "trigger":      "temporal_lunch",
                "reason":       "Midday -- good time for a break or a quick status review",
                "prompt":       "Quick midday status check?",
                "learned":      False,
                "prior_action": "temporal",
            })
        elif 17 <= h < 20:
            predictions.append({
                "action":       "daily_wrapup",
                "confidence":   0.25,
                "trigger":      "temporal_evening",
                "reason":       "Evening wrap-up: review completed goals and upcoming tasks",
                "prompt":       "Review completed tasks and wrap up today's work?",
                "learned":      False,
                "prior_action": "temporal",
            })

        # 4. De-duplicate: keep highest confidence per action
        unique: Dict[str, Dict[str, Any]] = {}
        for p in predictions:
            act = p["action"]
            if act not in unique or p["confidence"] > unique[act]["confidence"]:
                unique[act] = p

        ranked = sorted(unique.values(), key=lambda x: x["confidence"], reverse=True)
        return ranked[:3]
