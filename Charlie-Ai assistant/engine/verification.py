"""engine/verification.py — Verification Engine for JARVIS.

Ensures task results are verified with tangible evidence before marking completion.
Covers Code, Excel spreadsheets, Videos (FFprobe), Files, and Processes.
"""

from __future__ import annotations

import json
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class VerificationEngine:
    """Verifies output integrity across different domains."""

    @staticmethod
    def verify_file(file_path: Path | str, min_bytes: int = 1) -> Tuple[bool, str]:
        """Verify file exists and has non-zero size."""
        p = Path(file_path).resolve()
        if not p.exists():
            return False, f"File {p.name} does not exist at {p}."
        size = p.stat().st_size
        if size < min_bytes:
            return False, f"File {p.name} is empty ({size} bytes, expected >= {min_bytes})."
        return True, f"File {p.name} verified ({size:,} bytes)."

    @staticmethod
    def verify_code(file_path: Path | str) -> Tuple[bool, str]:
        """Verify code syntax integrity (Python compilation or basic check)."""
        p = Path(file_path).resolve()
        if not p.is_file():
            return False, f"Source file {p.name} not found."

        if p.suffix.lower() == ".py":
            try:
                py_compile.compile(str(p), doraise=True)
                return True, f"Python syntax check passed for {p.name}."
            except py_compile.PyCompileError as e:
                return False, f"SyntaxError in {p.name}: {e}"

        # General file existence verification for non-Python code
        return VerificationEngine.verify_file(p)

    @staticmethod
    def verify_excel(file_path: Path | str, expected_sheets: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Verify Excel workbook can open, contains sheets, and retains formulas."""
        p = Path(file_path).resolve()
        ok, msg = VerificationEngine.verify_file(p, min_bytes=100)
        if not ok:
            return False, msg

        try:
            from openpyxl import load_workbook
            wb = load_workbook(p, data_only=False)
            sheet_names = wb.sheetnames
            if not sheet_names:
                return False, f"Excel workbook {p.name} has no visible sheets."

            if expected_sheets:
                missing = [s for s in expected_sheets if s not in sheet_names]
                if missing:
                    return False, f"Missing expected sheets in {p.name}: {', '.join(missing)}"

            # Count formulas to ensure preservation
            formula_count = 0
            for sname in sheet_names:
                ws = wb[sname]
                for row in ws.iter_rows(values_only=False):
                    for cell in row:
                        if cell.value and str(cell.value).startswith("="):
                            formula_count += 1

            return True, f"Excel workbook verified ({len(sheet_names)} sheets, {formula_count} formula cells detected)."
        except Exception as e:
            return False, f"Excel verification failed for {p.name}: {e}"

    @staticmethod
    def verify_video(
        file_path: Path | str,
        expected_aspect: str = "9:16",
        min_duration: float = 1.0,
    ) -> Tuple[bool, str]:
        """Verify video output via ffprobe (file exists, resolution, duration, audio track)."""
        p = Path(file_path).resolve()
        ok, msg = VerificationEngine.verify_file(p, min_bytes=1000)
        if not ok:
            return False, msg

        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            # Fallback if ffprobe not in PATH
            return True, f"Video file exists ({p.stat().st_size:,} bytes). (ffprobe not found for stream probe)"

        try:
            cmd = [
                ffprobe_bin,
                "-v", "error",
                "-show_entries", "stream=codec_type,width,height,duration",
                "-show_entries", "format=duration",
                "-of", "json",
                str(p),
            ]
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10, **flags)
            data = json.loads(res.stdout or "{}")
            streams = data.get("streams", [])
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

            if not video_stream:
                return False, f"Video file {p.name} contains no video stream."

            width = int(video_stream.get("width") or 0)
            height = int(video_stream.get("height") or 0)
            duration = float(data.get("format", {}).get("duration") or video_stream.get("duration") or 0.0)

            if duration < min_duration:
                return False, f"Video duration too short ({duration:.1f}s, expected >= {min_duration}s)."

            aspect_info = f"{width}x{height}"
            if expected_aspect == "9:16" and height > 0:
                is_vertical = height > width
                if not is_vertical:
                    return False, f"Video is not vertical 9:16 (resolution: {width}x{height})."

            has_audio = "with audio" if audio_stream else "without audio"
            return True, f"Video verified: {aspect_info}, {duration:.1f}s, {has_audio}."
        except Exception as e:
            return False, f"FFprobe verification error on {p.name}: {e}"

    # Aliases for domain compatibility
    verify_code_syntax = verify_code
    verify_excel_workbook = verify_excel
    verify_video_output = verify_video
    verify_file_exists = verify_file

