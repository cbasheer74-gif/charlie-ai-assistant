"""engine/security/core.py — SecurityCore: Central Gatekeeper and Defense-in-Depth Coordinator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.security.audit_engine import AuditEngine, ExternalActionLedger
from engine.security.backup_recovery import BackupManager, RecoveryManager
from engine.security.binary_integrity import BinaryIntegrityChecker
from engine.security.command_safety import CommandSafetyEngine
from engine.security.file_safety import FileSafetyEngine
from engine.security.integrity_monitor import IntegrityMonitor, SecurityEventManager
from engine.security.models import (
    InstructionOrigin,
    PolicyVerdict,
    RiskLevel,
    SecurityEventType,
    SecurityPolicyDecision,
    SecuritySeverity,
)
from engine.security.policy_engine import SecurityPolicyEngine
from engine.security.reliability import (
    DownloadSecurityEngine,
    ReliabilitySupervisor,
    UpdateSafetyManager,
)
from engine.security.trust_guard import InputTrustClassifier, PromptInjectionDefense
from engine.security.vault import CredentialVault, SecretRedactionEngine


class SecurityCore:
    """Central authoritative security coordinator. All autonomous agents and tools must pass through SecurityCore."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else (Path.home() / ".jarvis")
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.vault = CredentialVault(vault_dir=self.base_dir / "vault")
        self.policy_engine = SecurityPolicyEngine()
        self.command_safety = CommandSafetyEngine()
        self.file_safety = FileSafetyEngine(quarantine_dir=self.base_dir / "quarantine")
        self.audit = AuditEngine(audit_file=self.base_dir / "audit" / "audit_chain.jsonl")
        self.action_ledger = ExternalActionLedger()
        self.backup_mgr = BackupManager(backup_dir=self.base_dir / "backups")
        self.recovery_mgr = RecoveryManager(self.backup_mgr)
        self.integrity_monitor = IntegrityMonitor()
        self.event_mgr = SecurityEventManager()
        self.download_sec = DownloadSecurityEngine(download_dir=self.base_dir / "downloads")
        self.reliability = ReliabilitySupervisor()
        self.update_safety = UpdateSafetyManager(self.backup_mgr, self.recovery_mgr)
        self.binary_integrity = BinaryIntegrityChecker()
        self._integrity_ok = True  # Assume ok until checked

    def integrity_check_on_startup(self) -> bool:
        """Run binary integrity verification at app startup.

        Returns True if all critical modules pass SHA256 verification.
        Logs warnings but does NOT block startup — allows self-repair/update flow.
        """
        ok, violations = self.binary_integrity.verify_all()
        self._integrity_ok = ok
        if not ok:
            for v in violations:
                self.event_mgr.record_event(
                    SecurityEventType.INTEGRITY_VIOLATION
                    if hasattr(SecurityEventType, "INTEGRITY_VIOLATION")
                    else SecurityEventType.BLOCKED_COMMAND,
                    SecuritySeverity.CRITICAL
                    if hasattr(SecuritySeverity, "CRITICAL")
                    else SecuritySeverity.HIGH,
                    "SecurityCore",
                    f"Binary integrity violation: {v}",
                )
        return ok

    def guard_execution(
        self,
        agent_name: str,
        tool_name: str,
        action: str,
        target: str,
        execution_fn: Callable[[], Any],
        origin: InstructionOrigin = InstructionOrigin.USER,
        risk_level: Optional[RiskLevel] = None,
        operation_id: Optional[str] = None,
    ) -> Tuple[bool, Any, str]:
        """Comprehensive execution pipeline: Zero-Trust -> Risk -> Policy -> Backup -> Execution -> Audit."""
        # 1. Duplicate Action Prevention (Section 80 & Tests 126/127)
        if operation_id and self.action_ledger.is_duplicate(operation_id):
            cached = self.action_ledger.get_existing_result(operation_id)
            return True, cached, "Duplicate action detected; returned existing verified result."

        # 2. Command or Target Safety Assessment
        eff_risk = risk_level or RiskLevel.R1_SAFE_WRITE
        if tool_name == "shell" or action == "execute_command":
            cmd_risk, is_blocked, reason = self.command_safety.evaluate_command(target)
            if is_blocked:
                self.event_mgr.record_event(
                    SecurityEventType.BLOCKED_COMMAND,
                    SecuritySeverity.HIGH,
                    agent_name,
                    f"Blocked shell command: {target} ({reason})",
                )
                self.audit.record_event("AGENT", agent_name, tool_name, action, target, cmd_risk.value, "DENY")
                return False, None, reason
            eff_risk = cmd_risk

        # 3. Security Policy Evaluation
        decision = self.policy_engine.evaluate(
            agent_name=agent_name,
            tool_name=tool_name,
            action=action,
            target=target,
            risk_level=eff_risk,
            origin=origin,
        )

        if decision.verdict == PolicyVerdict.DENY:
            self.event_mgr.record_event(
                SecurityEventType.PERMISSION_VIOLATION,
                SecuritySeverity.HIGH,
                agent_name,
                f"Policy denied '{action}' on '{target}': {decision.reason}",
            )
            self.audit.record_event("AGENT", agent_name, tool_name, action, target, eff_risk.value, "DENY", {"reason": decision.reason})
            return False, None, decision.reason

        # 3.5 Commercial FeatureGate Entitlement Check
        try:
            from engine.commercial.core import get_commercial_engine
            from engine.commercial.models import Entitlement
            comm_eng = get_commercial_engine()
            ent_to_check = None
            low_act = action.lower()
            if tool_name == "filmora" or "filmora" in low_act:
                ent_to_check = Entitlement.VIDEO_FILMORA
            elif tool_name == "coding" or agent_name == "CodingAgent":
                ent_to_check = Entitlement.CODING
            elif agent_name == "AntigravityAgent" or tool_name == "antigravity":
                ent_to_check = Entitlement.AUTONOMY_ADVANCED

            if ent_to_check:
                comm_res = comm_eng.can_use(ent_to_check)
                if not comm_res.allowed:
                    self.audit.record_event("COMMERCIAL", agent_name, tool_name, action, target, eff_risk.value, "DENY", {"reason": comm_res.reason})
                    return False, None, f"[COMMERCIAL_GATE_LOCKED] {comm_res.reason}"
        except Exception:
            pass

        # 4. Pre-Action Backup if Required (Section 37 & 40)
        backup_rec = None
        if decision.backup_required:
            target_p = Path(target)
            if target_p.exists() and target_p.is_file():
                ok, backup_rec, b_msg = self.backup_mgr.create_file_backup(target_p)
                if not ok:
                    return False, None, f"Pre-action backup failed: {b_msg}"

        # 5. Circuit Breaker Check
        cb = self.reliability.get_circuit_breaker(tool_name)
        if not cb.is_call_permitted():
            return False, None, f"Circuit breaker OPEN for tool '{tool_name}'. Repeated failures detected."

        # 6. Execute with Audit
        try:
            result = execution_fn()
            cb.record_success()

            if operation_id:
                self.action_ledger.record_completed(operation_id, action, {"result": str(result)})

            self.audit.record_event(
                "AGENT",
                agent_name,
                tool_name,
                action,
                target,
                eff_risk.value,
                "ALLOW",
                {"result": SecretRedactionEngine.redact(str(result)[:200])},
            )
            return True, result, "Executed successfully"

        except Exception as e:
            cb.record_failure()
            self.audit.record_event(
                "AGENT",
                agent_name,
                tool_name,
                action,
                target,
                eff_risk.value,
                "FAILED",
                {"error": str(e)},
            )
            return False, None, f"Execution raised error: {e}"
