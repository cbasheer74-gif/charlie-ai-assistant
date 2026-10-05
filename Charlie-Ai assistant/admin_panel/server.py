"""
admin_panel/server.py — Dedicated Standalone Web Server for CHARLIE AI Admin Panel.

Runs on port 8500 by default (separate from Licensing Server on 8400).
Usage:
  python admin_panel/server.py
"""

import http.server
import os
import socketserver
import sys
from pathlib import Path

PORT = int(os.getenv("CHARLIE_ADMIN_PORT", "8500"))
DIRECTORY = str(Path(__file__).resolve().parent)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        # Enable CORS and caching headers
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()


def main():
    print(f"==================================================")
    print(f"  CHARLIE AI — Dedicated Admin Panel Web Server")
    print(f"==================================================")
    print(f"  Serving directory: {DIRECTORY}")
    print(f"  Admin Panel URL:   http://localhost:{PORT}")
    print(f"  Backend API URL:   http://localhost:8400")
    print(f"==================================================")

    # Allow port reuse
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nAdmin panel web server stopped.")
            sys.exit(0)


if __name__ == "__main__":
    main()
