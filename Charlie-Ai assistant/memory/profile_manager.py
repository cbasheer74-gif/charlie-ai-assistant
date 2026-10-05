"""Profile-scoped identity and storage for CHARLIE.

The registry contains no secrets. Each profile gets its own directory so
conversation memory, goals, plans and meeting notes cannot bleed between
family members.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


from core.app_paths import get_memory_dir, get_profile_dir

MEMORY_DIR = get_memory_dir()
PROFILES_DIR = get_profile_dir()
REGISTRY_PATH = MEMORY_DIR / "profiles.json"
LEGACY_MEMORY_PATH = MEMORY_DIR / "long_term.json"
LEGACY_DB_PATH = MEMORY_DIR / "charlie_memory.db"
_OLD_JARVIS_DB_PATH = MEMORY_DIR / "jarvis_memory.db"
_lock = RLock()
_change_notifier = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return value[:40] or "primary"


def _profile_name_from_config() -> str:
    try:
        from memory.config_manager import get_user_name
        return get_user_name().strip() or "Primary user"
    except Exception:
        return "Primary user"


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _copy_sqlite(source: Path, target: Path) -> None:
    """Snapshot SQLite safely, including any committed WAL pages."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        src = sqlite3.connect(str(source))
        try:
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except Exception:
        target.unlink(missing_ok=True)
        shutil.copy2(source, target)


def _initial_registry() -> dict:
    name = _profile_name_from_config()
    profile_id = _slug(name)
    return {
        "version": 1,
        "active_profile": profile_id,
        "profiles": {
            profile_id: {
                "id": profile_id,
                "name": name,
                "created_at": _now(),
            }
        },
    }


def _ensure_registry() -> dict:
    with _lock:
        data = None
        if not REGISTRY_PATH.exists():
            legacy_cands = []
            if getattr(sys, "frozen", False):
                legacy_cands.append(Path(sys.executable).parent / "memory" / "profiles.json")
            legacy_cands.append(Path(__file__).resolve().parent.parent / "memory" / "profiles.json")
            for c in legacy_cands:
                if c.exists() and c.resolve() != REGISTRY_PATH.resolve():
                    try:
                        shutil.copy2(c, REGISTRY_PATH)
                        break
                    except Exception:
                        pass

        if REGISTRY_PATH.exists():
            try:
                candidate = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
                if isinstance(candidate, dict) and isinstance(candidate.get("profiles"), dict):
                    data = candidate
            except Exception:
                data = None
        if not data:
            data = _initial_registry()
            _atomic_write(REGISTRY_PATH, data)

        active = str(data.get("active_profile") or "")
        if active not in data["profiles"]:
            active = next(iter(data["profiles"]), "primary")
            data["active_profile"] = active
            _atomic_write(REGISTRY_PATH, data)

        profile_dir(active).mkdir(parents=True, exist_ok=True)
        target = profile_memory_path(active)
        if not target.exists() and LEGACY_MEMORY_PATH.exists():
            # Non-destructive first-run migration. The legacy file stays as a
            # rollback copy, but all future reads/writes use the profile path.
            shutil.copy2(LEGACY_MEMORY_PATH, target)
        profile_db = profile_dir(active) / "charlie_memory.db"
        if not profile_db.exists():
            old_profile_db = profile_dir(active) / "jarvis_memory.db"
            if old_profile_db.exists():
                _copy_sqlite(old_profile_db, profile_db)
            elif LEGACY_DB_PATH.exists():
                _copy_sqlite(LEGACY_DB_PATH, profile_db)
            elif _OLD_JARVIS_DB_PATH.exists():
                _copy_sqlite(_OLD_JARVIS_DB_PATH, profile_db)
        return data


def load_profiles() -> dict:
    data = _ensure_registry()
    return json.loads(json.dumps(data))


def active_profile_id() -> str:
    return str(_ensure_registry()["active_profile"])


def active_profile() -> dict:
    data = _ensure_registry()
    return dict(data["profiles"][data["active_profile"]])


_EDITABLE_PROFILE_FIELDS = {
    "name": 60,
    "email": 254,
    "phone": 30,
    "date_of_birth": 20,
    "pronouns": 40,
    "occupation": 100,
    "location": 120,
    "language": 60,
    "timezone": 60,
    "notes": 500,
}


def update_active_profile(details: dict) -> dict:
    """Update safe, user-editable details for the active local profile."""
    if not isinstance(details, dict):
        raise ValueError("Profile details must be provided as a mapping.")
    cleaned: dict[str, str] = {}
    for key, limit in _EDITABLE_PROFILE_FIELDS.items():
        value = " ".join(str(details.get(key) or "").split())[:limit]
        cleaned[key] = value
    if not cleaned["name"]:
        raise ValueError("Full name is required.")
    email = cleaned["email"].lower()
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Enter a valid email address.")
    cleaned["email"] = email

    with _lock:
        data = _ensure_registry()
        profile_id = data["active_profile"]
        data["profiles"][profile_id].update(cleaned)
        data["profiles"][profile_id]["updated_at"] = _now()
        _atomic_write(REGISTRY_PATH, data)
        record = dict(data["profiles"][profile_id])
    if _change_notifier:
        try:
            _change_notifier(record)
        except Exception:
            pass
    return record


def profile_dir(profile_id: str | None = None) -> Path:
    return PROFILES_DIR / _slug(profile_id or active_profile_id())


def profile_memory_path(profile_id: str | None = None) -> Path:
    return profile_dir(profile_id) / "long_term.json"


def profile_hub_path(profile_id: str | None = None) -> Path:
    return profile_dir(profile_id) / "personal_hub.json"


def profile_learning_path(profile_id: str | None = None) -> Path:
    return profile_dir(profile_id) / "learning_brain.json"


def list_profiles() -> list[dict]:
    data = _ensure_registry()
    active = data["active_profile"]
    return [dict(value, active=(key == active)) for key, value in data["profiles"].items()]


def create_profile(name: str) -> dict:
    clean_name = " ".join(str(name or "").split())[:60]
    if not clean_name:
        raise ValueError("Profile name is required.")
    with _lock:
        data = _ensure_registry()
        base = _slug(clean_name)
        profile_id = base
        suffix = 2
        while profile_id in data["profiles"]:
            existing = data["profiles"][profile_id]
            if existing.get("name", "").casefold() == clean_name.casefold():
                return dict(existing)
            profile_id = f"{base}-{suffix}"
            suffix += 1
        record = {"id": profile_id, "name": clean_name, "created_at": _now()}
        data["profiles"][profile_id] = record
        _atomic_write(REGISTRY_PATH, data)
        profile_dir(profile_id).mkdir(parents=True, exist_ok=True)
        return dict(record)


def switch_profile(identifier: str) -> dict:
    wanted = str(identifier or "").strip().casefold()
    with _lock:
        data = _ensure_registry()
        selected = None
        for key, record in data["profiles"].items():
            if wanted in {key.casefold(), str(record.get("name", "")).casefold()}:
                selected = key
                break
        if selected is None:
            raise ValueError(f"No profile named '{identifier}'.")
        changed = selected != data["active_profile"]
        data["active_profile"] = selected
        _atomic_write(REGISTRY_PATH, data)
        profile_dir(selected).mkdir(parents=True, exist_ok=True)
        record = dict(data["profiles"][selected])
    # Module-level MemoryManager instances resolve db_path dynamically, but a
    # newly selected profile still needs its schema before the next tool call.
    try:
        from engine.db import init_db, migrate_from_json_if_needed
        init_db()
        migrate_from_json_if_needed(json_path=profile_memory_path(selected))
    except Exception:
        pass
    if changed and _change_notifier:
        try:
            _change_notifier(record)
        except Exception:
            pass
    return record


def set_change_notifier(callback) -> None:
    global _change_notifier
    _change_notifier = callback


def notify_context_change() -> None:
    """Ask the live session to reload active-profile context, if it is running."""
    if _change_notifier:
        try:
            _change_notifier(active_profile())
        except Exception:
            pass
