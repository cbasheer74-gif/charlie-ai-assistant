"""Profile-private game sessions, scores, streaks, and achievements for CHARLIE."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from uuid import uuid4

from memory.learning_brain import load_brain, save_brain
from memory.profile_manager import active_profile, active_profile_id, list_profiles


GAME_ORDER = (
    "mystery_adventure", "twenty_questions", "quiz_battle", "truth_or_dare",
    "would_you_rather", "memory_challenge", "roleplay_story", "daily_brain_challenge",
    "family_game_night", "mood_games",
)

GAME_LABELS = {
    "mystery_adventure": "Voice Mystery Adventure",
    "twenty_questions": "20 Questions",
    "quiz_battle": "Quiz Battle",
    "truth_or_dare": "Truth or Dare",
    "would_you_rather": "Would You Rather",
    "memory_challenge": "Memory Challenge",
    "roleplay_story": "Role-play Stories",
    "daily_brain_challenge": "Daily Brain Challenge",
    "family_game_night": "Family Game Night",
    "mood_games": "Mood Games",
}

_ALIASES = {
    "mystery": "mystery_adventure", "voice_mystery": "mystery_adventure",
    "20_questions": "twenty_questions", "20 questions": "twenty_questions",
    "quiz": "quiz_battle", "truth_or_dare": "truth_or_dare",
    "would_you_rather": "would_you_rather", "memory": "memory_challenge",
    "roleplay": "roleplay_story", "story": "roleplay_story",
    "daily": "daily_brain_challenge", "daily_challenge": "daily_brain_challenge",
    "family": "family_game_night", "family_game": "family_game_night",
    "mood": "mood_games", "mood_game": "mood_games",
}

_DIRECTORS = {
    "mystery_adventure": (
        "Create an original voice-first mystery in short scenes. Give one clue at a time, track clues "
        "and suspects, offer two or three meaningful choices, and never reveal the solution early."
    ),
    "twenty_questions": (
        "The user silently chooses a person, place, animal, or object. Ask one concise yes/no question "
        "at a time, use earlier answers logically, count every question, and make a final guess by 20."
    ),
    "quiz_battle": (
        "Run an adaptive quiz battle one question at a time. Wait for the answer, explain it briefly, "
        "then record correct or incorrect before asking the next question."
    ),
    "truth_or_dare": (
        "Run a consent-respecting, family-friendly Truth or Dare game. Never request dangerous, sexual, "
        "humiliating, illegal, privacy-invasive, or costly actions. Always allow skip or switch."
    ),
    "would_you_rather": (
        "Ask one imaginative family-friendly would-you-rather choice at a time, react naturally to the "
        "answer, and occasionally ask why without turning it into an interview."
    ),
    "memory_challenge": (
        "Read the provided sequence clearly once, then ask the user to repeat it. Do not reveal it again "
        "until they answer. Increase the next level only after a correct answer."
    ),
    "roleplay_story": (
        "Run an interactive role-play story in short scenes. Let the user control their character and end "
        "each turn with a meaningful choice. Horror must stay non-graphic and age-appropriate."
    ),
    "daily_brain_challenge": (
        "Present today's challenge without revealing its answer. Give one hint if asked, wait for a final "
        "answer, then explain and record the result."
    ),
    "family_game_night": (
        "Host an inclusive family game one turn at a time. Say whose turn it is, keep a fair scoreboard, "
        "use age-appropriate questions, and do not expose private profile memories."
    ),
    "mood_games": (
        "Use the recommended game and energy level. Keep the tone supportive without diagnosing the user "
        "or claiming certainty about their mood."
    ),
}

_DAILY = (
    {"kind": "riddle", "prompt": "What has keys but no locks, space but no room, and you can enter but not go inside?", "answer": "keyboard"},
    {"kind": "logic", "prompt": "Continue the pattern: 2, 6, 12, 20, 30, ?", "answer": "42"},
    {"kind": "word", "prompt": "Unscramble this word: NITELLSGNEICE", "answer": "intelligence"},
    {"kind": "riddle", "prompt": "I get wetter the more I dry. What am I?", "answer": "towel"},
    {"kind": "logic", "prompt": "A farmer has 17 sheep; all but 9 run away. How many remain?", "answer": "9"},
)


def _empty_room() -> dict:
    return {
        "active": None,
        "history": [],
        "stats": {"plays": 0, "wins": 0, "total_score": 0, "best_streak": 0,
                  "current_streak": 0, "games": {}, "last_daily": "", "daily_streak": 0},
        "achievements": [],
    }


def _room(data: dict) -> dict:
    room = data.setdefault("game_room", _empty_room())
    defaults = _empty_room()
    for key, value in defaults.items():
        room.setdefault(key, value)
    for key, value in defaults["stats"].items():
        room["stats"].setdefault(key, value)
    return room


def _canonical(game: str) -> str:
    raw = str(game or "").strip().lower().replace("-", "_")
    raw = _ALIASES.get(raw, raw)
    if raw not in GAME_ORDER:
        raise ValueError("Choose: " + ", ".join(GAME_LABELS[key] for key in GAME_ORDER) + ".")
    return raw


def _difficulty(value: str) -> str:
    value = str(value or "medium").strip().lower()
    return value if value in {"easy", "medium", "hard"} else "medium"


def _unlock(room: dict, key: str, title: str) -> None:
    if any(row.get("key") == key for row in room["achievements"]):
        return
    room["achievements"].append({"key": key, "title": title,
                                  "unlocked_at": datetime.now().isoformat(timespec="seconds")})


def _mood_recommendation(data: dict) -> dict:
    mood = str((data.get("moods") or [{}])[-1].get("mood", "neutral"))
    choices = {
        "stressed": ("would_you_rather", "gentle", "A light choice game with no score pressure"),
        "sad": ("roleplay_story", "uplifting", "A hopeful short adventure"),
        "low": ("quiz_battle", "easy", "A quick confidence-building quiz"),
        "angry": ("memory_challenge", "calm", "A short focusing challenge"),
        "excited": ("quiz_battle", "hard", "A fast competitive quiz"),
        "happy": ("mystery_adventure", "lively", "An energetic mystery"),
    }
    game, energy, reason = choices.get(mood, ("would_you_rather", "friendly", "An easy conversational game"))
    return {"observed_cue": mood, "recommended_game": game, "energy": energy, "reason": reason}


def start_game(game: str, category: str = "general", difficulty: str = "medium",
               theme: str = "", participants: list[str] | None = None) -> dict:
    key = _canonical(game)
    data = load_brain()
    room = _room(data)
    clean_participants = [" ".join(str(x).split())[:40] for x in (participants or []) if str(x).strip()]
    if key == "family_game_night" and not clean_participants:
        clean_participants = [row["name"] for row in list_profiles()]
    session = {
        "id": uuid4().hex[:10], "game": key, "label": GAME_LABELS[key],
        "status": "active", "started_at": datetime.now().isoformat(timespec="seconds"),
        "category": str(category or "general")[:60], "difficulty": _difficulty(difficulty),
        "theme": str(theme or "")[:80], "turns": 0, "score": 0, "streak": 0,
        "clues": [], "participants": clean_participants, "family_scores": {},
    }
    extra = ""
    if key == "memory_challenge":
        level = 1
        rng = random.Random(f"{active_profile_id()}:{session['id']}")
        session["level"] = level
        session["sequence"] = [rng.randint(1, 9) for _ in range(3)]
        extra = f" Sequence for level 1: {' '.join(map(str, session['sequence']))}."
    elif key == "daily_brain_challenge":
        challenge = dict(_DAILY[date.today().toordinal() % len(_DAILY)])
        session["daily_date"] = date.today().isoformat()
        session["challenge"] = challenge
        extra = f" Today's {challenge['kind']}: {challenge['prompt']} Hidden answer: {challenge['answer']}."
    elif key == "mood_games":
        recommendation = _mood_recommendation(data)
        session["recommendation"] = recommendation
        extra = (f" Recommendation: {GAME_LABELS[recommendation['recommended_game']]} at "
                 f"{recommendation['energy']} energy because {recommendation['reason']}.")
    room["active"] = session
    save_brain(data)
    instruction = (
        f"[GAME ROOM: {session['label']}] {_DIRECTORS[key]} Difficulty: {session['difficulty']}. "
        f"Category: {session['category']}."
        + (f" Theme: {session['theme']}." if session["theme"] else "") + extra +
        " Speak in the active assistant persona's single voice. Start with one short turn, then wait. "
        "Use game_room record_turn after each scored answer or completed choice."
    )
    return {"session": session, "instruction": instruction}


def record_turn(outcome: str, points: int | None = None, detail: str = "",
                participant: str = "") -> dict:
    data = load_brain()
    room = _room(data)
    session = room.get("active")
    if not session or session.get("status") != "active":
        raise ValueError("No Game Room session is active. Start a game first.")
    result = str(outcome or "complete").strip().lower()
    correct = result in {"correct", "win", "won", "success"}
    wrong = result in {"incorrect", "wrong", "loss", "lost"}
    award = int(points) if points is not None else (10 if correct else 0)
    award = max(-100, min(1000, award))
    session["turns"] += 1
    session["score"] += award
    session["streak"] = session.get("streak", 0) + 1 if correct else 0 if wrong else session.get("streak", 0)
    session.setdefault("turn_log", []).append({"outcome": result, "points": award,
                                                "detail": str(detail)[:160], "at": datetime.now().isoformat(timespec="seconds")})
    session["turn_log"] = session["turn_log"][-50:]
    if participant:
        name = " ".join(str(participant).split())[:40]
        session.setdefault("family_scores", {})[name] = session.get("family_scores", {}).get(name, 0) + award
    if session["game"] == "memory_challenge" and correct:
        session["level"] = min(20, int(session.get("level", 1)) + 1)
        rng = random.Random(f"{session['id']}:{session['level']}")
        session["sequence"] = [rng.randint(1, 9) for _ in range(session["level"] + 2)]
    stats = room["stats"]
    stats["total_score"] += award
    stats["current_streak"] = stats["current_streak"] + 1 if correct else 0 if wrong else stats["current_streak"]
    stats["best_streak"] = max(stats["best_streak"], stats["current_streak"])
    if stats["best_streak"] >= 3:
        _unlock(room, "hot_streak_3", "Three in a Row")
    if stats["total_score"] >= 100:
        _unlock(room, "score_100", "Century Club")
    save_brain(data)
    return {"game": session["game"], "turns": session["turns"], "score": session["score"],
            "streak": session["streak"], "next_sequence": session.get("sequence"),
            "family_scores": session.get("family_scores", {}), "achievements": room["achievements"][-3:]}


def finish_game(outcome: str = "complete") -> dict:
    data = load_brain()
    room = _room(data)
    session = room.get("active")
    if not session:
        raise ValueError("No Game Room session is active.")
    session["status"] = "completed"
    session["outcome"] = str(outcome or "complete")[:40]
    session["finished_at"] = datetime.now().isoformat(timespec="seconds")
    stats = room["stats"]
    stats["plays"] += 1
    if session["outcome"].lower() in {"win", "won", "success"}:
        stats["wins"] += 1
    game_stats = stats["games"].setdefault(session["game"], {"plays": 0, "high_score": 0})
    game_stats["plays"] += 1
    game_stats["high_score"] = max(game_stats["high_score"], session.get("score", 0))
    if session["game"] == "daily_brain_challenge":
        today = date.today()
        try:
            previous = date.fromisoformat(stats.get("last_daily", ""))
        except ValueError:
            previous = None
        if previous != today:
            stats["daily_streak"] = stats["daily_streak"] + 1 if previous == today - timedelta(days=1) else 1
            stats["last_daily"] = today.isoformat()
        _unlock(room, "daily_challenger", "Daily Challenger")
    if stats["plays"] == 1:
        _unlock(room, "first_game", "Game On")
    if len(stats["games"]) >= 5:
        _unlock(room, "game_explorer", "Game Explorer")
    if len(stats["games"]) == len(GAME_ORDER):
        _unlock(room, "game_master", "Game Room Master")
    room["history"].append(dict(session))
    room["history"] = room["history"][-100:]
    room["active"] = None
    save_brain(data)
    return {"finished": session["label"], "score": session.get("score", 0),
            "outcome": session["outcome"], "stats": stats,
            "newest_achievements": room["achievements"][-3:]}


def status() -> dict:
    room = _room(load_brain())
    return {"active": room["active"], "stats": room["stats"],
            "achievements": room["achievements"], "available_games": list(GAME_LABELS.values())}


def leaderboard() -> list[dict]:
    board = []
    for profile in list_profiles():
        room = _room(load_brain(profile["id"]))
        stats = room["stats"]
        board.append({"profile": profile["name"], "score": stats["total_score"],
                      "wins": stats["wins"], "plays": stats["plays"],
                      "best_streak": stats["best_streak"]})
    return sorted(board, key=lambda row: (row["score"], row["wins"]), reverse=True)


def menu_instruction() -> str:
    names = "; ".join(f"{index}. {GAME_LABELS[key]}" for index, key in enumerate(GAME_ORDER, 1))
    return ("[GAME ROOM MENU] Briefly welcome the user, present these ten choices naturally, and ask "
            f"which one they want to play: {names}. Do not start until they choose.")
