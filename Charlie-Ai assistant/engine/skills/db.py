"""engine/skills/db.py — Persistent Database for Skills, Versions, and Corrections.

Stores structured procedural workflows, triggers, variables, execution history,
and user corrections in SQLite with foreign keys and WAL mode.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.db import get_db, utc_now_iso
from engine.skills.models import (
    Skill,
    SkillCategory,
    SkillCorrection,
    SkillStatus,
    SkillStep,
    SkillTrigger,
    SkillVariable,
)


class SkillDatabase:
    """Manages SQLite tables for reusable skills, versioning, and learning metrics."""

    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path else None
        self.init_schema()
        self._migrate_legacy_json()

    def init_schema(self) -> None:
        """Create skill tables and indices."""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            intent TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            confidence REAL DEFAULT 0.5,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'manual',
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_used_at TEXT
        );

        CREATE TABLE IF NOT EXISTS skill_versions (
            id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            definition_json TEXT NOT NULL,
            changelog TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE,
            UNIQUE(skill_id, version)
        );

        CREATE TABLE IF NOT EXISTS skill_triggers (
            id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            phrase TEXT NOT NULL,
            match_type TEXT DEFAULT 'semantic',
            priority INTEGER DEFAULT 10,
            FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS skill_variables (
            id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'string',
            default_value TEXT,
            description TEXT,
            required INTEGER DEFAULT 0,
            FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS skill_execution_history (
            id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            task_id TEXT,
            inputs_json TEXT,
            outputs_json TEXT,
            status TEXT NOT NULL,
            duration REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS skill_corrections (
            id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            original_behavior TEXT,
            user_correction TEXT NOT NULL,
            corrected_behavior TEXT,
            scope TEXT DEFAULT 'SKILL',
            confidence REAL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
        CREATE INDEX IF NOT EXISTS idx_skills_intent ON skills(intent);
        CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);
        CREATE INDEX IF NOT EXISTS idx_skill_triggers_phrase ON skill_triggers(phrase);
        """
        with get_db(self.db_path) as conn:
            conn.executescript(schema_sql)

    def _migrate_legacy_json(self) -> None:
        """Migrate existing flat memory/skills.json to SQLite if present."""
        # Explicit database paths are used for isolated profiles and tests.
        # Import only a legacy file beside that database; never pull personal
        # workflows from the process working directory into another profile.
        legacy_path = ((self.db_path.parent / "skills.json")
                       if self.db_path else Path("memory/skills.json"))
        if not legacy_path.exists():
            return

        try:
            data = json.loads(legacy_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return

            from engine.skills.builtin_skills import get_builtin_skills
            builtin_names = {s.name.lower() for s in get_builtin_skills()}

            for name, content in data.items():
                if name.lower() in builtin_names:
                    continue
                real_name = content.get("name", name) if isinstance(content, dict) else name
                if real_name.lower() in builtin_names:
                    continue
                if not self.get_skill_by_name(real_name):
                    desc = content.get("workflow", "") if isinstance(content, dict) else str(content)
                    skill = Skill(
                        id=f"skill_legacy_{uuid.uuid4().hex[:8]}",
                        name=real_name,
                        description=desc[:200],
                        intent=real_name.replace("_", " "),
                        category=SkillCategory.CUSTOM,
                        status=SkillStatus.STABLE,
                        triggers=[SkillTrigger(phrase=real_name.replace("_", " "))],
                        source="legacy_json",
                    )
                    self.save_skill(skill, changelog="Imported from legacy skills.json")
        except Exception:
            pass

    def save_skill(self, skill: Skill, changelog: str = "") -> bool:
        """Insert or update a complete Skill record and archive version."""
        now = utc_now_iso()
        skill.updated_at = now

        meta = {
            "required_agents": skill.required_agents,
            "required_tools": skill.required_tools,
            "required_permissions": skill.required_permissions,
            "preconditions": skill.preconditions,
            "verification_rules": skill.verification_rules,
            "recovery_rules": skill.recovery_rules,
            "dependencies": skill.dependencies,
            "steps": [s.to_dict() for s in skill.steps],
        }

        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO skills (
                    id, name, description, intent, category, status, version,
                    confidence, success_count, failure_count, source, metadata_json,
                    created_at, updated_at, last_used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    intent = excluded.intent,
                    category = excluded.category,
                    status = excluded.status,
                    version = excluded.version,
                    confidence = excluded.confidence,
                    success_count = excluded.success_count,
                    failure_count = excluded.failure_count,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    last_used_at = excluded.last_used_at;
                """,
                (
                    skill.id,
                    skill.name,
                    skill.description,
                    skill.intent,
                    skill.category.value if isinstance(skill.category, SkillCategory) else str(skill.category),
                    skill.status.value if isinstance(skill.status, SkillStatus) else str(skill.status),
                    skill.version,
                    skill.confidence,
                    skill.success_count,
                    skill.failure_count,
                    skill.source,
                    json.dumps(meta, ensure_ascii=False),
                    skill.created_at,
                    skill.updated_at,
                    skill.last_used_at,
                ),
            )

            # Store Version Snapshot
            v_id = f"v_{skill.id}_{skill.version}"
            conn.execute(
                """
                INSERT INTO skill_versions (id, skill_id, version, definition_json, changelog, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(skill_id, version) DO UPDATE SET
                    definition_json = excluded.definition_json,
                    changelog = excluded.changelog;
                """,
                (v_id, skill.id, skill.version, json.dumps(skill.to_dict(), ensure_ascii=False), changelog, now),
            )

            # Clear and rebuild triggers
            conn.execute("DELETE FROM skill_triggers WHERE skill_id = ?;", (skill.id,))
            for trg in skill.triggers:
                t_id = f"trg_{uuid.uuid4().hex[:8]}"
                conn.execute(
                    "INSERT INTO skill_triggers (id, skill_id, phrase, match_type, priority) VALUES (?, ?, ?, ?, ?);",
                    (t_id, skill.id, trg.phrase, trg.match_type, trg.priority),
                )

            # Clear and rebuild variables
            conn.execute("DELETE FROM skill_variables WHERE skill_id = ?;", (skill.id,))
            for var in skill.variables:
                var_id = f"var_{uuid.uuid4().hex[:8]}"
                conn.execute(
                    "INSERT INTO skill_variables (id, skill_id, name, type, default_value, description, required) VALUES (?, ?, ?, ?, ?, ?, ?);",
                    (var_id, skill.id, var.name, var.type, json.dumps(var.default), var.description, 1 if var.required else 0),
                )

            return True

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        with get_db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM skills WHERE id = ?;", (skill_id,)).fetchone()
            if not row:
                return None
            return self._hydrate_skill(conn, row)

    def get_skill_by_name(self, name: str) -> Optional[Skill]:
        with get_db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM skills WHERE name = ? COLLATE NOCASE;", (name.strip(),)).fetchone()
            if not row:
                return None
            return self._hydrate_skill(conn, row)

    def get_skill_by_intent(self, intent: str) -> Optional[Skill]:
        with get_db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM skills WHERE intent = ? COLLATE NOCASE;", (intent.strip(),)).fetchone()
            if not row:
                return None
            return self._hydrate_skill(conn, row)

    def list_skills(self, category: Optional[str] = None, status: Optional[str] = None) -> List[Skill]:
        query = "SELECT * FROM skills WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY confidence DESC, success_count DESC;"

        with get_db(self.db_path) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._hydrate_skill(conn, r) for r in rows]

    def delete_skill(self, skill_id: str) -> bool:
        with get_db(self.db_path) as conn:
            cur = conn.execute("DELETE FROM skills WHERE id = ?;", (skill_id,))
            return cur.rowcount > 0

    def get_versions(self, skill_id: str) -> List[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            rows = conn.execute(
                "SELECT version, changelog, created_at FROM skill_versions WHERE skill_id = ? ORDER BY version DESC;",
                (skill_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_version_definition(self, skill_id: str, version: int) -> Optional[Dict[str, Any]]:
        with get_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT definition_json FROM skill_versions WHERE skill_id = ? AND version = ?;",
                (skill_id, version),
            ).fetchone()
            if row:
                return json.loads(row["definition_json"])
            return None

    def record_execution(
        self,
        skill_id: str,
        version: int,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        status: str,
        duration: float,
        task_id: Optional[str] = None,
    ) -> None:
        now = utc_now_iso()
        hist_id = f"shist_{uuid.uuid4().hex[:10]}"
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO skill_execution_history (
                    id, skill_id, version, task_id, inputs_json, outputs_json, status, duration, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    hist_id,
                    skill_id,
                    version,
                    task_id,
                    json.dumps(inputs, ensure_ascii=False),
                    json.dumps(outputs, ensure_ascii=False),
                    status,
                    duration,
                    now,
                ),
            )
            if status == "SUCCESS":
                conn.execute(
                    """
                    UPDATE skills SET
                        success_count = success_count + 1,
                        confidence = MIN(1.0, confidence + 0.05),
                        last_used_at = ?
                    WHERE id = ?;
                    """,
                    (now, skill_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE skills SET
                        failure_count = failure_count + 1,
                        confidence = MAX(0.1, confidence - 0.1),
                        last_used_at = ?
                    WHERE id = ?;
                    """,
                    (now, skill_id),
                )

    def record_correction(self, correction: SkillCorrection) -> None:
        with get_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO skill_corrections (
                    id, skill_id, original_behavior, user_correction, corrected_behavior, scope, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    correction.id,
                    correction.skill_id,
                    correction.original_behavior,
                    correction.user_correction,
                    correction.corrected_behavior,
                    correction.scope,
                    correction.confidence,
                    correction.created_at,
                ),
            )

    def get_corrections(self, skill_id: Optional[str] = None) -> List[SkillCorrection]:
        query = "SELECT * FROM skill_corrections"
        params = []
        if skill_id:
            query += " WHERE skill_id = ?"
            params.append(skill_id)
        query += " ORDER BY created_at DESC;"

        with get_db(self.db_path) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                SkillCorrection(
                    id=r["id"],
                    skill_id=r["skill_id"],
                    original_behavior=r["original_behavior"],
                    user_correction=r["user_correction"],
                    corrected_behavior=r["corrected_behavior"],
                    scope=r["scope"],
                    confidence=float(r["confidence"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def _hydrate_skill(self, conn, row) -> Skill:
        meta = json.loads(row["metadata_json"] or "{}")

        # Fetch triggers
        trg_rows = conn.execute("SELECT phrase, match_type, priority FROM skill_triggers WHERE skill_id = ?;", (row["id"],)).fetchall()
        triggers = [SkillTrigger(phrase=t["phrase"], match_type=t["match_type"], priority=t["priority"]) for t in trg_rows]

        # Fetch variables
        var_rows = conn.execute("SELECT name, type, default_value, description, required FROM skill_variables WHERE skill_id = ?;", (row["id"],)).fetchall()
        variables = []
        for v in var_rows:
            def_val = json.loads(v["default_value"]) if v["default_value"] else None
            variables.append(SkillVariable(
                name=v["name"],
                type=v["type"],
                default=def_val,
                description=v["description"],
                required=bool(v["required"]),
            ))

        # Reconstruct steps
        steps = [SkillStep(**s) for s in meta.get("steps", [])]

        return Skill(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            intent=row["intent"],
            category=SkillCategory(row["category"]),
            status=SkillStatus(row["status"]),
            version=row["version"],
            triggers=triggers,
            variables=variables,
            steps=steps,
            required_agents=meta.get("required_agents", []),
            required_tools=meta.get("required_tools", []),
            required_permissions=meta.get("required_permissions", []),
            preconditions=meta.get("preconditions", []),
            verification_rules=meta.get("verification_rules", []),
            recovery_rules=meta.get("recovery_rules", []),
            dependencies=meta.get("dependencies", []),
            success_count=row["success_count"],
            failure_count=row["failure_count"],
            confidence=float(row["confidence"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_used_at=row["last_used_at"],
            source=row["source"],
        )
