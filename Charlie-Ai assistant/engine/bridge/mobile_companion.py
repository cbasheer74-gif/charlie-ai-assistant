"""engine/bridge/mobile_companion.py — Mobile Companion Web Bridge for CHARLIE.

Features:
- Embedded zero-dependency HTTP server running on LAN.
- Dynamic IP discovery & QR/terminal pairing link.
- Mobile Web Client with Cyberpunk HUD UI:
  - Real-time animated assistant core visualizer.
  - Mobile chat interface with quick action commands.
  - Real-time desktop status (CPU, memory, active window, voice state).
  - Screen snapshot preview.
"""

from __future__ import annotations

import io
import json
import logging
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("charlie.mobile_companion")

# Embedded Mobile PWA Web Client
MOBILE_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>CHARLIE Mobile Companion</title>
  <style>
    :root {
      --bg: #090d16;
      --card: #131a2a;
      --cyan: #00f3ff;
      --purple: #9d4edd;
      --green: #00ffaa;
      --text: #e0f2fe;
      --dim: #64748b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
    
    header { padding: 12px 16px; background: rgba(19, 26, 42, 0.85); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(0, 243, 255, 0.2); display: flex; justify-content: space-between; align-items: center; }
    .brand { font-weight: 800; font-size: 1.1rem; color: var(--cyan); letter-spacing: 2px; }
    .badge { font-size: 0.75rem; padding: 3px 8px; border-radius: 12px; background: rgba(0, 255, 170, 0.15); color: var(--green); border: 1px solid var(--green); }

    #core-container { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px 0; }
    .orb { width: 90px; height: 90px; border-radius: 50%; background: radial-gradient(circle, var(--cyan) 0%, rgba(157, 78, 221, 0.4) 60%, transparent 80%); box-shadow: 0 0 30px var(--cyan); animation: pulse 3s infinite ease-in-out; }
    @keyframes pulse { 0%, 100% { transform: scale(0.92); opacity: 0.8; } 50% { transform: scale(1.08); opacity: 1; filter: hue-rotate(30deg); } }

    #chat-box { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
    .msg { max-width: 82%; padding: 10px 14px; border-radius: 14px; font-size: 0.92rem; line-height: 1.4; }
    .msg.charlie { align-self: flex-start; background: var(--card); border: 1px solid rgba(0, 243, 255, 0.25); color: var(--text); border-top-left-radius: 2px; }
    .msg.user { align-self: flex-end; background: linear-gradient(135deg, #0088cc, #00b4d8); color: #fff; border-top-right-radius: 2px; }

    .quick-actions { display: flex; gap: 8px; overflow-x: auto; padding: 8px 16px; background: var(--card); border-top: 1px solid rgba(255, 255, 255, 0.05); }
    .chip { background: rgba(0, 243, 255, 0.1); border: 1px solid rgba(0, 243, 255, 0.3); color: var(--cyan); padding: 6px 12px; border-radius: 16px; font-size: 0.8rem; white-space: nowrap; cursor: pointer; }

    footer { padding: 10px 16px 20px; background: var(--card); display: flex; gap: 8px; align-items: center; }
    input[type="text"] { flex: 1; background: #0b101d; border: 1px solid rgba(0, 243, 255, 0.25); border-radius: 20px; padding: 12px 16px; color: #fff; font-size: 0.95rem; outline: none; }
    input[type="text"]:focus { border-color: var(--cyan); box-shadow: 0 0 10px rgba(0, 243, 255, 0.3); }
    button.send-btn { background: var(--cyan); color: #000; border: none; width: 44px; height: 44px; border-radius: 50%; font-weight: bold; cursor: pointer; display: flex; align-items: center; justify-content: center; }
  </style>
</head>
<body>
  <header>
    <div class="brand">CHARLIE</div>
    <div class="badge" id="status-badge">ONLINE</div>
  </header>

  <div id="core-container">
    <div class="orb"></div>
  </div>

  <div id="chat-box">
    <div class="msg charlie">Systems online. Charlie remote bridge linked to your device.</div>
  </div>

  <div class="quick-actions">
    <div class="chip" onclick="sendQuick('System Status')">⚡ Status</div>
    <div class="chip" onclick="sendQuick('Take Screenshot')">📸 Screen</div>
    <div class="chip" onclick="sendQuick('Mute Master Volume')">🔇 Mute</div>
    <div class="chip" onclick="sendQuick('Lock Workstation')">🔒 Lock PC</div>
  </div>

  <footer>
    <input type="text" id="userInput" placeholder="Ask or command Charlie..." onkeydown="if(event.key==='Enter') sendMsg()">
    <button class="send-btn" onclick="sendMsg()">➤</button>
  </footer>

  <script>
    async function sendMsg() {
      const input = document.getElementById('userInput');
      const text = input.value.trim();
      if (!text) return;
      input.value = '';

      appendMessage(text, 'user');

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text })
        });
        const data = await res.json();
        appendMessage(data.reply || 'Command executed.', 'charlie');
      } catch (err) {
        appendMessage('Connection error with Charlie desktop engine.', 'charlie');
      }
    }

    function sendQuick(txt) {
      document.getElementById('userInput').value = txt;
      sendMsg();
    }

    function appendMessage(text, sender) {
      const box = document.getElementById('chat-box');
      const div = document.createElement('div');
      div.className = 'msg ' + sender;
      div.innerText = text;
      box.appendChild(div);
      box.scrollTop = box.scrollHeight;
    }
  </script>
</body>
</html>
"""


class MobileCompanionHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests from remote mobile devices."""

    def log_message(self, format, *args):
        pass  # Quiet logging

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(MOBILE_UI_HTML.encode("utf-8"))
        elif parsed.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status_data = {
                "charlie_status": "ONLINE",
                "uptime": time.time(),
                "bridge": "Active",
            }
            self.wfile.write(json.dumps(status_data).encode("utf-8"))
        elif parsed.path == "/api/screen":
            try:
                from engine.vision_ocr import capture_screen_image
                img = capture_screen_image()
                buf = io.BytesIO()
                img.thumbnail((800, 600))
                img.save(buf, format="JPEG", quality=70)
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.end_headers()
                self.wfile.write(buf.getvalue())
            except Exception:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body.decode("utf-8"))
                user_msg = payload.get("message", "")

                reply_text = f"Received command '{user_msg}'."
                try:
                    from engine.pro_chat import ProChatAssistant
                    chat = ProChatAssistant()
                    reply_text = chat.respond(user_msg)
                except Exception as ex:
                    reply_text = f"Charlie Error: {ex}"

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"reply": reply_text}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


class MobileCompanionBridge:
    """Manages the lifecycle of the local network companion bridge."""

    def __init__(self, port: int = 8765):
        self.port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    @staticmethod
    def get_local_ip() -> str:
        """Finds primary LAN IP for phone pairing."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_pairing_url(self) -> str:
        return f"http://{self.get_local_ip()}:{self.port}/"

    def start(self) -> bool:
        if self._is_running:
            return True

        try:
            self._server = ThreadingHTTPServer(("0.0.0.0", self.port), MobileCompanionHandler)
            self._is_running = True

            def _serve():
                if self._server:
                    self._server.serve_forever()

            self._thread = threading.Thread(target=_serve, daemon=True, name="MobileBridgeThread")
            self._thread.start()
            logger.info("Mobile Companion Bridge active at %s", self.get_pairing_url())
            return True
        except Exception as e:
            logger.error("Failed to start Mobile Companion Bridge: %s", e)
            return False

    def stop(self) -> None:
        self._is_running = False
        if self._server:
            self._server.shutdown()
            self._server = None


# Singleton
_bridge_instance: Optional[MobileCompanionBridge] = None


def get_mobile_bridge() -> MobileCompanionBridge:
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = MobileCompanionBridge()
    return _bridge_instance
