"""Profile-private adaptive learning for CHARLIE.

The learning brain stores preferences and compact derived signals, never API
keys. Voiceprints are optional convenience embeddings kept locally and are not
treated as authentication for sensitive actions.
"""

from __future__ import annotations

import json
import math
import random
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from uuid import uuid4

from memory.profile_manager import (
    active_profile, list_profiles, notify_context_change, profile_learning_path,
)

_lock = RLock()
_voice_lock = RLock()
_recent_voice: tuple[bytes, int] | None = None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty() -> dict:
    return {
        "version": 1,
        "settings": {
            "emotion_support": True,
            "routine_suggestions": True,
            "vision_copilot": "ask",
            "daily_intelligence": True,
            "voice_identification": False,
        },
        "moods": [],
        "relationships": [],
        "knowledge": [],
        "routine_decisions": [],
        "voiceprint": {"samples": [], "updated_at": ""},
        "activities": [],
        "daily_reviews": [],
    }


def load_brain(profile_id: str | None = None) -> dict:
    path = profile_learning_path(profile_id)
    with _lock:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for key, value in _empty().items():
                        data.setdefault(key, value)
                    for key, value in _empty()["settings"].items():
                        data["settings"].setdefault(key, value)
                    return data
            except Exception:
                pass
        return _empty()


def save_brain(data: dict, profile_id: str | None = None) -> None:
    path = profile_learning_path(profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    with _lock:
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)


def update_settings(**changes) -> dict:
    allowed = {
        "emotion_support": {True, False},
        "routine_suggestions": {True, False},
        "vision_copilot": {"off", "ask", "on"},
        "daily_intelligence": {True, False},
        "voice_identification": {True, False},
    }
    data = load_brain()
    for key, value in changes.items():
        if value is None or key not in allowed:
            continue
        if key in {"emotion_support", "routine_suggestions", "daily_intelligence",
                   "voice_identification"}:
            value = bool(value)
        else:
            value = str(value).strip().lower()
        if value not in allowed[key]:
            raise ValueError(f"Invalid {key} setting.")
        data["settings"][key] = value
    save_brain(data)
    notify_context_change()
    return dict(data["settings"])


# 3. Routine learning -------------------------------------------------------

def discover_routines(minimum_repeats: int = 3) -> list[dict]:
    if not load_brain()["settings"].get("routine_suggestions", True):
        return []
    from core.task_history import recent
    ignored = {"action_history", "learning_brain", "personal_hub", "save_memory",
               "remember_correction"}
    groups: dict[str, list[dict]] = {}
    for event in recent(200):
        if event.get("state") != "completed" or event.get("tool") in ignored:
            continue
        params = event.get("parameters") if isinstance(event.get("parameters"), dict) else {}
        stable = {k: v for k, v in params.items() if k not in {"date", "time", "query"}}
        signature = f"{event.get('tool')}|{json.dumps(stable, sort_keys=True, ensure_ascii=False)}"
        groups.setdefault(signature, []).append(event)

    decisions = {d.get("signature"): d for d in load_brain()["routine_decisions"]}
    found = []
    for signature, events in groups.items():
        if len(events) < max(2, int(minimum_repeats)):
            continue
        previous = decisions.get(signature, {})
        if previous.get("decision") == "dismissed":
            continue
        sample = events[0]
        found.append({
            "id": "routine_" + uuid4().hex[:8],
            "signature": signature,
            "tool": sample.get("tool"),
            "parameters": sample.get("parameters", {}),
            "repetitions": len(events),
            "first_seen": events[-1].get("at"),
            "last_seen": events[0].get("at"),
            "decision": previous.get("decision", "pending"),
        })
    return sorted(found, key=lambda row: row["repetitions"], reverse=True)[:8]


def decide_routine(signature: str, decision: str, name: str = "") -> dict:
    decision = str(decision).strip().lower()
    if decision not in {"approved", "dismissed"}:
        raise ValueError("Routine decision must be approved or dismissed.")
    data = load_brain()
    data["routine_decisions"] = [
        row for row in data["routine_decisions"] if row.get("signature") != signature
    ]
    record = {"signature": signature, "decision": decision, "name": name.strip()[:80],
              "updated_at": _now()}
    data["routine_decisions"].append(record)
    data["routine_decisions"] = data["routine_decisions"][-40:]
    save_brain(data)
    return record


# 4. Emotional conversation intelligence ----------------------------------

_MOOD_WORDS = {
    "stressed": ("stressed", "stress", "overwhelmed", "pressure", "tension", "pareshan", "tensed"),
    "frustrated": ("frustrated", "annoyed", "irritated", "fed up", "gussa", "bekaar", "not working"),
    "sad": ("sad", "upset", "down", "lonely", "hurt", "dukhi", "bura lag"),
    "anxious": ("anxious", "worried", "nervous", "scared", "dar", "chinta"),
    "excited": ("excited", "amazing", "great news", "can't wait", "khush", "maza"),
    "confused": ("confused", "don't understand", "samajh nahi", "unclear", "lost"),
}


def observe_user_turn(text: str) -> dict | None:
    data = load_brain()
    if not data["settings"].get("emotion_support", True):
        return None
    lower = " ".join(str(text or "").casefold().split())
    scores = {mood: sum(1 for word in words if word in lower)
              for mood, words in _MOOD_WORDS.items()}
    mood, score = max(scores.items(), key=lambda item: item[1], default=("", 0))
    if score <= 0:
        return None
    event = {"mood": mood, "intensity": min(3, score), "at": _now()}
    data["moods"].append(event)
    data["moods"] = data["moods"][-20:]
    save_brain(data)
    return event


# 5. Personal knowledge vault ----------------------------------------------

def _extract_file(path: Path) -> str:
    if path.stat().st_size > 15 * 1024 * 1024:
        raise ValueError("Knowledge files must be 15 MB or smaller.")
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".rst", ".json", ".csv", ".xml", ".py", ".js",
                  ".ts", ".java", ".c", ".cpp", ".html", ".css", ".log"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    if suffix == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(str(path)).paragraphs)
    if suffix == ".pptx":
        from pptx import Presentation
        return "\n".join(shape.text for slide in Presentation(str(path)).slides
                         for shape in slide.shapes if hasattr(shape, "text"))
    raise ValueError("Supported knowledge files: TXT, Markdown, PDF, DOCX, PPTX, JSON, CSV and code files.")


def add_knowledge(file_path: str, title: str = "") -> dict:
    path = Path(file_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ValueError(f"Knowledge file not found: {file_path}")
    text = re.sub(r"\n{3,}", "\n\n", _extract_file(path)).strip()
    if not text:
        raise ValueError("No readable text was found in that file.")
    text = text[:60_000]
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < 60:
        chunks.append(text[start:start + 1200])
        start += 1050
    data = load_brain()
    doc = {"id": "doc_" + uuid4().hex[:10], "title": (title.strip() or path.stem)[:120],
           "file_name": path.name, "source_path": str(path), "added_at": _now(),
           "characters": len(text), "chunks": chunks}
    data["knowledge"] = [row for row in data["knowledge"]
                         if row.get("source_path", "").casefold() != str(path).casefold()]
    data["knowledge"].append(doc)
    data["knowledge"] = data["knowledge"][-30:]
    save_brain(data)
    return {k: doc[k] for k in ("id", "title", "file_name", "characters", "added_at")}


def search_knowledge(query: str, limit: int = 5) -> list[dict]:
    terms = {term for term in re.findall(r"[\w'-]{3,}", str(query).casefold())}
    if not terms:
        return []
    ranked = []
    for doc in load_brain()["knowledge"]:
        for index, chunk in enumerate(doc.get("chunks", [])):
            lower = chunk.casefold()
            score = sum(lower.count(term) for term in terms)
            if score:
                ranked.append((score, {"title": doc.get("title"), "file_name": doc.get("file_name"),
                                       "chunk": index + 1, "excerpt": chunk[:1400]}))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in ranked[:max(1, min(int(limit), 8))]]


def remove_knowledge(identifier: str) -> bool:
    wanted = str(identifier or "").strip().casefold()
    data = load_brain()
    before = len(data["knowledge"])
    data["knowledge"] = [row for row in data["knowledge"] if wanted not in {
        str(row.get("id", "")).casefold(), str(row.get("title", "")).casefold(),
        str(row.get("file_name", "")).casefold()}]
    if len(data["knowledge"]) != before:
        save_brain(data)
        return True
    return False


# 6. Relationship memory ----------------------------------------------------

def remember_relationship(name: str, relation: str = "", details: str = "",
                          important_date: str = "", follow_up: str = "") -> dict:
    clean = " ".join(str(name or "").split())[:80]
    if not clean:
        raise ValueError("A person's name is required.")
    data = load_brain()
    person = next((row for row in data["relationships"]
                   if row.get("name", "").casefold() == clean.casefold()), None)
    if person is None:
        person = {"id": "person_" + uuid4().hex[:8], "name": clean, "created_at": _now()}
        data["relationships"].append(person)
    updates = {"relation": relation, "details": details, "important_date": important_date,
               "follow_up": follow_up}
    for key, value in updates.items():
        if str(value or "").strip():
            person[key] = str(value).strip()[:500]
    person["updated_at"] = _now()
    data["relationships"] = data["relationships"][-100:]
    save_brain(data)
    return dict(person)


def list_relationships() -> list[dict]:
    return [{k: row.get(k, "") for k in
             ("id", "name", "relation", "details", "important_date", "follow_up")}
            for row in load_brain()["relationships"]]


# 8. Conversation activities ------------------------------------------------

_ACTIVITY_RULES = {
    "story": "Tell an interactive story in short scenes. End each scene with one meaningful choice.",
    "quiz": "Run a five-question adaptive quiz, one question at a time, and explain answers gently.",
    "debate": "Take the requested opposing view respectfully, test reasoning, and summarize common ground.",
    "interview": "Act as a realistic interviewer, ask one question at a time, then give actionable feedback.",
    "language": "Run a natural role-play in the target language and correct mistakes without breaking flow.",
    "meditation": "Guide a calm, safety-conscious breathing or grounding exercise with unhurried pacing.",
    "motivation": "Give practical encouragement tied to the user's real goal and choose one immediate next step.",
    "game": "Start a family-friendly conversational game, state simple rules, and keep score when useful.",
}

_SURPRISE_RULES = {
    "mystery": "Open a tiny interactive mystery with one intriguing clue and ask what the user investigates first.",
    "brain_teaser": "Give one playful, fair brain teaser. Wait for an answer before revealing or explaining it.",
    "two_minute_challenge": "Offer a useful two-minute challenge that can be started immediately, then ask if they accept.",
    "would_you_rather": "Ask one imaginative, family-friendly would-you-rather question and react to the choice.",
    "interactive_story": "Begin a vivid interactive story in two or three sentences, then offer exactly two choices.",
}


def start_activity(kind: str, topic: str = "") -> str:
    kind = str(kind or "").strip().lower()
    if kind == "surprise":
        return start_surprise(topic)
    if kind not in _ACTIVITY_RULES:
        raise ValueError("Activity must be story, quiz, debate, interview, language, meditation, motivation, game, or surprise.")
    data = load_brain()
    data["activities"].append({"type": kind, "topic": topic.strip()[:160], "at": _now()})
    data["activities"] = data["activities"][-30:]
    save_brain(data)
    return _ACTIVITY_RULES[kind] + (f" Topic: {topic.strip()}." if topic.strip() else "")


def start_surprise(topic: str = "") -> str:
    """Pick a fresh, short interaction instead of delivering a passive monologue."""
    data = load_brain()
    recent = [row.get("variant") for row in data.get("activities", [])[-3:]
              if row.get("type") == "surprise"]
    choices = [key for key in _SURPRISE_RULES if key not in recent[-1:]] or list(_SURPRISE_RULES)
    variant = random.choice(choices)
    data["activities"].append({"type": "surprise", "variant": variant,
                               "topic": topic.strip()[:160], "at": _now()})
    data["activities"] = data["activities"][-30:]
    save_brain(data)
    extra = f" Gently weave in this interest: {topic.strip()}." if topic.strip() else ""
    return ("[SURPRISE MODE] " + _SURPRISE_RULES[variant] + extra +
            " Keep it under 25 seconds, use one consistent voice, and wait for the user's reply.")


# 9. Optional local voice identification -----------------------------------

def set_recent_voice_sample(audio: bytes, sample_rate: int) -> None:
    global _recent_voice
    if not audio:
        return
    with _voice_lock:
        _recent_voice = (bytes(audio[-sample_rate * 2 * 8:]), int(sample_rate))


def _voice_embedding(audio: bytes, sample_rate: int) -> list[float]:
    try:
        import numpy as np
    except ImportError as exc:
        raise ValueError("Local voice matching requires NumPy.") from exc
    values = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
    if values.size < sample_rate:
        raise ValueError("Please speak for at least two seconds before voice identification.")
    values -= float(values.mean())
    peak = float(np.max(np.abs(values))) or 1.0
    values /= peak
    frame = max(256, int(sample_rate * 0.025))
    hop = max(128, int(sample_rate * 0.0125))
    features = []
    energies = []
    window = np.hanning(frame)
    for start in range(0, values.size - frame, hop):
        block = values[start:start + frame]
        energy = float(np.sqrt(np.mean(block * block)))
        if energy < 0.025:
            continue
        spec = np.abs(np.fft.rfft(block * window, n=512)) + 1e-7
        freqs = np.fft.rfftfreq(512, 1.0 / sample_rate)
        bands = []
        edges = np.geomspace(80, min(7600, sample_rate / 2 - 10), 25)
        for lo, hi in zip(edges[:-1], edges[1:]):
            mask = (freqs >= lo) & (freqs < hi)
            bands.append(float(np.log(spec[mask].mean() + 1e-7)) if mask.any() else -16.0)
        centroid = float((freqs * spec).sum() / spec.sum()) / max(1.0, sample_rate / 2)
        zcr = float(np.mean(np.abs(np.diff(np.signbit(block)))))
        features.append(bands + [centroid, zcr])
        energies.append(energy)
    if len(features) < 20:
        raise ValueError("I need a clearer two-to-four second voice sample. Please try again in a quiet room.")
    matrix = np.asarray(features, dtype=np.float32)
    vector = np.concatenate([np.mean(matrix, axis=0), np.std(matrix, axis=0)])
    norm = float(np.linalg.norm(vector)) or 1.0
    return [round(float(value), 7) for value in vector / norm]


def enroll_recent_voice(consent: bool) -> dict:
    if not consent:
        raise ValueError("Voice enrollment needs the user's explicit consent because it stores a local biometric-style embedding.")
    with _voice_lock:
        sample = _recent_voice
    if sample is None:
        raise ValueError("No recent voice sample is available. Speak for a few seconds, then ask again.")
    embedding = _voice_embedding(*sample)
    data = load_brain()
    samples = data["voiceprint"].setdefault("samples", [])
    samples.append(embedding)
    data["voiceprint"]["samples"] = samples[-5:]
    data["voiceprint"]["updated_at"] = _now()
    save_brain(data)
    return {"profile": active_profile()["name"], "samples": len(data["voiceprint"]["samples"]),
            "note": "Convenience matching only; sensitive actions still require confirmation."}


def identify_recent_voice() -> dict:
    with _voice_lock:
        sample = _recent_voice
    if sample is None:
        raise ValueError("No recent voice sample is available.")
    query = _voice_embedding(*sample)
    scored = []
    for profile in list_profiles():
        brain = load_brain(profile["id"])
        templates = brain.get("voiceprint", {}).get("samples", [])
        if not templates:
            continue
        similarities = [sum(a * b for a, b in zip(query, template)) for template in templates]
        scored.append((max(similarities), profile))
    if not scored:
        return {"matched": False, "reason": "No profiles have an enrolled voice."}
    score, profile = max(scored, key=lambda item: item[0])
    # The lightweight local spectral signature is intentionally conservative.
    matched = score >= 0.965
    return {"matched": matched, "profile_id": profile["id"] if matched else "",
            "profile": profile["name"] if matched else "", "confidence": round(float(score), 3),
            "security": "convenience_only"}


def delete_voiceprint() -> None:
    data = load_brain()
    data["voiceprint"] = {"samples": [], "updated_at": ""}
    data["settings"]["voice_identification"] = False
    save_brain(data)


# 10. Daily intelligence ----------------------------------------------------

def daily_intelligence(review: str = "morning") -> dict:
    from memory.personal_hub import daily_plan
    review = "evening" if str(review).lower() == "evening" else "morning"
    data = load_brain()
    plan = daily_plan()
    mood = data["moods"][-1] if data["moods"] else None
    followups = [{"name": row.get("name"), "follow_up": row.get("follow_up")}
                 for row in data["relationships"] if row.get("follow_up")][:5]
    routines = [row for row in discover_routines() if row.get("decision") == "pending"][:3]
    snapshot = {"type": review, "generated_at": _now(), "plan": plan,
                "latest_mood": mood, "relationship_followups": followups,
                "routine_suggestions": routines,
                "knowledge_documents": len(data["knowledge"])}
    data["daily_reviews"].append({"type": review, "at": snapshot["generated_at"]})
    data["daily_reviews"] = data["daily_reviews"][-30:]
    save_brain(data)
    return snapshot


def prompt_context() -> str:
    data = load_brain()
    settings = data["settings"]
    lines = ["[LEARNING BRAIN]",
             "Apply explicit user corrections over older assumptions. Never claim a habit from one occurrence."]
    if settings.get("emotion_support") and data["moods"]:
        latest = data["moods"][-1]
        try:
            fresh = datetime.now() - datetime.fromisoformat(latest["at"]) < timedelta(hours=6)
        except Exception:
            fresh = False
        if fresh:
            lines.append(f"Recent emotional cue: {latest['mood']}. Acknowledge gently; do not diagnose or overstate it.")
    relationships = [row for row in data["relationships"] if row.get("follow_up")]
    if relationships:
        lines.append("Relationship follow-ups: " + "; ".join(
            f"{row['name']}: {row['follow_up']}" for row in relationships[-4:]))
    lines.append(f"Vision copilot privacy mode: {settings.get('vision_copilot', 'ask')}. "
                 "Never capture the screen continuously; ask before a new capture unless the user just requested it.")
    if settings.get("voice_identification"):
        lines.append("Optional local voice matching is enabled for profile convenience only, never security approval.")
    if data["knowledge"]:
        lines.append("Private knowledge vault titles: " + ", ".join(
            row.get("title", "Untitled") for row in data["knowledge"][-8:]))
    active_game = data.get("game_room", {}).get("active")
    if active_game:
        lines.append(
            f"Active Game Room session: {active_game.get('label', active_game.get('game'))}; "
            f"turn {active_game.get('turns', 0)}, score {active_game.get('score', 0)}. "
            "Continue from saved progress and ask only one game question or choice at a time."
        )
    lines.append("Learn routines by suggesting them first. Never auto-run a learned routine without approval.")
    return "\n".join(lines)
