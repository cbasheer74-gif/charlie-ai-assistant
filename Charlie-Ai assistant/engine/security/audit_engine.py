"""engine/security/audit_engine.py — Tamper-Evident Hash-Chained Audit Logging and Duplicate Action Prevention."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.security.models import AuditEvent
from engine.security.vault import SecretRedactionEngine


class AuditEngine:
    """Tamper-evident, hash-chained append-only audit log for forensic traceability (Section 50 & 52)."""

    def __init__(self, audit_file: Optional[Path] = None):
        if audit_file is None:
            a_dir = Path.home() / ".jarvis" / "audit"
            a_dir.mkdir(parents=True, exist_ok=True)
            self.audit_file = a_dir / "audit_chain.jsonl"
        else:
            self.audit_file = Path(audit_file)
            self.audit_file.parent.mkdir(parents=True, exist_ok=True)

        self._last_hash = "GENESIS_ROOT_HASH"
        self._load_last_hash()

    def _load_last_hash(self) -> None:
        if not self.audit_file.exists():
            return
        try:
            lines = self.audit_file.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last_record = json.loads(lines[-1])
                self._last_hash = last_record.get("event_hash", "GENESIS_ROOT_HASH")
        except Exception:
            self._last_hash = "GENESIS_ROOT_HASH"

    def record_event(
        self,
        initiator: str,
        agent_name: str,
        tool_name: str,
        action: str,
        target: str,
        risk_level: str,
        verdict: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Records an action in the tamper-evident chain with secret redaction (Section 50 & Test 128)."""
        now = time.time()
        event_id = f"aud_{int(now*1000)}"

        # Redact any accidental secrets from details dict
        details_str = SecretRedactionEngine.redact(json.dumps(details or {}))
        safe_details = json.loads(details_str)

        raw_payload = f"{self._last_hash}|{event_id}|{now}|{initiator}|{agent_name}|{tool_name}|{action}|{target}|{risk_level}|{verdict}|{details_str}"
        event_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

        event = AuditEvent(
            id=event_id,
            prev_hash=self._last_hash,
            timestamp=now,
            initiator=initiator,
            agent_name=agent_name,
            tool_name=tool_name,
            action=action,
            target=target,
            risk_level=risk_level,
            verdict=verdict,
            details=safe_details,
            event_hash=event_hash,
        )

        # Append to log
        with open(self.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.__dict__) + "\n")

        self._last_hash = event_hash
        return event

    def verify_integrity(self) -> Tuple[bool, Optional[str]]:
        """Verifies the hash chain across all audit entries to detect tampering (Section 52 & Test 129)."""
        if not self.audit_file.exists():
            return True, None

        current_prev = "GENESIS_ROOT_HASH"
        try:
            lines = self.audit_file.read_text(encoding="utf-8").strip().splitlines()
            for idx, line in enumerate(lines):
                rec = json.loads(line)
                if rec.get("prev_hash") != current_prev:
                    return False, f"Tamper detected at line {idx + 1}: prev_hash mismatch"

                details_str = json.dumps(rec.get("details", {}))
                raw_payload = f"{rec['prev_hash']}|{rec['id']}|{rec['timestamp']}|{rec['initiator']}|{rec['agent_name']}|{rec['tool_name']}|{rec['action']}|{rec['target']}|{rec['risk_level']}|{rec['verdict']}|{details_str}"
                recomputed = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

                if recomputed != rec.get("event_hash"):
                    return False, f"Tamper detected at line {idx + 1}: hash mismatch"

                current_prev = rec["event_hash"]

            return True, None
        except Exception as e:
            return False, f"Audit verification failed with error: {e}"


class ExternalActionLedger:
    """Tracks operation IDs for external actions (email, calendar, uploads) to prevent duplicate execution (Section 80 & Tests 126/127)."""

    def __init__(self):
        self._completed_operations: Dict[str, Dict[str, Any]] = {}

    def is_duplicate(self, operation_id: str) -> bool:
        return operation_id in self._completed_operations

    def record_completed(self, operation_id: str, action_type: str, response_payload: Dict[str, Any]) -> None:
        self._completed_operations[operation_id] = {
            "action_type": action_type,
            "response": response_payload,
            "timestamp": time.time(),
        }

    def get_existing_result(self, operation_id: str) -> Optional[Dict[str, Any]]:
        record = self._completed_operations.get(operation_id)
        return record.get("response") if record else None
