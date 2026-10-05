"""core/app_paths.py — Centralized runtime data path management for CHARLIE.

Directs all writable runtime data (memory, logs, cache, profiles, RAG store)
to %APPDATA%\\CHARLIE (or CHARLIE_DATA_DIR override) in packaged production mode,
guaranteeing safe execution when installed under C:\\Program Files.
Preserves existing local paths in development mode unless explicitly configured.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Optional


def is_frozen() -> bool:
    """Check if running in a frozen PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def get_project_root() -> Path:
    """Return repository root directory in development mode."""
    return Path(__file__).resolve().parent.parent


def get_app_data_dir() -> Path:
    """Return root directory for writable user data.

    Packaged EXE: %APPDATA%\\CHARLIE (or %CHARLIE_DATA_DIR%).
    Development: Project root directory (or %CHARLIE_DATA_DIR% / %CHARLIE_USE_APPDATA%).
    """
    if "CHARLIE_DATA_DIR" in os.environ:
        d = Path(os.environ["CHARLIE_DATA_DIR"]).resolve()
        d.mkdir(parents=True, exist_ok=True)
        return d

    if is_frozen() or os.environ.get("CHARLIE_USE_APPDATA") == "1":
        appdata = os.environ.get("APPDATA")
        if appdata:
            d = Path(appdata) / "CHARLIE"
        else:
            d = Path.home() / ".charlie" / "CHARLIE"
    else:
        d = get_project_root()

    d.mkdir(parents=True, exist_ok=True)
    return d


def get_memory_dir() -> Path:
    """Directory for long-term memory, RAG store, and profile databases."""
    d = get_app_data_dir() / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_profile_dir() -> Path:
    """Directory for profile-scoped user state."""
    d = get_memory_dir() / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_log_dir() -> Path:
    """Directory for application runtime logs."""
    d = get_app_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_cache_dir() -> Path:
    """Directory for transient cache and temporary files."""
    d = get_app_data_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_config_dir() -> Path:
    """Directory for writable user configuration."""
    d = get_app_data_dir() / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_rag_db_path() -> Path:
    """Return canonical path to production RAG SQLite database."""
    return get_memory_dir() / "rag_store.sqlite3"


def migrate_rag_db_if_needed(target_path: Optional[Path] = None, source_path: Optional[Path] = None) -> bool:
    """Idempotently migrate existing RAG database if destination does not exist.

    1. Checks if target RAG database already exists. If yes, no-op (preserves newer).
    2. Checks legacy candidate locations (beside executable, in source tree, or custom source).
    3. Safely copies and verifies database integrity.
    4. Preserves source file.
    """
    dest = target_path or get_rag_db_path()
    if dest.exists() and dest.stat().st_size > 0:
        return True

    candidates = []
    if source_path:
        candidates.append(Path(source_path))
    if is_frozen():
        candidates.append(Path(sys.executable).parent / "memory" / "rag_store.sqlite3")
    candidates.append(get_project_root() / "memory" / "rag_store.sqlite3")

    for src in candidates:
        if src.exists() and src.resolve() != dest.resolve() and src.stat().st_size > 0:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    s_conn = sqlite3.connect(str(src))
                    try:
                        d_conn = sqlite3.connect(str(dest))
                        try:
                            s_conn.backup(d_conn)
                        finally:
                            d_conn.close()
                    finally:
                        s_conn.close()
                except Exception:
                    shutil.copy2(src, dest)

                # Verify target opens cleanly
                check_conn = sqlite3.connect(str(dest))
                try:
                    check_conn.execute("SELECT 1").fetchall()
                finally:
                    check_conn.close()
                return True
            except Exception:
                if dest.exists():
                    dest.unlink(missing_ok=True)
    return False

