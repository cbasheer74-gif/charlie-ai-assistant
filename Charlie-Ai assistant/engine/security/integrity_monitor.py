"""engine/security/integrity_monitor.py — File Integrity Monitoring and Security Event Logging."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.security.models import (
    SecurityEvent,
    SecurityEventType,
    SecuritySeverity,
)


class IntegrityMonitor:
    """Monitors critical JARVIS files (security configs, policies, trusted skills) for tampering (Section 57 & 58)."""

    def __init__(self):
        self._baseline_hashes: Dict[str, str] = {}

    def register_baseline_file(self, file_path: Path) -> bool:
        """Registers expected hash for a critical file."""
        if not file_path.exists():
            return False
        content = file_path.read_bytes()
        self._baseline_hashes[str(file_path.resolve())] = hashlib.sha256(content).hexdigest()
        return True

    def check_integrity(self) -> Tuple[bool, List[str]]:
        """Verifies current file contents against baseline hashes (Test 130)."""
        tampered_files: List[str] = []
        for path_str, expected_hash in self._baseline_hashes.items():
            p = Path(path_str)
            if not p.exists():
                tampered_files.append(f"{path_str} (MISSING)")
                continue

            current_hash = hashlib.sha256(p.read_bytes()).hexdigest()
            if current_hash != expected_hash:
                tampered_files.append(f"{path_str} (MODIFIED)")

        is_intact = len(tampered_files) == 0
        return is_intact, tampered_files


class SecurityEventManager:
    """Central manager for security violations, intrusion attempts, and blocked operations (Section 55 & 56)."""

    def __init__(self):
        self._events: List[SecurityEvent] = []

    def record_event(
        self,
        event_type: SecurityEventType,
        severity: SecuritySeverity,
        source: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SecurityEvent:
        event = SecurityEvent(
            id=f"se_{int(time.time()*1000)}",
            event_type=event_type,
            severity=severity,
            source=source,
            description=description,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def list_events(self, min_severity: Optional[SecuritySeverity] = None) -> List[SecurityEvent]:
        if not min_severity:
            return list(self._events)
        # Severity ordering
        levels = {
            SecuritySeverity.INFO: 1,
            SecuritySeverity.WARNING: 2,
            SecuritySeverity.HIGH: 3,
            SecuritySeverity.CRITICAL: 4,
        }
        min_rank = levels.get(min_severity, 1)
        return [e for e in self._events if levels.get(e.severity, 1) >= min_rank]
