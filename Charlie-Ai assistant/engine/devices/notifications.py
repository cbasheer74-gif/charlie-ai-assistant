"""
JARVIS Phase 10: Notification & Remote Confirmation Manager
Handles privacy-safe notifications (lock screen masking), remote approvals, and deduplication.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .models import NotificationCategory, NotificationPayload

logger = logging.getLogger("jarvis.devices.notifications")


class NotificationManager:
    """Manages notifications dispatched to mobile companions with privacy controls and approval flows."""

    def __init__(self, audit_engine: Optional[Any] = None):
        self.audit_engine = audit_engine
        self._notifications: Dict[str, NotificationPayload] = {}
        # action_token -> approval_record
        self._action_tokens: Dict[str, Dict[str, Any]] = {}
        self._seen_notification_keys: set = set()

    def dispatch_notification(
        self,
        category: NotificationCategory,
        title: str,
        summary: str,
        details: Optional[Dict[str, Any]] = None,
        privacy_safe_text: Optional[str] = None,
        target_device_id: Optional[str] = None,
        requires_approval: bool = False,
        approval_action_payload: Optional[Dict[str, Any]] = None,
        token_ttl: float = 300.0,
    ) -> Tuple[bool, str, NotificationPayload]:
        """Dispatches notification with privacy-aware text and optional bound approval token."""
        # Deduplication key check
        dedup_key = f"{category.value}:{title}:{summary}"
        if dedup_key in self._seen_notification_keys and not requires_approval:
            return False, "Duplicate notification suppressed.", None

        self._seen_notification_keys.add(dedup_key)

        notification_id = f"notif_{uuid.uuid4().hex[:12]}"
        action_token = None

        if requires_approval and approval_action_payload:
            action_token = f"appr_{secrets.token_urlsafe(16)}"
            self._action_tokens[action_token] = {
                "action_token": action_token,
                "notification_id": notification_id,
                "payload": approval_action_payload,
                "created_at": time.time(),
                "expires_at": time.time() + token_ttl,
                "used": False,
                "decision": None,
            }

        # Mask sensitive text for lock-screen
        safe_text = privacy_safe_text or self._generate_default_safe_text(category)

        notif = NotificationPayload(
            notification_id=notification_id,
            category=category,
            title=title,
            summary=summary,
            details=details or {},
            privacy_safe_text=safe_text,
            created_at=time.time(),
            requires_approval=requires_approval,
            action_token=action_token,
            target_device_id=target_device_id,
            delivered=True,
        )

        self._notifications[notification_id] = notif
        logger.info(f"Dispatched notification {notification_id} [{category.value}] to {target_device_id or 'ALL'}")
        return True, "Notification dispatched.", notif

    def process_confirmation(self, action_token: str, approved: bool) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Processes remote user decision (Approve / Reject) bound to exact action token.
        Guarantees single-use and expiration checks.
        """
        record = self._action_tokens.get(action_token)
        if not record:
            return False, "Invalid or nonexistent action approval token.", None

        if time.time() > record["expires_at"]:
            del self._action_tokens[action_token]
            return False, "Action approval token has expired.", None

        if record["used"]:
            return False, "Action approval token has already been consumed (replay prevented).", None

        # Mark consumed
        record["used"] = True
        record["decision"] = "APPROVED" if approved else "REJECTED"

        if self.audit_engine:
            self.audit_engine.log_security_event(
                event_type="REMOTE_ACTION_CONFIRMATION",
                severity="HIGH" if approved else "MEDIUM",
                details={
                    "action_token": action_token,
                    "approved": approved,
                    "action_payload": record["payload"],
                },
            )

        status_msg = "Action approved and bound payload released." if approved else "Action rejected by user."
        return True, status_msg, record["payload"] if approved else None

    def get_notification(self, notification_id: str) -> Optional[NotificationPayload]:
        return self._notifications.get(notification_id)

    def list_notifications(self, target_device_id: Optional[str] = None) -> List[NotificationPayload]:
        if not target_device_id:
            return list(self._notifications.values())
        return [
            n for n in self._notifications.values()
            if n.target_device_id in (target_device_id, None, "ALL")
        ]

    def _generate_default_safe_text(self, category: NotificationCategory) -> str:
        mapping = {
            NotificationCategory.TASK_COMPLETE: "JARVIS: Task finished.",
            NotificationCategory.TASK_FAILED: "JARVIS: Task encountered an issue.",
            NotificationCategory.CONFIRMATION_REQUIRED: "JARVIS: Authorization required.",
            NotificationCategory.SECURITY_ALERT: "JARVIS: Security alert.",
            NotificationCategory.MEETING: "JARVIS: Upcoming schedule event.",
            NotificationCategory.BACKUP_FAILURE: "JARVIS: Backup notice.",
            NotificationCategory.EXPORT_COMPLETE: "JARVIS: Export finished.",
            NotificationCategory.PROJECT_BLOCKED: "JARVIS: Project requires attention.",
        }
        return mapping.get(category, "JARVIS notification.")
