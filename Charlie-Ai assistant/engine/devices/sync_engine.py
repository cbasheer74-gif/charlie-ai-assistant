"""
JARVIS Phase 10: Selective Memory Sync & Conflict Resolver
Handles selective syncing of project metadata, task statuses, user preferences, and skills.
Strictly prevents synchronization of passwords, OAuth tokens, private keys, or credentials.
Provides deterministic conflict resolution.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .models import SyncRecord, SyncScope

logger = logging.getLogger("jarvis.devices.sync")


class SyncEngine:
    """Manages selective state synchronization across trusted devices."""

    FORBIDDEN_SYNC_KEYS = {
        "password",
        "private_key",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "credential",
        "oauth",
        "cookie",
        "api_key",
    }

    def __init__(self):
        # record_id -> SyncRecord
        self._synced_data: Dict[str, SyncRecord] = {}

    def prepare_sync_record(
        self, record_id: str, scope: SyncScope, data: Dict[str, Any], origin_device: str, version: int = 1
    ) -> Tuple[bool, str, Optional[SyncRecord]]:
        """
        Prepares a record for synchronization after strict sanitization.
        Refuses any record containing sensitive secrets or private keys.
        """
        # Inspect for prohibited sensitive tokens/keys
        for k in data.keys():
            k_lower = k.lower()
            if any(forbidden in k_lower for forbidden in self.FORBIDDEN_SYNC_KEYS):
                msg = f"Security Refusal: Prohibited sensitive key '{k}' detected in sync payload."
                logger.error(msg)
                return False, msg, None

        serialized = json.dumps(data, sort_keys=True)
        data_hash = hashlib.sha256(serialized.encode()).hexdigest()

        record = SyncRecord(
            record_id=record_id,
            scope=scope,
            version=version,
            data=data,
            origin_device=origin_device,
            updated_at=time.time(),
            data_hash=data_hash,
        )
        return True, "Sanitized and prepared.", record

    def apply_remote_record(self, remote_record: SyncRecord) -> Tuple[bool, str]:
        """Applies a verified remote record into the local sync store."""
        local = self._synced_data.get(remote_record.record_id)
        if not local:
            self._synced_data[remote_record.record_id] = remote_record
            return True, "Record inserted."

        if remote_record.version > local.version:
            self._synced_data[remote_record.record_id] = remote_record
            return True, "Record updated to newer version."

        if remote_record.version == local.version and remote_record.data_hash == local.data_hash:
            return True, "Record already up to date."

        return False, f"Version conflict or stale record (local: {local.version}, remote: {remote_record.version})"

    def get_record(self, record_id: str) -> Optional[SyncRecord]:
        return self._synced_data.get(record_id)

    def list_records_by_scope(self, scope: SyncScope) -> List[SyncRecord]:
        return [r for r in self._synced_data.values() if r.scope == scope]


class ConflictResolver:
    """
    Detects and resolves conflicts between local and remote updates deterministically.
    Avoids silent, arbitrary overwriting.
    """

    @staticmethod
    def detect_conflict(local_record: SyncRecord, remote_record: SyncRecord) -> bool:
        """Returns True if versions or data diverge at equal timestamps or divergent modifications."""
        if local_record.record_id != remote_record.record_id:
            return False
        # If hashes match, no conflict
        if local_record.data_hash == remote_record.data_hash:
            return False
        # Both modified independently (same version number or divergent contents)
        return local_record.version == remote_record.version

    @staticmethod
    def resolve(
        local_record: SyncRecord, remote_record: SyncRecord, strategy: str = "LATEST_VERIFIED"
    ) -> Tuple[SyncRecord, str]:
        """
        Resolves conflict using explicit strategy:
        - 'LATEST_VERIFIED': Selects higher timestamp
        - 'PC_AUTHORITATIVE': Windows host takes precedence
        """
        if strategy == "PC_AUTHORITATIVE":
            if "host" in local_record.origin_device.lower() or "windows" in local_record.origin_device.lower():
                return local_record, "PC authoritative choice applied."
            return remote_record, "PC authoritative choice applied."

        # Default LATEST_VERIFIED
        if remote_record.updated_at > local_record.updated_at:
            winning = remote_record
            desc = "Resolved to latest remote modification."
        else:
            winning = local_record
            desc = "Resolved to latest local modification."

        # Increment version to seal resolved record
        winning.version = max(local_record.version, remote_record.version) + 1
        return winning, desc
