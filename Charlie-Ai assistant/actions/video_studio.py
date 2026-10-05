"""actions/video_studio.py — Video Production and Shorts Studio Action.

Exposes vertical short video generation (1080x1920, 9:16), media probe, and verification.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from engine.agents.video_agent import VideoAgent
from engine.error_recovery import ErrorRecoveryEngine
from engine.memory_manager import MemoryManager
from engine.permissions import PermissionManager
from engine.rollback import RollbackManager
from engine.task_planner import TaskPlanner
from engine.verification import VerificationEngine

_mem = MemoryManager()
_perm = PermissionManager()
_ver = VerificationEngine()
_rec = ErrorRecoveryEngine(_mem)
_roll = RollbackManager()
_plan = TaskPlanner(_mem)
_agent = VideoAgent(_mem, _plan, _perm, _ver, _rec, _roll)


def video_studio(parameters: dict, **_unused) -> str:
    """Execute short-form video operations."""
    params = parameters or {}
    action = str(params.get("action") or "probe").strip().lower()
    src = str(params.get("source_path") or "").strip()
    dest = str(params.get("output_path") or "").strip() or None
    duration = float(params.get("duration") or 30.0)

    if action == "preflight":
        res = _agent.check_video_prerequisites()
        filmora = res["filmora"]
        filmora_desc = f"Installed ({filmora['executable']})" if filmora["installed"] else "Not installed (searched standard system paths)"
        ffmpeg_desc = f"Available ({res['ffmpeg_path']})" if res["ffmpeg"] else "Not available"
        return (
            "Video Production Preflight Diagnostics:\n"
            f"• Active Video Engine: {str(res.get('active_engine')).upper()}\n"
            f"• Wondershare Filmora 14: {filmora_desc}\n"
            f"• Local FFmpeg: {ffmpeg_desc}\n"
            f"• Automated Graceful Fallback: {'READY (FFmpeg)' if res.get('fallback_ready') else 'NOT READY'}\n"
            f"• System Readiness: {res.get('status')}"
        )

    if action == "probe":
        if not src:
            return "Please specify source_path."
        res = _agent.probe_media(src)
        return f"Media probe for {res['file']}: {res['details']}"

    if action == "create_short":
        if not src:
            return "Please specify source_path for vertical short creation."
        res = _agent.create_vertical_short(src, output_path=dest, duration=duration)
        if res.get("status") == "failed":
            return f"Video generation failed: {res.get('error')}"
        return (
            f"Vertical Short (9:16) created: {res['destination']}\n"
            f"Resolution: {res['resolution']} | Duration: {res['duration']}s\n"
            f"Verification: {res['verification']}"
        )

    return f"Unknown video_studio action: {action}. Supported: preflight, probe, create_short."


TOOL = {
    "name": "video_studio",
    "description": (
        "Create vertical 9:16 YouTube Shorts / Reels (1080x1920) with audio normalization, "
        "preflight Filmora 14 / FFmpeg dependency check with automated fallback, and FFprobe verification."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["preflight", "probe", "create_short"],
                "description": "Action: preflight dependency check, probe video properties, or create 1080x1920 vertical Short.",
            },
            "source_path": {"type": "STRING", "description": "Path to input video file (required for probe/create_short)."},
            "output_path": {"type": "STRING", "description": "Optional destination path."},
            "duration": {"type": "NUMBER", "description": "Target duration in seconds (default: 30)."},
        },
        "required": ["action"],
    },
    "handler": video_studio,
}
