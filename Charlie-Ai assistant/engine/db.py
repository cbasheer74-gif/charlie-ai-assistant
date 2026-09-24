"""engine/db.py — Persistent SQLite storage for JARVIS Intelligence Engine.

Provides thread-safe connections, schema management, and secret redaction.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
DB_PATH = BASE_DIR / "memory" / "charlie_memory.db"
_LEGACY_DB_PATH = BASE_DIR / "memory" / "jarvis_memory.db"
if not DB_PATH.exists() and _LEGACY_DB_PATH.exists():
    try:
        import shutil
        shutil.copy2(_LEGACY_DB_PATH, DB_PATH)
    except Exception:
        pass

_DB_LOCK = threading.RLock()

_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token|auth[_-]?token|bearer|otp|private[_-]?key)\s*[:=]\s*['\"]?([^'\"\s,;]+)"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"AIzaSy[a-zA-Z0-9_-]{33}"),
]


def get_default_db_path() -> Path:
    """Resolve the active profile's database; fall back during early bootstrap."""
    try:
        from memory.profile_manager import profile_dir
        p_db = profile_dir() / "charlie_memory.db"
        if not p_db.exists():
            legacy_p_db = profile_dir() / "jarvis_memory.db"
            if legacy_p_db.exists():
                return legacy_p_db
        return p_db
    except Exception:
        return DB_PATH


def redact_secrets(text: str) -> str:
    """Mask any passwords, API keys, OTPs or bearer tokens before persistence."""
    if not text or not isinstance(text, str):
        return text
    clean = text
    for pattern in _SECRET_PATTERNS:
        clean = pattern.sub(r"[REDACTED_SECRET]", clean)
    return clean


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_db(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Provide a thread-safe SQLite connection with foreign keys and WAL mode."""
    target_path = Path(db_path) if db_path else get_default_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with _DB_LOCK:
        conn = sqlite3.connect(
            str(target_path),
            timeout=30.0,
            check_same_thread=False,
            isolation_level=None,  # autocommit mode
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            yield conn
        finally:
            conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize all schema tables and indices if not already existing."""
    with get_db(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_memories (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'default_user',
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                importance REAL NOT NULL DEFAULT 5.0,
                confidence REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'interaction',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed_at TEXT,
                access_count INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_user_memories_cat ON user_memories(category, is_active);
            CREATE INDEX IF NOT EXISTS idx_user_memories_active ON user_memories(is_active, importance);

            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                root_path TEXT DEFAULT '',
                project_type TEXT DEFAULT 'general',
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_opened_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);

            CREATE TABLE IF NOT EXISTS project_memories (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                importance REAL NOT NULL DEFAULT 5.0,
                confidence REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'interaction',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                UNIQUE(project_id, category, key)
            );
            CREATE INDEX IF NOT EXISTS idx_proj_mem_cat ON project_memories(project_id, category, is_active);

            CREATE TABLE IF NOT EXISTS task_memories (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                task_name TEXT NOT NULL,
                goal TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                summary TEXT DEFAULT '',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                last_checkpoint TEXT DEFAULT '',
                next_action TEXT DEFAULT '',
                steps_json TEXT DEFAULT '[]',
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_task_mem_status ON task_memories(status);

            CREATE TABLE IF NOT EXISTS procedural_memories (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                intent TEXT NOT NULL,
                steps_json TEXT NOT NULL DEFAULT '[]',
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_success TEXT,
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_procedural_intent ON procedural_memories(intent);

            CREATE TABLE IF NOT EXISTS error_memories (
                id TEXT PRIMARY KEY,
                error_signature TEXT NOT NULL UNIQUE,
                application TEXT DEFAULT '',
                project_id TEXT,
                root_cause TEXT DEFAULT '',
                failed_attempts_json TEXT DEFAULT '[]',
                successful_fix TEXT DEFAULT '',
                verification TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                occurrence_count INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_error_mem_sig ON error_memories(error_signature);

            CREATE TABLE IF NOT EXISTS conversation_summaries (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                important_entities_json TEXT DEFAULT '{}',
                decisions_json TEXT DEFAULT '[]',
                pending_actions_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_execution_history (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                tool_name TEXT NOT NULL,
                arguments_summary TEXT DEFAULT '',
                result_summary TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'completed',
                duration REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tool_history_tool ON tool_execution_history(tool_name, status);

            CREATE TABLE IF NOT EXISTS memory_embeddings (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(entity_type, entity_id)
            );
            CREATE INDEX IF NOT EXISTS idx_embeddings_entity ON memory_embeddings(entity_type, entity_id);
            """
        )
        # Ensure default user exists
        now = utc_now_iso()
        conn.execute(
            """
            INSERT OR IGNORE INTO users (id, display_name, created_at, updated_at)
            VALUES ('default_user', 'User', ?, ?)
            """,
            (now, now),
        )


def migrate_from_json_if_needed(db_path: Optional[Path] = None, json_path: Optional[Path] = None) -> int:
    """Migrate legacy long_term.json to SQLite if long_term.json exists and DB is empty."""
    if json_path:
        j_path = Path(json_path)
    else:
        try:
            from memory.profile_manager import profile_memory_path
            j_path = profile_memory_path()
        except Exception:
            j_path = BASE_DIR / "memory" / "long_term.json"
    if not j_path.exists():
        return 0

    init_db(db_path)
    with get_db(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM user_memories;").fetchone()[0]
        if count > 0:
            return 0  # already populated

        try:
            data = json.loads(j_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return 0
        except Exception:
            return 0

        now = utc_now_iso()
        migrated = 0
        import uuid

        conn.execute("BEGIN IMMEDIATE;")
        for category, items in data.items():
            if not isinstance(items, dict):
                continue
            for key, entry in items.items():
                val = ""
                if isinstance(entry, dict):
                    val = str(entry.get("value", "") or "").strip()
                else:
                    val = str(entry or "").strip()
                if not val:
                    continue

                val = redact_secrets(val)
                mem_id = f"mig_{uuid.uuid4().hex[:12]}"
                content = f"{key}: {val}" if category in ("identity", "preferences") else val
                conn.execute(
                    """
                    INSERT INTO user_memories (
                        id, user_id, category, content, importance, confidence,
                        source, created_at, updated_at, last_accessed_at, access_count, is_active
                    ) VALUES (?, 'default_user', ?, ?, 6.0, 1.0, 'migration', ?, ?, ?, 1, 1);
                    """,
                    (mem_id, category, content, now, now, now),
                )
                migrated += 1
        conn.execute("COMMIT;")
        return migrated
