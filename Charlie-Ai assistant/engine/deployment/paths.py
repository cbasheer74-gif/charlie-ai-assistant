"""
JARVIS Phase 14: Deployment Paths and Port Management
Handles stable per-user application directories and dynamic localhost port allocation.
"""

import os
import socket
from pathlib import Path
from typing import Dict, Optional


class DeploymentPathManager:
    """Manages stable user application paths and ensures directories exist."""

    def __init__(self, data_dir_override: Optional[str] = None):
        if data_dir_override:
            self._data_dir = Path(data_dir_override).resolve()
        elif "JARVIS_DATA_DIR" in os.environ:
            self._data_dir = Path(os.environ["JARVIS_DATA_DIR"]).resolve()
        else:
            appdata = os.environ.get("APPDATA")
            if appdata:
                self._data_dir = Path(appdata) / "JARVIS"
            else:
                self._data_dir = Path.home() / ".jarvis" / "JARVIS"

        self.ensure_dirs()

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def ensure_dirs(self) -> None:
        """Create all standard application data subdirectories."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        for sub in [
            "memory",
            "graph",
            "plugins",
            "skills",
            "backups",
            "logs",
            "checkpoints",
            "updates",
            "diagnostics",
            "config",
        ]:
            (self._data_dir / sub).mkdir(parents=True, exist_ok=True)

    def get_sub_dir(self, name: str) -> Path:
        p = self._data_dir / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_log_file(self) -> Path:
        return self.get_sub_dir("logs") / "jarvis.log"

    def get_config_file(self) -> Path:
        return self.get_sub_dir("config") / "jarvis_config.json"


class PortManager:
    """Discovers available localhost ports and maps them to services."""

    def __init__(self, default_port: int = 3008):
        self.default_port = default_port
        self._service_ports: Dict[str, int] = {}

    def is_port_available(self, port: int, host: str = "127.0.0.1") -> bool:
        """Check if port can be bound."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return True
            except (OSError, socket.error):
                return False

    def find_available_port(self, start_port: Optional[int] = None, max_attempts: int = 50) -> int:
        """Find the next available port starting from start_port."""
        start = start_port or self.default_port
        for p in range(start, start + max_attempts):
            if self.is_port_available(p):
                return p
        raise RuntimeError(f"No available port found in range [{start}, {start + max_attempts})")

    def reserve_port(self, service_name: str, port: Optional[int] = None) -> int:
        """Assign an available port to a named service."""
        target_port = port if port and self.is_port_available(port) else self.find_available_port()
        self._service_ports[service_name] = target_port
        return target_port

    def get_service_port(self, service_name: str) -> Optional[int]:
        return self._service_ports.get(service_name)
