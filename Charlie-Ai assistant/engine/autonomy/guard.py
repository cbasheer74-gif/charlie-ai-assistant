"""engine/autonomy/guard.py — External Action Guard & High-Impact Boundary Protection.

Prevents autonomous agents from transmitting external communications, publishing media,
initiating payments, or altering security configs without explicit immediate user confirmation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from engine.permissions import PermissionManager, RiskLevel


class ExternalActionType(str, Enum):
    SEND = "SEND"                      # Email, message, webhook
    PUBLISH = "PUBLISH"                # YouTube upload, blog post, tweet
    UPLOAD = "UPLOAD"                  # Cloud storage, remote server
    PAY = "PAY"                        # Checkout, financial transaction
    PURCHASE = "PURCHASE"              # In-app purchase, license
    DELETE_REMOTE = "DELETE_REMOTE"    # Remote git delete, cloud resource drop
    MODIFY_SECURITY = "MODIFY_SECURITY" # Firewall, certificates, sudo/admin
    HIGH_IMPACT = "HIGH_IMPACT"        # Destructive bulk delete / system formatting



class ExternalActionGuard:
    """Safety barrier restricting external side-effects even in high-autonomy modes."""

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.perm_mgr = permission_manager

    def validate_action(
        self,
        action_type: str,
        target_entity: str,
        details: Dict[str, Any],
        confirm_callback: Optional[Callable[[str], bool]] = None,
    ) -> Tuple[bool, str]:
        """Verify whether an external action is permitted to run autonomously."""
        act_upper = action_type.strip().upper()

        # All guarded external action types unconditionally require authorization
        guarded_types = {e.value for e in ExternalActionType}

        is_guarded = (
            act_upper in guarded_types
            or any(act_upper.startswith(e.value) for e in ExternalActionType)
            or any(w in act_upper for w in ("SEND", "PAY", "PURCHASE", "DELETE", "UPLOAD", "PUBLISH", "SECURITY", "EXEC", "SHELL", "FORMAT"))
        )

        if is_guarded:
            reason = (
                f"External action barrier: '{act_upper}' to '{target_entity}' has irreversible external impact."
            )
            # If confirmation callback provided (e.g. GUI or voice prompt), ask user
            if confirm_callback:
                allowed = confirm_callback(reason)
                if allowed:
                    return True, "User granted explicit permission."
                return False, f"User denied external action: {act_upper}"

            # Fallback to permission manager confirmation gate if configured
            if self.perm_mgr:
                ok, msg = self.perm_mgr.guard_action(
                    name=act_upper,
                    risk_level=RiskLevel.HIGH_IMPACT,
                    action_fn=lambda: "Action permitted by user confirmation.",
                    description=reason,
                )
                if ok:
                    return True, msg
                return False, f"{reason} ({msg})"

            return False, reason

        return True, "Action allowed within safe boundary."
