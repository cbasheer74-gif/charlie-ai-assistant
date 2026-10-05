"""Persistent, read-only file discovery for autonomous tasks.

The catalog searches on demand, remembers aliases and recent selections, and
returns exact paths. It never edits, moves, opens, or deletes a file itself.
"""
from __future__ import annotations

import json
import os
import string
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path


from core.app_paths import get_memory_dir

_STORE = get_memory_dir() / "file_catalog.json"
_KINDS = {
    "video": {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".m4v"},
    "excel": {".xlsx", ".xlsm", ".xls", ".csv", ".ods"},
    "document": {".docx", ".doc", ".pdf", ".txt", ".rtf", ".odt"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".heic"},
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"},
}
_SKIP = {
    "$recycle.bin", "system volume information", "windows", "program files",
    "program files (x86)", "programdata", "appdata", ".git", "node_modules",
    "__pycache__", ".venv", "venv",
}


def _load() -> dict:
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="catalog-", suffix=".json", dir=_STORE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(name, _STORE)
    finally:
        if os.path.exists(name):
            try:
                os.unlink(name)
            except OSError:
                pass


def _common_roots() -> list[Path]:
    home = Path.home()
    roots = [home / name for name in ("Desktop", "Documents", "Downloads", "Videos", "Pictures", "Music")]
    # OneDrive often owns the visible Windows folders.
    roots += [home / "OneDrive" / name for name in ("Desktop", "Documents", "Pictures")]
    out, seen = [], set()
    for root in roots:
        try:
            key = str(root.resolve()).casefold()
        except OSError:
            continue
        if root.is_dir() and key not in seen:
            seen.add(key)
            out.append(root)
    return out


def _drive_roots() -> list[Path]:
    roots = _common_roots()
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if drive.is_dir():
                roots.append(drive)
    return roots


def _matches_kind(path: Path, kind: str) -> bool:
    if kind in ("", "any"):
        return True
    return path.suffix.lower() in _KINDS.get(kind, set())


def _walk(roots: list[Path], kind: str, max_files: int = 60000):
    visited = 0
    stack = list(reversed(roots))
    while stack and visited < max_files:
        folder = stack.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if visited >= max_files:
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name.casefold() not in _SKIP and not entry.name.startswith("."):
                                stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            visited += 1
                            path = Path(entry.path)
                            if _matches_kind(path, kind):
                                yield path
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            continue


def _score(path: Path, query: str) -> tuple[float, float]:
    q = query.casefold().strip()
    name = path.name.casefold()
    stem = path.stem.casefold()
    score = 0.0
    if q:
        if q == name or q == stem:
            score += 1000
        elif name.startswith(q) or stem.startswith(q):
            score += 650
        elif q in name:
            score += 450
        else:
            words = [w for w in q.replace("_", " ").replace("-", " ").split() if w]
            score += sum(70 for word in words if word in name)
            if words and not any(word in name for word in words):
                return (-1, 0)
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0
    # Recency breaks naming ties without overwhelming a strong name match.
    score += max(0.0, 30 - (time.time() - modified) / 86400 / 12)
    return score, modified


def _find(query: str, kind: str, scope: str, limit: int) -> list[Path]:
    data = _load()
    alias = (data.get("aliases") or {}).get(query.casefold()) if query else None
    if alias and Path(alias).is_file() and _matches_kind(Path(alias), kind):
        return [Path(alias)]
    roots = _drive_roots() if scope == "all_drives" else _common_roots()
    ranked = []
    for path in _walk(roots, kind):
        score, modified = _score(path, query)
        if score >= 0:
            ranked.append((score, modified, path))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in ranked[:limit]]


def _format(paths: list[Path], kind: str, query: str) -> str:
    if not paths:
        return f"No {kind if kind != 'any' else ''} file matched '{query}'.".replace("  ", " ")
    lines = [f"FILE MATCHES ({len(paths)}):"]
    for index, path in enumerate(paths, 1):
        try:
            stat = path.stat()
            stamp = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            size = stat.st_size / (1024 * 1024)
            lines.append(f"{index}. {path}\n   Modified: {stamp}; Size: {size:.1f} MB")
        except OSError:
            lines.append(f"{index}. {path}")
    if len(paths) == 1:
        lines.append("Exact file resolved. Use this full path with the appropriate file tool.")
    else:
        lines.append("If the intended file is not clear from names and dates, ask one short clarification.")
    return "\n".join(lines)


def file_catalog(parameters: dict, player=None, **_unused) -> str:
    params = parameters or {}
    action = str(params.get("action") or "find").strip().lower()
    query = str(params.get("query") or "").strip()
    kind = str(params.get("kind") or "any").strip().lower()
    scope = str(params.get("scope") or "common").strip().lower()
    limit = max(1, min(12, int(params.get("limit") or 6)))
    if kind not in {*_KINDS, "any"}:
        return "kind must be video, excel, document, image, audio, or any."
    data = _load()

    if action in {"find", "recent"}:
        paths = _find(query if action == "find" else "", kind, scope, limit)
        data["last_results"] = [str(path) for path in paths]
        data["last_kind"] = kind
        _save(data)
        return _format(paths, kind, query)

    if action == "remember":
        alias = str(params.get("alias") or "").strip().casefold()
        path = Path(str(params.get("path") or "").strip().strip('"'))
        if not alias or not path.is_file():
            return "A short alias and an existing file path are required."
        data.setdefault("aliases", {})[alias] = str(path.resolve())
        _save(data)
        return f"Remembered '{alias}' as {path.resolve()}"

    if action == "last":
        paths = [Path(p) for p in data.get("last_results", []) if Path(p).is_file()]
        return _format(paths[:limit], data.get("last_kind", kind), "last selection")

    if action == "roots":
        return "Search locations:\n" + "\n".join(str(path) for path in _common_roots())
    return "action must be find, recent, remember, last, or roots."


TOOL = {
    "name": "file_catalog",
    "description": (
        "Find the exact local file for an autonomous task and remember file aliases. "
        "Use before editing a video, Excel workbook, resume, document, image, or audio "
        "when the user did not provide a full path. Start with common scope; use "
        "all_drives only when common folders have no match. If one result is returned, "
        "continue without asking. If several plausible matches remain, ask one concise question."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "find | recent | remember | last | roots"},
            "query": {"type": "STRING", "description": "File name, partial name, or user alias"},
            "kind": {"type": "STRING", "description": "video | excel | document | image | audio | any"},
            "scope": {"type": "STRING", "description": "common (default) | all_drives"},
            "limit": {"type": "INTEGER", "description": "Maximum matches, 1-12"},
            "alias": {"type": "STRING", "description": "Short remembered name for remember"},
            "path": {"type": "STRING", "description": "Exact existing path for remember"},
        },
        "required": ["action"],
    },
    "handler": file_catalog,
}
