"""
licensing_server/run.py — Entry point for the JARVIS licensing server.

Usage:
  python -m licensing_server.run
  # or
  python licensing_server/run.py
"""

import uvicorn

from licensing_server.config import config

if __name__ == "__main__":
    uvicorn.run(
        "licensing_server.app:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level="info",
    )
