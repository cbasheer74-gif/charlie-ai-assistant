"""Voice tool for CHARLIE Game Room."""

from __future__ import annotations

import json

from memory import game_room as games


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def game_room(parameters: dict, **_unused) -> str:
    params = parameters or {}
    action = str(params.get("action") or "menu").strip().lower()
    try:
        if action == "menu":
            return games.menu_instruction()
        if action == "start":
            result = games.start_game(
                params.get("game", ""), params.get("category", "general"),
                params.get("difficulty", "medium"), params.get("theme", ""),
                params.get("participants") or [],
            )
            return result["instruction"] + "\nSESSION STATE:\n" + _json(result["session"])
        if action == "record_turn":
            result = games.record_turn(params.get("outcome", "complete"), params.get("points"),
                                       params.get("detail", ""), params.get("participant", ""))
            return "Scoreboard updated. Continue with one game turn, then wait.\n" + _json(result)
        if action == "finish":
            return "Game finished. Celebrate briefly and offer a rematch.\n" + _json(
                games.finish_game(params.get("outcome", "complete")))
        if action == "status":
            return _json(games.status())
        if action == "leaderboard":
            return "Family Game Room leaderboard:\n" + _json(games.leaderboard())
        return "Unknown Game Room action. Use menu, start, record_turn, finish, status, or leaderboard."
    except (ValueError, TypeError, OSError) as exc:
        return str(exc)


TOOL = {
    "name": "game_room",
    "description": (
        "Play and persist CHARLIE voice games: Mystery Adventure, 20 Questions, Quiz Battle, "
        "family-safe Truth or Dare, Would You Rather, Memory Challenge, role-play stories, "
        "Daily Brain Challenge, Family Game Night, and mood-aware games. Tracks profile-private "
        "scores, turns, streaks, achievements, saved progress, and family leaderboards."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "menu, start, record_turn, finish, status, or leaderboard."},
            "game": {"type": "STRING", "description": (
                "mystery_adventure, twenty_questions, quiz_battle, truth_or_dare, would_you_rather, "
                "memory_challenge, roleplay_story, daily_brain_challenge, family_game_night, or mood_games.")},
            "category": {"type": "STRING", "description": "Quiz/game category; default general."},
            "difficulty": {"type": "STRING", "description": "easy, medium, or hard."},
            "theme": {"type": "STRING", "description": "Story theme such as detective, superhero, space, or non-graphic horror."},
            "participants": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Family player names."},
            "participant": {"type": "STRING", "description": "Player whose score changes this turn."},
            "outcome": {"type": "STRING", "description": "correct, incorrect, win, loss, choice, skip, or complete."},
            "points": {"type": "INTEGER", "description": "Optional points; defaults to 10 for a correct answer."},
            "detail": {"type": "STRING", "description": "Short clue, choice, or answer note for saved progress."},
        },
        "required": ["action"],
    },
    "handler": game_room,
}
