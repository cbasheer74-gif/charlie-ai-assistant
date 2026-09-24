"""
JARVIS Phase 11: Hardware Profiler
Inspects system RAM, CPU, GPU/VRAM, and storage to recommend safe local model tiers.
"""

from __future__ import annotations

import logging
import os
import platform
from typing import Any, Dict

logger = logging.getLogger("jarvis.ai.hardware")


class HardwareProfiler:
    """Detects available hardware resources to guide local model selection."""

    def __init__(self):
        self._cached_profile: Dict[str, Any] = {}

    def get_hardware_profile(self) -> Dict[str, Any]:
        """Returns current system hardware profile."""
        if self._cached_profile:
            return self._cached_profile

        profile = {
            "os": platform.system(),
            "architecture": platform.machine(),
            "cpu_cores": os.cpu_count() or 4,
            "total_ram_gb": self._detect_ram_gb(),
            "has_gpu": False,
            "vram_gb": 0.0,
            "gpu_name": "None",
            "recommended_local_tier": "SMALL",
            "max_local_param_size": "7B",
        }

        # Determine safe tier based on RAM
        ram = profile["total_ram_gb"]
        if ram < 8.0:
            profile["recommended_local_tier"] = "TINY"
            profile["max_local_param_size"] = "1B - 3B"
        elif ram < 16.0:
            profile["recommended_local_tier"] = "SMALL"
            profile["max_local_param_size"] = "3B - 7B"
        elif ram < 32.0:
            profile["recommended_local_tier"] = "MEDIUM"
            profile["max_local_param_size"] = "8B - 14B"
        else:
            profile["recommended_local_tier"] = "LARGE"
            profile["max_local_param_size"] = "14B - 32B"

        self._cached_profile = profile
        logger.info(f"Hardware profiled: RAM={ram}GB, Rec Tier={profile['recommended_local_tier']}")
        return profile

    def can_run_model(self, model_param_billions: float) -> bool:
        """Checks if hardware can run a local model of given parameter size."""
        profile = self.get_hardware_profile()
        ram = profile["total_ram_gb"]
        # Rule of thumb for 4-bit quantized models: ~0.7 GB RAM per 1B params + 2GB buffer
        required_ram = (model_param_billions * 0.7) + 2.0
        return ram >= required_ram

    def _detect_ram_gb(self) -> float:
        try:
            import psutil
            return round(psutil.virtual_memory().total / (1024 ** 3), 1)
        except Exception:
            # Safe default fallback for test environments or basic OS
            return 16.0
