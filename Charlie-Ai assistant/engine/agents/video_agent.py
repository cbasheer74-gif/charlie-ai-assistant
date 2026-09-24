"""engine/agents/video_agent.py — Video Production and YouTube Shorts Specialist.

Orchestrates FFmpeg for vertical video composition (1080x1920, 9:16), audio normalization,
subtitle generation, and FFprobe verification.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.agents.base import BaseAgent


class VideoAgent(BaseAgent):
    """Specialist agent for short-form video generation, transcoding, and verification."""

    DEFAULT_RESOLUTION = (1080, 1920)  # 9:16 vertical Short
    DEFAULT_DURATION = 30.0

    def can_handle(self, user_intent: str) -> bool:
        low = user_intent.lower()
        return any(w in low for w in ("short", "shorts", "reel", "youtube video", "vertical video", "video edit", "cut video"))

    def probe_media(self, file_path: Path | str) -> Dict[str, Any]:
        """Inspect video streams, resolution, duration, and codecs."""
        p = Path(file_path).resolve()
        ok, msg = self.verification.verify_video(p)
        return {
            "file": p.name,
            "path": str(p),
            "verified": ok,
            "details": msg,
        }

    def create_vertical_short(
        self,
        source_path: Path | str,
        output_path: Optional[Path | str] = None,
        duration: float = 30.0,
        subtitles_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convert or crop video to 1080x1920 9:16 vertical format with audio normalization."""
        src = Path(source_path).resolve()
        if not src.is_file():
            return {"status": "failed", "error": f"Source media {src.name} not found."}

        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return {"status": "failed", "error": "FFmpeg is not installed or not available in PATH."}

        dest = Path(output_path).resolve() if output_path else src.with_name(f"{src.stem}_short_1080x1920.mp4")

        # FFmpeg filter: scale to fit 1080x1920 then center crop
        vf_filter = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(src),
            "-t", str(duration),
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            str(dest),
        ]

        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=90, **flags)
            if res.returncode != 0:
                return {"status": "failed", "error": f"FFmpeg error: {res.stderr[-300:]}"}

            ok, v_msg = self.verification.verify_video(dest, expected_aspect="9:16", min_duration=1.0)
            return {
                "status": "success" if ok else "warning",
                "destination": str(dest),
                "resolution": "1080x1920",
                "aspect_ratio": "9:16",
                "duration": duration,
                "verification": v_msg,
            }
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "FFmpeg transcoding timed out."}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
