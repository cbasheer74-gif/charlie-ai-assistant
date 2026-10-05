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
        return any(w in low for w in ("short", "shorts", "reel", "youtube video", "vertical video", "video edit", "cut video", "filmora", "preflight"))

    def detect_filmora(self) -> Dict[str, Any]:
        """Detect presence and version of Wondershare Filmora (e.g. Filmora 14) on Windows/macOS."""
        candidates = []
        if sys.platform == "win32":
            p_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            p_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
            local_app = os.environ.get("LOCALAPPDATA", "")

            candidates.extend([
                Path(p_files) / "Wondershare" / "Wondershare Filmora" / "Filmora.exe",
                Path(p_files) / "Wondershare" / "Wondershare Filmora 14" / "Filmora.exe",
                Path(p_files) / "Wondershare" / "Wondershare Filmora" / "Filmora14.exe",
                Path(p_files_x86) / "Wondershare" / "Wondershare Filmora" / "Filmora.exe",
                Path(local_app) / "Programs" / "Wondershare" / "Wondershare Filmora" / "Filmora.exe",
            ])

            # Registry scan fallback
            try:
                import winreg
                for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    for subkey in (
                        r"SOFTWARE\Wondershare\Wondershare Filmora",
                        r"SOFTWARE\Wondershare\Filmora",
                        r"SOFTWARE\WOW6432Node\Wondershare\Wondershare Filmora",
                    ):
                        try:
                            with winreg.OpenKey(root_key, subkey) as k:
                                val, _ = winreg.QueryValueEx(k, "InstallPath")
                                if val:
                                    candidates.append(Path(val) / "Filmora.exe")
                        except Exception:
                            pass
            except Exception:
                pass
        elif sys.platform == "darwin":
            candidates.extend([
                Path("/Applications/Wondershare Filmora.app/Contents/MacOS/Filmora"),
                Path("/Applications/Wondershare Filmora 14.app/Contents/MacOS/Filmora"),
            ])

        which_path = shutil.which("Filmora.exe") or shutil.which("filmora")
        if which_path:
            candidates.insert(0, Path(which_path))

        for cand in candidates:
            try:
                if cand.is_file():
                    ver = "14.x" if "14" in str(cand) else "Detected"
                    return {
                        "installed": True,
                        "executable": str(cand.resolve()),
                        "version": ver,
                        "details": f"Wondershare Filmora found at {cand}",
                    }
            except Exception:
                continue

        return {
            "installed": False,
            "executable": None,
            "version": None,
            "details": "Wondershare Filmora 14 not detected in standard system locations.",
        }

    def check_video_prerequisites(self) -> Dict[str, Any]:
        """Preflight dependency check: Filmora 14 detector with automated graceful FFmpeg fallback."""
        filmora = self.detect_filmora()
        ffmpeg_bin = shutil.which("ffmpeg")
        ffprobe_bin = shutil.which("ffprobe")

        has_filmora = filmora["installed"]
        has_ffmpeg = bool(ffmpeg_bin)

        if has_filmora:
            active_engine = "filmora"
            fallback_ready = has_ffmpeg
            status = "ready"
        elif has_ffmpeg:
            active_engine = "ffmpeg"
            fallback_ready = True
            status = "ready (fallback active)"
        else:
            active_engine = None
            fallback_ready = False
            status = "missing_dependencies"

        return {
            "status": status,
            "active_engine": active_engine,
            "fallback_ready": fallback_ready,
            "filmora": filmora,
            "ffmpeg": has_ffmpeg,
            "ffmpeg_path": ffmpeg_bin,
            "ffprobe": bool(ffprobe_bin),
            "ffprobe_path": ffprobe_bin,
        }

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
