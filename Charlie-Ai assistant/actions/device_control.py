"""
CHARLIE Phase 10: Device Control Actions
Commands for managing paired devices, pairing codes, and remote status.
"""

from typing import Any, Dict, List, Optional
from engine.devices.core import DeviceOrchestrator
from engine.devices.models import DeviceType, TrustState


class DeviceControlActions:
    """High-level actions exposed to CHARLIE for managing multi-device system."""

    def __init__(self, orchestrator: Optional[DeviceOrchestrator] = None):
        self.orchestrator = orchestrator or DeviceOrchestrator()

    def list_devices(self, include_revoked: bool = False) -> List[Dict[str, Any]]:
        devices = self.orchestrator.registry.list_devices(include_revoked=include_revoked)
        return [
            {
                "device_id": d.device_id,
                "device_name": d.device_name,
                "device_type": d.device_type.value,
                "trust_state": d.trust_state.value,
                "last_seen": d.last_seen,
                "permissions": [p.value for p in d.permissions],
            }
            for d in devices
        ]

    def start_pairing(self) -> Dict[str, Any]:
        session_id, code, qr_payload = self.orchestrator.pairing_manager.create_pairing_session()
        return {
            "session_id": session_id,
            "pairing_code": code,
            "qr_payload": qr_payload,
            "message": f"Pairing code generated: {code}. Expires in 5 minutes.",
        }

    def revoke_device(self, device_id: str, reason: str = "User command") -> Dict[str, Any]:
        success = self.orchestrator.revocation_manager.revoke_device(device_id, reason=reason)
        return {
            "success": success,
            "device_id": device_id,
            "message": f"Device {device_id} revoked." if success else "Failed to revoke device.",
        }

    def get_pc_presence(self) -> Dict[str, Any]:
        status = self.orchestrator.presence_manager.get_pc_status()
        return {
            "pc_status": status.value,
            "message": f"Main Windows PC is currently {status.value}.",
        }
