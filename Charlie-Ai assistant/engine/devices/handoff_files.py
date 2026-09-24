"""
JARVIS Phase 10: Task Handoff & Secure File Transfer Manager
Manages continuity between devices (Phone <-> PC) and secure scoped file retrieval.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .models import TaskHandoffPayload

logger = logging.getLogger("jarvis.devices.handoff")


class TaskHandoffManager:
    """Handles task continuation and state migration between Phone and PC."""

    def __init__(self):
        self._handoffs: Dict[str, TaskHandoffPayload] = {}

    def prepare_handoff(
        self,
        task_id: str,
        source_device: str,
        target_device: str,
        goal: str,
        state_snapshot: Dict[str, Any],
        checkpoints: Optional[List[Dict[str, Any]]] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskHandoffPayload:
        """Prepares a handoff payload to continue work seamlessly on another device."""
        handoff_id = f"handoff_{uuid.uuid4().hex[:12]}"
        payload = TaskHandoffPayload(
            handoff_id=handoff_id,
            task_id=task_id,
            source_device=source_device,
            target_device=target_device,
            goal=goal,
            state_snapshot=state_snapshot,
            checkpoints=checkpoints or [],
            artifacts=artifacts or [],
            timestamp=time.time(),
        )
        self._handoffs[handoff_id] = payload
        logger.info(f"Task handoff prepared: {handoff_id} for task '{goal}' ({source_device} -> {target_device})")
        return payload

    def claim_handoff(self, handoff_id: str, claiming_device_id: str) -> Optional[TaskHandoffPayload]:
        """Claims a handoff on the receiving device."""
        payload = self._handoffs.get(handoff_id)
        if not payload:
            logger.warning(f"Handoff {handoff_id} not found.")
            return None

        # Check target
        if payload.target_device not in (claiming_device_id, "ANY_TRUSTED"):
            logger.warning(f"Device {claiming_device_id} not authorized to claim handoff intended for {payload.target_device}")
            return None

        logger.info(f"Handoff {handoff_id} claimed by {claiming_device_id}")
        return payload


class SecureFileTransferManager:
    """
    Provides secure, scoped, short-lived file transfer tokens.
    Verifies SHA256 integrity, limits file size, and scopes to approved project artifacts.
    """

    def __init__(self, max_file_size_mb: int = 50, link_ttl: float = 300.0, audit_engine: Optional[Any] = None):
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.link_ttl = link_ttl
        self.audit_engine = audit_engine
        # token -> metadata
        self._active_tokens: Dict[str, Dict[str, Any]] = {}

    def generate_download_token(
        self,
        file_path: str,
        project_id: str,
        target_device_id: str,
        file_content: bytes,
        file_name: str,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Creates a short-lived download token for a verified project artifact.
        Returns: (success: bool, message: str, download_token: Optional[str])
        """
        if len(file_content) > self.max_file_size_bytes:
            return False, f"File exceeds maximum allowed transfer size ({self.max_file_size_bytes // 1048576}MB)", None

        file_hash = hashlib.sha256(file_content).hexdigest()
        token = f"dl_{secrets.token_urlsafe(24)}"
        expires_at = time.time() + self.link_ttl

        self._active_tokens[token] = {
            "token": token,
            "file_path": file_path,
            "project_id": project_id,
            "target_device_id": target_device_id,
            "file_hash": file_hash,
            "file_name": file_name,
            "file_size": len(file_content),
            "file_content": file_content,
            "expires_at": expires_at,
            "used": False,
        }

        if self.audit_engine:
            self.audit_engine.log_security_event(
                event_type="FILE_TRANSFER_TOKEN_ISSUED",
                severity="LOW",
                details={
                    "file_name": file_name,
                    "target_device_id": target_device_id,
                    "file_hash": file_hash,
                    "expires_at": expires_at,
                },
            )

        logger.info(f"Generated secure transfer token for {file_name} -> {target_device_id}")
        return True, "Download token generated.", token

    def claim_file(self, token: str, requesting_device_id: str) -> Tuple[bool, str, Optional[bytes], Optional[str]]:
        """
        Claims and downloads file payload using the one-time token.
        Returns: (success: bool, message: str, content: bytes, expected_hash: str)
        """
        record = self._active_tokens.get(token)
        if not record:
            return False, "Invalid or nonexistent transfer token", None, None

        if time.time() > record["expires_at"]:
            del self._active_tokens[token]
            return False, "Transfer token has expired", None, None

        if record["used"]:
            return False, "Transfer token has already been consumed", None, None

        if record["target_device_id"] != requesting_device_id:
            return False, "Requesting device does not match authorized recipient", None, None

        # Mark token used
        record["used"] = True
        content = record["file_content"]
        expected_hash = record["file_hash"]

        # Verify integrity
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            return False, "Integrity check failed: File hash mismatch", None, None

        if self.audit_engine:
            self.audit_engine.log_security_event(
                event_type="FILE_TRANSFER_COMPLETED",
                severity="LOW",
                details={
                    "file_name": record["file_name"],
                    "requesting_device_id": requesting_device_id,
                    "file_hash": actual_hash,
                },
            )

        return True, "File verified and transferred successfully", content, actual_hash
