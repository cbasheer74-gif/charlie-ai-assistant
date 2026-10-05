from __future__ import annotations

import atexit
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QVBoxLayout, QWidget

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception:
    QWebEngineView = None
    QWebEngineSettings = None


_SERVER_PROC: subprocess.Popen | None = None


def is_port_open(host: str = "127.0.0.1", port: int = 5173, timeout: float = 0.5) -> bool:
    """Check if the Vite server port is already open."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def get_charlie_3d_dir() -> Path | None:
    """Locate the charlie-3d directory across different workspace layouts."""
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent.parent / "charlie-3d",
        here.parent.parent / "charlie-3d",
        Path.cwd() / "charlie-3d",
        Path.cwd().parent / "charlie-3d",
    ]
    for c in candidates:
        if c.exists() and (c / "package.json").exists():
            return c
    return None


def ensure_charlie_3d_server() -> bool:
    """Start the Vite dev server in the background if not already running."""
    global _SERVER_PROC
    if is_port_open():
        return True

    cdir = get_charlie_3d_dir()
    if not cdir:
        return False

    is_win = sys.platform.startswith("win")
    creationflags = 0
    if is_win:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    vite_bin = cdir / "node_modules" / ".bin" / ("vite.cmd" if is_win else "vite")
    commands_to_try = []
    if vite_bin.exists():
        commands_to_try.append([str(vite_bin), "--host", "127.0.0.1", "--port", "5173"])
    if is_win:
        commands_to_try.append(["cmd.exe", "/c", "npm", "run", "dev"])
        commands_to_try.append(["npm.cmd", "run", "dev"])
    else:
        commands_to_try.append(["npm", "run", "dev"])

    for cmd in commands_to_try:
        try:
            _SERVER_PROC = subprocess.Popen(
                cmd,
                cwd=str(cdir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                shell=is_win,
            )
            return True
        except Exception as e:
            print(f"[Charlie 3D] Launch attempt failed ({cmd}): {e}")

    return False


def _cleanup_server():
    global _SERVER_PROC
    if _SERVER_PROC is not None:
        try:
            _SERVER_PROC.terminate()
            _SERVER_PROC.wait(timeout=1.0)
        except Exception:
            pass
        _SERVER_PROC = None


atexit.register(_cleanup_server)


class Charlie3DAvatar(QWidget):
    """Embedded TalkingHead 3D avatar with hardware-accelerated WebEngine."""

    def __init__(self, parent=None, url: str = "http://127.0.0.1:5173/"):
        super().__init__(parent)
        self._target_url = url
        self._retry_count = 0
        self._is_ready = False

        ensure_charlie_3d_server()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if QWebEngineView is not None:
            self.web = QWebEngineView(self)
            self._configure_web_settings()

            self.web.setStyleSheet("background: transparent; border: none;")
            try:
                page = self.web.page()
                if page is not None:
                    page.setBackgroundColor(QColor(5, 7, 11, 0))
            except Exception:
                pass

            self.web.loadFinished.connect(self._on_load_finished)
            layout.addWidget(self.web)

            self._poll_timer = QTimer(self)
            self._poll_timer.timeout.connect(self._check_server_and_connect)

            if is_port_open():
                self.web.setUrl(QUrl(self._target_url))
            else:
                self._show_loading_screen()
                self._poll_timer.start(350)
        else:
            print("[Charlie 3D] WARNING: PyQt6-WebEngine not available in current Python environment. Run via .venv to display 3D avatar.")
            self.web = None

    def _show_loading_screen(self):
        if self.web is None:
            return
        loading_html = """
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            html, body {
              margin: 0; padding: 0; width: 100%; height: 100%;
              overflow: hidden; background: transparent;
              display: flex; align-items: center; justify-content: center;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            .loader {
              display: flex; flex-direction: column; align-items: center; gap: 14px;
            }
            .spinner {
              width: 38px; height: 38px;
              border: 3px solid rgba(56, 189, 248, 0.15);
              border-top-color: #38bdf8;
              border-radius: 50%;
              animation: spin 1s linear infinite;
            }
            .text {
              color: #38bdf8; font-size: 11px; letter-spacing: 1.5px;
              text-transform: uppercase; font-weight: 600; opacity: 0.85;
            }
            @keyframes spin { to { transform: rotate(360deg); } }
          </style>
        </head>
        <body>
          <div class="loader">
            <div class="spinner"></div>
            <div class="text">STARTING CHARLIE 3D...</div>
          </div>
        </body>
        </html>
        """
        self.web.setHtml(loading_html)

    def _check_server_and_connect(self):
        if is_port_open():
            self._poll_timer.stop()
            if self.web is not None:
                self.web.setUrl(QUrl(self._target_url))
        else:
            self._retry_count += 1
            if self._retry_count % 4 == 0:
                ensure_charlie_3d_server()
            if self._retry_count > 60:
                self._poll_timer.stop()

    def _configure_web_settings(self):
        if self.web is None or QWebEngineSettings is None:
            return
        try:
            settings = self.web.settings()
            if settings is not None:
                settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        except Exception:
            pass

    def _on_load_finished(self, ok: bool):
        current_url = self.web.url().toString() if self.web is not None else ""
        if ok and "127.0.0.1:5173" in current_url:
            self._is_ready = True
            self._retry_count = 0
            self.set_view("head")
        elif not ok and "127.0.0.1:5173" in current_url:
            self._is_ready = False
            if hasattr(self, "_poll_timer") and not self._poll_timer.isActive():
                self._poll_timer.start(500)

    def _run_js(self, script: str) -> None:
        if self.web is None:
            return
        try:
            page = self.web.page()
            if page is not None:
                page.runJavaScript(script)
        except Exception:
            pass

    SPAN: float = 1.0

    def paint(self, *args, **kwargs) -> None:
        """No-op paint hook for software render fallback compatibility."""
        pass

    def glance(self, dx: float = 0.0, dy: float = 0.0, hold: float = 1.1) -> None:
        """Avatar gaze direction hook."""
        pass

    def trigger_nod(self, amplitude: float = 0.005, duration: float = 0.65) -> None:
        """Affirmative nod gesture hook."""
        pass

    def step(self, dt: float, amp: float, speaking: bool = False, **kwargs) -> None:
        """Frame step hook synced from HUD loop."""
        if speaking != getattr(self, "_last_speaking", None):
            self._last_speaking = speaking
            self.set_speaking(speaking)

    def set_emotion(self, emotion: object, intensity: float = 0.3) -> None:
        """Map HUD emotion name to TalkingHead mood."""
        emo_str = emotion.name.lower() if hasattr(emotion, "name") else str(emotion).lower()
        mood_map = {
            "happy": "happy",
            "excited": "happy",
            "sad": "sad",
            "angry": "angry",
            "thinking": "neutral",
            "surprised": "love",
            "neutral": "neutral",
        }
        self.set_mood(mood_map.get(emo_str, "neutral"))

    def speak_text(self, text: str, mood: str = "neutral"):
        """Animate avatar mouth and head to speak text with optional mood."""
        if not text:
            return

        text_js = json.dumps(text)
        mood_js = json.dumps(mood)

        self._run_js(
            f"""
            if (window.charlie && window.charlie.speakText) {{
                window.charlie.speakText({text_js}, {{
                    avatarMood: {mood_js}
                }});
            }}
            """
        )

    def stop_speaking(self):
        """Immediately stop speech and mouth animations."""
        self._run_js(
            """
            if (window.charlie && window.charlie.stopSpeaking) {
                window.charlie.stopSpeaking();
            }
            """
        )

    def set_speaking(self, speaking: bool):
        """Toggle speaking gestures."""
        if not speaking:
            self.stop_speaking()
        else:
            self._run_js(
                """
                if (window.charlie && window.charlie.startSpeaking) {
                    window.charlie.startSpeaking();
                }
                """
            )

    def set_mood(self, mood: str):
        """Change facial emotion expression (neutral, happy, serious, etc.)."""
        mood_js = json.dumps(mood)
        self._run_js(
            f"""
            if (window.charlie && window.charlie.setMood) {{
                window.charlie.setMood({mood_js});
            }}
            """
        )

    def set_view(self, view: str = "upper"):
        """Change camera framing: 'upper', 'head', 'mid', or 'full'."""
        view_js = json.dumps(view)
        self._run_js(
            f"""
            if (window.charlie && window.charlie.setView) {{
                window.charlie.setView({view_js});
            }}
            """
        )

    def reload(self):
        if self.web is not None:
            self.web.reload()

    def is_ready(self) -> bool:
        return self._is_ready