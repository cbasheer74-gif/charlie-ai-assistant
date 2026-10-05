"""memory/kids_activity.py — Profile-aware state and engines for Children's Activities.

Features:
- Bedtime Storyteller: Interactive chapter-by-chapter bedtime stories with gentle themes.
- Math Quest: Gamified arithmetic challenges with difficulty levels, stars, and streaks.
- Voice Drawing Coach: Step-by-step shape-based drawing instructions.
- Kid-Safe Content Guard: Content filtering, screen time tracking, and parental PIN protection.
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

from memory.profile_manager import active_profile_id, profile_dir

_lock = RLock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return date.today().isoformat()


def _store_path() -> Path:
    pdir = profile_dir(active_profile_id())
    pdir.mkdir(parents=True, exist_ok=True)
    return pdir / "kids_activity.json"


def _default_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "stars": 0,
        "guard": {
            "enabled": False,
            "parent_pin": "1234",
            "filter_level": "strict",
            "daily_limit_minutes": 60,
            "used_minutes_today": 0,
            "last_active_date": _today(),
        },
        "math_quest": {
            "level": "easy",
            "current_question": None,
            "current_answer": None,
            "streak": 0,
            "best_streak": 0,
            "total_correct": 0,
        },
        "story": {
            "active": False,
            "theme": "space",
            "chapter": 0,
            "history": [],
        },
        "drawing": {
            "active": False,
            "subject": "",
            "step_index": 0,
            "total_steps": 0,
            "completed_drawings": [],
        },
    }


def load_state() -> Dict[str, Any]:
    path = _store_path()
    with _lock:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    base = _default_state()
                    for k, v in base.items():
                        if k not in data:
                            data[k] = v
                    return data
            except Exception:
                pass
        return _default_state()


def save_state(state: Dict[str, Any]) -> None:
    path = _store_path()
    with _lock:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


# --- 1. Math Quest Engine ---
def generate_math_problem(difficulty: str = "easy") -> Dict[str, Any]:
    state = load_state()
    diff = difficulty.lower()
    if diff == "hard":
        a = random.randint(10, 50)
        b = random.randint(2, 12)
        op = random.choice(["+", "-", "*"])
    elif diff == "medium":
        a = random.randint(5, 20)
        b = random.randint(3, 15)
        op = random.choice(["+", "-"])
    else:  # easy
        a = random.randint(1, 10)
        b = random.randint(1, 10)
        op = "+"

    if op == "+":
        ans = a + b
    elif op == "-":
        if a < b:
            a, b = b, a
        ans = a - b
    else:
        ans = a * b

    expr = f"{a} {op} {b}"
    state["math_quest"]["current_question"] = expr
    state["math_quest"]["current_answer"] = ans
    state["math_quest"]["level"] = diff
    save_state(state)

    return {
        "question": expr,
        "difficulty": diff,
        "prompt": f"What is {expr}?",
    }


def check_math_answer(user_answer: int | str) -> Dict[str, Any]:
    state = load_state()
    quest = state["math_quest"]
    correct_ans = quest.get("current_answer")

    if correct_ans is None:
        return {"status": "no_question", "message": "No active question. Start a new math quest!"}

    try:
        val = int(str(user_answer).strip())
    except ValueError:
        return {"status": "invalid", "message": "Please provide a valid number."}

    if val == correct_ans:
        quest["streak"] += 1
        quest["total_correct"] += 1
        if quest["streak"] > quest["best_streak"]:
            quest["best_streak"] = quest["streak"]
        state["stars"] += 10
        quest["current_question"] = None
        quest["current_answer"] = None
        save_state(state)
        return {
            "status": "correct",
            "message": f"Awesome job! {val} is correct! [+10 Stars!] (Streak: {quest['streak']})",
            "streak": quest["streak"],
            "total_stars": state["stars"],
        }
    else:
        streak_ended = quest["streak"]
        quest["streak"] = 0
        save_state(state)
        return {
            "status": "incorrect",
            "message": f"Almost! The correct answer was {correct_ans}. Keep trying!",
            "streak_ended": streak_ended,
        }


# --- 2. Bedtime Storyteller Engine ---
_STORY_STARTERS = {
    "space": "Once upon a time, a curious little robot named Pip lived on a friendly moon surrounded by sparkling stardust...",
    "forest": "Deep inside the Whispering Forest, an energetic baby fox named Oliver discovered a glowing silver acorn...",
    "ocean": "Beneath the calm blue waves of Coral Cove, a gentle sea turtle named Barnaby found a map to the singing shells...",
    "magic": "High in the clouds above Mount Starlight, a friendly young dragon named Sparky was learning how to make bedtime lullabies...",
}


def start_story(theme: str = "space") -> Dict[str, Any]:
    state = load_state()
    theme = theme.lower() if theme.lower() in _STORY_STARTERS else "space"
    starter = _STORY_STARTERS[theme]

    state["story"] = {
        "active": True,
        "theme": theme,
        "chapter": 1,
        "history": [starter],
    }
    save_state(state)
    return {
        "theme": theme,
        "chapter": 1,
        "content": starter,
        "prompt": "What should happen next? Choose or suggest the next adventure!",
    }


def next_chapter(user_choice: str) -> Dict[str, Any]:
    state = load_state()
    story = state["story"]
    if not story.get("active"):
        return start_story()

    story["chapter"] += 1
    story["history"].append(user_choice)
    save_state(state)

    return {
        "chapter": story["chapter"],
        "theme": story["theme"],
        "instruction": f"Continue chapter {story['chapter']} softly for bedtime based on: '{user_choice}'. End with 2 gentle choices.",
    }


# --- 3. Voice Drawing Coach ---
_DRAWING_SUBJECTS = {
    "cat": [
        "First, draw a large neat circle in the center for the head.",
        "Now, add two small triangles on top of the circle for the cute cat ears.",
        "Inside the circle, draw two shiny oval eyes, a small upside-down triangle nose, and 3 whiskers on each side.",
        "Draw a soft oval body below the head, 2 small front paws, and a curved fluffy tail. Color your happy cat!",
    ],
    "rocket": [
        "Start by drawing a tall, curved triangle or bullet shape pointing up to the sky.",
        "Draw a round circle window right in the middle for the astronaut.",
        "Add two sharp fins at the bottom left and right sides of the rocket.",
        "Draw fiery wavy booster flames coming out of the bottom nozzle. Ready for blast off!",
    ],
    "house": [
        "Draw a nice square in the middle of your page.",
        "Put a triangular roof right on top of the square.",
        "Draw a rectangle door in the bottom center and two square windows with cross panes.",
        "Add a small chimney on the roof with gentle puffy smoke rings drifting away!",
    ],
}


def start_drawing(subject: str = "cat") -> Dict[str, Any]:
    state = load_state()
    sub = subject.lower().strip()
    if sub not in _DRAWING_SUBJECTS:
        sub = "cat"

    steps = _DRAWING_SUBJECTS[sub]
    state["drawing"] = {
        "active": True,
        "subject": sub,
        "step_index": 1,
        "total_steps": len(steps),
        "completed_drawings": state["drawing"].get("completed_drawings", []),
    }
    save_state(state)
    return {
        "subject": sub,
        "step": 1,
        "total_steps": len(steps),
        "instruction": steps[0],
    }


def next_drawing_step() -> Dict[str, Any]:
    state = load_state()
    d = state["drawing"]
    if not d.get("active"):
        return start_drawing()

    steps = _DRAWING_SUBJECTS.get(d["subject"], [])
    current = d["step_index"]

    if current < len(steps):
        d["step_index"] += 1
        save_state(state)
        return {
            "subject": d["subject"],
            "step": d["step_index"],
            "total_steps": len(steps),
            "instruction": steps[d["step_index"] - 1],
            "finished": False,
        }
    else:
        d["active"] = False
        if d["subject"] not in d["completed_drawings"]:
            d["completed_drawings"].append(d["subject"])
        state["stars"] += 15
        save_state(state)
        return {
            "subject": d["subject"],
            "finished": True,
            "instruction": f"Masterpiece complete! You drew a fantastic {d['subject']}! [+15 Stars awarded!]",
            "total_stars": state["stars"],
        }


# --- 4. Kid-Safe Content Guard ---
def update_guard(enabled: bool, pin: str, limit_minutes: int = 60, filter_level: str = "strict") -> Dict[str, Any]:
    state = load_state()
    guard = state["guard"]
    if pin != guard["parent_pin"]:
        return {"status": "error", "message": "Incorrect parent PIN."}

    guard["enabled"] = bool(enabled)
    guard["daily_limit_minutes"] = max(10, min(360, int(limit_minutes)))
    guard["filter_level"] = filter_level if filter_level in ("strict", "moderate") else "strict"
    save_state(state)

    return {
        "status": "success",
        "guard_enabled": guard["enabled"],
        "daily_limit_minutes": guard["daily_limit_minutes"],
        "filter_level": guard["filter_level"],
    }


def get_kids_status() -> Dict[str, Any]:
    state = load_state()
    return {
        "total_stars": state.get("stars", 0),
        "guard_active": state["guard"]["enabled"],
        "filter_level": state["guard"]["filter_level"],
        "daily_limit_minutes": state["guard"]["daily_limit_minutes"],
        "math_streak": state["math_quest"]["streak"],
        "math_total_correct": state["math_quest"]["total_correct"],
        "story_active": state["story"]["active"],
        "completed_drawings": state["drawing"].get("completed_drawings", []),
    }
