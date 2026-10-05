"""memory/memory_manager.py — Core Memory Management for CHARLIE.

Maintains backward-compatible JSON caching alongside SQLite Engine synchronization.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from threading import Lock


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
# Legacy location retained as a non-destructive migration source. Runtime
# memory is resolved from the active family profile by get_memory_path().
MEMORY_PATH = BASE_DIR / "memory" / "long_term.json"
_lock = Lock()
MAX_VALUE_LENGTH = 380

MEMORY_MAX_CHARS = 300_000
PROMPT_CORE_CHARS = 1_400
PROMPT_INDEX_CHARS = 700
PROMPT_MAX_PER_CATEGORY = 8


def _empty_memory() -> dict:
    return {
        "identity": {},
        "preferences": {},
        "projects": {},
        "relationships": {},
        "wishes": {},
        "notes": {},
        "corrections": {},
    }


def get_memory_path() -> Path:
    try:
        from memory.profile_manager import profile_memory_path
        return profile_memory_path()
    except Exception:
        return MEMORY_PATH


def load_memory() -> dict:
    path = get_memory_path()
    if not path.exists():
        return _empty_memory()
    with _lock:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")
            return _empty_memory()


def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


_trim_notifier = None


def set_trim_notifier(fn) -> None:
    """Register a callable(str) that surfaces trims to the user."""
    global _trim_notifier
    _trim_notifier = fn


def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    dropped = []
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        dropped.append(f"{cat}/{key}")
        print(f"[Memory] [TRIMMED] {cat}/{key}")
    if dropped and _trim_notifier:
        try:
            _trim_notifier(
                f"SYS: Memory full — forgot {len(dropped)} oldest entries "
                f"({', '.join(dropped[:3])}{'…' if len(dropped) > 3 else ''})"
            )
        except Exception:
            pass
    return memory


def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    path = get_memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        path.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] [SAVED] {list(memory_update.keys())}")
        # Sync to persistent SQLite engine
        try:
            from engine.memory_manager import MemoryManager
            em = MemoryManager()
            for cat, items in memory_update.items():
                if isinstance(items, dict):
                    for k, v in items.items():
                        val = v.get("value") if isinstance(v, dict) else v
                        if val:
                            em.remember(cat, f"{k}: {val}")
        except Exception as e:
            print(f"[Memory] [NOTICE] SQLite sync notice: {e}")
    return memory


def _entry_value(entry) -> str:
    if isinstance(entry, dict):
        return str(entry.get("value", "") or "").strip()
    return str(entry or "").strip()


def _pretty(key: str) -> str:
    return key.replace("_", " ").strip()


_CATEGORY_LABELS = {
    "preferences": "Preferences",
    "projects": "Active projects / goals",
    "relationships": "People in their life",
    "wishes": "Wishes / plans",
    "notes": "Notes",
    "corrections": "User corrections (follow these over older assumptions)",
}

_IDENTITY_FIELDS = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]


def format_memory_for_prompt(memory: dict | None) -> str:
    """Build the memory block that goes into the system prompt."""
    if not memory:
        return ""

    core_lines: list[str] = []

    # 1. Identity - always, in full
    identity = memory.get("identity", {}) or {}
    for field in _IDENTITY_FIELDS:
        val = _entry_value(identity.get(field))
        if not val:
            continue
        if field == "language":
            core_lines.append(
                f"Has spoken to you in: {val} (an observation about the past — "
                f"always answer in the language of their CURRENT message)"
            )
        else:
            core_lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in _IDENTITY_FIELDS:
            continue
        val = _entry_value(entry)
        if val:
            core_lines.append(f"{_pretty(key).title()}: {val}")

    # 2. Everything else, most recently updated first
    rest: list[tuple[str, str, str, str]] = []  # (updated, cat, key, value)
    for cat in _CATEGORY_LABELS:
        for key, entry in (memory.get(cat, {}) or {}).items():
            val = _entry_value(entry)
            if not val:
                continue
            updated = (entry.get("updated", "") if isinstance(entry, dict) else "") or "0000-00-00"
            rest.append((updated, cat, key, val))
    rest.sort(key=lambda t: t[0], reverse=True)

    budget = PROMPT_CORE_CHARS
    chosen_lines: list[str] = []
    indexed_keys: list[tuple[str, str]] = []
    category_counts: dict[str, int] = {}

    for _updated, cat, key, val in rest:
        count = category_counts.get(cat, 0)
        line = f"- {_pretty(key)}: {val}"
        line_len = len(line) + 1
        if count < PROMPT_MAX_PER_CATEGORY and line_len <= budget:
            chosen_lines.append((cat, line))
            budget -= line_len
            category_counts[cat] = count + 1
        else:
            indexed_keys.append((cat, _pretty(key)))

    by_cat: dict[str, list[str]] = {}
    for cat, line in chosen_lines:
        by_cat.setdefault(cat, []).append(line)

    for cat in _CATEGORY_LABELS:
        lines = by_cat.get(cat, [])
        if not lines:
            continue
        core_lines.append(f"\n[{_CATEGORY_LABELS[cat].upper()}]")
        core_lines.extend(lines)

    # 3. Index of remaining stored keys
    if indexed_keys:
        idx_budget = PROMPT_INDEX_CHARS
        idx_cats: dict[str, list[str]] = {}
        for cat, key in indexed_keys:
            frag = key if not idx_cats.get(cat) else f", {key}"
            if len(frag) > idx_budget:
                break
            idx_cats.setdefault(cat, []).append(key)
            idx_budget -= len(frag)
        if idx_cats:
            core_lines.append("\n[ALSO REMEMBERED — call recall_memory to read values]")
            for cat, keys in idx_cats.items():
                lbl = _CATEGORY_LABELS.get(cat, cat.title())
                core_lines.append(f"- {lbl}: {', '.join(keys)}")

    return "\n".join(core_lines).strip()


def _score(words: list[str], cat: str, key: str, val: str) -> int:
    text = f"{cat} {key} {val}".lower()
    return sum(1 for w in words if w in text)


def search_memory(query: str, limit: int = 8) -> str:
    """Find stored facts matching `query`. Backs the recall_memory tool."""
    # First query SQLite semantic engine
    try:
        from engine.memory_manager import MemoryManager
        em = MemoryManager()
        res = em.recall(query, limit=limit)
        if res and not res.startswith("No remembered records"):
            return res
    except Exception:
        pass

    # Fallback to local dict scan
    memory = load_memory()
    words = [w for w in re.split(r"[^\w]+", (query or "").lower()) if len(w) > 1]

    rows: list[tuple[int, str, str, str]] = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            s = _score(words, cat, key, val) if words else 1
            if s > 0:
                rows.append((s, cat, key, val))

    if not rows:
        return f"Nothing stored about '{query}'." if query else "I have not stored anything about this person yet."

    rows.sort(key=lambda r: (-r[0], r[2]))
    lines = [f"{cat}/{_pretty(key)}: {val}" for _s, cat, key, val in rows[: max(1, limit)]]
    head = f"Stored facts matching '{query}':" if query else "Everything currently stored:"
    more = f"\n(+{len(rows) - len(lines)} more — search with a narrower keyword)" if len(rows) > len(lines) else ""
    return head + "\n" + "\n".join(lines) + more


def all_entries_for_ui() -> list[dict]:
    memory = load_memory()
    rows = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            rows.append({
                "category": cat,
                "key": key,
                "value": val,
                "updated": (entry.get("updated", "") if isinstance(entry, dict) else ""),
            })
    rows.sort(key=lambda r: (r["updated"] or "0000-00-00"), reverse=True)
    return rows


def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes", "corrections"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget

_SESSION_MAX = 3


def save_session_summary(summary: str, language: str = "") -> None:
    summary = (summary or "").strip()
    if not summary:
        return
    memory = load_memory()
    sessions = memory.get("sessions", [])
    if not isinstance(sessions, list):
        sessions = []
    entry: dict = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": summary[:280],
    }
    if language:
        entry["language"] = language
    sessions.append(entry)
    memory["sessions"] = sessions[-_SESSION_MAX:]
    path = get_memory_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    print(f"[Memory] [SESSION_SAVED] ({entry['date']}): {summary[:60]}...")


def pop_last_session() -> dict | None:
    path = get_memory_path()
    with _lock:
        if not path.exists():
            return None
        try:
            memory = json.loads(path.read_text(encoding="utf-8"))
            sessions = memory.get("sessions", [])
            if not isinstance(sessions, list) or not sessions:
                return None
            entry = sessions.pop()
            memory["sessions"] = sessions
            path.write_text(
                json.dumps(memory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return entry
        except Exception as e:
            print(f"[Memory] [ERROR] pop_last_session error: {e}")
            return None
