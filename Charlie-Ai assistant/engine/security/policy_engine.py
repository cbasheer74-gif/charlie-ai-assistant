"""engine/security/policy_engine.py — Security Policy Engine, Capability Tokens, Lockdown, and Safe Mode."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from engine.security.models import (
    CapabilityToken,
    InstructionOrigin,
    PolicyVerdict,
    RiskLevel,
    SecurityPolicyDecision,
)
from engine.security.trust_guard import InputTrustClassifier


class SecurityPolicyEngine:
    """Centralized security policy evaluation engine for all JARVIS agents and tools."""

    def __init__(self):
        self.lockdown_mode: bool = False
        self.safe_mode: bool = False
        self.emergency_stop_active: bool = False
        self._capability_tokens: Dict[str, CapabilityToken] = {}

    def set_lockdown(self, active: bool) -> None:
        """Enables/disables Lockdown Mode (Section 103 & Test 131)."""
        self.lockdown_mode = active

    def set_safe_mode(self, active: bool) -> None:
        """Enables/disables Safe Mode (Section 104 & Test 132)."""
        self.safe_mode = active

    def trigger_emergency_stop(self) -> None:
        """Triggers emergency stop (Section 102 & Test 133)."""
        self.emergency_stop_active = True

    def reset_emergency_stop(self) -> None:
        self.emergency_stop_active = False

    def grant_capability(
        self,
        token_id: str,
        target_resource: str,
        operations: List[str],
        duration_sec: float = 300.0,
    ) -> CapabilityToken:
        token = CapabilityToken(
            id=token_id,
            target_resource=target_resource,
            allowed_operations=operations,
            expires_at=time.time() + duration_sec,
        )
        self._capability_tokens[token_id] = token
        return token

    def evaluate(
        self,
        agent_name: str,
        tool_name: str,
        action: str,
        target: str,
        risk_level: RiskLevel,
        origin: InstructionOrigin = InstructionOrigin.USER,
        token_id: Optional[str] = None,
    ) -> SecurityPolicyDecision:
        """Evaluates execution request against active policies, modes, risk tiers, and origins."""
        # 1. Emergency Stop Gate
        if self.emergency_stop_active:
            return SecurityPolicyDecision(
                verdict=PolicyVerdict.DENY,
                reason="Emergency stop is currently active. All automation halted.",
                risk_level=risk_level,
            )

        # 2. Lockdown Mode Gate: All write/execute actions blocked (Test 131)
        if self.lockdown_mode:
            if risk_level != RiskLevel.R0_READ_ONLY:
                return SecurityPolicyDecision(
                    verdict=PolicyVerdict.DENY,
                    reason="Lockdown Mode active: All write, shell, and external actions are prohibited.",
                    risk_level=risk_level,
                )

        # 3. Safe Mode Gate: Autonomous tools blocked, recovery/audit only (Test 132)
        if self.safe_mode:
            if tool_name not in ("memory_engine", "backup_manager", "audit_viewer", "system_status", "recovery_manager"):
                return SecurityPolicyDecision(
                    verdict=PolicyVerdict.DENY,
                    reason="Safe Mode active: Autonomous agents and execution tools are disabled.",
                    risk_level=risk_level,
                )

        # 4. Zero-Trust Origin Gate: Untrusted external content CANNOT trigger high-impact actions (Test 111, 112, 119)
        if InputTrustClassifier.is_untrusted(origin):
            if not InputTrustClassifier.can_authorize_action(origin, action):
                return SecurityPolicyDecision(
                    verdict=PolicyVerdict.DENY,
                    reason=f"Zero-Trust Violation: External untrusted input ({origin.value}) cannot authorize '{action}'.",
                    risk_level=risk_level,
                )

        # 5. Risk-Tier Policy Logic
        if risk_level == RiskLevel.R4_CRITICAL:
            return SecurityPolicyDecision(
                verdict=PolicyVerdict.DENY,
                reason="Critical risk action blocked by default policy. Explicit human authorization required.",
                risk_level=risk_level,
                confirmation_required=True,
            )

        if risk_level == RiskLevel.R3_HIGH_IMPACT:
            return SecurityPolicyDecision(
                verdict=PolicyVerdict.ALLOW_WITH_CONFIRMATION,
                reason="High impact operation requires explicit confirmation and prior backup.",
                risk_level=risk_level,
                backup_required=True,
                confirmation_required=True,
            )

        if risk_level == RiskLevel.R2_REVERSIBLE_CHANGE:
            return SecurityPolicyDecision(
                verdict=PolicyVerdict.ALLOW_WITH_BACKUP,
                reason="System or environment change requires pre-action backup.",
                risk_level=risk_level,
                backup_required=True,
            )

        return SecurityPolicyDecision(
            verdict=PolicyVerdict.ALLOW,
            reason="Action conforms to security policy.",
            risk_level=risk_level,
        )
