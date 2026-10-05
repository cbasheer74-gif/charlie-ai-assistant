"""actions/security_control.py — CHARLIE Security Dashboard & Emergency Control Actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from engine.security.core import SecurityCore

_security_core = SecurityCore()


def security_control(parameters: dict, **_unused) -> str:
    """Security management and emergency control action for CHARLIE (Phase 9)."""
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()

    if action == "status":
        p = _security_core.policy_engine
        intact, tampered = _security_core.integrity_monitor.check_integrity()
        audit_ok, audit_err = _security_core.audit.verify_integrity()
        events = _security_core.event_mgr.list_events()

        return (
            f"SecurityCore Status: ACTIVE\n"
            f"- Lockdown Mode: {'ENABLED' if p.lockdown_mode else 'DISABLED'}\n"
            f"- Safe Mode: {'ENABLED' if p.safe_mode else 'DISABLED'}\n"
            f"- Emergency Stop: {'ACTIVE' if p.emergency_stop_active else 'READY'}\n"
            f"- Core Integrity: {'VERIFIED' if intact else f'TAMPER DETECTED ({tampered})'}\n"
            f"- Audit Chain: {'INTACT' if audit_ok else f'TAMPER DETECTED ({audit_err})'}\n"
            f"- Recorded Security Events: {len(events)}"
        )

    if action == "lockdown":
        enable = bool(params.get("enable", True))
        _security_core.policy_engine.set_lockdown(enable)
        return f"Lockdown Mode {'ENABLED' if enable else 'DISABLED'}. Write & shell operations restricted."

    if action == "safe_mode":
        enable = bool(params.get("enable", True))
        _security_core.policy_engine.set_safe_mode(enable)
        return f"Safe Mode {'ENABLED' if enable else 'DISABLED'}. Autonomous tools gated."

    if action == "emergency_stop":
        _security_core.policy_engine.trigger_emergency_stop()
        return "EMERGENCY STOP TRIGGERED! All ongoing autonomous actions and cursor/keyboard automation halted."

    if action == "reset_emergency":
        _security_core.policy_engine.reset_emergency_stop()
        return "Emergency stop reset. Automation restored to normal policy gating."

    if action == "audit_inspect":
        audit_ok, audit_err = _security_core.audit.verify_integrity()
        return f"Audit log verification: {'PASS (No tampering detected)' if audit_ok else f'FAIL ({audit_err})'}"

    return "Unknown security action. Supported: status, lockdown, safe_mode, emergency_stop, reset_emergency, audit_inspect."


TOOL = {
    "name": "security_control",
    "description": "Inspect security health, toggle Lockdown or Safe Mode, trigger Emergency Stop, or inspect audit integrity.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["status", "lockdown", "safe_mode", "emergency_stop", "reset_emergency", "audit_inspect"],
                "description": "Action to perform.",
            },
            "enable": {"type": "BOOLEAN", "description": "Enable or disable mode for lockdown/safe_mode."},
        },
    },
    "handler": security_control,
}
