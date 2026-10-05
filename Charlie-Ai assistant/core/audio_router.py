"""core/audio_router.py — Live Audio Device Hot-Swapping & Dynamic Hardware Router for CHARLIE.

Features:
- Live polling & notification for plugged/unplugged audio hardware (USB headsets, mics, interfaces).
- Seamless stream migration hierarchy (Headset > USB Interface > Integrated Audio > System Default).
- Zero-crash fallback when active audio output or input device vanishes.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from core.audio_devices import get_cached_devices, resolve, DEFAULT_VALUE

logger = logging.getLogger("charlie.audio_router")


@dataclass
class AudioDeviceState:
    input_devices: List[str] = field(default_factory=list)
    output_devices: List[str] = field(default_factory=list)
    active_input: str = DEFAULT_VALUE
    active_output: str = DEFAULT_VALUE
    last_checked: float = 0.0


class AudioDeviceRouter:
    """Monitors audio hardware endpoints and dynamically re-routes active streams on hot-swap events."""

    INPUT_PRIORITIES = ["headset", "usb", "wireless", "realtek", "microphone"]
    OUTPUT_PRIORITIES = ["headset", "headphones", "usb", "wireless", "speakers", "realtek"]

    def __init__(self, check_interval: float = 2.0):
        self.check_interval = check_interval
        self._state = AudioDeviceState()
        self._is_monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[str, str, str], None]] = []

    def scan_devices(self) -> AudioDeviceState:
        """Queries physical endpoints and detects additions/removals."""
        try:
            inputs = get_cached_devices("input")
            outputs = get_cached_devices("output")
        except Exception:
            inputs = ["System default"]
            outputs = ["System default"]

        with self._lock:
            old_inputs = set(self._state.input_devices)
            old_outputs = set(self._state.output_devices)

            self._state.input_devices = inputs
            self._state.output_devices = outputs
            self._state.last_checked = time.time()

            new_inputs = set(inputs)
            new_outputs = set(outputs)

            # Detect input changes
            if old_inputs and new_inputs != old_inputs:
                added = new_inputs - old_inputs
                removed = old_inputs - new_inputs
                logger.info("Audio inputs changed: added=%s, removed=%s", added, removed)
                self._handle_device_change("input", added, removed)

            # Detect output changes
            if old_outputs and new_outputs != old_outputs:
                added = new_outputs - old_outputs
                removed = old_outputs - new_outputs
                logger.info("Audio outputs changed: added=%s, removed=%s", added, removed)
                self._handle_device_change("output", added, removed)

            return self._state

    def select_best_device(self, direction: str, available: List[str]) -> str:
        """Picks the highest priority device based on hardware profile."""
        if not available:
            return DEFAULT_VALUE

        priorities = self.INPUT_PRIORITIES if direction == "input" else self.OUTPUT_PRIORITIES

        for prio in priorities:
            for dev in available:
                if prio in dev.lower():
                    return dev

        return available[0] if available else DEFAULT_VALUE

    def _handle_device_change(self, direction: str, added: Set[str], removed: Set[str]) -> None:
        """Determines if active route needs to migrate."""
        current_active = self._state.active_input if direction == "input" else self._state.active_output
        available = self._state.input_devices if direction == "input" else self._state.output_devices

        new_target = current_active

        # If current device was unplugged, migrate to best available
        if current_active in removed or (current_active and current_active not in available):
            new_target = self.select_best_device(direction, available)
            logger.warning("Active %s device was unplugged! Migrating to '%s'", direction, new_target)
        # If a high-priority device was newly plugged in (e.g. Headset), auto-switch
        elif added:
            best_new = self.select_best_device(direction, list(added))
            if any(p in best_new.lower() for p in ["headset", "headphones"]):
                new_target = best_new
                logger.info("High priority %s device attached: Auto-switching to '%s'", direction, new_target)

        if new_target != current_active:
            if direction == "input":
                self._state.active_input = new_target
            else:
                self._state.active_output = new_target

            for cb in self._callbacks:
                try:
                    cb(direction, current_active, new_target)
                except Exception:
                    pass

    def add_change_callback(self, callback: Callable[[str, str, str], None]) -> None:
        """Callback signature: (direction: 'input'|'output', old_device: str, new_device: str)"""
        self._callbacks.append(callback)

    def start_monitoring(self) -> bool:
        if self._is_monitoring:
            return True
        self._is_monitoring = True

        def _loop():
            while self._is_monitoring:
                try:
                    self.scan_devices()
                except Exception as e:
                    logger.debug("Audio router loop error: %s", e)
                time.sleep(self.check_interval)

        self._monitor_thread = threading.Thread(target=_loop, daemon=True, name="AudioRouterThread")
        self._monitor_thread.start()
        return True

    def stop_monitoring(self) -> None:
        self._is_monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)


# Singleton
_router_instance: Optional[AudioDeviceRouter] = None


def get_audio_router() -> AudioDeviceRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = AudioDeviceRouter()
    return _router_instance
