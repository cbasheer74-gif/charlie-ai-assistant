import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("=== CHECKING CHARLIE 3D ENVIRONMENT ===")

# 1. Check PyQt6 and QWebEngineView
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    print("[OK] PyQt6 and QWebEngineView imported successfully.")
except Exception as e:
    print(f"[FAIL] PyQt6.QtWebEngineWidgets import error: {e}")

# 2. Check core.charlie_3d
try:
    from core.charlie_3d import Charlie3DAvatar
    print("[OK] Charlie3DAvatar imported successfully.")
except Exception as e:
    print(f"[FAIL] Charlie3DAvatar import error: {e}")

# 3. Check charlie-3d directory
charlie_3d_dir = Path(__file__).resolve().parent.parent.parent / "charlie-3d"
print(f"charlie-3d dir path: {charlie_3d_dir} (exists: {charlie_3d_dir.exists()})")
if charlie_3d_dir.exists():
    index_html = charlie_3d_dir / "index.html"
    charlie_glb = charlie_3d_dir / "public" / "avatars" / "charlie.glb"
    print(f"  index.html exists: {index_html.exists()}")
    print(f"  charlie.glb exists: {charlie_glb.exists()} ({charlie_glb.stat().st_size if charlie_glb.exists() else 0} bytes)")

# 4. Check socket on 5173
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1.0)
try:
    res = s.connect_ex(('127.0.0.1', 5173))
    print(f"Port 5173 status: {'OPEN (server running)' if res == 0 else 'CLOSED'}")
except Exception as e:
    print(f"Port 5173 check error: {e}")
finally:
    s.close()
