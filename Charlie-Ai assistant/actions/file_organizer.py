# actions/file_organizer.py
"""
Smart Desktop & Downloads Auto-Organizer for Charlie.

Voice commands:
  "Clean up my desktop"
  "Organize my downloads folder"
  "Tidy up my files"
  "Show me what needs organizing"
  "Undo file organization"
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TOOL = {
    "name": "file_organizer",
    "description": (
        "Organizes cluttered Desktop or Downloads folders into categorized subfolders "
        "(Documents, Images, Media, Archives, Installers, Code). "
        "Includes safe dry-run preview and instant undo functionality. "
        "Trigger on: 'clean desktop', 'organize downloads', 'tidy folder', "
        "'sort files', 'clean up my files', 'undo organization'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["organize", "preview", "undo", "status"],
                "description": "organize=move files, preview=dry run without moving, undo=revert last organize, status=check folder clutter",
            },
            "target": {
                "type": "string",
                "enum": ["desktop", "downloads", "custom"],
                "description": "Folder to organize (default desktop)",
            },
            "custom_path": {
                "type": "string",
                "description": "Absolute folder path if target=custom",
            },
        },
        "required": ["action"],
    },
}

_EXT_MAP = {
    "Documents": {".pdf", ".docx", ".doc", ".txt", ".xlsx", ".xls", ".pptx", ".ppt", ".csv", ".odt", ".rtf"},
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tiff"},
    "Media": {".mp4", ".mkv", ".mov", ".avi", ".mp3", ".wav", ".flac", ".m4a", ".aac"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".iso"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".sql", ".cpp", ".c", ".java", ".go", ".rs"},
}

_IGNORE_EXTS = {".lnk", ".ini", ".sys", ".crdownload", ".part", ".tmp"}
from core.app_paths import get_config_dir

_UNDO_LOG = get_config_dir() / "organizer_undo.json"


def _get_target_dir(target: str, custom_path: Optional[str] = None) -> Path:
    home = Path.home()
    if target == "downloads":
        return home / "Downloads"
    if target == "custom" and custom_path:
        return Path(custom_path)
    return home / "Desktop"


def _categorize(ext: str) -> str:
    ext_lower = ext.lower()
    for cat, exts in _EXT_MAP.items():
        if ext_lower in exts:
            return cat
    return "Other"


def execute(
    action: str = "preview",
    target: str = "desktop",
    custom_path: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Execute file organizer action."""
    target_dir = _get_target_dir(target, custom_path)
    if not target_dir.exists():
        return f"Target folder not found: {target_dir}"

    if action == "undo":
        if not _UNDO_LOG.exists():
            return "No previous organization action found to undo."
        try:
            records = json.loads(_UNDO_LOG.read_text(encoding="utf-8"))
            reverted = 0
            for rec in records:
                src = Path(rec["new_path"])
                dest = Path(rec["orig_path"])
                if src.exists() and not dest.exists():
                    shutil.move(str(src), str(dest))
                    reverted += 1
            _UNDO_LOG.unlink(missing_ok=True)
            return f"↩️ Undo complete: {reverted} files restored to their original locations."
        except Exception as e:
            return f"Error executing undo: {e}"

    # Scan top-level files
    files_to_move: List[Tuple[Path, str]] = []
    for item in target_dir.iterdir():
        if item.is_file() and not item.name.startswith("."):
            if item.suffix.lower() in _IGNORE_EXTS:
                continue
            cat = _categorize(item.suffix)
            files_to_move.append((item, cat))

    if not files_to_move:
        return f"✨ {target_dir.name} is already completely tidy! No loose files found."

    if action in ("preview", "status"):
        breakdown: Dict[str, int] = {}
        for _, cat in files_to_move:
            breakdown[cat] = breakdown.get(cat, 0) + 1

        summary_lines = [f"• **{cat}**: {count} files" for cat, count in sorted(breakdown.items())]
        return (
            f"🧹 **Found {len(files_to_move)} files in {target_dir.name}:**\n"
            + "\n".join(summary_lines)
            + f"\n\nSay **'clean up my {target}'** to organize them into subfolders."
        )

    if action == "organize":
        undo_records = []
        moved_count = 0
        for item, cat in files_to_move:
            dest_dir = target_dir / cat
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / item.name

            # Collision prevention
            if dest_file.exists():
                stem = item.stem
                suffix = item.suffix
                dest_file = dest_dir / f"{stem}_{int(datetime.now().timestamp())}{suffix}"

            try:
                shutil.move(str(item), str(dest_file))
                undo_records.append({"orig_path": str(item), "new_path": str(dest_file)})
                moved_count += 1
            except Exception:
                continue

        try:
            _UNDO_LOG.parent.mkdir(parents=True, exist_ok=True)
            _UNDO_LOG.write_text(json.dumps(undo_records, indent=2), encoding="utf-8")
        except Exception:
            pass

        return (
            f"✅ **Cleaned up {target_dir.name}!**\n"
            f"Moved {moved_count} files into neat category subfolders.\n"
            f"💡 Say **'undo file organization'** at any time if you want them back."
        )

    return "Unknown action. Say 'preview', 'organize', or 'undo'."
