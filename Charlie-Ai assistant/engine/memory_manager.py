"""engine/memory_manager.py — Central Memory Engine for JARVIS.

Manages users, project states, task checkpoints, procedural memory,
error solutions, semantic search, and deduplication/superseding.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.db import get_db, init_db, migrate_from_json_if_needed, redact_secrets, utc_now_iso
from engine.semantic import SemanticEngine, cosine_similarity


class MemoryManager:
    """Unified memory manager with SQLite persistence and semantic retrieval."""

    def __init__(self, db_path: Optional[Path] = None, api_key: Optional[str] = None):
        self.db_path = db_path
        init_db(self.db_path)
        migrate_from_json_if_needed(self.db_path)
        self.semantic = SemanticEngine(api_key=api_key)

    # ── User Memory ──────────────────────────────────────────────────────────

    def remember(
        self,
        category: str,
        content: str,
        importance: float = 5.0,
        user_id: str = "default_user",
        source: str = "interaction",
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        """Store a user memory with automatic secret redaction and deduplication."""
        clean_content = redact_secrets(content.strip())
        if not clean_content:
            return {}

        now = utc_now_iso()
        vec = self.semantic.get_embedding(clean_content)

        with get_db(self.db_path) as conn:
            # Check for existing active memory in this category to prevent duplicate explosion
            existing = conn.execute(
                """
                SELECT id, content, importance, access_count, updated_at
                FROM user_memories
                WHERE user_id = ? AND category = ? AND is_active = 1;
                """,
                (user_id, category),
            ).fetchall()

            for row in existing:
                row_vec = self._get_stored_embedding(conn, "user_memory", row["id"])
                if row_vec and cosine_similarity(vec, row_vec) > 0.88:
                    # Update existing record: bump access count & update timestamp
                    new_imp = max(float(row["importance"]), float(importance))
                    conn.execute(
                        """
                        UPDATE user_memories
                        SET content = ?, importance = ?, updated_at = ?, access_count = access_count + 1
                        WHERE id = ?;
                        """,
                        (clean_content, new_imp, now, row["id"]),
                    )
                    self._save_embedding(conn, "user_memory", row["id"], vec)
                    return {"id": row["id"], "action": "updated", "content": clean_content}

            # Insert new record
            mem_id = f"mem_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO user_memories (
                    id, user_id, category, content, importance, confidence, source,
                    created_at, updated_at, last_accessed_at, access_count, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1);
                """,
                (mem_id, user_id, category, clean_content, float(importance), float(confidence), source, now, now, now),
            )
            self._save_embedding(conn, "user_memory", mem_id, vec)
            return {"id": mem_id, "action": "created", "content": clean_content}

    def supersede_memory(self, old_memory_id: str, new_content: str, category: Optional[str] = None) -> bool:
        """Mark an older memory as superseded and create the replacement."""
        clean_new = redact_secrets(new_content.strip())
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            old = conn.execute(
                "SELECT user_id, category, importance FROM user_memories WHERE id = ?;",
                (old_memory_id,),
            ).fetchone()
            if not old:
                return False

            conn.execute(
                "UPDATE user_memories SET is_active = 0, updated_at = ? WHERE id = ?;",
                (now, old_memory_id),
            )
            cat = category or old["category"]
            self.remember(cat, clean_new, importance=old["importance"], user_id=old["user_id"])
            return True

    def forget_memory(self, memory_id: str) -> bool:
        """Deactivate or remove a memory by ID."""
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE user_memories SET is_active = 0, updated_at = ? WHERE id = ?;",
                (now, memory_id),
            )
            return cur.rowcount > 0

    # ── Project Memory ───────────────────────────────────────────────────────

    def register_or_get_project(self, name: str, root_path: str = "", project_type: str = "general") -> Dict[str, Any]:
        """Ensure a project exists and return its metadata."""
        now = utc_now_iso()
        with get_db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM projects WHERE name = ?;", (name.strip(),)).fetchone()
            if row:
                if root_path and not row["root_path"]:
                    conn.execute(
                        "UPDATE projects SET root_path = ?, updated_at = ?, last_opened_at = ? WHERE id = ?;",
                        (root_path, now, now, row["id"]),
                    )
                else:
                    conn.execute("UPDATE projects SET last_opened_at = ? WHERE id = ?;", (now, row["id"]))
                return dict(row)

            proj_id = f"proj_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO projects (id, name, description, root_path, project_type, status, created_at, updated_at, last_opened_at)
                VALUES (?, ?, '', ?, ?, 'active', ?, ?, ?);
                """,
                (proj_id, name.strip(), root_path, project_type, now, now, now),
            )
            return {
                "id": proj_id,
                "name": name.strip(),
                "root_path": root_path,
                "project_type": project_type,
                "status": "active",
            }

    def set_project_memory(
        self,
        project_name: str,
        category: str,
        key: str,
        value: str,
        importance: float = 6.0,
    ) -> bool:
        """Set a project-specific key-value fact (e.g. port, tech_stack, architecture)."""
        proj = self.register_or_get_project(project_name)
        now = utc_now_iso()
        clean_val = redact_secrets(value.strip())
        mem_id = f"pmem_{uuid.uuid4().hex[:12]}"

        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO project_memories (
                    id, project_id, category, key, value, importance, confidence,
                    source, created_at, updated_at, last_accessed_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, 1.0, 'user', ?, ?, ?, 1)
                ON CONFLICT(project_id, category, key) DO UPDATE SET
                    value = excluded.value,
                    importance = excluded.importance,
                    updated_at = excluded.updated_at,
                    is_active = 1;
                """,
                (mem_id, proj["id"], category, key, clean_val, float(importance), now, now, now),
            )
            return True

    def get_project_context(self, project_name: Optional[str] = None) -> Dict[str, Any]:
        """Fetch all facts and recent task status for a project."""
        with get_db(self.db_path) as conn:
            if project_name:
                proj = conn.execute("SELECT * FROM projects WHERE name = ?;", (project_name.strip(),)).fetchone()
            else:
                proj = conn.execute("SELECT * FROM projects ORDER BY last_opened_at DESC LIMIT 1;").fetchone()
            if not proj:
                return {}

            mems = conn.execute(
                "SELECT category, key, value, importance FROM project_memories WHERE project_id = ? AND is_active = 1;",
                (proj["id"],),
            ).fetchall()

            facts = {}
            for m in mems:
                facts.setdefault(m["category"], {})[m["key"]] = m["value"]

            last_task = conn.execute(
                "SELECT * FROM task_memories WHERE project_id = ? ORDER BY started_at DESC LIMIT 1;",
                (proj["id"],),
            ).fetchone()

            return {
                "project": dict(proj),
                "facts": facts,
                "last_task": dict(last_task) if last_task else None,
            }

    # ── Task Checkpointing ───────────────────────────────────────────────────

    def create_task(
        self,
        task_name: str,
        goal: str,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        """Initialize a new durable task record."""
        now = utc_now_iso()
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        proj_id = None
        target_proj = project_name or project_id
        if target_proj:
            proj = self.register_or_get_project(target_proj)
            proj_id = proj["id"]


        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO task_memories (
                    id, project_id, task_name, goal, status, summary, started_at, last_checkpoint, next_action
                ) VALUES (?, ?, ?, ?, 'RUNNING', '', ?, 'Started', '');
                """,
                (task_id, proj_id, task_name, goal, now),
            )
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Fetch task memory record by ID."""
        with get_db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM task_memories WHERE id = ?;", (task_id,)).fetchone()
            return dict(row) if row else None


    def store_task_checkpoint(
        self,
        task_id: str,
        checkpoint_name: Optional[str] = None,
        summary: str = "",
        next_action: str = "",
        status: str = "RUNNING",
        checkpoint_data: Optional[Any] = None,
    ) -> bool:
        """Update task checkpoint so execution can resume across restarts."""
        now = utc_now_iso()
        if checkpoint_data is not None and not checkpoint_name:
            checkpoint_name = json.dumps(checkpoint_data, ensure_ascii=False) if isinstance(checkpoint_data, (dict, list)) else str(checkpoint_data)
        checkpoint_val = checkpoint_name or "Checkpoint"
        with get_db(self.db_path) as conn:
            completed_at = now if status in ("COMPLETED", "FAILED") else None
            cur = conn.execute(
                """
                UPDATE task_memories
                SET last_checkpoint = ?, summary = ?, next_action = ?, status = ?, completed_at = coalesce(?, completed_at)
                WHERE id = ?;
                """,
                (checkpoint_val, summary, next_action, status, completed_at, task_id),
            )
            return cur.rowcount > 0

    def get_recent_task_context(self, project_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve latest active or interrupted task."""
        with get_db(self.db_path) as conn:
            if project_name:
                row = conn.execute(
                    """
                    SELECT t.*, p.name as project_name
                    FROM task_memories t
                    JOIN projects p ON t.project_id = p.id
                    WHERE p.name = ?
                    ORDER BY t.started_at DESC LIMIT 1;
                    """,
                    (project_name,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT t.*, p.name as project_name
                    FROM task_memories t
                    LEFT JOIN projects p ON t.project_id = p.id
                    ORDER BY t.started_at DESC LIMIT 1;
                    """
                ).fetchone()
            return dict(row) if row else None

    def resume_task(self, project_name: Optional[str] = None, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve most recent incomplete or active task for resuming."""
        return self.get_recent_task_context(project_name=project_name or project_id)


    # ── Procedural & Error Memory ────────────────────────────────────────────

    def store_successful_procedure(self, name: str, intent: str, steps: List[str]) -> bool:
        """Store a proven multi-step workflow for future reuse."""
        now = utc_now_iso()
        steps_json = json.dumps(steps, ensure_ascii=False)
        proc_id = f"proc_{uuid.uuid4().hex[:12]}"
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO procedural_memories (
                    id, name, intent, steps_json, success_count, last_success, confidence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, 1.0, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    steps_json = excluded.steps_json,
                    success_count = success_count + 1,
                    last_success = excluded.last_success,
                    updated_at = excluded.updated_at;
                """,
                (proc_id, name, intent, steps_json, now, now, now),
            )
            return True

    def get_procedure(self, intent_or_name: str) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM procedural_memories
                WHERE name = ? OR intent LIKE ?
                ORDER BY success_count DESC LIMIT 1;
                """,
                (intent_or_name, f"%{intent_or_name}%"),
            ).fetchone()
            if row:
                res = dict(row)
                res["steps"] = json.loads(res.get("steps_json") or "[]")
                return res
            return None

    def store_error_solution(
        self,
        error_signature: str,
        root_cause: str = "",
        successful_fix: str = "",
        application: str = "",
        project_name: Optional[str] = None,
        verification: str = "",
        failed_attempts: Optional[List[str]] = None,
        solution: Optional[str] = None,
    ) -> bool:
        """Store verified bugfix knowledge in error_memories."""
        if solution and not successful_fix:
            successful_fix = solution
        now = utc_now_iso()
        proj_id = None
        if project_name:
            proj = self.register_or_get_project(project_name)
            proj_id = proj["id"]

        failed_json = json.dumps(failed_attempts or [], ensure_ascii=False)
        err_id = f"err_{uuid.uuid4().hex[:12]}"

        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO error_memories (
                    id, error_signature, application, project_id, root_cause,
                    failed_attempts_json, successful_fix, verification, created_at, last_seen_at, occurrence_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(error_signature) DO UPDATE SET
                    root_cause = excluded.root_cause,
                    successful_fix = excluded.successful_fix,
                    verification = excluded.verification,
                    last_seen_at = excluded.last_seen_at,
                    occurrence_count = occurrence_count + 1;
                """,
                (err_id, error_signature, application, proj_id, root_cause, failed_json, successful_fix, verification, now, now),
            )
            return True

    def find_error_solution(self, error_signature_or_text: str) -> Optional[Dict[str, Any]]:
        """Search error memory for known working fixes."""
        clean = error_signature_or_text.strip()
        with get_db(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM error_memories
                WHERE error_signature = ? OR ? LIKE ('%' || error_signature || '%')
                ORDER BY occurrence_count DESC LIMIT 1;
                """,
                (clean, clean),
            ).fetchone()
            return dict(row) if row else None

    # ── Search & Recall ──────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        project_name: Optional[str] = None,
        memory_types: Optional[List[str]] = None,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        """Ranked semantic search across user and project memories."""
        clean_q = query.strip()
        if not clean_q:
            return []

        q_vec = self.semantic.get_embedding(clean_q)
        results = []

        with get_db(self.db_path) as conn:
            # 1. Search User Memories
            rows = conn.execute(
                "SELECT id, category, content, importance, updated_at, access_count FROM user_memories WHERE is_active = 1;"
            ).fetchall()

            for r in rows:
                vec = self._get_stored_embedding(conn, "user_memory", r["id"])
                sim = cosine_similarity(q_vec, vec) if vec else 0.1
                score = self.semantic.compute_ranking_score(
                    semantic_sim=sim,
                    importance=r["importance"],
                    updated_at_iso=r["updated_at"],
                    is_current_project=False,
                    access_count=r["access_count"],
                )
                if score > 0.18 or sim > 0.35:
                    results.append({
                        "type": "user_memory",
                        "category": r["category"],
                        "content": r["content"],
                        "score": score,
                        "similarity": sim,
                    })

            # 2. Search Project Memories
            p_rows = conn.execute(
                """
                SELECT pm.id, pm.category, pm.key, pm.value, pm.importance, pm.updated_at, p.name as project_name
                FROM project_memories pm
                JOIN projects p ON pm.project_id = p.id
                WHERE pm.is_active = 1;
                """
            ).fetchall()

            for pr in p_rows:
                content = f"{pr['category']}: {pr['key']} = {pr['value']}"
                vec = self.semantic.get_embedding(content)
                sim = cosine_similarity(q_vec, vec)
                is_curr = bool(project_name and pr["project_name"].lower() == project_name.lower())
                score = self.semantic.compute_ranking_score(
                    semantic_sim=sim,
                    importance=pr["importance"],
                    updated_at_iso=pr["updated_at"],
                    is_current_project=is_curr,
                    access_count=2,
                )
                if score > 0.18 or sim > 0.35:
                    results.append({
                        "type": "project_memory",
                        "project": pr["project_name"],
                        "category": pr["category"],
                        "content": content,
                        "score": score,
                        "similarity": sim,
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def recall(self, query: str, project_name: Optional[str] = None, limit: int = 8) -> str:
        """Return formatted string answer for recall_memory tool."""
        res = self.search(query, project_name=project_name, limit=limit)
        if not res:
            return f"No remembered records found for '{query}'."
        lines = [f"Found {len(res)} relevant memory record(s):"]
        for i, item in enumerate(res, 1):
            prefix = f"[{item.get('project', 'USER')}:{item.get('category', 'general')}]"
            lines.append(f"{i}. {prefix} {item['content']}")
        return "\n".join(lines)

    # ── Legacy Adapter & Prompt Formatting ───────────────────────────────────

    def to_legacy_dict(self) -> Dict[str, Dict[str, Any]]:
        """Export SQLite user memories into dict structure expected by older modules."""
        out = {
            "identity": {},
            "preferences": {},
            "projects": {},
            "relationships": {},
            "wishes": {},
            "notes": {},
            "corrections": {},
        }
        with get_db(self.db_path) as conn:
            rows = conn.execute(
                "SELECT category, content, updated_at FROM user_memories WHERE is_active = 1 ORDER BY updated_at DESC;"
            ).fetchall()
            for r in rows:
                cat = r["category"]
                if cat not in out:
                    out[cat] = {}
                # Split key: value if formatted
                raw = r["content"]
                if ": " in raw:
                    k, v = raw.split(": ", 1)
                else:
                    k, v = f"item_{len(out[cat]) + 1}", raw
                out[cat][k] = {"value": v, "updated": r["updated_at"][:10]}
        return out

    # ── Internal Embedding Storage Helpers ───────────────────────────────────

    def _get_stored_embedding(self, conn: sqlite3.Connection, entity_type: str, entity_id: str) -> Optional[List[float]]:
        row = conn.execute(
            "SELECT vector_json FROM memory_embeddings WHERE entity_type = ? AND entity_id = ?;",
            (entity_type, entity_id),
        ).fetchone()
        if row and row["vector_json"]:
            try:
                return json.loads(row["vector_json"])
            except Exception:
                pass
        return None

    def _save_embedding(self, conn: sqlite3.Connection, entity_type: str, entity_id: str, vector: List[float]) -> None:
        now = utc_now_iso()
        vec_json = json.dumps(vector)
        conn.execute(
            """
            INSERT INTO memory_embeddings (id, entity_type, entity_id, vector_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                vector_json = excluded.vector_json,
                created_at = excluded.created_at;
            """,
            (f"emb_{uuid.uuid4().hex[:12]}", entity_type, entity_id, vec_json, now),
        )
